"""
FinTech Agent — Pre-Phase 6 Remediation & Final Verification Test Suite
Comprehensive regression tests for:
  A. Financial Semantics: Overdue vs. Defaulted Loans, Nonexistent Fields, Caveats
  B. MQL Result Volume Policy: Hard Limit Capping, Terminal Limits, Unwind Bounds
  C. Multi-Turn Conversation Context: Follow-ups, Context Isolation, Boundary Rules
  D. Gemini Provider Reliability: Bounded Retries, Jitter, 503/429 Handling, Fail-Fast
  E. Windows Logging: CP1252 Compatibility, Secret Redaction, ASCII-Safe Outputs
  F. Graph & API Integration: State Flow, Request Modes, Guardrail Rejections
  G. Security & Zero-Execution: ReadOnly Proxies, Inactive Stubs, AST Allowlist Enforcement
"""

import asyncio
from datetime import datetime, timezone
import io
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.graph import agent_graph
from backend.app.agent.nodes.input_guardrail import input_guardrail_node
from backend.app.agent.nodes.mql_policy_validator import (
    MQLPolicyValidator,
    mql_policy_validator_node,
    mql_validator,
)
from backend.app.agent.nodes.query_synthesizer import query_synthesizer_node
from backend.app.agent.nodes.request_intent_router import intent_router_node
from backend.app.agent.nodes.response_composer import response_composer_node
from backend.app.agent.prompts.intent_classification import mock_classify_intent
from backend.app.agent.prompts.query_synthesis import (
    PipelineSynthesisOutput,
    mock_synthesize_query,
)
from backend.app.agent.state import AgentState
from backend.app.config import settings
from backend.app.core.exceptions import (
    DatabaseWriteProhibitedError,
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from backend.app.core.logging import RedactingFormatter, make_ascii_safe, sanitize_error_message
from backend.app.db.mongo_client import mongo_manager
from backend.app.main import app
from backend.app.services.llm_service import OpenAICompatibleProvider, llm_service


client = TestClient(app)


# ==============================================================================
# A. FINANCIAL SEMANTICS TESTS
# ==============================================================================

def test_financial_semantics_defaulted_loans_supported():
    """Verify 'Show defaulted loans' synthesizes a valid defaulted status query."""
    res = mock_synthesize_query("Show defaulted loans", schema_context={})
    assert res.target_collection == "loans"
    assert len(res.pipeline) > 0
    match_stage = res.pipeline[0].get("$match", {})
    assert match_stage.get("status") == "defaulted"
    assert "defaulted" in res.explanation.lower()


def test_financial_semantics_defaulted_principal_aggregated():
    """Verify calculating outstanding principal of defaulted loans aggregates outstanding_amount."""
    res = mock_synthesize_query("Calculate outstanding principal of defaulted loans", schema_context={})
    assert res.target_collection == "loans"
    assert len(res.pipeline) >= 2
    match_stage = res.pipeline[0].get("$match", {})
    assert match_stage.get("status") == "defaulted"
    group_stage = res.pipeline[1].get("$group", {})
    assert "total_defaulted_principal" in group_stage
    assert group_stage["total_defaulted_principal"] == {"$sum": "$outstanding_amount"}
    assert "outstanding principal" in res.explanation.lower()


def test_financial_semantics_overdue_loans_unsupported():
    """Verify 'Show overdue loans' is strictly NOT mapped to defaulted loans."""
    res = mock_synthesize_query("Show overdue loans", schema_context={})
    assert res.target_collection == "loans"
    assert res.pipeline == []
    assert "overdue_amount" in res.unsupported_concepts_identified
    assert "days_past_due" in res.unsupported_concepts_identified
    assert "distinct from overdue" in res.explanation.lower()


def test_financial_semantics_overdue_amount_unsupported():
    """Verify 'Calculate overdue debt' is flagged as unsupported without defaulted proxy."""
    res = mock_synthesize_query("Calculate overdue debt and overdue amount", schema_context={})
    assert res.pipeline == []
    assert len(res.unsupported_concepts_identified) > 0
    assert "overdue_amount" in res.unsupported_concepts_identified


def test_financial_semantics_days_past_due_unsupported():
    """Verify queries requesting 30 days past due or DPD are unsupported."""
    res = mock_synthesize_query("Show loans with more than 30 days past due", schema_context={})
    assert res.pipeline == []
    assert "days_past_due" in res.unsupported_concepts_identified


@pytest.mark.asyncio
async def test_financial_semantics_node5_unsupported_status():
    """Verify Node 5 sets validation_status='UNSUPPORTED' when concepts are unsupported."""
    state: AgentState = {
        "request_id": "req-fin-1",
        "target_collection": "loans",
        "generated_pipeline": [],
        "query_parameters": {
            "unsupported_concepts": ["overdue_amount", "days_past_due"],
            "assumptions": [],
        },
        "trace": [],
    }
    node5_res = await mql_policy_validator_node(state)
    assert node5_res["validation_status"] == "UNSUPPORTED"
    assert node5_res["is_pipeline_valid"] is False
    assert len(node5_res["validation_errors"]) > 0


@pytest.mark.asyncio
async def test_financial_semantics_response_composer_explains_distinction():
    """Verify response composer explains that overdue arrears != remaining principal."""
    state: AgentState = {
        "request_id": "req-fin-2",
        "request_mode": "QUERY_ONLY",
        "validation_status": "UNSUPPORTED",
        "target_collection": "loans",
        "query_parameters": {
            "unsupported_concepts": ["overdue_amount", "days_past_due"],
        },
        "trace": [],
    }
    comp_res = await response_composer_node(state)
    resp_text = comp_res["graph_response"]
    assert "Unsupported Banking Concept" in resp_text
    assert "outstanding_amount" in resp_text
    assert "overdue_amount" in resp_text
    assert "defaulted" in resp_text


# ==============================================================================
# B. MQL RESULT VOLUME POLICY TESTS
# ==============================================================================

def test_mql_limit_above_max_rejected():
    """Verify limit exceeding RESULT_DOC_LIMIT (1000) is invalid."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {"$limit": 10000},
    ]
    res = validator.validate_pipeline("accounts", pipeline)
    assert res.validation_status == "INVALID"
    assert any("exceeds maximum allowed result limit" in err for err in res.validation_errors)


def test_mql_limit_within_max_allowed():
    """Verify limit within maximum limit is valid."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {"$limit": 500},
    ]
    res = validator.validate_pipeline("accounts", pipeline, require_terminal_limit=True)
    assert res.validation_status == "VALID"
    assert res.validation_errors == []


