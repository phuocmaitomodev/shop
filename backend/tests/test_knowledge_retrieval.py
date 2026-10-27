import asyncio
import math
from types import SimpleNamespace

import pytest

from app.rag import retrieval


def _embedding() -> list[float]:
    return [1.0] + [0.0] * 767


def test_knowledge_retrieval_exposes_public_result_and_function() -> None:
    assert hasattr(retrieval, "RetrievedKnowledge")
    assert hasattr(retrieval, "retrieve_knowledge")


@pytest.mark.parametrize(
    "embedding",
    (
        [1.0],
        [0.0] * 768,
        [math.nan] + [0.0] * 767,
        [math.inf] + [0.0] * 767,
    ),
)
def test_knowledge_retrieval_rejects_invalid_embedding_before_querying(
    embedding: list[float],
) -> None:
    with pytest.raises(ValueError, match="query embedding"):
        asyncio.run(
            retrieval.retrieve_knowledge(
                None,
                "đổi trả trong bao lâu",
                embedding,
            )
        )


@pytest.mark.parametrize(
    ("query_text", "options", "message"),
    (
        ("   ", {}, "query text"),
        ("x" * 1001, {}, "query text"),
        ("đổi trả", {"limit": 0}, "limit"),
        ("đổi trả", {"limit": 21}, "limit"),
        ("đổi trả", {"limit": 4, "candidate_limit": 3}, "candidate limit"),
        ("đổi trả", {"candidate_limit": 101}, "candidate limit"),
        ("đổi trả", {"similarity_threshold": -0.1}, "similarity threshold"),
        ("đổi trả", {"similarity_threshold": 1.1}, "similarity threshold"),
        ("đổi trả", {"rrf_k": 0}, "RRF constant"),
    ),
)
def test_knowledge_retrieval_rejects_unbounded_request_before_querying(
    query_text: str,
    options: dict,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        asyncio.run(
            retrieval.retrieve_knowledge(
                None,
                query_text,
                _embedding(),
                **options,
            )
        )


def test_knowledge_retrieval_uses_configured_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval,
        "get_settings",
        lambda: SimpleNamespace(
            rag_knowledge_top_k=4,
            rag_knowledge_candidate_limit=3,
            rag_knowledge_similarity_threshold=0.2,
            rag_knowledge_rrf_k=60,
        ),
        raising=False,
    )

    with pytest.raises(ValueError, match="candidate limit"):
        asyncio.run(
            retrieval.retrieve_knowledge(
                None,
                "đổi trả",
                _embedding(),
            )
        )
