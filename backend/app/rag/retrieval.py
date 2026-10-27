import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.catalog import (
    Category,
    Color,
    Product,
    ProductVariant,
    Size,
)
from app.models.knowledge import RagChunk, RagDocument, VectorType


EMBEDDING_DIMENSION = 768
MAX_RETRIEVAL_LIMIT = 20


@dataclass(frozen=True)
class ProductRetrievalFilters:
    category: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    color: str | None = None
    size: str | None = None


@dataclass(frozen=True)
class RetrievedVariant:
    color: str
    color_slug: str
    size: str
    stock_quantity: int


@dataclass(frozen=True)
class RetrievedProduct:
    product_id: UUID
    source_id: UUID
    rag_document_id: UUID
    chunk_ids: tuple[UUID, ...]
    score: float
    slug: str
    name: str
    image_url: str | None
    effective_price: int
    available_colors: tuple[str, ...]
    available_sizes: tuple[str, ...]
    in_stock: bool
    variants: tuple[RetrievedVariant, ...]


@dataclass(frozen=True)
class _Candidate:
    product_id: UUID
    document_id: UUID
    chunk_id: UUID
    distance: float


def _normalized_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _validate_retrieval_request(
    query_embedding: list[float],
    filters: ProductRetrievalFilters,
    *,
    limit: int,
) -> tuple[list[float], ProductRetrievalFilters]:
    if limit < 1 or limit > MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")
    if len(query_embedding) != EMBEDDING_DIMENSION:
        raise ValueError("query embedding must have 768 dimensions")
    try:
        normalized_embedding = [float(value) for value in query_embedding]
    except (TypeError, ValueError) as error:
        raise ValueError("query embedding must contain finite numbers") from error
    if not all(math.isfinite(value) for value in normalized_embedding):
        raise ValueError("query embedding must contain finite numbers")
    magnitude = math.sqrt(sum(value * value for value in normalized_embedding))
    if magnitude == 0:
        raise ValueError("query embedding must be non-zero")

    if filters.min_price is not None and filters.min_price < 0:
        raise ValueError("minimum price must be non-negative")
    if filters.max_price is not None and filters.max_price < 0:
        raise ValueError("maximum price must be non-negative")
    if (
        filters.min_price is not None
        and filters.max_price is not None
        and filters.min_price > filters.max_price
    ):
        raise ValueError("price range minimum must not exceed maximum")

    return normalized_embedding, ProductRetrievalFilters(
        category=_normalized_optional(filters.category),
        min_price=filters.min_price,
        max_price=filters.max_price,
        color=_normalized_optional(filters.color),
        size=_normalized_optional(filters.size),
    )


def _hard_filters(filters: ProductRetrievalFilters):
    predicates = [
        Product.is_active.is_(True),
        Product.deleted_at.is_(None),
        Category.is_active.is_(True),
    ]
    if filters.category is not None:
        predicates.append(func.lower(Category.slug) == filters.category)

    effective_price = func.coalesce(Product.sale_price, Product.price)
    if filters.min_price is not None:
        predicates.append(effective_price >= filters.min_price)
    if filters.max_price is not None:
        predicates.append(effective_price <= filters.max_price)

    if filters.color is not None or filters.size is not None:
        variant_predicates = [
            ProductVariant.product_id == Product.id,
            ProductVariant.is_active.is_(True),
            ProductVariant.stock_quantity > 0,
            Color.is_active.is_(True),
            Size.is_active.is_(True),
        ]
        if filters.color is not None:
            variant_predicates.append(func.lower(Color.slug) == filters.color)
        if filters.size is not None:
            variant_predicates.append(func.lower(Size.code) == filters.size)
        predicates.append(
            select(1)
            .select_from(ProductVariant)
            .join(Color, Color.id == ProductVariant.color_id)
            .join(Size, Size.id == ProductVariant.size_id)
            .where(*variant_predicates)
            .exists()
        )
    return predicates


def _rag_eligibility():
    return (
        RagDocument.source_type == "product",
        RagDocument.is_active.is_(True),
        RagDocument.index_status == "indexed",
        RagChunk.is_active.is_(True),
        RagChunk.source_version == RagDocument.source_version,
    )


def _load_options():
    return (
        joinedload(Product.category),
        joinedload(Product.images),
        joinedload(Product.variants).joinedload(ProductVariant.color),
        joinedload(Product.variants).joinedload(ProductVariant.size),
    )


