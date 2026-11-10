"""
FinTech Agent — Phase 3 Test Suite: Schema Catalog, Embeddings, ChromaDB & Semantic Retrieval
Verifies:
1. Reusable schema catalog builder and metadata extraction across all 12 collections.
2. 22 verified cross-collection relationships and ground-truth foreign keys.
3. Accurate representation of loans.outstanding_amount and 100% absence of days_past_due/overdue_amount.
4. Deterministic schema fingerprinting.
5. RAG document generation (collections, fields, relationships, glossary) with deterministic IDs and 0 PII.
6. Provider-independent embedding abstraction, deterministic mock behavior, and failure shielding.
7. Persistent ChromaDB vector store, idempotent upserting, stale document cleanup, and dimension checks.
8. Semantic retrieval, multi-collection join path discovery, and unsupported concept shielding.
9. FastAPI endpoints (/api/v1/schema/health, /api/v1/schema/search, /api/v1/schema/index).
10. Benchmark retrieval evaluation over SAMPLE_QUERIES.md test cases.
"""

import math
import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.core.exceptions import MissingAPIKeyError, ProviderAPIError
from backend.app.embeddings.mock_provider import MockEmbeddingProvider
from backend.app.embeddings.openai_provider import OpenAICompatibleEmbeddingProvider
from backend.app.embeddings.provider_factory import get_embedding_provider
from backend.app.main import app
from backend.app.rag.chroma_store import ChromaModelMismatchError, ChromaSchemaStore, chroma_store
from backend.app.rag.evaluation import evaluation_runner
from backend.app.rag.indexer import SchemaIndexer, schema_indexer
from backend.app.rag.retriever import SchemaRetriever, schema_retriever
from backend.app.schema.catalog_builder import SchemaCatalogBuilder, schema_catalog_builder
from backend.app.schema.document_builder import SchemaDocumentBuilder, schema_document_builder
from backend.app.schema.fingerprint import compute_schema_fingerprint
from backend.app.schema.glossary_mapper import find_glossary_for_term, load_glossary_entries


# ==============================================================================
# 1. Schema Catalog & Metadata Extraction Tests
# ==============================================================================

def test_catalog_builder_extracts_all_12_collections():
    """Verify that all 12 planned banking collections are represented in the catalog."""
    catalog = schema_catalog_builder.load_catalog()
    assert catalog.database == "fintech_agent_db"
    assert len(catalog.collections) == 12

    expected_collections = {
        "branches", "employees", "merchants", "customers",
        "accounts", "transactions", "cards", "loans",
        "kyc_documents", "support_tickets", "fraud_alerts", "investments"
    }
    assert set(catalog.collections.keys()) == expected_collections


def test_catalog_primary_keys_and_field_inventories():
    """Verify primary keys and field count integrity for key collections."""
    catalog = schema_catalog_builder.load_catalog()

    # Check primary keys
    assert catalog.collections["branches"].primary_key == "branch_id"
    assert catalog.collections["customers"].primary_key == "customer_id"
    assert catalog.collections["accounts"].primary_key == "account_id"
    assert catalog.collections["transactions"].primary_key == "transaction_id"
    assert catalog.collections["loans"].primary_key == "loan_id"

    # Total fields across all collections should equal exactly 200
    total_fields = sum(len(col.fields) for col in catalog.collections.values())
    assert total_fields == 200


def test_catalog_accurately_represents_loan_fields():
    """Verify loans.outstanding_amount exists and loans.days_past_due/overdue_amount do NOT exist."""
    catalog = schema_catalog_builder.load_catalog()
    loan_fields = catalog.collections["loans"].fields

    assert "outstanding_amount" in loan_fields
    assert loan_fields["outstanding_amount"].data_type == "number"

    # Negative check: must not invent missing fields
    assert "days_past_due" not in loan_fields
    assert "overdue_amount" not in loan_fields


def test_catalog_extracts_all_22_relationships():
    """Verify all 22 verified cross-collection relationships are extracted."""
    catalog = schema_catalog_builder.load_catalog()
    assert len(catalog.relationships) == 22

    # Check key relationships
    rel_tuples = {(r.from_collection, r.from_field, r.to_collection, r.to_field) for r in catalog.relationships}
    assert ("accounts", "customer_id", "customers", "customer_id") in rel_tuples
    assert ("loans", "customer_id", "customers", "customer_id") in rel_tuples
    assert ("transactions", "account_id", "accounts", "account_id") in rel_tuples
    assert ("transactions", "merchant_id", "merchants", "merchant_id") in rel_tuples
    assert ("employees", "branch_id", "branches", "branch_id") in rel_tuples


def test_deterministic_schema_fingerprint():
    """Verify compute_schema_fingerprint produces identical hash across invocations."""
    catalog = schema_catalog_builder.load_catalog()
    fp1 = compute_schema_fingerprint(catalog.model_dump())
    fp2 = compute_schema_fingerprint(catalog.model_dump())
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex string


