import math
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Integer, and_, case, func, literal, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.models.catalog import (
    Category,
    Color,
    Product,
    ProductVariant,
    Size,
)
from app.models.knowledge import (
    KnowledgeDocument,
    RagChunk,
    RagDocument,
    VectorType,
)


EMBEDDING_DIMENSION = 768
MAX_RETRIEVAL_LIMIT = 20
MAX_KNOWLEDGE_CANDIDATE_LIMIT = 100
MAX_KNOWLEDGE_QUERY_LENGTH = 1_000


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
class RetrievedKnowledge:
    source_id: UUID
    rag_document_id: UUID
    chunk_ids: tuple[UUID, ...]
    score: float
    title: str
    content: str


@dataclass(frozen=True)
class _Candidate:
    product_id: UUID
    document_id: UUID
    chunk_id: UUID
    distance: float


@dataclass
class _KnowledgeGroup:
    source_id: UUID
    document_id: UUID
    title: str
    score: float
    chunk_ids: list[UUID]
    contents: list[str]


def _normalized_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _validate_embedding(query_embedding: list[float]) -> list[float]:
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
    return normalized_embedding


def _validate_retrieval_request(
    query_embedding: list[float],
    filters: ProductRetrievalFilters,
    *,
    limit: int,
) -> tuple[list[float], ProductRetrievalFilters]:
    if limit < 1 or limit > MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")
    normalized_embedding = _validate_embedding(query_embedding)

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


def _validate_knowledge_retrieval_request(
    query_text: str,
    query_embedding: list[float],
    *,
    limit: int,
    candidate_limit: int,
    similarity_threshold: float,
    rrf_k: int,
) -> tuple[str, list[float]]:
    normalized_query = query_text.strip()
    if not normalized_query or len(normalized_query) > MAX_KNOWLEDGE_QUERY_LENGTH:
        raise ValueError(
            f"query text must contain between 1 and {MAX_KNOWLEDGE_QUERY_LENGTH} characters"
        )
    if limit < 1 or limit > MAX_RETRIEVAL_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_RETRIEVAL_LIMIT}")
    if candidate_limit < limit or candidate_limit > MAX_KNOWLEDGE_CANDIDATE_LIMIT:
        raise ValueError(
            "candidate limit must be greater than or equal to limit and no greater "
            f"than {MAX_KNOWLEDGE_CANDIDATE_LIMIT}"
        )
    if not 0 <= similarity_threshold <= 1:
        raise ValueError("similarity threshold must be between 0 and 1")
    if rrf_k < 1 or rrf_k > 1_000:
        raise ValueError("RRF constant must be between 1 and 1000")
    return normalized_query, _validate_embedding(query_embedding)


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


