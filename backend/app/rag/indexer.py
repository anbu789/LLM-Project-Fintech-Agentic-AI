"""
FinTech Agent — Schema Catalog Vector Indexer
Orchestrates schema catalog generation, RAG document building,
embedding generation, and persistent upsert into ChromaDB.
"""

import time
from typing import Any, Dict, Optional

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.embeddings.base import BaseEmbeddingProvider
from backend.app.embeddings.provider_factory import get_embedding_provider
from backend.app.rag.chroma_store import ChromaSchemaStore, chroma_store
from backend.app.schema.catalog_builder import SchemaCatalogBuilder, schema_catalog_builder
from backend.app.schema.document_builder import SchemaDocumentBuilder, schema_document_builder
from backend.app.schema.models import SchemaCatalog


class SchemaIndexer:
    """Coordinates building, embedding, and indexing schema documents into ChromaDB."""

    def __init__(
        self,
        catalog_builder: SchemaCatalogBuilder = schema_catalog_builder,
        doc_builder: SchemaDocumentBuilder = schema_document_builder,
        store: ChromaSchemaStore = chroma_store,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
    ):
        self.catalog_builder = catalog_builder
        self.doc_builder = doc_builder
        self.store = store
        self._provider = embedding_provider

    @property
    def embedding_provider(self) -> BaseEmbeddingProvider:
        if self._provider is None:
            self._provider = get_embedding_provider()
        return self._provider

    def index_schema(self, force: bool = False) -> Dict[str, Any]:
        """
        Indexes the database schema into ChromaDB.
        Skips embedding generation if the schema fingerprint is unchanged and not forced.
        """
        start_time = time.time()
        catalog: SchemaCatalog = self.catalog_builder.load_catalog()
        active_fingerprint = catalog.catalog_fingerprint

        # Check existing index stats
        stats = self.store.get_stats()
        current_fingerprint = stats.get("schema_fingerprint")
        current_count = stats.get("document_count", 0)

        provider = self.embedding_provider

        # Check if already up to date
        if not force and current_count > 0 and current_fingerprint == active_fingerprint:
            duration = round(time.time() - start_time, 3)
            logger.info(f"Schema vector index is already up to date (fingerprint={active_fingerprint[:12]}..., {current_count} docs).")
            return {
                "status": "already_up_to_date",
                "document_count": current_count,
                "schema_fingerprint": active_fingerprint,
                "embedding_provider": provider.provider_name,
                "embedding_model": provider.model_name,
                "duration_seconds": duration,
                "skipped_reindex": True
            }

        logger.info(f"Starting schema indexing (force={force}, fingerprint={active_fingerprint[:12]}...)")

        # 1. Generate RAG documents
        documents = self.doc_builder.build_documents(catalog)
        texts = [doc.content for doc in documents]
        active_ids = {doc.id for doc in documents}

        # 2. Generate embeddings in batches
        embeddings = provider.embed_batch(texts)

        # 3. Upsert into ChromaDB
        upserted_count = self.store.upsert_documents(
            documents=documents,
            embeddings=embeddings,
            schema_fingerprint=active_fingerprint
        )

        # 4. Clean up stale documents
        deleted_stale = self.store.delete_stale_documents(active_ids)

        duration = round(time.time() - start_time, 3)
        logger.info(f"Indexed {upserted_count} schema documents in {duration}s ({deleted_stale} stale deleted).")

        return {
            "status": "indexed",
            "document_count": upserted_count,
            "stale_documents_deleted": deleted_stale,
            "schema_fingerprint": active_fingerprint,
            "embedding_provider": provider.provider_name,
            "embedding_model": provider.model_name,
            "embedding_dimension": provider.dimension,
            "duration_seconds": duration,
            "skipped_reindex": False
        }


schema_indexer = SchemaIndexer()
