import hashlib
import math
from collections.abc import Sequence
from typing import Protocol


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
