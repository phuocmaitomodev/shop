import math

import pytest

from app.rag.retrieval import ProductRetrievalFilters, _validate_retrieval_request


def _embedding() -> list[float]:
    return [1.0] + [0.0] * 767


def test_retrieval_request_accepts_valid_embedding_filters_and_limit() -> None:
    filters = ProductRetrievalFilters(
        category=" AO-THUN ",
        min_price=100_000,
        max_price=500_000,
        color=" DEN ",
        size=" M ",
    )

    normalized, normalized_filters = _validate_retrieval_request(
        _embedding(), filters, limit=5
    )

    assert normalized == _embedding()
    assert normalized_filters == ProductRetrievalFilters(
        category="ao-thun",
        min_price=100_000,
        max_price=500_000,
        color="den",
        size="m",
    )


@pytest.mark.parametrize(
    "embedding",
    [
        [1.0],
        [0.0] * 768,
        [math.nan] + [0.0] * 767,
        [math.inf] + [0.0] * 767,
    ],
)
def test_retrieval_request_rejects_invalid_embedding(embedding: list[float]) -> None:
    with pytest.raises(ValueError, match="query embedding"):
        _validate_retrieval_request(embedding, ProductRetrievalFilters(), limit=5)


@pytest.mark.parametrize("limit", [0, 21])
def test_retrieval_request_rejects_unbounded_limit(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        _validate_retrieval_request(_embedding(), ProductRetrievalFilters(), limit=limit)


def test_retrieval_request_rejects_inverted_price_range() -> None:
    with pytest.raises(ValueError, match="price range"):
        _validate_retrieval_request(
            _embedding(),
            ProductRetrievalFilters(min_price=500_000, max_price=100_000),
            limit=5,
        )
