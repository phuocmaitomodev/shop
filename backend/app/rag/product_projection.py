import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Category, Product
from app.models.knowledge import RagDocument, RagIndexJob


@dataclass(frozen=True)
class ProductProjectionSyncResult:
    created: int = 0
    updated: int = 0
    deactivated: int = 0


def _is_public(product: Product, category: Category) -> bool:
    return product.is_active and product.deleted_at is None and category.is_active


def _embedding_content(product: Product, category: Category) -> str:
    lines = [
        f"Tên sản phẩm: {product.name.strip()}",
        f"Danh mục: {category.name.strip()}",
    ]
    if product.description and product.description.strip():
        lines.append(f"Mô tả: {product.description.strip()}")
    return "\n".join(lines)


def _projection_checksum(
    product: Product, category: Category, *, is_active: bool
) -> str:
    canonical = json.dumps(
        [
            product.name.strip(),
            category.name.strip(),
            (product.description or "").strip(),
            is_active,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _enqueue(
    session: AsyncSession,
    projection: RagDocument,
    *,
    event_type: str,
    payload: dict[str, str],
) -> None:
    session.add(
        RagIndexJob(
            source_type="product",
            source_id=projection.source_id,
            source_version=projection.source_version,
            event_type=event_type,
            payload=payload,
        )
    )


async def sync_product_projections(
    session: AsyncSession,
) -> ProductProjectionSyncResult:
    """Synchronize catalog products into the durable RAG projection/outbox."""
    product_rows = (
        await session.execute(
            select(Product, Category)
            .join(Category, Category.id == Product.category_id)
            .order_by(Product.id)
        )
    ).all()
    projections = {
        projection.source_id: projection
        for projection in await session.scalars(
            select(RagDocument)
            .where(RagDocument.source_type == "product")
            .with_for_update()
        )
    }

    created = 0
    updated = 0
    deactivated = 0
    catalog_ids: set[UUID] = set()

    for product, category in product_rows:
        catalog_ids.add(product.id)
        is_active = _is_public(product, category)
        content = _embedding_content(product, category)
        checksum = _projection_checksum(product, category, is_active=is_active)
        projection = projections.get(product.id)

        if projection is None:
            projection = RagDocument(
                source_type="product",
                source_id=product.id,
                title=product.name.strip(),
                content_for_embedding=content,
                source_version=1,
                checksum=checksum,
                index_status="pending",
                is_active=is_active,
            )
            session.add(projection)
            _enqueue(
                session,
                projection,
                event_type="upsert" if is_active else "delete",
                payload={"category_slug": category.slug},
            )
            created += 1
            if not is_active:
                deactivated += 1
            continue

        if projection.checksum == checksum and projection.is_active == is_active:
            continue

        was_active = projection.is_active
        projection.title = product.name.strip()
        projection.content_for_embedding = content
        projection.source_version += 1
        projection.checksum = checksum
        projection.index_status = "pending"
        projection.is_active = is_active
        _enqueue(
            session,
            projection,
            event_type="upsert" if is_active else "delete",
            payload={"category_slug": category.slug},
        )
        if was_active and not is_active:
            deactivated += 1
        else:
            updated += 1

    for source_id, projection in projections.items():
        if source_id in catalog_ids or not projection.is_active:
            continue
        projection.source_version += 1
        projection.checksum = hashlib.sha256(
            json.dumps(
                [projection.title, projection.content_for_embedding, False],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        projection.index_status = "pending"
        projection.is_active = False
        _enqueue(session, projection, event_type="delete", payload={})
        deactivated += 1

    return ProductProjectionSyncResult(
        created=created,
        updated=updated,
        deactivated=deactivated,
    )
