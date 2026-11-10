"""
FinTech Agent — Embedding Provider Factory
Constructs and validates the active embedding provider based on configuration.
"""

from typing import Optional
from backend.app.config import settings
from backend.app.core.exceptions import ProviderConfigurationError
from backend.app.embeddings.base import BaseEmbeddingProvider
from backend.app.embeddings.local_provider import SentenceTransformersEmbeddingProvider
from backend.app.embeddings.mock_provider import MockEmbeddingProvider
from backend.app.embeddings.openai_provider import OpenAICompatibleEmbeddingProvider


def get_embedding_provider(
    provider_type: Optional[str] = None,
    model: Optional[str] = None,
    dimension: Optional[int] = None,
    simulate_failure: bool = False
) -> BaseEmbeddingProvider:
    """
    Returns an instantiated BaseEmbeddingProvider implementation.
    Defaults to configuration in Settings if arguments are omitted.
    """
    chosen_provider = (provider_type or settings.EMBEDDING_PROVIDER).lower().strip()
    chosen_model = model or settings.EMBEDDING_MODEL
    chosen_dim = dimension or settings.EMBEDDING_DIMENSION

    if chosen_provider == "mock":
        return MockEmbeddingProvider(
            dimension=chosen_dim,
            model_name=chosen_model,
            simulate_failure=simulate_failure
        )
    elif chosen_provider == "openai":
        return OpenAICompatibleEmbeddingProvider(
            model_name=chosen_model,
            dimension=chosen_dim or 1536,
            batch_size=settings.EMBEDDING_BATCH_SIZE
        )
    elif chosen_provider in ("sentence-transformers", "local"):
        return SentenceTransformersEmbeddingProvider(
            model_name=chosen_model,
            dimension=chosen_dim
        )
    else:
        raise ProviderConfigurationError(
            f"Unsupported embedding provider: '{chosen_provider}'. "
            f"Supported providers: 'mock', 'openai', 'sentence-transformers'."
        )
