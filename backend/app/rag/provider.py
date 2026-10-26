import hashlib
import math
from collections.abc import Sequence
from typing import Literal, Protocol
from urllib.parse import quote

import httpx


class EmbeddingProvider(Protocol):
    model_name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for each input text, preserving order."""
        ...


class RetryableIndexingError(Exception):
    def __init__(self, public_code: str = "retryable_provider_error") -> None:
        super().__init__(public_code)
        self.public_code = public_code


class PermanentIndexingError(Exception):
    def __init__(self, public_code: str = "permanent_indexing_error") -> None:
        super().__init__(public_code)
        self.public_code = public_code


class DeterministicEmbeddingProvider:
    """Offline provider used by local development and deterministic tests."""

    model_name = "stub-deterministic-v1"

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [((seed[index % len(seed)] / 255.0) * 2.0) - 1.0 for index in range(self.dimension)]
            magnitude = math.sqrt(sum(value * value for value in vector))
            vectors.append([value / magnitude for value in vector])
        return vectors


class GeminiEmbeddingProvider:
    """Gemini batch embedding adapter with a stable, sanitized error taxonomy."""

    _base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        dimension: int,
        task_type: Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"] = "RETRIEVAL_DOCUMENT",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        normalized_model = model_name.removeprefix("models/").strip()
        if not normalized_model:
            raise ValueError("GEMINI_EMBEDDING_MODEL is required")
        self.model_name = normalized_model
        self.dimension = dimension
        self.task_type = task_type
        self._api_key = api_key
        self._client = client

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model_path = f"models/{self.model_name}"
        payload = {
            "requests": [
                {
                    "model": model_path,
                    "content": {"parts": [{"text": text}]},
                    "taskType": self.task_type,
                    "outputDimensionality": self.dimension,
                }
                for text in texts
            ]
        }
        endpoint = (
            f"{self._base_url}/models/{quote(self.model_name, safe='')}:"
            "batchEmbedContents"
        )
        if self._client is not None:
            response = await self._request(self._client, endpoint, payload)
        else:
            async with httpx.AsyncClient() as client:
                response = await self._request(client, endpoint, payload)
        return self._parse_vectors(response, expected_count=len(texts))

    async def _request(
        self, client: httpx.AsyncClient, endpoint: str, payload: dict
    ) -> httpx.Response:
        try:
            response = await client.post(
                endpoint,
                headers={"x-goog-api-key": self._api_key},
                json=payload,
            )
        except httpx.RequestError:
            raise RetryableIndexingError("provider_temporarily_unavailable") from None
        if response.status_code in (408, 409, 429) or response.status_code >= 500:
            raise RetryableIndexingError("provider_temporarily_unavailable")
        if response.status_code >= 400:
            raise PermanentIndexingError("provider_request_rejected")
        return response

    def _parse_vectors(
        self, response: httpx.Response, *, expected_count: int
    ) -> list[list[float]]:
        try:
            embeddings = response.json()["embeddings"]
            vectors = [embedding["values"] for embedding in embeddings]
        except (ValueError, KeyError, TypeError):
            raise PermanentIndexingError("invalid_embedding_response") from None
        if len(vectors) != expected_count:
            raise PermanentIndexingError("embedding_count_mismatch")

        normalized: list[list[float]] = []
        for vector in vectors:
            if (
                not isinstance(vector, list)
                or len(vector) != self.dimension
                or not all(isinstance(value, (int, float)) for value in vector)
            ):
                raise PermanentIndexingError("embedding_dimension_mismatch")
            float_vector = [float(value) for value in vector]
            if not all(math.isfinite(value) for value in float_vector):
                raise PermanentIndexingError("invalid_embedding_vector")
            magnitude = math.sqrt(sum(value * value for value in float_vector))
            if magnitude == 0:
                raise PermanentIndexingError("invalid_embedding_vector")
            normalized.append([value / magnitude for value in float_vector])
        return normalized