def test_glossary_entries_and_term_mapping():
    """Verify glossary entries include critical business terms and unsupported concept warnings."""
    entries = load_glossary_entries()
    assert len(entries) >= 30

    # Test term lookup
    cust_entry = find_glossary_for_term("Customer")
    assert cust_entry is not None
    assert "customers" in cust_entry.mapped_collections

    # Test synonym lookup
    vendor_entry = find_glossary_for_term("vendor")
    assert vendor_entry is not None
    assert vendor_entry.term == "Merchant"

    # Test overdue guidance warns about overdue_amount
    overdue_entry = find_glossary_for_term("Overdue amount")
    assert overdue_entry is not None
    assert "NOT an existing field" in overdue_entry.implementation_guidance


# ==============================================================================
# 2. RAG Document Generation Tests
# ==============================================================================

def test_document_builder_generates_all_269_documents():
    """Verify document builder creates 12 collection, 200 field, 22 relationship, and 35 glossary docs."""
    catalog = schema_catalog_builder.load_catalog()
    docs = schema_document_builder.build_documents(catalog)
    assert len(docs) == 269

    by_type = {
        "collection": [d for d in docs if d.doc_type == "collection"],
        "field": [d for d in docs if d.doc_type == "field"],
        "relationship": [d for d in docs if d.doc_type == "relationship"],
        "glossary": [d for d in docs if d.doc_type == "glossary"],
    }
    assert len(by_type["collection"]) == 12
    assert len(by_type["field"]) == 200
    assert len(by_type["relationship"]) == 22
    assert len(by_type["glossary"]) == 35


def test_document_ids_are_deterministic():
    """Verify document IDs follow stable naming schemas without random UUIDs."""
    catalog = schema_catalog_builder.load_catalog()
    docs = schema_document_builder.build_documents(catalog)

    ids = {d.id for d in docs}
    assert "coll:customers" in ids
    assert "coll:accounts" in ids
    assert "field:loans.outstanding_amount" in ids
    assert "field:accounts.balance" in ids
    assert "rel:accounts.customer_id->customers.customer_id" in ids
    assert "glossary:customer" in ids


def test_no_raw_banking_data_in_documents():
    """Verify no sensitive records, card secrets, credentials, or raw PII documents are embedded."""
    catalog = schema_catalog_builder.load_catalog()
    docs = schema_document_builder.build_documents(catalog)

    # Search for forbidden credentials and raw data patterns
    for d in docs:
        content_lower = d.content.lower()
        assert "password" not in content_lower
        assert "secret" not in content_lower
        assert "cvv" not in content_lower
        # Verify valid doc types only
        assert d.doc_type in {"collection", "field", "relationship", "glossary"}


# ==============================================================================
# 3. Embedding Provider Abstraction Tests
# ==============================================================================

def test_mock_embedding_provider_deterministic_behavior():
    """Verify MockEmbeddingProvider produces deterministic, normalized vectors."""
    provider = MockEmbeddingProvider(dimension=384)
    v1 = provider.embed_text("Show accounts belonging to customers in Chennai")
    v2 = provider.embed_text("Show accounts belonging to customers in Chennai")
    assert v1 == v2
    assert len(v1) == 384

    # Verify L2 normalization: sum(x^2) ≈ 1.0
    norm = math.sqrt(sum(x * x for x in v1))
    assert abs(norm - 1.0) < 1e-5


def test_mock_embedding_semantic_proximity():
    """Verify that domain-related queries exhibit higher cosine similarity than unrelated queries."""
    provider = MockEmbeddingProvider(dimension=384)
    v_base = provider.embed_text("Show active loans for customers")
    v_close = provider.embed_text("Find customer loans with active status")
    v_distant = provider.embed_text("List branches located in Bangalore")

    sim_close = sum(a * b for a, b in zip(v_base, v_close))
    sim_distant = sum(a * b for a, b in zip(v_base, v_distant))

    assert sim_close > sim_distant, f"Expected {sim_close} > {sim_distant}"


def test_mock_embedding_batch_and_failure_simulation():
    """Verify batch embedding and simulated failure raising ProviderAPIError."""
    provider = MockEmbeddingProvider(dimension=128)
    batch = provider.embed_batch(["text one", "text two", "text three"])
    assert len(batch) == 3
    assert len(batch[0]) == 128

    # Failure simulation
    failing_provider = MockEmbeddingProvider(dimension=128, simulate_failure=True)
    with pytest.raises(ProviderAPIError):
        failing_provider.embed_text("test failure")


def test_openai_embedding_provider_missing_key():
    """Verify OpenAICompatibleEmbeddingProvider raises MissingAPIKeyError if key is missing."""
    provider = OpenAICompatibleEmbeddingProvider(api_key="")
    with pytest.raises(MissingAPIKeyError):
        provider._get_api_key()


def test_embedding_factory_unsupported_provider():
    """Verify get_embedding_provider raises ProviderConfigurationError for unknown provider."""
    from backend.app.core.exceptions import ProviderConfigurationError
    with pytest.raises(ProviderConfigurationError):
        get_embedding_provider("unknown_provider")


# ==============================================================================
# 4. ChromaDB Persistent Store & Indexing Tests
# ==============================================================================

