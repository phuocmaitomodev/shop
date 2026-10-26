import asyncio
import json
import math

import httpx
import pytest

from app.rag.provider import (
    GeminiEmbeddingProvider,
    PermanentIndexingError,
    RetryableIndexingError,
)


def test_gemini_provider_uses_configured_model_and_768_dimensions() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    {"values": [2.0] + [0.0] * 767},
                    {"values": [0.0, 3.0] + [0.0] * 766},
                ]
            },
        )

    async def exercise() -> list[list[float]]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = GeminiEmbeddingProvider(
                api_key="test-key-not-secret",
                model_name="configured-embedding-model",
                dimension=768,
                client=client,
            )
            return await provider.embed(["áo thoáng khí", "váy công sở"])

    vectors = asyncio.run(exercise())

    assert len(requests) == 1
    request = requests[0]
    assert request.url.path.endswith(
        "/v1beta/models/configured-embedding-model:batchEmbedContents"
    )
    assert request.headers["x-goog-api-key"] == "test-key-not-secret"
    payload = json.loads(request.content)
    assert payload == {
        "requests": [
            {
                "model": "models/configured-embedding-model",
                "content": {"parts": [{"text": "áo thoáng khí"}]},
                "taskType": "RETRIEVAL_DOCUMENT",
                "outputDimensionality": 768,
            },
            {
                "model": "models/configured-embedding-model",
                "content": {"parts": [{"text": "váy công sở"}]},
                "taskType": "RETRIEVAL_DOCUMENT",
                "outputDimensionality": 768,
            },
        ]
    }
    assert len(vectors) == 2
    assert all(len(vector) == 768 for vector in vectors)
    assert all(math.sqrt(sum(value * value for value in vector)) == 1.0 for vector in vectors)


def test_gemini_provider_rejects_dimension_mismatch() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [{"values": [1.0, 2.0]}]})

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = GeminiEmbeddingProvider(
                api_key="test-key",
                model_name="configured-model",
                dimension=768,
                client=client,
            )
            with pytest.raises(
                PermanentIndexingError, match="embedding_dimension_mismatch"
            ):
                await provider.embed(["nội dung"])

    asyncio.run(exercise())


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_gemini_provider_maps_transient_http_errors_to_retryable(
    status_code: int,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": "sensitive"}})

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = GeminiEmbeddingProvider(
                api_key="test-key",
                model_name="configured-model",
                dimension=768,
                client=client,
            )
            with pytest.raises(
                RetryableIndexingError, match="provider_temporarily_unavailable"
            ):
                await provider.embed(["nội dung"])

    asyncio.run(exercise())


def test_gemini_provider_maps_invalid_response_to_permanent_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "response"})

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = GeminiEmbeddingProvider(
                api_key="test-key",
                model_name="configured-model",
                dimension=768,
                client=client,
            )
            with pytest.raises(
                PermanentIndexingError, match="invalid_embedding_response"
            ):
                await provider.embed(["nội dung"])

    asyncio.run(exercise())