async def retrieve_knowledge(
    session: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    *,
    limit: int | None = None,
    candidate_limit: int | None = None,
    similarity_threshold: float | None = None,
    rrf_k: int | None = None,
) -> list[RetrievedKnowledge]:
    """Retrieve grounded Vietnamese return-policy knowledge."""
    if (
        limit is None
        or candidate_limit is None
        or similarity_threshold is None
        or rrf_k is None
    ):
        settings = get_settings()
        limit = settings.rag_knowledge_top_k if limit is None else limit
        candidate_limit = (
            settings.rag_knowledge_candidate_limit
            if candidate_limit is None
            else candidate_limit
        )
        similarity_threshold = (
            settings.rag_knowledge_similarity_threshold
            if similarity_threshold is None
            else similarity_threshold
        )
        rrf_k = settings.rag_knowledge_rrf_k if rrf_k is None else rrf_k
    normalized_query, embedding = _validate_knowledge_retrieval_request(
        query_text,
        query_embedding,
        limit=limit,
        candidate_limit=candidate_limit,
        similarity_threshold=similarity_threshold,
        rrf_k=rrf_k,
    )
    query_vector = literal(embedding, type_=VectorType(EMBEDDING_DIMENSION))
    distance = RagChunk.embedding.op("<=>")(query_vector)
    fts_config = literal_column("'simple'")
    text_vector = func.to_tsvector(fts_config, RagChunk.content)
    text_query = func.websearch_to_tsquery(fts_config, normalized_query)
    keyword_rank = func.ts_rank_cd(text_vector, text_query)

    eligible_chunks = (
        select(
            KnowledgeDocument.id.label("source_id"),
            RagDocument.id.label("document_id"),
            RagChunk.id.label("chunk_id"),
            KnowledgeDocument.title.label("title"),
            RagChunk.content.label("content"),
            distance.label("distance"),
            keyword_rank.label("keyword_score"),
            text_vector.op("@@")(text_query).label("keyword_match"),
        )
        .select_from(RagChunk)
        .join(RagDocument, RagDocument.id == RagChunk.rag_document_id)
        .join(
            KnowledgeDocument,
            KnowledgeDocument.id == RagDocument.source_id,
        )
        .where(
            RagDocument.source_type == "knowledge",
            KnowledgeDocument.document_type == "return_policy",
            KnowledgeDocument.locale == "vi",
            KnowledgeDocument.is_active.is_(True),
            RagDocument.is_active.is_(True),
            RagDocument.index_status == "indexed",
            RagDocument.source_version == KnowledgeDocument.version,
            RagChunk.is_active.is_(True),
            RagChunk.source_version == RagDocument.source_version,
        )
        .cte("eligible_knowledge_chunks")
    )
    vector_ranked_chunks = (
        select(
            eligible_chunks,
            func.row_number()
            .over(
                partition_by=eligible_chunks.c.source_id,
                order_by=(
                    eligible_chunks.c.distance,
                    eligible_chunks.c.document_id,
                    eligible_chunks.c.chunk_id,
                ),
            )
            .label("source_chunk_rank"),
        )
        .where(eligible_chunks.c.distance <= 1.0 - similarity_threshold)
        .cte("vector_ranked_knowledge_chunks")
    )
    vector_candidates = (
        select(
            vector_ranked_chunks.c.source_id,
            vector_ranked_chunks.c.document_id,
            vector_ranked_chunks.c.chunk_id,
            vector_ranked_chunks.c.title,
            vector_ranked_chunks.c.content,
            func.row_number()
            .over(
                order_by=(
                    vector_ranked_chunks.c.distance,
                    vector_ranked_chunks.c.source_id,
                    vector_ranked_chunks.c.document_id,
                    vector_ranked_chunks.c.chunk_id,
                )
            )
            .label("vector_rank"),
            literal(None, type_=Integer).label("keyword_rank"),
        )
        .where(vector_ranked_chunks.c.source_chunk_rank == 1)
        .order_by(
            vector_ranked_chunks.c.distance,
            vector_ranked_chunks.c.source_id,
            vector_ranked_chunks.c.document_id,
            vector_ranked_chunks.c.chunk_id,
        )
        .limit(candidate_limit)
    )
    keyword_ranked_chunks = (
        select(
            eligible_chunks,
            func.row_number()
            .over(
                partition_by=eligible_chunks.c.source_id,
                order_by=(
                    eligible_chunks.c.keyword_score.desc(),
                    eligible_chunks.c.document_id,
                    eligible_chunks.c.chunk_id,
                ),
            )
            .label("source_chunk_rank"),
        )
        .where(eligible_chunks.c.keyword_match.is_(True))
        .cte("keyword_ranked_knowledge_chunks")
    )
    keyword_candidates = (
        select(
            keyword_ranked_chunks.c.source_id,
            keyword_ranked_chunks.c.document_id,
            keyword_ranked_chunks.c.chunk_id,
            keyword_ranked_chunks.c.title,
            keyword_ranked_chunks.c.content,
            literal(None, type_=Integer).label("vector_rank"),
            func.row_number()
            .over(
                order_by=(
                    keyword_ranked_chunks.c.keyword_score.desc(),
                    keyword_ranked_chunks.c.source_id,
                    keyword_ranked_chunks.c.document_id,
                    keyword_ranked_chunks.c.chunk_id,
                )
            )
            .label("keyword_rank"),
        )
        .where(keyword_ranked_chunks.c.source_chunk_rank == 1)
        .order_by(
            keyword_ranked_chunks.c.keyword_score.desc(),
            keyword_ranked_chunks.c.source_id,
            keyword_ranked_chunks.c.document_id,
            keyword_ranked_chunks.c.chunk_id,
        )
        .limit(candidate_limit)
    )
    candidates = vector_candidates.union_all(keyword_candidates).cte(
        "knowledge_candidates"
    )
    ranked_sources = (
        select(
            candidates.c.source_id,
            candidates.c.document_id,
            candidates.c.title,
            func.min(candidates.c.vector_rank).label("vector_rank"),
            func.min(candidates.c.keyword_rank).label("keyword_rank"),
        )
        .group_by(
            candidates.c.source_id,
            candidates.c.document_id,
            candidates.c.title,
        )
        .cte("ranked_knowledge_sources")
    )
    rrf_score = (
        case(
            (
                ranked_sources.c.vector_rank.is_not(None),
                1.0 / (rrf_k + ranked_sources.c.vector_rank),
            ),
            else_=0.0,
        )
        + case(
            (
                ranked_sources.c.keyword_rank.is_not(None),
                1.0 / (rrf_k + ranked_sources.c.keyword_rank),
            ),
            else_=0.0,
        )
    ).label("rrf_score")
    scored_sources = select(ranked_sources, rrf_score).cte("scored_knowledge_sources")
    top_sources = (
        select(scored_sources)
        .order_by(
            scored_sources.c.rrf_score.desc(),
            scored_sources.c.source_id,
            scored_sources.c.document_id,
        )
        .limit(limit)
        .cte("top_knowledge_sources")
    )
    rows = (
        await session.execute(
            select(
                top_sources.c.source_id,
                top_sources.c.document_id,
                candidates.c.chunk_id,
                top_sources.c.title,
                candidates.c.content,
                top_sources.c.rrf_score,
            )
            .join(
                candidates,
                and_(
                    candidates.c.source_id == top_sources.c.source_id,
                    candidates.c.document_id == top_sources.c.document_id,
                ),
            )
            .order_by(
                top_sources.c.rrf_score.desc(),
                top_sources.c.source_id,
                top_sources.c.document_id,
                candidates.c.chunk_id,
            )
        )
    ).all()

    grouped: dict[UUID, _KnowledgeGroup] = {}
    for row in rows:
        score = float(row.rrf_score)
        if not math.isfinite(score):
            raise RuntimeError("database returned a non-finite knowledge retrieval score")
        group = grouped.setdefault(
            row.source_id,
            _KnowledgeGroup(
                source_id=row.source_id,
                document_id=row.document_id,
                score=score,
                title=row.title,
                chunk_ids=[],
                contents=[],
            )
        )
        if row.chunk_id not in group.chunk_ids:
            group.chunk_ids.append(row.chunk_id)
            group.contents.append(row.content)

    return [
        RetrievedKnowledge(
            source_id=group.source_id,
            rag_document_id=group.document_id,
            chunk_ids=tuple(group.chunk_ids),
            score=group.score,
            title=group.title,
            content="\n\n".join(group.contents),
        )
        for group in grouped.values()
    ]
