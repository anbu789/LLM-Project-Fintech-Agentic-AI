"""
FinTech Agent — Deterministic Mock Embedding Provider
Generates reproducible, normalized pseudo-semantic embeddings based on token
and n-gram hashing for reliable testing, development, and offline evaluation.
"""

import hashlib
import math
import re
from typing import List
from backend.app.core.exceptions import ProviderAPIError
from backend.app.embeddings.base import BaseEmbeddingProvider


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic mock embedding provider.
    Produces repeatable vectors with domain similarity preservation:
    texts sharing domain terms (e.g. 'customers', 'Chennai', 'loan')
    exhibit high cosine similarity.
    """

    def __init__(
        self,
        dimension: int = 384,
        model_name: str = "mock-banking-embedding-384",
        simulate_failure: bool = False
    ):
        self._dimension = dimension
        self._model_name = model_name
        self.simulate_failure = simulate_failure

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _hash_token(self, token: str) -> List[float]:
        """Converts a single token into a deterministic vector."""
        vec = [0.0] * self._dimension
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        # Seed pseudo-random values from digest
        for i in range(self._dimension):
            byte_val = digest[i % len(digest)]
            val = ((byte_val ^ (i * 31 % 256)) - 128.0) / 128.0
            vec[i] = val
        return vec

    def embed_text(self, text: str) -> List[float]:
        """Generates a deterministic normalized embedding vector for text."""
        if self.simulate_failure:
            raise ProviderAPIError("mock", "Simulated embedding provider connection failure")

        cleaned = text.lower().strip()
        tokens = re.findall(r"\w+", cleaned)
        if not tokens:
            # Deterministic non-zero unit vector for empty input
            vec = [1.0 / math.sqrt(self._dimension)] * self._dimension
            return vec

        accumulated = [0.0] * self._dimension

        # 1. Whole token hashing
        for token in tokens:
            t_vec = self._hash_token(token)
            for i in range(self._dimension):
                accumulated[i] += t_vec[i]

        # 2. Substring / 3-gram hashing for morphology (e.g. "customer" vs "customers")
        for token in tokens:
            if len(token) >= 3:
                for j in range(len(token) - 2):
                    ngram = token[j:j+3]
                    n_vec = self._hash_token(ngram)
                    for i in range(self._dimension):
                        accumulated[i] += n_vec[i] * 0.3

        # L2 Normalization
        norm = math.sqrt(sum(x * x for x in accumulated))
        if norm > 1e-9:
            return [x / norm for x in accumulated]
        return [1.0 / math.sqrt(self._dimension)] * self._dimension

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embedding vectors for a batch of strings."""
        return [self.embed_text(t) for t in texts]