def test_mql_missing_terminal_limit_rejected_when_required():
    """Verify row-returning pipeline without terminal limit fails validation."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("lacks an effective terminal $limit stage" in err for err in res.validation_errors)


def test_mql_count_stage_exempt_from_terminal_limit():
    """Verify $count stage is valid without an explicit $limit stage."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {"$count": "total_active"},
    ]
    res = validator.validate_pipeline("customers", pipeline, require_terminal_limit=True)
    assert res.validation_status == "VALID"


def test_mql_scalar_group_exempt_from_terminal_limit():
    """Verify $group with _id: None is recognized as single document and exempt."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": None, "total": {"$sum": "$balance"}}},
    ]
    res = validator.validate_pipeline("accounts", pipeline, require_terminal_limit=True)
    assert res.validation_status == "VALID"


def test_mql_unwind_after_limit_rejected():
    """Verify $unwind after $limit without subsequent limit is rejected for potential unbounded expansion."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {"$limit": 10},
        {"$unwind": "$branch_id"},
    ]
    res = validator.validate_pipeline("accounts", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("followed by $unwind" in err for err in res.validation_errors)


def test_mql_inconsistent_multiple_limits_rejected():
    """Verify a subsequent $limit cannot expand an earlier $limit stage."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "active"}},
        {"$limit": 20},
        {"$limit": 100},
    ]
    res = validator.validate_pipeline("accounts", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("cannot expand earlier" in err for err in res.validation_errors)


def test_mql_limit_before_sort_rejected():
    """Verify $limit before $sort is rejected as semantically invalid."""
    validator = MQLPolicyValidator()
    pipeline = [
        {"$match": {"status": "completed"}},
        {"$limit": 50},
        {"$sort": {"amount": -1}},
        {"$limit": 50},
    ]
    res = validator.validate_pipeline("transactions", pipeline, require_terminal_limit=True)
    assert res.validation_status == "INVALID"
    assert any("precedes $sort" in err for err in res.validation_errors)


# ==============================================================================
# C. CONVERSATION CONTEXT TESTS
# ==============================================================================

def test_conversation_followup_with_history():
    """Verify follow-up query inherits prior banking context when history is provided."""
    history = [
        {"role": "user", "content": "Show customers from Chennai"},
        {"role": "assistant", "content": "Found 15 customers in Chennai."},
    ]
    res = mock_classify_intent("What about Coimbatore?", conversation_history=history)
    assert res["request_mode"] == "QUERY_ONLY"
    assert "Chennai" in res["query_description"]
    assert "Coimbatore" in res["query_description"]


def test_conversation_followup_without_history():
    """Verify same follow-up without history cannot infer banking context."""
    res = mock_classify_intent("What about Coimbatore?", conversation_history=[])
    assert res["request_mode"] in ("CLARIFICATION_REQUIRED", "OUT_OF_SCOPE")


def test_conversation_isolation_between_sessions():
    """Verify context from Session 1 is isolated and does not leak to Session 2."""
    session1_hist = [
        {"role": "user", "content": "Show customers from Chennai"},
        {"role": "assistant", "content": "Found 15 customers in Chennai."},
    ]
    res1 = mock_classify_intent("What about Coimbatore?", conversation_history=session1_hist)
    assert res1["request_mode"] == "QUERY_ONLY"
    assert "Chennai" in res1["query_description"]
    assert "Coimbatore" in res1["query_description"]

    # Session 2 has no history — same follow-up must not infer banking context
    res2 = mock_classify_intent("What about Coimbatore?", conversation_history=[])
    assert res2["request_mode"] in ("CLARIFICATION_REQUIRED", "OUT_OF_SCOPE")


def test_conversation_long_history_bounded():
    """Verify prompt builder safely truncates and handles multi-turn histories."""
    from backend.app.agent.prompts.intent_classification import build_intent_classification_prompt
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}"} for i in range(20)]
    prompt = build_intent_classification_prompt("Show active accounts", history)
    assert "Show active accounts" in prompt
    assert len(prompt.splitlines()) < 50


# ==============================================================================
# D. GEMINI PROVIDER RELIABILITY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_gemini_503_retry_and_recovery():
    """Verify provider retries on transient 503 and returns response if subsequent attempt succeeds."""
    provider = OpenAICompatibleProvider(
        model="gemini-3.8-flash",
        api_key="mock-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        timeout=10,
        provider_name="gemini",
    )

    resp_503 = httpx.Response(503, text="Service Unavailable: High demand")
    resp_200 = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "SUCCESS_AFTER_RETRY"}}]},
    )

    with patch("httpx.AsyncClient.post", side_effect=[resp_503, resp_200]) as mock_post:
        res = await provider.generate_response("Test prompt")
        assert res == "SUCCESS_AFTER_RETRY"
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_gemini_503_exhausted_retries_raises_api_error():
    """Verify provider fails with ProviderAPIError after 3 exhausted 503 attempts."""
    provider = OpenAICompatibleProvider(
        model="gemini-3.8-flash",
        api_key="mock-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        timeout=10,
        provider_name="gemini",
    )

    resp_503 = httpx.Response(503, text="Service Unavailable: High demand")

    with patch("httpx.AsyncClient.post", return_value=resp_503) as mock_post:
        with pytest.raises(ProviderAPIError) as exc_info:
            await provider.generate_response("Test prompt")
        assert "Status 503" in str(exc_info.value)
        assert mock_post.call_count == 3


@pytest.mark.asyncio
async def test_gemini_auth_error_fails_fast_without_retries():
    """Verify 401 Authentication error fails immediately on attempt 1."""
    provider = OpenAICompatibleProvider(
        model="gemini-3.8-flash",
        api_key="bad-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        timeout=10,
        provider_name="gemini",
    )

    resp_401 = httpx.Response(401, text="Unauthorized: Invalid API key")

    with patch("httpx.AsyncClient.post", return_value=resp_401) as mock_post:
        with pytest.raises(ProviderAuthenticationError):
            await provider.generate_response("Test prompt")
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_gemini_quota_exhaustion_fails_fast():
    """Verify 429 quota exhaustion fails immediately without retrying."""
    provider = OpenAICompatibleProvider(
        model="gemini-3.8-flash",
        api_key="mock-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        timeout=10,
        provider_name="gemini",
    )

    resp_429 = httpx.Response(429, text="Resource has been exhausted: insufficient_quota")

    with patch("httpx.AsyncClient.post", return_value=resp_429) as mock_post:
        with pytest.raises(ProviderRateLimitError) as exc_info:
            await provider.generate_response("Test prompt")
        assert "Quota exhausted" in str(exc_info.value)
        assert mock_post.call_count == 1


# ==============================================================================
# E. WINDOWS LOGGING COMPATIBILITY TESTS
# ==============================================================================

def test_windows_logging_cp1252_safe():
    """Verify logging replaces non-ASCII Unicode characters with safe ASCII representations."""
    test_str = "Status: \u2705 OK | Indian Rupee: \u20b9500 | Flow: A \u2192 B"
    safe = make_ascii_safe(test_str)
    assert "[OK]" in safe
    assert "INR 500" in safe
    assert "->" in safe
    # Prove it encodes cleanly to cp1252
    encoded = safe.encode("cp1252")
    assert isinstance(encoded, bytes)


def test_windows_logging_secret_redaction():
    """Verify sensitive keys and passwords in logs are redacted."""
    sensitive_log = "Connected with AIzaSyD1234567890abcdef1234567890abcde and mongodb://admin:secretPass@localhost:27017/"
    sanitized = sanitize_error_message(sensitive_log)
    assert "AIzaSy" not in sanitized
    assert "secretPass" not in sanitized
    assert "[REDACTED]" in sanitized


# ==============================================================================
# F. GRAPH AND API INTEGRATION TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_graph_e2e_valid_query():
    """Verify valid query flows through nodes 1 -> 2 -> 3 -> 4 -> 5 -> 8."""
    initial_state: AgentState = {
        "request_id": "req-g-1",
        "conversation_id": "conv-g-1",
        "natural_language_query": "Show failed transactions",
        "conversation_history": [],
        "user_role": "analyst",
        "retry_count": 0,
        "max_retries": 3,
        "error_history": [],
        "trace": [],
    }
    with patch.object(settings, "LLM_PROVIDER", "mock"):
        final_state = await agent_graph.ainvoke(initial_state)
    assert final_state["request_mode"] == "QUERY_ONLY"
    assert final_state["target_collection"] == "transactions"
    assert final_state["is_pipeline_valid"] is True
    assert "Query Understood" in final_state["final_response"] or "Pipeline Generated" in final_state["final_response"]


@pytest.mark.asyncio
async def test_graph_e2e_guardrail_rejection():
    """Verify destructive query is blocked at Node 1 without running synthesis or execution."""
    initial_state: AgentState = {
        "request_id": "req-g-2",
        "conversation_id": "conv-g-2",
        "natural_language_query": "Show accounts; db.customers.drop()",
        "conversation_history": [],
        "user_role": "analyst",
        "retry_count": 0,
        "max_retries": 3,
        "error_history": [],
        "trace": [],
    }
    final_state = await agent_graph.ainvoke(initial_state)
    assert final_state["guardrail_status"] == "rejected"
    assert final_state["final_status"] == "rejected"
    assert final_state.get("generated_pipeline") is None


# ==============================================================================
# G. SECURITY AND ZERO-EXECUTION TESTS
# ==============================================================================

def test_security_readonly_proxy_blocks_writes():
    """Verify application proxy strictly blocks mutating database commands."""
    db = mongo_manager.get_banking_db()
    with pytest.raises(DatabaseWriteProhibitedError):
        db.customers.insert_one({"name": "Unauthorized Customer"})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.accounts.delete_one({"account_id": "ACC001"})

    with pytest.raises(DatabaseWriteProhibitedError):
        db.loans.drop()


def test_security_future_stubs_inactive():
    """Verify Node 6 query executor stub performs zero database execution."""
    from backend.app.agent.nodes.query_executor import query_executor_stub
    res = asyncio.run(query_executor_stub({}))
    assert res["raw_results"] is None
    assert res["execution_time_ms"] is None
    assert any(t["node"] == "query_executor" and t["status"] == "stub" for t in res["trace"])


def test_security_mql_blocks_prohibited_operators():
    """Verify validator strictly blocks $where and javascript execution."""
    validator = MQLPolicyValidator()
    bad_pipeline = [
        {"$match": {"$where": "this.balance > 1000"}},
        {"$limit": 10},
    ]
    res = validator.validate_pipeline("accounts", bad_pipeline)
    assert res.validation_status == "INVALID"
    assert any("prohibited operator '$where'" in err for err in res.validation_errors)
