"""
FinTech Agent — Embedding Provider Base Abstraction
Defines common interface for generating vector embeddings across
mock, local, and remote provider implementations.
"""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingProvider(ABC):
    """Abstract base class for all vector embedding providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns provider identifier (e.g. 'mock', 'openai', 'sentence-transformers')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Returns embedding model identifier."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Returns output embedding vector dimensionality."""
        pass

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generates an embedding vector for a single string."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embedding vectors for a list of strings."""
        pass
