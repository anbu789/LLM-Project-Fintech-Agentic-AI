"""
FinTech Agent — Pre-Phase 4 Remediation & Security Hardening Test Suite
Verifies:
1. Complete read-only protection across all database and collection access paths:
   - db["customers"]
   - db.customers
   - db.get_collection("customers")
   - col.database (ensuring no leakage of unwrapped write-capable objects)
2. Blocking of all collection mutations and administrative database commands ($out, $merge, dropDatabase, etc.).
3. Comprehensive secret redaction (Google AIza, Mongo URI passwords, Bearer tokens, URL query keys).
4. Safe API error sanitization without raw exception or path leakage.
5. Conversation ID validation (rejection of CRLF, spaces, oversized IDs, unicode controls).
6. HTTP Request Body size limit enforcement (HTTP 413 on oversized payloads).
7. In-memory IP rate limiting (HTTP 429 on abuse).
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.core.exceptions import DatabaseWriteProhibitedError
from backend.app.core.logging import sanitize_error_message
from backend.app.core.rate_limit import InMemoryRateLimiter, chat_rate_limiter
from backend.app.db.mongo_client import (
    ReadOnlyCollectionProxy,
    ReadOnlyDatabaseProxy,
    mongo_manager,
)
from backend.app.main import app

client = TestClient(app)


# ==============================================================================
# 1. Database Access Path Read-Only Protection Tests
# ==============================================================================

def test_all_collection_access_paths_return_readonly_proxy():
    """Verify that item access, attribute access, and get_collection() all return ReadOnlyCollectionProxy."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)
    assert isinstance(db, ReadOnlyDatabaseProxy)

    # 1. Item access: db["customers"]
    col_item = db["customers"]
    assert isinstance(col_item, ReadOnlyCollectionProxy)

    # 2. Attribute access: db.customers
    col_attr = db.customers
    assert isinstance(col_attr, ReadOnlyCollectionProxy)

    # 3. Method access: db.get_collection("customers")
    col_method = db.get_collection("customers")
    assert isinstance(col_method, ReadOnlyCollectionProxy)

    # 4. Property access: col.database returns ReadOnlyDatabaseProxy, never raw Database
    assert isinstance(col_item.database, ReadOnlyDatabaseProxy)
    assert isinstance(col_attr.database, ReadOnlyDatabaseProxy)


def test_mutation_blocked_on_all_access_paths():
    """Verify write operations fail with DatabaseWriteProhibitedError regardless of access path."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)

    # 1. Item access write
    with pytest.raises(DatabaseWriteProhibitedError):
        db["customers"].insert_one({"name": "Attacker"})

    # 2. Attribute access write (The audit-identified bypass)
    with pytest.raises(DatabaseWriteProhibitedError):
        db.customers.insert_one({"name": "Attacker"})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.customers.delete_many({})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.accounts.update_one({"account_id": "ACC000001"}, {"$set": {"balance": 999999}})

    # 3. get_collection access write (The audit-identified bypass)
    with pytest.raises(DatabaseWriteProhibitedError):
        db.get_collection("customers").insert_one({"name": "Attacker"})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.get_collection("customers").delete_many({})

    # 4. col.database navigation write
    with pytest.raises(DatabaseWriteProhibitedError):
        db.customers.database.drop_collection("customers")


def test_comprehensive_collection_mutation_api_blocking():
    """Verify every PyMongo mutation API is blocked on ReadOnlyCollectionProxy."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)
    col = db.loans

    mutation_calls = [
        lambda: col.insert_one({"loan_id": "TEST"}),
        lambda: col.insert_many([{"loan_id": "TEST"}]),
        lambda: col.update_one({"loan_id": "LN00001"}, {"$set": {"status": "closed"}}),
        lambda: col.update_many({}, {"$set": {"status": "defaulted"}}),
        lambda: col.replace_one({"loan_id": "LN00001"}, {"loan_id": "LN00001"}),
        lambda: col.delete_one({"loan_id": "LN00001"}),
        lambda: col.delete_many({}),
        lambda: col.find_one_and_delete({"loan_id": "LN00001"}),
        lambda: col.find_one_and_replace({"loan_id": "LN00001"}, {"loan_id": "LN00001"}),
        lambda: col.find_one_and_update({"loan_id": "LN00001"}, {"$set": {"status": "closed"}}),
        lambda: col.drop(),
        lambda: col.rename("loans_renamed"),
        lambda: col.create_index([("loan_id", 1)]),
        lambda: col.create_indexes([]),
        lambda: col.drop_index("loan_id_1"),
        lambda: col.drop_indexes(),
        lambda: col.bulk_write([]),
        lambda: col.reindex(),
        lambda: col.create_search_index({"name": "idx"}),
        lambda: col.drop_search_index("idx"),
    ]

    for call in mutation_calls:
        with pytest.raises(DatabaseWriteProhibitedError):
            call()