def test_chroma_store_initial_indexing_and_count():
    """Verify ChromaSchemaStore successfully indexes and counts 269 schema documents."""
    summary = schema_indexer.index_schema(force=True)
    assert summary["status"] == "indexed"
    assert summary["document_count"] == 269

    stats = chroma_store.get_stats()
    assert stats["document_count"] == 269
    assert stats["collection_name"] == settings.CHROMA_COLLECTION_NAME


def test_chroma_idempotent_indexing_skips_unchanged():
    """Verify repeated indexing of unchanged schema skips re-indexing."""
    summary = schema_indexer.index_schema(force=False)
    assert summary["status"] == "already_up_to_date"
    assert summary["skipped_reindex"] is True


def test_chroma_model_mismatch_detection():
    """Verify ChromaSchemaStore raises ChromaModelMismatchError when dimension changes."""
    # Attempt to request collection with mismatched dimension
    with pytest.raises(ChromaModelMismatchError):
        chroma_store.get_collection(create_if_missing=False, expected_dimension=1536)


def test_chroma_metadata_filtering():
    """Verify ChromaSchemaStore query respects where_filter by doc_type and collection."""
    provider = get_embedding_provider()
    query_vec = provider.embed_text("accounts")

    # Filter by doc_type = "collection"
    hits = chroma_store.query(query_vec, top_k=5, where_filter={"doc_type": "collection"})
    for hit in hits:
        assert hit["metadata"]["doc_type"] == "collection"

    # Filter by collection = "loans"
    loan_hits = chroma_store.query(query_vec, top_k=5, where_filter={"collection": "loans"})
    for hit in loan_hits:
        assert hit["metadata"]["collection"] == "loans"


# ==============================================================================
# 5. Semantic Schema Retrieval Tests
# ==============================================================================

def test_retriever_single_collection_query():
    """Verify single-collection query returns matching collection and fields."""
    res = schema_retriever.retrieve("Show customers from Chennai", top_k=5)
    assert "customers" in res.relevant_collections
    assert len(res.retrieved_documents) > 0


def test_retriever_multi_collection_relationship_discovery():
    """Verify multi-collection query discovers linking join relationships."""
    res = schema_retriever.retrieve("Show customers with active loans", top_k=5)
    assert "customers" in res.relevant_collections
    assert "loans" in res.relevant_collections

    # Must discover relationship: loans.customer_id -> customers.customer_id
    rels = {f"{r['from']}->{r['to']}" for r in res.relevant_relationships}
    assert "loans.customer_id->customers.customer_id" in rels


def test_retriever_unsupported_concept_warnings():
    """Verify that queries mentioning days_past_due or overdue_amount return explicit warnings."""
    res = schema_retriever.retrieve("Find overdue loans with days past due and overdue amount")
    assert len(res.unsupported_concepts) >= 2
    flagged = {c["concept"] for c in res.unsupported_concepts}
    assert "days_past_due" in flagged
    assert "overdue_amount" in flagged


def test_retriever_empty_query_returns_safe_response():
    """Verify empty query returns empty RetrievalResult without crashing."""
    res = schema_retriever.retrieve("")
    assert res.total_hits == 0
    assert len(res.retrieved_documents) == 0


# ==============================================================================
# 6. Schema API Endpoint Tests (FastAPI)
# ==============================================================================

@pytest.fixture
def client():
    return TestClient(app)


def test_schema_health_endpoint(client):
    """Verify GET /api/v1/schema/health returns 200 with vector store status."""
    resp = client.get("/api/v1/schema/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["document_count"] == 269
    assert data["collection_name"] == settings.CHROMA_COLLECTION_NAME
    assert data["schema_version"] == "2"


def test_schema_search_endpoint_success(client):
    """Verify POST /api/v1/schema/search returns 200 with relevant schema data."""
    payload = {
        "query": "Find credit cards expiring this month",
        "top_k": 3
    }
    resp = client.post("/api/v1/schema/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "cards" in data["relevant_collections"]
    assert len(data["retrieved_documents"]) <= 3


def test_schema_search_rejects_empty_query(client):
    """Verify POST /api/v1/schema/search rejects whitespace query with 422."""
    resp = client.post("/api/v1/schema/search", json={"query": "    "})
    assert resp.status_code == 422


def test_schema_index_endpoint_idempotent(client):
    """Verify POST /api/v1/schema/index returns 200 and skips if up-to-date."""
    resp = client.post("/api/v1/schema/index", json={"force": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["skipped_reindex"] is True


# ==============================================================================
# 7. Benchmark Retrieval Evaluation Test
# ==============================================================================

def test_benchmark_retrieval_evaluation():
    """Verify benchmark evaluation achieves expected accuracy across SAMPLE_QUERIES.md."""
    eval_result = evaluation_runner.run_evaluation()
    metrics = eval_result["metrics"]

    assert eval_result["total_test_cases"] == 10
    assert metrics["collection_retrieval_hit_rate"] == 1.0
    assert metrics["recall_at_k"] >= 0.85
    assert metrics["relationship_discovery_rate"] == 1.0
    assert metrics["unsupported_concept_shield_rate"] == 1.0
    assert metrics["mean_reciprocal_rank_mrr"] >= 0.70