def _hydrate_candidate(
    product: Product,
    document: RagDocument,
    chunk: RagChunk,
    distance: float,
) -> RetrievedProduct:
    active_variants = sorted(
        (
            variant
            for variant in product.variants
            if variant.is_active and variant.color.is_active and variant.size.is_active
        ),
        key=lambda variant: variant.variant_sku,
    )
    variants = tuple(
        RetrievedVariant(
            color=variant.color.name,
            color_slug=variant.color.slug,
            size=variant.size.code,
            stock_quantity=variant.stock_quantity,
        )
        for variant in active_variants
    )
    in_stock_variants = [
        variant for variant in active_variants if variant.stock_quantity > 0
    ]
    available_colors = tuple(
        sorted({variant.color.name for variant in in_stock_variants})
    )
    available_sizes = tuple(
        size.code
        for size in sorted(
            {variant.size.id: variant.size for variant in in_stock_variants}.values(),
            key=lambda item: (item.sort_order, item.code),
        )
    )
    images = sorted(
        product.images,
        key=lambda image: (not image.is_primary, image.sort_order, str(image.id)),
    )
    image_url = images[0].file_path if images else None
    score = 1.0 - distance
    if not math.isfinite(score):
        raise RuntimeError("database returned a non-finite retrieval score")

    return RetrievedProduct(
        product_id=product.id,
        source_id=document.source_id,
        rag_document_id=document.id,
        chunk_ids=(chunk.id,),
        score=score,
        slug=product.slug,
        name=product.name,
        image_url=image_url,
        effective_price=(
            product.sale_price if product.sale_price is not None else product.price
        ),
        available_colors=available_colors,
        available_sizes=available_sizes,
        in_stock=bool(in_stock_variants),
        variants=variants,
    )


async def retrieve_products(
    session: AsyncSession,
    query_embedding: list[float],
    filters: ProductRetrievalFilters | None = None,
    *,
    limit: int = 5,
) -> list[RetrievedProduct]:
    """Rank product chunks, enforce hard SQL filters, then hydrate live catalog rows."""
    embedding, filters = _validate_retrieval_request(
        query_embedding,
        filters or ProductRetrievalFilters(),
        limit=limit,
    )
    query_vector = literal(embedding, type_=VectorType(EMBEDDING_DIMENSION))
    distance = RagChunk.embedding.op("<=>")(query_vector)
    ranked_chunks = (
        select(
            RagDocument.source_id.label("product_id"),
            RagDocument.id.label("document_id"),
            RagChunk.id.label("chunk_id"),
            distance.label("distance"),
            func.row_number()
            .over(
                partition_by=RagDocument.source_id,
                order_by=(distance, RagChunk.id),
            )
            .label("chunk_rank"),
        )
        .select_from(RagChunk)
        .join(RagDocument, RagDocument.id == RagChunk.rag_document_id)
        .join(Product, Product.id == RagDocument.source_id)
        .join(Category, Category.id == Product.category_id)
        .where(*_rag_eligibility(), *_hard_filters(filters))
        .subquery()
    )
    candidate_rows = (
        await session.execute(
            select(
                ranked_chunks.c.product_id,
                ranked_chunks.c.document_id,
                ranked_chunks.c.chunk_id,
                ranked_chunks.c.distance,
            )
            .where(ranked_chunks.c.chunk_rank == 1)
            .order_by(ranked_chunks.c.distance, ranked_chunks.c.product_id)
            .limit(limit)
        )
    ).all()
    candidates = []
    for row in candidate_rows:
        candidate_distance = float(row.distance)
        if not math.isfinite(candidate_distance):
            raise RuntimeError("database returned a non-finite retrieval distance")
        candidates.append(
            _Candidate(
                product_id=row.product_id,
                document_id=row.document_id,
                chunk_id=row.chunk_id,
                distance=candidate_distance,
            )
        )
    if not candidates:
        return []

    candidate_predicates = [
        and_(
            Product.id == candidate.product_id,
            RagDocument.id == candidate.document_id,
            RagChunk.id == candidate.chunk_id,
        )
        for candidate in candidates
    ]
    hydrated_rows = (
        (
            await session.execute(
                select(Product, RagDocument, RagChunk)
                .join(Category, Category.id == Product.category_id)
                .join(
                    RagDocument,
                    and_(
                        RagDocument.source_type == "product",
                        RagDocument.source_id == Product.id,
                    ),
                )
                .join(RagChunk, RagChunk.rag_document_id == RagDocument.id)
                .where(
                    or_(*candidate_predicates),
                    *_rag_eligibility(),
                    *_hard_filters(filters),
                )
                .options(*_load_options())
                .execution_options(populate_existing=True)
            )
        )
        .unique()
        .all()
    )
    rows_by_product = {
        product.id: (product, document, chunk)
        for product, document, chunk in hydrated_rows
    }
    return [
        _hydrate_candidate(
            *rows_by_product[candidate.product_id],
            candidate.distance,
        )
        for candidate in candidates
        if candidate.product_id in rows_by_product
    ]