def test_aggregation_mutating_stages_blocked():
    """Verify aggregation stages $out and $merge are intercepted and blocked on all access paths."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)

    with pytest.raises(DatabaseWriteProhibitedError) as exc_info:
        db.transactions.aggregate([{"$match": {}}, {"$out": "leaked_transactions"}])
    assert "$out" in str(exc_info.value)

    with pytest.raises(DatabaseWriteProhibitedError) as exc_info2:
        db.get_collection("customers").aggregate([{"$match": {}}, {"$merge": {"into": "target"}}])
    assert "$merge" in str(exc_info2.value)


def test_administrative_commands_blocked():
    """Verify that dangerous database commands are intercepted and blocked."""
    db = mongo_manager.get_banking_db(enforce_proxy=True)

    blocked_cmds = [
        "dropDatabase", "drop", "delete", "insert", "update",
        "createIndexes", "collMod", "renameCollection", "applyOps", "reIndex"
    ]

    for cmd in blocked_cmds:
        with pytest.raises(DatabaseWriteProhibitedError):
            db.command(cmd)

        with pytest.raises(DatabaseWriteProhibitedError):
            db.command({cmd: "target"})


# ==============================================================================
# 2. Secret Redaction Tests
# ==============================================================================

def test_secret_redaction_comprehensive():
    """Verify all sensitive credential formats are redacted from error strings and logs."""
    test_cases = [
        ("AIzaSyA1234567890abcdef12345678901234567", "AIzaSy"),
        ("https://example.com/api?key=SECRET_VALUE_12345", "SECRET_VALUE_12345"),
        ("mongodb://admin:SuperSecret123@localhost:27017/fintech_agent_db", "SuperSecret123"),
        ("mongodb+srv://admin:SuperSecret456@example.mongodb.net/fintech_agent_db", "SuperSecret456"),
        ("Authorization: Bearer SECRET_TOKEN_VALUE_ABC", "SECRET_TOKEN_VALUE_ABC"),
        ("api_key=SECRET_API_KEY_VALUE_XYZ", "SECRET_API_KEY_VALUE_XYZ"),
        ("password=SECRET_PASSWORD_VALUE_999", "SECRET_PASSWORD_VALUE_999"),
        ("sk-ant-api03-abcdef1234567890abcdef123456", "sk-ant-"),
        ("gsk_abcdef1234567890abcdef", "gsk_"),
    ]

    for raw, secret_sub in test_cases:
        sanitized = sanitize_error_message(raw)
        assert secret_sub not in sanitized, f"Secret '{secret_sub}' was leaked in '{sanitized}'"
        assert "[REDACTED]" in sanitized


# ==============================================================================
# 3. Conversation ID Validation & Log Injection Tests
# ==============================================================================

def test_conversation_id_validation(monkeypatch):
    """Verify conversation_id rejects CRLF injection, oversized inputs, and whitespace."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    # CRLF injection attempt
    resp_crlf = client.post("/api/v1/chat", json={
        "message": "Hello",
        "conversation_id": "conv-123\r\n[CRITICAL] Admin granted"
    })
    assert resp_crlf.status_code == 422
    assert "CRLF" in resp_crlf.text or "validation" in resp_crlf.text.lower()

    # Oversized ID attempt (> 64 chars)
    resp_oversized = client.post("/api/v1/chat", json={
        "message": "Hello",
        "conversation_id": "C" * 65
    })
    assert resp_oversized.status_code == 422

    # Malformed characters attempt
    resp_invalid = client.post("/api/v1/chat", json={
        "message": "Hello",
        "conversation_id": "conv; DROP TABLE; --"
    })
    assert resp_invalid.status_code == 422

    # Valid ID succeeds
    resp_valid = client.post("/api/v1/chat", json={
        "message": "What is an NPA?",
        "conversation_id": "conv-valid-test_123"
    })
    assert resp_valid.status_code == 200
    assert resp_valid.json()["conversation_id"] == "conv-valid-test_123"


