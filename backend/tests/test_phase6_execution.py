"""
FinTech Agent — Phase 6 Execution & Verification Test Suite
Comprehensive testing for Part A (Gemini retries, MQL sort/limit, nested lookup constraints)
and Part B (Node 6 query executor, fail-closed gate, Node 7 result verifier, LangGraph integration).

Guarantees:
  - ZERO live queries to fintech_agent_db.
  - Fail-closed gate verification.
  - 15 deterministic mocked-transport scenarios for Gemini.
"""

from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from bson import Decimal128
import httpx
import pytest
from pymongo.errors import ConnectionFailure, ExecutionTimeout, OperationFailure

from backend.app.agent.graph import agent_graph, build_agent_graph
from backend.app.agent.nodes.mql_policy_validator import MQLPolicyValidator
from backend.app.agent.nodes.query_executor import query_executor_node
from backend.app.agent.nodes.response_composer import response_composer_node
from backend.app.agent.nodes.result_verifier import result_verifier_node
from backend.app.config import settings
from backend.app.core.exceptions import (
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from backend.app.services.llm_service import OpenAICompatibleProvider


# ==============================================================================
# PART A.1: GEMINI RETRY VERIFICATION (15 MOCKED-TRANSPORT SCENARIOS)
# ==============================================================================

@pytest.fixture(autouse=True)
def ensure_mock_provider_for_graph_tests():
    orig = settings.LLM_PROVIDER
    settings.LLM_PROVIDER = "mock"
    yield
    settings.LLM_PROVIDER = orig


class MockHttpxResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = "", headers: Dict[str, str] = None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or json.dumps(self._json_data)
        self.headers = headers or {}

    def json(self):
        return self._json_data


@pytest.fixture
def gemini_provider():
    return OpenAICompatibleProvider(
        provider_name="gemini",
        api_key="test_api_key_valid",
        model="gemini-3.8-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
    )


@pytest.mark.asyncio
async def test_scenario_01_200_ok_immediate_success(gemini_provider):
    """Scenario 1: 200 OK returns immediate success on first attempt."""
    mock_resp = MockHttpxResponse(
        200,
        json_data={"choices": [{"message": {"content": "Hello banking world"}}]}
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        res = await gemini_provider.generate_response("Hi")
        assert res == "Hello banking world"
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_scenario_02_401_unauthorized_fails_fast(gemini_provider):
    """Scenario 2: 401 Unauthorized fails fast without retrying."""
    mock_resp = MockHttpxResponse(401, text="Invalid API key")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderAuthenticationError):
            await gemini_provider.generate_response("Hi")
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_scenario_03_403_forbidden_fails_fast(gemini_provider):
    """Scenario 3: 403 Forbidden fails fast without retrying."""
    mock_resp = MockHttpxResponse(403, text="Permission denied for project")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderAuthenticationError):
            await gemini_provider.generate_response("Hi")
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_scenario_04_400_bad_request_fails_fast(gemini_provider):
    """Scenario 4: 400 Bad Request fails fast without retrying."""
    mock_resp = MockHttpxResponse(400, text="Invalid parameters")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderAPIError) as exc_info:
            await gemini_provider.generate_response("Hi")
        assert exc_info.value.status_code == 400
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_scenario_05_404_not_found_fails_fast(gemini_provider):
    """Scenario 5: 404 Not Found fails fast without retrying."""
    mock_resp = MockHttpxResponse(404, text="Model not found")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderAPIError) as exc_info:
            await gemini_provider.generate_response("Hi")
        assert exc_info.value.status_code == 404
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_scenario_06_429_quota_exhausted_fails_fast(gemini_provider):
    """Scenario 6: 429 Quota Exhausted fails fast without retrying."""
    mock_resp = MockHttpxResponse(429, text="Resource has been exhausted: insufficient_quota")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderRateLimitError) as exc_info:
            await gemini_provider.generate_response("Hi")
        assert "Quota exhausted" in str(exc_info.value)
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_scenario_07_429_transient_recovered_on_attempt_2(gemini_provider):
    """Scenario 7: Transient 429 rate limit recovers on attempt 2."""
    resp_429 = MockHttpxResponse(429, text="Too many requests - transient spike")
    resp_200 = MockHttpxResponse(200, json_data={"choices": [{"message": {"content": "Recovered response"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_post.side_effect = [resp_429, resp_200]
        res = await gemini_provider.generate_response("Hi")
        assert res == "Recovered response"
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_scenario_08_429_transient_exhausted_after_3_attempts(gemini_provider):
    """Scenario 8: Transient 429 exhausted after 3 attempts raises ProviderRateLimitError."""
    resp_429 = MockHttpxResponse(429, text="Rate limit persistent")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [resp_429, resp_429, resp_429]
        with pytest.raises(ProviderRateLimitError):
            await gemini_provider.generate_response("Hi")
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_scenario_09_429_retry_after_header_bounded(gemini_provider):
    """Scenario 9: 429 with Retry-After header parses and bounds wait to <= 4.0s."""
    resp_429 = MockHttpxResponse(429, text="Rate limit", headers={"retry-after": "10"})
    resp_200 = MockHttpxResponse(200, json_data={"choices": [{"message": {"content": "Success"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_post.side_effect = [resp_429, resp_200]
        res = await gemini_provider.generate_response("Hi")
        assert res == "Success"
        assert mock_sleep.call_count == 1
        # Bounded sleep argument must be <= 4.0s
        sleep_duration = mock_sleep.call_args[0][0]
        assert sleep_duration <= 4.0


@pytest.mark.asyncio
async def test_scenario_10_500_internal_error_recovered_on_attempt_2(gemini_provider):
    """Scenario 10: 500 Internal Server Error recovered on attempt 2."""
    resp_500 = MockHttpxResponse(500, text="Internal server error")
    resp_200 = MockHttpxResponse(200, json_data={"choices": [{"message": {"content": "500 recovered"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [resp_500, resp_200]
        res = await gemini_provider.generate_response("Hi")
        assert res == "500 recovered"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_scenario_11_500_exhausted_raises_api_error(gemini_provider):
    """Scenario 11: 500 error exhausted after 3 attempts raises ProviderAPIError with status 500."""
    resp_500 = MockHttpxResponse(500, text="Server crashed")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [resp_500, resp_500, resp_500]
        with pytest.raises(ProviderAPIError) as exc_info:
            await gemini_provider.generate_response("Hi")
        assert exc_info.value.status_code == 500
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_scenario_12_503_service_unavailable_recovered_on_attempt_3(gemini_provider):
    """Scenario 12: 503 Service Unavailable recovered on attempt 3."""
    resp_503 = MockHttpxResponse(503, text="Service temporarily unavailable")
    resp_200 = MockHttpxResponse(200, json_data={"choices": [{"message": {"content": "503 recovered"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [resp_503, resp_503, resp_200]
        res = await gemini_provider.generate_response("Hi")
        assert res == "503 recovered"
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_scenario_13_timeout_recovered_on_attempt_2(gemini_provider):
    """Scenario 13: httpx.TimeoutException recovered on attempt 2."""
    resp_200 = MockHttpxResponse(200, json_data={"choices": [{"message": {"content": "Timeout recovered"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [httpx.ReadTimeout("Timeout"), resp_200]
        res = await gemini_provider.generate_response("Hi")
        assert res == "Timeout recovered"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_scenario_14_timeout_exhausted_raises_provider_timeout_error(gemini_provider):
    """Scenario 14: httpx.TimeoutException exhausted raises ProviderTimeoutError."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [httpx.ReadTimeout("T1"), httpx.ReadTimeout("T2"), httpx.ReadTimeout("T3")]
        with pytest.raises(ProviderTimeoutError):
            await gemini_provider.generate_response("Hi")
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_scenario_15_network_request_error_exhausted(gemini_provider):
    """Scenario 15: httpx.ConnectError exhausted raises ProviderAPIError."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.ConnectError("Connection reset"),
            httpx.ConnectError("Host unreachable"),
        ]
        with pytest.raises(ProviderAPIError) as exc_info:
            await gemini_provider.generate_response("Hi")
        assert "Network connection error" in str(exc_info.value)
        assert mock_post.call_count == 3


# ==============================================================================
# PART A.2: MQL SORT AND LIMIT SEMANTICS & BOUNDS
# ==============================================================================

def test_mql_sort_before_limit_is_valid():
    """Verify $sort preceding $limit is valid for top-N ranking."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$sort": {"amount": -1}},
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("transactions", pipeline, require_terminal_limit=True)
    assert res.validation_status == "VALID"
    assert len(res.validation_errors) == 0


def test_mql_limit_before_sort_is_rejected():
    """Verify $limit preceding $sort is rejected as semantically invalid."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$limit": 10},
        {"$sort": {"amount": -1}},
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("transactions", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("precedes $sort" in err for err in res.validation_errors)


def test_mql_skip_before_sort_is_rejected():
    """Verify $skip preceding $sort is rejected as non-deterministic."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$skip": 5},
        {"$sort": {"amount": -1}},
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("transactions", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("precedes $sort" in err for err in res.validation_errors)


def test_mql_valid_pagination_sort_skip_limit():
    """Verify standard pagination order ($sort -> $skip -> $limit) is valid."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$sort": {"created_at": -1}},
        {"$skip": 20},
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("transactions", pipeline, require_terminal_limit=True)
    assert res.validation_status == "VALID"


def test_mql_hard_max_limit_enforcement():
    """Verify $limit exceeding RESULT_DOC_LIMIT (1,000) is rejected."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {"$limit": 1001},
    ]
    res = validator.validate_pipeline("accounts", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("exceeds maximum allowed result limit" in err for err in res.validation_errors)


def test_mql_row_query_requires_terminal_limit():
    """Verify non-scalar row query without terminal limit is rejected."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("Pipeline lacks an effective terminal $limit stage" in err for err in res.validation_errors)


# ==============================================================================
# PART A.3: NESTED $LOOKUP OUTPUT CONSTRAINTS & AGGREGATE SAFETY
# ==============================================================================

def test_mql_lookup_primary_key_inherently_bounded():
    """Verify lookup joining on confirmed unique foreignField (customers.customer_id) is valid without sub-pipeline."""
    validator = MQLPolicyValidator()
    # accounts joins customers on customer_id (confirmed unique index in customers)
    pipeline = [
        {"$match": {"account_type": "savings"}},
        {
            "$lookup": {
                "from": "customers",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "customer_info",
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("accounts", pipeline, require_terminal_limit=True)
    assert res.validation_status == "VALID"


def test_mql_lookup_domain_key_without_unique_index_requires_bound():
    """Verify lookup joining on non-unique domain foreignField (accounts.customer_id) requires inner limit."""
    validator = MQLPolicyValidator()
    # customers joins accounts on customer_id (customer_id is non-unique in accounts, 1:N)
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "accounts",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "customer_accounts",
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("non-primary/non-unique field" in err for err in res.validation_errors)


def test_mql_lookup_1_to_n_unbounded_is_rejected():
    """Verify 1:N lookup on non-primary foreign field without inner limit is rejected."""
    validator = MQLPolicyValidator()
    # customers joins transactions on foreignField="customer_id" (non-primary in transactions)
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "transactions",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "as": "customer_txs",
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("unbounded joined document volume is prohibited" in err for err in res.validation_errors)


def test_mql_lookup_1_to_n_bounded_with_inner_limit_is_valid():
    """Verify 1:N lookup with inner pipeline limit <= 100 is valid."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "transactions",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "pipeline": [{"$limit": 50}],
                "as": "recent_transactions",
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "VALID"


def test_mql_lookup_inner_limit_exceeding_max_is_rejected():
    """Verify 1:N lookup with inner pipeline limit > 100 is rejected."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "transactions",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "pipeline": [{"$limit": 150}],
                "as": "transactions_list",
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("exceeding maximum allowed limit of 100" in err for err in res.validation_errors)


def test_mql_downstream_aggregate_on_truncated_join_is_rejected():
    """Verify downstream $unwind + $group $sum on truncated 1:N join is rejected."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "transactions",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "pipeline": [{"$limit": 100}],
                "as": "tx_list",
            }
        },
        {"$unwind": "$tx_list"},
        {
            "$group": {
                "_id": "$customer_id",
                "calculated_sum": {"$sum": "$tx_list.amount"},
            }
        },
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=False)
    assert res.validation_status == "INVALID"
    assert any("Calculating financial aggregates over a truncated join" in err for err in res.validation_errors)


# ==============================================================================
# PART B.1: NODE 6 QUERY EXECUTOR PRECONDITIONS & EXECUTION GATE
# ==============================================================================

@pytest.mark.asyncio
async def test_node6_skips_when_guardrail_rejected():
    """Verify Node 6 skips execution when guardrail rejected request."""
    state = {
        "guardrail_status": "rejected",
        "final_status": "rejected",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {"status": "active"}}, {"$limit": 10}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "SKIPPED"
    assert res["raw_results"] is None


@pytest.mark.asyncio
async def test_node6_skips_when_pipeline_invalid():
    """Verify Node 6 skips execution when pipeline failed validation."""
    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {"bad_field": 1}}],
        "is_pipeline_valid": False,
        "validation_status": "INVALID",
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "VALIDATION_FAILED"
    assert res["raw_results"] is None


@pytest.mark.asyncio
async def test_node6_skips_when_unsupported_concepts():
    """Verify Node 6 skips execution when query has unsupported concepts."""
    state = {
        "guardrail_status": "allowed",
        "target_collection": "loans",
        "validation_status": "UNSUPPORTED",
        "is_pipeline_valid": False,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "UNSUPPORTED"
    assert res["raw_results"] is None


@pytest.mark.asyncio
async def test_node6_fail_closed_gate_when_live_execution_disabled():
    """Verify Node 6 fails closed when PHASE6_LIVE_EXECUTION_ENABLED is False (default)."""
    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {"status": "active"}}, {"$limit": 5}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
    }
    # Ensure live execution gate is closed
    with patch.object(settings, "PHASE6_LIVE_EXECUTION_ENABLED", False):
        res = await query_executor_node(state)
        assert res["execution_status"] == "GATE_BLOCKED"
        assert res["raw_results"] is None
        assert "Live database execution is gated" in res["execution_error"]


@pytest.mark.asyncio
async def test_node6_fail_closed_blocks_fintech_agent_db_even_if_passed_as_test_db():
    """Verify Node 6 strictly blocks executing against fintech_agent_db even if passed as test_db."""
    mock_db = MagicMock()
    mock_db.name = "fintech_agent_db"

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {"status": "active"}}, {"$limit": 5}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    with patch.object(settings, "PHASE6_LIVE_EXECUTION_ENABLED", False):
        res = await query_executor_node(state)
        assert res["execution_status"] == "GATE_BLOCKED"
        assert "Targeting database 'fintech_agent_db' is strictly prohibited" in res["execution_error"]
        assert mock_db.__getitem__.call_count == 0


# ==============================================================================
# PART B.2: CONTROLLED EXECUTION & ERROR SHIELDING
# ==============================================================================

@pytest.mark.asyncio
async def test_node6_executes_against_isolated_test_db():
    """Verify Node 6 executes read-only aggregation on isolated test db."""
    mock_col = MagicMock()
    mock_cursor = [{"customer_id": "CUST_001", "name": "Alice"}, {"customer_id": "CUST_002", "name": "Bob"}]
    mock_col.aggregate.return_value = iter(mock_cursor)

    mock_db = MagicMock()
    mock_db.name = "isolated_test_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {"status": "active"}}, {"$limit": 2}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "SUCCESS"
    assert len(res["raw_results"]) == 2
    assert res["result_row_count"] == 2
    assert res["execution_time_ms"] >= 0
    # Verify aggregate parameters
    mock_col.aggregate.assert_called_once_with(
        state["approved_pipeline"],
        maxTimeMS=settings.QUERY_TIMEOUT_MS,
        allowDiskUse=False,
    )


@pytest.mark.asyncio
async def test_node6_result_capping_truncation():
    """Verify Node 6 caps results and flags result_truncated when cursor exceeds doc limit."""
    doc_limit = 5
    fake_docs = [{"_id": i, "val": i} for i in range(doc_limit + 10)]

    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter(fake_docs)

    mock_db = MagicMock()
    mock_db.name = "isolated_test_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "transactions",
        "approved_pipeline": [{"$match": {"status": "completed"}}, {"$limit": doc_limit}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    with patch.object(settings, "RESULT_DOC_LIMIT", doc_limit):
        res = await query_executor_node(state)
        assert res["execution_status"] == "SUCCESS_LIMITED"
        assert len(res["raw_results"]) == doc_limit
        assert res["result_truncated"] is True


@pytest.mark.asyncio
async def test_node6_payload_size_bounding():
    """Verify Node 6 flags RESULT_OVERSIZED if payload exceeds MAX_RESULT_BYTES."""
    huge_doc = {"huge_field": "X" * 1000}
    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([huge_doc])

    mock_db = MagicMock()
    mock_db.name = "isolated_test_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 1}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    with patch.object(settings, "MAX_RESULT_BYTES", 500):  # low threshold for testing
        res = await query_executor_node(state)
        assert res["execution_status"] == "RESULT_OVERSIZED"
        assert res["raw_results"] is None
        assert "exceeded maximum allowed" in res["execution_error"]


@pytest.mark.asyncio
async def test_node6_timeout_error_shielding():
    """Verify Node 6 shields ExecutionTimeout cleanly."""
    mock_col = MagicMock()
    mock_col.aggregate.side_effect = ExecutionTimeout("operation exceeded time limit")

    mock_db = MagicMock()
    mock_db.name = "isolated_test_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "transactions",
        "approved_pipeline": [{"$match": {}}, {"$limit": 10}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "TIMEOUT"
    assert "Query execution timed out" in res["execution_error"]
    assert res["raw_results"] is None


@pytest.mark.asyncio
async def test_node6_auth_error_shielding():
    """Verify Node 6 shields authorization failure code 13 cleanly."""
    mock_col = MagicMock()
    mock_col.aggregate.side_effect = OperationFailure("not authorized on db to execute command", code=13)

    mock_db = MagicMock()
    mock_db.name = "isolated_test_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 10}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "AUTH_ERROR"
    assert "Database authorization error" in res["execution_error"]
    assert "mongodb://" not in res["execution_error"]


@pytest.mark.asyncio
async def test_node6_connection_error_shielding():
    """Verify Node 6 shields ConnectionFailure cleanly."""
    mock_col = MagicMock()
    mock_col.aggregate.side_effect = ConnectionFailure("connection dropped by peer")

    mock_db = MagicMock()
    mock_db.name = "isolated_test_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "loans",
        "approved_pipeline": [{"$match": {}}, {"$limit": 10}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "CONNECTION_ERROR"
    assert "Database connection error" in res["execution_error"]


# ==============================================================================
# PART B.3: NODE 7 RESULT VERIFIER & RECOVERY
# ==============================================================================

@pytest.mark.asyncio
async def test_node7_verifies_success_with_data():
    """Verify Node 7 handles SUCCESS with data correctly."""
    state = {
        "execution_status": "SUCCESS",
        "raw_results": [{"account_id": "ACC_001", "balance": 5000.0}],
        "execution_time_ms": 12,
        "target_collection": "accounts",
    }
    res = await result_verifier_node(state)
    assert res["verification_status"] == "SUCCESS_WITH_DATA"
    assert res["result_status"] == "VALID_WITH_DATA"
    assert res["result_row_count"] == 1
    assert "returned 1 records" in res["interpretation_summary"]


@pytest.mark.asyncio
async def test_node7_verifies_success_empty():
    """Verify Node 7 handles SUCCESS with 0 records correctly."""
    state = {
        "execution_status": "SUCCESS",
        "raw_results": [],
        "execution_time_ms": 5,
        "target_collection": "customers",
    }
    res = await result_verifier_node(state)
    assert res["verification_status"] == "SUCCESS_EMPTY"
    assert res["result_status"] == "VALID_EMPTY"
    assert res["result_row_count"] == 0
    assert "returned 0 matching records" in res["interpretation_summary"]


@pytest.mark.asyncio
async def test_node7_verifies_gate_blocked():
    """Verify Node 7 handles EXECUTION_GATE_BLOCKED correctly."""
    state = {
        "execution_status": "GATE_BLOCKED",
        "execution_error": "Live database execution is gated",
    }
    res = await result_verifier_node(state)
    assert res["verification_status"] == "EXECUTION_GATE_BLOCKED"
    assert res["result_status"] == "EXECUTION_GATE_BLOCKED"
    assert "Live database execution is currently gated" in res["interpretation_summary"]


@pytest.mark.asyncio
async def test_node7_bounded_recovery_tracks_attempts():
    """Verify Node 7 tracks retry attempts on connection error without modifying filters."""
    state = {
        "execution_status": "CONNECTION_ERROR",
        "execution_error": "Connection lost",
        "retry_count": 0,
        "all_attempts": [],
    }
    res = await result_verifier_node(state)
    assert res["verification_status"] == "CONNECTION_ERROR"
    assert res["result_status"] == "RETRYABLE_ERROR"
    assert len(res["all_attempts"]) == 1
    assert res["all_attempts"][0]["attempt"] == 1


# ==============================================================================
# PART B.4: LANGGRAPH PIPELINE INTEGRATION
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_graph_query_with_gate_blocked_by_default():
    """Verify full graph execution with default gate blocks DB execution and returns validated plan."""
    initial_state = {
        "request_id": "test_phase6_gated_01",
        "user_id": "auditor_user",
        "session_id": "session_601",
        "thread_id": "thread_601",
        "natural_language_query": "List active customers in Bangalore",
        "conversation_history": [],
        "retry_count": 0,
        "max_retries": 3,
        "all_attempts": [],
    }
    with patch.object(settings, "PHASE6_LIVE_EXECUTION_ENABLED", False):
        final_state = await agent_graph.ainvoke(initial_state)
        assert final_state["request_mode"] == "QUERY_ONLY"
        assert final_state["validation_status"] == "VALID"
        assert final_state["verification_status"] == "EXECUTION_GATE_BLOCKED"
        assert final_state["final_response"] is not None
        assert "execution has not occurred" in final_state["final_response"].lower()
        # Verify trace passes through Node 6 and Node 7
        node_names = [t.get("node") for t in final_state.get("trace", [])]
        assert "query_executor" in node_names
        assert "result_verifier" in node_names


@pytest.mark.asyncio
async def test_e2e_graph_controlled_execution_with_test_db():
    """Verify full graph execution with test_db executes and composes results response."""
    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([
        {"customer_id": "CUST_100", "city": "Bangalore", "status": "active"}
    ])
    mock_db = MagicMock()
    mock_db.name = "isolated_sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    initial_state = {
        "request_id": "test_phase6_exec_02",
        "user_id": "auditor_user",
        "session_id": "session_602",
        "thread_id": "thread_602",
        "natural_language_query": "List active customers in Bangalore",
        "conversation_history": [],
        "retry_count": 0,
        "max_retries": 3,
        "all_attempts": [],
        "test_db": mock_db,
    }
    final_state = await agent_graph.ainvoke(initial_state)
    assert final_state["request_mode"] == "QUERY_ONLY"
    assert final_state["validation_status"] == "VALID"
    assert final_state["verification_status"] == "SUCCESS_WITH_DATA"
    assert final_state["result_row_count"] == 1
    assert "Query Executed Successfully" in final_state["final_response"]
    assert "CUST_100" in final_state["final_response"]


@pytest.mark.asyncio
async def test_e2e_graph_unsupported_concept_bypasses_executor():
    """Verify overdue loans query is flagged unsupported and bypasses query execution."""
    initial_state = {
        "request_id": "test_phase6_unsupported_03",
        "user_id": "auditor_user",
        "session_id": "session_603",
        "thread_id": "thread_603",
        "natural_language_query": "Show overdue loans",
        "conversation_history": [],
        "retry_count": 0,
        "max_retries": 3,
        "all_attempts": [],
    }
    final_state = await agent_graph.ainvoke(initial_state)
    assert final_state["validation_status"] == "UNSUPPORTED"
    assert "[UNSUPPORTED]" in final_state["final_response"]
    node_names = [t.get("node") for t in final_state.get("trace", [])]
    assert "query_executor" not in node_names  # bypassed via conditional edge!


# ==============================================================================
# PART B.5: PHASE 6 FINAL HARDENING TESTS
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Exact Financial Precision (Decimal128 & String Preservation)
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_financial_precision_large_amounts_and_cents():
    """Verify Decimal128 conversion in Node 7 preserves exact Decimal without binary float rounding."""
    large_val_str = "1234567890123456.78"
    raw_doc = {
        "_id": "tx_prec_01",
        "amount": Decimal128(large_val_str),
        "fractional_fee": Decimal128("0.07"),
        "subtotal": Decimal128("19.99"),
        "whale_balance": Decimal128("1000000000000000.05"),
    }
    state = {
        "execution_status": "SUCCESS",
        "raw_results": [raw_doc],
        "result_row_count": 1,
        "result_truncated": False,
        "execution_time_ms": 5.0,
    }
    res = await result_verifier_node(state)
    assert res["verification_status"] == "SUCCESS_WITH_DATA"
    verified_doc = res["verified_results"][0]

    # Verify each value is an exact Decimal instance with exact string representation
    assert isinstance(verified_doc["amount"], Decimal)
    assert str(verified_doc["amount"]) == large_val_str
    # Crucial proof: IEEE 754 float loses cents for 1234567890123456.78
    assert float(large_val_str) == 1234567890123456.8  # float precision loss
    assert str(verified_doc["amount"]) != str(float(large_val_str))  # Decimal preserved precision!

    assert isinstance(verified_doc["fractional_fee"], Decimal)
    assert str(verified_doc["fractional_fee"]) == "0.07"

    assert isinstance(verified_doc["subtotal"], Decimal)
    assert str(verified_doc["subtotal"]) == "19.99"

    assert isinstance(verified_doc["whale_balance"], Decimal)
    assert str(verified_doc["whale_balance"]) == "1000000000000000.05"


@pytest.mark.asyncio
async def test_financial_precision_response_composer_json_rendering():
    """Verify Node 8 formats exact Decimal values without float serialization artifacts."""
    large_val_str = "1234567890123456.78"
    state = {
        "request_mode": "QUERY_ONLY",
        "verification_status": "SUCCESS_WITH_DATA",
        "target_collection": "transactions",
        "pipeline_explanation": "Precision test pipeline",
        "execution_time_ms": 12.5,
        "verified_results": [
            {
                "transaction_id": "TX_999",
                "amount": Decimal(large_val_str),
                "fee": Decimal("0.07"),
            }
        ],
    }
    res = await response_composer_node(state)
    response_text = res["graph_response"]
    assert "1234567890123456.78" in response_text
    assert "0.07" in response_text
    # Ensure float artifact like "0.070000000000000006" is NOT in response
    assert "0.070000000000000006" not in response_text


# ------------------------------------------------------------------------------
# 2. Incremental Byte Limit Enforcement & Boundary Conditions
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_incremental_byte_limit_exact_boundary():
    """Verify documents fitting up to exact byte boundary are admitted."""
    doc1 = {"_id": 1, "k": "a"}
    doc2 = {"_id": 2, "k": "b"}
    exact_bytes = len(json.dumps([doc1, doc2], default=str).encode("utf-8"))

    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([doc1, doc2])
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 10}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    with patch.object(settings, "MAX_RESULT_BYTES", exact_bytes):
        res = await query_executor_node(state)
        assert res["execution_status"] == "SUCCESS"
        assert len(res["raw_results"]) == 2
        assert res["result_byte_count"] == exact_bytes


@pytest.mark.asyncio
async def test_incremental_byte_limit_aborts_before_adding_excess_document():
    """Verify iteration aborts BEFORE adding a document that exceeds the remaining budget."""
    doc1 = {"_id": 1, "data": "X" * 100}
    doc2 = {"_id": 2, "data": "Y" * 100}
    doc1_bytes = len(json.dumps([doc1], default=str).encode("utf-8"))

    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([doc1, doc2])
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 10}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    # Cap budget to fit doc1 but NOT doc2
    with patch.object(settings, "MAX_RESULT_BYTES", doc1_bytes + 10):
        res = await query_executor_node(state)
        # MUST return RESULT_OVERSIZED and raw_results=None; NO partial results returned as complete!
        assert res["execution_status"] == "RESULT_OVERSIZED"
        assert res["raw_results"] is None
        assert res["result_row_count"] == 0
        assert "exceeded maximum allowed limit" in res["execution_error"]


@pytest.mark.asyncio
async def test_incremental_byte_limit_single_oversized_document():
    """Verify a single document exceeding 5MB cap is rejected immediately."""
    huge_doc = {"_id": 1, "blob": "Z" * 1000}
    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([huge_doc])
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 1}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    with patch.object(settings, "MAX_RESULT_BYTES", 500):
        res = await query_executor_node(state)
        assert res["execution_status"] == "RESULT_OVERSIZED"
        assert res["raw_results"] is None


@pytest.mark.asyncio
async def test_incremental_byte_limit_deeply_nested_document():
    """Verify deeply nested structures are evaluated accurately during iteration."""
    nested_doc = {"_id": 1, "level1": {"level2": {"level3": [{"a": 1}, {"b": 2}]}}}
    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([nested_doc])
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 1}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    with patch.object(settings, "MAX_RESULT_BYTES", 50):  # Too small for nested doc
        res = await query_executor_node(state)
        assert res["execution_status"] == "RESULT_OVERSIZED"
        assert res["raw_results"] is None


# ------------------------------------------------------------------------------
# 3. Honest Result-Limit Reporting & Capping Interpretation
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_result_limit_below_cap_returns_success():
    """Verify result set strictly under limit returns SUCCESS without truncation notice."""
    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([{"_id": i} for i in range(10)])
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "accounts",
        "approved_pipeline": [{"$match": {}}, {"$limit": 1000}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "SUCCESS"
    assert res["result_truncated"] is False
    assert len(res["raw_results"]) == 10

    # Pass to Node 7
    v_state = {**state, **res}
    v_res = await result_verifier_node(v_state)
    assert v_res["verification_status"] == "SUCCESS_WITH_DATA"
    assert v_res["result_status"] == "VALID_WITH_DATA"


@pytest.mark.asyncio
async def test_result_limit_exact_1000_flags_capped_and_honest_notice():
    """Verify exactly 1,000 documents triggers SUCCESS_LIMITED with honest unverified count note."""
    doc_limit = 1000
    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([{"_id": i} for i in range(doc_limit)])
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "transactions",
        "approved_pipeline": [{"$match": {}}, {"$limit": doc_limit}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "SUCCESS_LIMITED"
    assert res["result_truncated"] is True
    assert len(res["raw_results"]) == 1000

    # Pass to Node 7
    v_state = {**state, **res}
    v_res = await result_verifier_node(v_state)
    assert v_res["verification_status"] == "SUCCESS_LIMITED"
    assert "total matching record count" in v_res["interpretation_summary"].lower()
    assert "unverified" in v_res["interpretation_summary"].lower()
    assert "exceeds" not in v_res["interpretation_summary"]  # does not invent an unproven number!


@pytest.mark.asyncio
async def test_result_limit_cursor_overrun_flags_capped():
    """Verify cursor offering 1001 documents is strictly capped to 1000 with SUCCESS_LIMITED."""
    doc_limit = 1000
    mock_col = MagicMock()
    mock_col.aggregate.return_value = iter([{"_id": i} for i in range(doc_limit + 5)])
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    state = {
        "guardrail_status": "allowed",
        "target_collection": "transactions",
        "approved_pipeline": [{"$match": {}}, {"$limit": doc_limit}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "SUCCESS_LIMITED"
    assert res["result_truncated"] is True
    assert len(res["raw_results"]) == 1000


# ------------------------------------------------------------------------------
# 4. Downstream Lookup Safety & Expression Auditing
# ------------------------------------------------------------------------------

def test_downstream_lookup_rejection_size_operator():
    """Verify $size over a bounded joined array in $project is strictly rejected."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "transactions",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "pipeline": [{"$limit": 50}],
                "as": "recent_txs",
            }
        },
        {
            "$project": {
                "customer_id": 1,
                "tx_count": {"$size": "$recent_txs"},
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("aggregated using ['$size']" in err for err in res.validation_errors)
    assert any("truncated join produces incomplete and mathematically incorrect results" in err for err in res.validation_errors)


def test_downstream_lookup_rejection_sum_operator():
    """Verify $sum over a bounded joined array in $project is strictly rejected."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "transactions",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "pipeline": [{"$limit": 50}],
                "as": "recent_txs",
            }
        },
        {
            "$project": {
                "customer_id": 1,
                "total_spend": {"$sum": "$recent_txs.amount"},
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("aggregated using ['$sum']" in err for err in res.validation_errors)


def test_downstream_lookup_rejection_reduce_operator():
    """Verify $reduce over a bounded joined array in $addFields is strictly rejected."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {
            "$lookup": {
                "from": "transactions",
                "localField": "customer_id",
                "foreignField": "customer_id",
                "pipeline": [{"$limit": 50}],
                "as": "recent_txs",
            }
        },
        {
            "$addFields": {
                "reduced_amount": {
                    "$reduce": {
                        "input": "$recent_txs",
                        "initialValue": 0,
                        "in": {"$add": ["$$value", "$$this.amount"]},
                    }
                }
            }
        },
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("aggregated using ['$reduce']" in err for err in res.validation_errors)


# ------------------------------------------------------------------------------
# 5. Actual Bounded Recovery Loop via LangGraph Edge
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_graph_bounded_recovery_retries_and_recovers():
    """Verify graph routes back to query_executor on transient error and succeeds on retry."""
    call_count = 0
    def mock_aggregate(pipeline, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionFailure("Temporary network disconnect")
        return iter([{"customer_id": "CUST_RECOVERED", "city": "Mumbai", "status": "active"}])

    mock_col = MagicMock()
    mock_col.aggregate.side_effect = mock_aggregate
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    initial_state = {
        "request_id": "test_phase6_recovery_01",
        "user_id": "auditor_user",
        "session_id": "session_605",
        "thread_id": "thread_605",
        "natural_language_query": "List active customers in Mumbai",
        "conversation_history": [],
        "retry_count": 0,
        "max_retries": 3,
        "all_attempts": [],
        "test_db": mock_db,
    }
    final_state = await agent_graph.ainvoke(initial_state)
    assert call_count == 2
    assert final_state["retry_count"] == 1
    assert final_state["verification_status"] == "SUCCESS_WITH_DATA"
    assert len(final_state["all_attempts"]) == 1  # 1 failure recorded before success
    assert final_state["all_attempts"][0]["status"] == "CONNECTION_ERROR"
    assert "CUST_RECOVERED" in final_state["final_response"]


@pytest.mark.asyncio
async def test_e2e_graph_bounded_recovery_exhausted_terminates():
    """Verify graph bounds retry attempts at max_retries and terminates cleanly without looping."""
    call_count = 0
    def mock_aggregate(pipeline, **kwargs):
        nonlocal call_count
        call_count += 1
        raise ExecutionTimeout("Query exceeded maxTimeMS")

    mock_col = MagicMock()
    mock_col.aggregate.side_effect = mock_aggregate
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    initial_state = {
        "request_id": "test_phase6_recovery_02",
        "user_id": "auditor_user",
        "session_id": "session_606",
        "thread_id": "thread_606",
        "natural_language_query": "List active customers in Mumbai",
        "conversation_history": [],
        "retry_count": 0,
        "max_retries": 3,
        "all_attempts": [],
        "test_db": mock_db,
    }
    final_state = await agent_graph.ainvoke(initial_state)
    # Total attempts: 1 initial + 3 retries = 4 executions
    assert call_count == 4
    assert final_state["retry_count"] == 3
    assert final_state["verification_status"] == "TIMEOUT"
    assert len(final_state["all_attempts"]) == 4
    assert "Query Execution Failed" in final_state["final_response"]


@pytest.mark.asyncio
async def test_e2e_graph_auth_error_fails_fast_zero_retries():
    """Verify database authentication failure (code 13) does NOT retry and fails fast."""
    call_count = 0
    def mock_aggregate(pipeline, **kwargs):
        nonlocal call_count
        call_count += 1
        raise OperationFailure("Unauthorized", code=13)

    mock_col = MagicMock()
    mock_col.aggregate.side_effect = mock_aggregate
    mock_db = MagicMock()
    mock_db.name = "sandbox_db"
    mock_db.__getitem__.return_value = mock_col

    initial_state = {
        "request_id": "test_phase6_auth_fail_01",
        "user_id": "auditor_user",
        "session_id": "session_607",
        "thread_id": "thread_607",
        "natural_language_query": "List active customers in Mumbai",
        "conversation_history": [],
        "retry_count": 0,
        "max_retries": 3,
        "all_attempts": [],
        "test_db": mock_db,
    }
    final_state = await agent_graph.ainvoke(initial_state)
    assert call_count == 1  # Exactly 1 attempt! No retries for auth errors
    assert final_state["retry_count"] == 0
    assert final_state["verification_status"] == "AUTH_ERROR"
    assert "Query Execution Failed" in final_state["final_response"]


# ------------------------------------------------------------------------------
# 6. Multi-Factor Live Execution Gate & Untrusted Injection Defense
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_gate_blocked_when_mongo_auth_disabled():
    """Verify live execution is blocked when MONGO_AUTH_ENABLED=False even if live flag is True."""
    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 5}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
    }
    with patch.object(settings, "PHASE6_LIVE_EXECUTION_ENABLED", True), \
         patch.object(settings, "MONGO_AUTH_ENABLED", False):
        res = await query_executor_node(state)
        assert res["execution_status"] == "GATE_BLOCKED"
        assert "MONGO_AUTH_ENABLED" in res["execution_error"]


@pytest.mark.asyncio
async def test_security_gate_blocked_when_native_auth_unverified():
    """Verify live execution is blocked when native MongoDB auth is unverified."""
    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 5}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
    }
    with patch.object(settings, "PHASE6_LIVE_EXECUTION_ENABLED", True), \
         patch.object(settings, "MONGO_AUTH_ENABLED", True), \
         patch.object(settings, "ALLOW_UNAUTHENTICATED_DEV", False), \
         patch.object(settings, "MONGO_READONLY_USERNAME", "banking_agent_ro"), \
         patch.object(settings, "MONGO_READONLY_PASSWORD", "bank_pass_123"), \
         patch.object(settings, "MONGO_METADATA_USERNAME", "metadata_agent_rw"), \
         patch.object(settings, "MONGO_METADATA_PASSWORD", "meta_pass_456"), \
         patch.object(settings, "MONGO_NATIVE_AUTH_VERIFIED", False):
        res = await query_executor_node(state)
        assert res["execution_status"] == "GATE_BLOCKED"
        assert "Native MongoDB server-side authorization status is unverified" in res["execution_error"]


@pytest.mark.asyncio
async def test_security_gate_blocked_when_credentials_shared():
    """Verify live execution is blocked if banking and metadata use shared/identical credentials."""
    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 5}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
    }
    with patch.object(settings, "PHASE6_LIVE_EXECUTION_ENABLED", True), \
         patch.object(settings, "MONGO_AUTH_ENABLED", True), \
         patch.object(settings, "ALLOW_UNAUTHENTICATED_DEV", False), \
         patch.object(settings, "MONGO_READONLY_USERNAME", "shared_admin"), \
         patch.object(settings, "MONGO_READONLY_PASSWORD", "same_password"), \
         patch.object(settings, "MONGO_METADATA_USERNAME", "shared_admin"), \
         patch.object(settings, "MONGO_METADATA_PASSWORD", "same_password"), \
         patch.object(settings, "MONGO_NATIVE_AUTH_VERIFIED", True):
        res = await query_executor_node(state)
        assert res["execution_status"] == "GATE_BLOCKED"
        assert "must be separate and distinct" in res["execution_error"]


@pytest.mark.asyncio
async def test_security_gate_blocked_untrusted_api_injection_of_test_db():
    """Verify Node 6 blocks test_db or mock_db when injected via API/untrusted request."""
    mock_db = MagicMock()
    mock_db.name = "injected_db"

    state = {
        "guardrail_status": "allowed",
        "target_collection": "customers",
        "approved_pipeline": [{"$match": {}}, {"$limit": 5}],
        "is_pipeline_valid": True,
        "validation_status": "VALID",
        "test_db": mock_db,
        "is_api_request": True,  # Flagged by chat route
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "GATE_BLOCKED"
    assert "Untrusted test_db or mock_db injection detected" in res["execution_error"]
    assert mock_db.__getitem__.call_count == 0
