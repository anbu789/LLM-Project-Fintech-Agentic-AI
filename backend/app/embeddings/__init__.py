"""
FinTech Agent — Embedding Provider Abstraction Module
"""

from backend.app.embeddings.base import BaseEmbeddingProvider
from backend.app.embeddings.local_provider import SentenceTransformersEmbeddingProvider
from backend.app.embeddings.mock_provider import MockEmbeddingProvider
from backend.app.embeddings.openai_provider import OpenAICompatibleEmbeddingProvider
from backend.app.embeddings.provider_factory import get_embedding_provider

__all__ = [
    "BaseEmbeddingProvider",
    "MockEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "SentenceTransformersEmbeddingProvider",
    "get_embedding_provider",
]