# ==============================================================================
# 4. HTTP Request-Size Limit Tests
# ==============================================================================

def test_request_body_size_limits(monkeypatch):
    """Verify RequestBodyLimitMiddleware rejects payloads exceeding configured max_body_bytes."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    # Test normal request succeeds
    normal_resp = client.post("/api/v1/chat", json={"message": "What is KYC?"})
    assert normal_resp.status_code == 200

    # Test oversized payload (> 1MB) returns 413 Payload Too Large
    oversized_data = "x" * 1_100_000
    oversized_resp = client.post(
        "/api/v1/chat",
        content=oversized_data,
        headers={"Content-Type": "application/json"}
    )
    assert oversized_resp.status_code == 413
    assert "exceeds maximum allowed limit" in oversized_resp.json()["message"]


# ==============================================================================
# 5. Rate Limiting Tests
# ==============================================================================

def test_rate_limiter_in_memory():
    """Verify InMemoryRateLimiter triggers HTTP 429 when threshold is exceeded."""
    limiter = InMemoryRateLimiter(requests_per_minute=3)
    test_ip = "192.168.1.100"

    assert limiter.is_allowed(test_ip) is True
    assert limiter.is_allowed(test_ip) is True
    assert limiter.is_allowed(test_ip) is True
    # 4th request must be rejected
    assert limiter.is_allowed(test_ip) is False

    limiter.reset()
    assert limiter.is_allowed(test_ip) is True


# ==============================================================================
# 6. Milestone B: Schema Catalog & RAG Verification Tests
# ==============================================================================

def test_glossary_fields_match_schema_json():
    """Verify all mapped fields in glossary exist in schema.json and hallucinated fields are fixed."""
    from backend.app.schema.glossary_mapper import (
        CANONICAL_GLOSSARY,
        validate_glossary_against_schema,
    )

    # 1. Structural validation
    discrepancies = validate_glossary_against_schema()
    assert len(discrepancies) == 0, f"Glossary discrepancies found: {discrepancies}"

    # 2. Verify specific hallucinated fields were corrected
    all_mapped_fields = {
        field_ref
        for item in CANONICAL_GLOSSARY
        for field_ref in item.get("mapped_fields", [])
    }

    assert "kyc_documents.document_type" in all_mapped_fields
    assert "kyc_documents.doc_type" not in all_mapped_fields

    assert "fraud_alerts.risk_score" in all_mapped_fields
    assert "fraud_alerts.severity" not in all_mapped_fields

    assert "merchants.category" in all_mapped_fields
    assert "merchants.merchant_category" not in all_mapped_fields


def test_chromadb_cosine_space_and_similarity():
    """Verify ChromaDB collection uses cosine space and computes similarity in [0, 1]."""
    from backend.app.rag.chroma_store import chroma_store

    col = chroma_store.get_collection()
    # ChromaDB stores hnsw space in configuration['hnsw']['space']
    space = None
    if hasattr(col, "configuration") and col.configuration:
        space = col.configuration.get("hnsw", {}).get("space")
    if not space and col.metadata:
        space = col.metadata.get("hnsw:space")
    assert space == "cosine"

    # Query with mock vector
    mock_vec = [0.05] * settings.EMBEDDING_DIMENSION
    hits = chroma_store.query(mock_vec, top_k=3)
    assert len(hits) > 0
    for hit in hits:
        assert 0.0 <= hit["similarity"] <= 1.0
        assert hit["distance"] is not None


def test_retriever_ranking_preserves_vector_similarity():
    """Verify retriever orders collections by relevance instead of alphabetical sorting."""
    from backend.app.rag.retriever import schema_retriever

    res = schema_retriever.retrieve("Show debit cards and credit cards with PIN set")
    # 'cards' should be the highest-relevance collection
    assert len(res.relevant_collections) > 0
    assert res.relevant_collections[0] == "cards"
    assert res.status == "ready"


def test_unsupported_loan_concepts_shielding():
    """Verify conservative mapping detects banking synonyms for missing loan fields without false positives."""
    from backend.app.rag.retriever import schema_retriever

    # 1. Overdue loans
    res_overdue = schema_retriever.retrieve("Find overdue loans with overdue amount")
    overdue_flags = {w["concept"] for w in res_overdue.unsupported_concepts}
    assert "overdue_amount" in overdue_flags

    # 2. Delinquent borrowers & arrears
    res_delinquent = schema_retriever.retrieve("Show delinquent borrowers with loans in arrears")
    delinq_flags = {w["concept"] for w in res_delinquent.unsupported_concepts}
    assert "delinquent_loans" in delinq_flags
    assert "loan_arrears" in delinq_flags

    # 3. NPA & DPD
    res_npa = schema_retriever.retrieve("Show NPA loans with DPD greater than 90")
    npa_flags = {w["concept"] for w in res_npa.unsupported_concepts}
    assert "npa" in npa_flags
    assert "days_past_due" in npa_flags

    # 4. Safe control query: MUST NOT trigger any warning
    res_safe = schema_retriever.retrieve("Show customers with outstanding loans")
    assert len(res_safe.unsupported_concepts) == 0


def test_retrieval_empty_query_status():
    """Verify empty or whitespace query returns status='no_hits' and 0 documents."""
    from backend.app.rag.retriever import schema_retriever

    res = schema_retriever.retrieve("   ")
    assert res.status == "no_hits"
    assert res.total_hits == 0
    assert len(res.retrieved_documents) == 0


def test_rag_benchmark_evaluation_metrics():
    """Verify 18 benchmark test cases run and meet quality thresholds."""
    from backend.app.rag.evaluation import (
        EXTENDED_BENCHMARK_TEST_CASES,
        evaluation_runner,
    )

    report = evaluation_runner.run_evaluation(test_cases=EXTENDED_BENCHMARK_TEST_CASES, top_k=5)
    assert report["total_test_cases"] >= 18
    metrics = report["metrics"]
    assert metrics["collection_retrieval_hit_rate"] >= 0.95
    assert metrics["unsupported_concept_shield_rate"] == 1.0
    assert metrics["mean_reciprocal_rank_mrr"] > 0.8


def test_embedding_provider_error_handling():
    """Verify real provider abstraction raises appropriate exceptions when misconfigured."""
    from backend.app.core.exceptions import MissingAPIKeyError, ProviderConfigurationError
    from backend.app.embeddings.openai_provider import OpenAICompatibleEmbeddingProvider
    from backend.app.embeddings.provider_factory import get_embedding_provider

    # Missing API key
    provider = OpenAICompatibleEmbeddingProvider(api_key="")
    with pytest.raises(MissingAPIKeyError):
        provider.embed_text("test")

    # Invalid provider type
    with pytest.raises(ProviderConfigurationError):
        get_embedding_provider(provider_type="unsupported_provider_xyz")


# ==============================================================================
# 7. Milestone C: LLM Conversation Handling & Persistence Tests
# ==============================================================================

def test_multi_turn_conversation_persistence_and_routes(monkeypatch):
    """Verify chat endpoint stores multi-turn conversation in agent_metadata_db and exposes CRUD routes."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    test_conv_id = "conv-test-remediation-turn-1"

    # Turn 1
    resp1 = client.post("/api/v1/chat", json={
        "message": "What is KYC?",
        "conversation_id": test_conv_id
    })
    assert resp1.status_code == 200
    assert resp1.json()["conversation_id"] == test_conv_id

    # Turn 2 (Follow-up)
    resp2 = client.post("/api/v1/chat", json={
        "message": "Can you explain more about that?",
        "conversation_id": test_conv_id
    })
    assert resp2.status_code == 200

    # Retrieve conversation detail
    detail_resp = client.get(f"/api/v1/chat/conversations/{test_conv_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["conversation_id"] == test_conv_id
    # Should have 4 messages (2 user + 2 assistant)
    assert len(detail["messages"]) == 4
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][1]["role"] == "assistant"
    assert detail["messages"][2]["role"] == "user"
    assert detail["messages"][3]["role"] == "assistant"

    # List conversations
    list_resp = client.get("/api/v1/chat/conversations")
    assert list_resp.status_code == 200
    conv_ids = [c["conversation_id"] for c in list_resp.json()]
    assert test_conv_id in conv_ids

    # Delete conversation
    del_resp = client.delete(f"/api/v1/chat/conversations/{test_conv_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Confirm 404 after deletion
    detail_after = client.get(f"/api/v1/chat/conversations/{test_conv_id}")
    assert detail_after.status_code == 404


def test_fail_fast_production_configuration(monkeypatch):
    """Verify production environment rejects mock provider or empty LLM configuration."""
    from backend.app.core.exceptions import ProviderConfigurationError
    from backend.app.services.llm_service import llm_service

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    with pytest.raises(ProviderConfigurationError) as exc_info:
        llm_service.get_provider()
    assert "prohibited in production" in str(exc_info.value)


@pytest.mark.asyncio
async def test_anthropic_multiple_content_blocks_handling(monkeypatch):
    """Verify Anthropic provider correctly extracts text block from thinking or mixed blocks."""
    from backend.app.services.llm_service import AnthropicProvider

    provider = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="dummy_key")

    mock_response_data = {
        "content": [
            {"type": "thinking", "thinking": "Internal reasoning step..."},
            {"type": "text", "text": "Extracted banking explanation."}
        ]
    }

    import httpx
    class MockAsyncResponse:
        status_code = 200
        def json(self):
            return mock_response_data

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return MockAsyncResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    text = await provider.generate_response("Explain NPA")
    assert text == "Extracted banking explanation."


@pytest.mark.asyncio
async def test_openai_refusal_and_safety_filter(monkeypatch):
    """Verify OpenAI adapter handles safety filter finish_reason and refusals safely."""
    from backend.app.core.exceptions import ProviderAPIError
    from backend.app.services.llm_service import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(model="gpt-4o", api_key="dummy_key")

    import httpx

    # 1. Content filter response
    class MockContentFilterResponse:
        status_code = 200
        def json(self):
            return {
                "choices": [{
                    "finish_reason": "content_filter",
                    "message": {"role": "assistant", "content": None}
                }]
            }

    class MockClientContentFilter:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return MockContentFilterResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClientContentFilter)
    with pytest.raises(ProviderAPIError) as exc:
        await provider.generate_response("Unsafe prompt")
    assert "safety controls" in str(exc.value)

    # 2. Refusal in message
    class MockRefusalResponse:
        status_code = 200
        def json(self):
            return {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": None, "refusal": "I cannot fulfill this financial advice request."}
                }]
            }

    class MockClientRefusal:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return MockRefusalResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClientRefusal)
    res = await provider.generate_response("Question")
    assert "[Refusal]:" in res


