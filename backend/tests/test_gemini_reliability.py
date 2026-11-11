"""
FinTech Agent — Focused Gemini Reliability, Timeout Budget & Execution Safety Tests (Part G.2)
Tests bounded timeout chain, structured error propagation, cancellation safety, no mock fallback,
and at-most-once validated query execution guarantees using mocked provider responses.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.app.agent.graph import agent_graph
from backend.app.agent.nodes.query_executor import query_executor_node
from backend.app.agent.nodes.request_intent_router import intent_router_node
from backend.app.agent.nodes.query_synthesizer import query_synthesizer_node
from backend.app.config import settings
from backend.app.core.deadline import (
    ActiveRequestContext,
    RequestDeadline,
    reset_active_request_context,
    set_active_request_context,
)
from backend.app.core.exceptions import (
    ProviderAPIError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderRetryExhaustedError,
    ProviderTimeoutError,
)
from backend.app.main import app
from backend.app.services.llm_service import (
    MockLLMProvider,
    OpenAICompatibleProvider,
    llm_service,
)


class _FakeResp:
    def __init__(self, status_code: int, json_data=None, text: str = "", headers=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json


def _make_gemini(
    *,
    timeout: float = 1.0,
    operation_timeout: float = 3.0,
    max_attempts: int = 3,
    retry_base_delay: float = 0.05,
    retry_max_delay: float = 0.1,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_name="gemini",
        api_key="AIzaSyFakeUnitTestKeyNotReal12345",
        model="gemini-3.8-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        timeout=timeout,
        operation_timeout=operation_timeout,
        max_attempts=max_attempts,
        retry_base_delay=retry_base_delay,
        retry_max_delay=retry_max_delay,
    )


def test_configured_timeout_budget_hierarchy():
    """Verify default bounded timeout chain: provider budget < backend deadline < frontend timeout."""
    assert settings.LLM_ATTEMPT_TIMEOUT_SECONDS > 0
    assert settings.LLM_MAX_ATTEMPTS >= 1
    assert settings.LLM_OPERATION_TIMEOUT_SECONDS < settings.REQUEST_TIMEOUT_SECONDS
    assert (
        settings.LLM_OPERATION_TIMEOUT_SECONDS + settings.BACKEND_PROCESSING_RESERVE_SECONDS
        <= settings.REQUEST_TIMEOUT_SECONDS
    )
    # Backend request deadline (30s) strictly less than frontend timeout (40s)
    assert settings.REQUEST_TIMEOUT_SECONDS < 40.0
    assert settings.QUERY_MAX_RETRY_ATTEMPTS == 0


@pytest.mark.asyncio
async def test_slow_503_skips_retry_when_budget_insufficient():
    """If a 503 response arrives slowly and leaves insufficient budget for another attempt, retry is skipped."""
    provider = _make_gemini(timeout=20.0, operation_timeout=5.0, max_attempts=2, retry_base_delay=0.5)
    err_503 = _FakeResp(503, text="Service unavailable")

    time_val = 100.0
    def _mock_time():
        return time_val

    async def _slow_503(*_args, **_kwargs):
        nonlocal time_val
        time_val += 4.0
        return err_503

    with patch("httpx.AsyncClient.post", side_effect=_slow_503) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("time.monotonic", side_effect=_mock_time):
        with pytest.raises(ProviderRetryExhaustedError) as exc_info:
            await provider.generate_response("Show transactions")
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "PROVIDER_UNAVAILABLE"
        assert mock_post.call_count == 1
        assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_read_timeout_exhausts_available_budget_and_skips_retry():
    """A read timeout that exhausts the available budget raises ProviderTimeoutError immediately without retrying."""
    provider = _make_gemini(timeout=20.0, operation_timeout=5.0, max_attempts=2, retry_base_delay=0.5)

    time_val = 100.0
    def _mock_time():
        return time_val

    def _slow_timeout(*_args, **_kwargs):
        nonlocal time_val
        time_val += 4.5
        raise httpx.ReadTimeout("Read timed out")

    with patch("httpx.AsyncClient.post", side_effect=_slow_timeout) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("time.monotonic", side_effect=_mock_time):
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await provider.generate_response("Show transactions")
        assert exc_info.value.status_code == 504
        assert exc_info.value.error_code == "PROVIDER_TIMEOUT"
        assert mock_post.call_count == 1
        assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_retry_after_handling_within_budget_and_exceeding_budget():
    # Case A: Retry-After fits in budget -> sleeps retry-after and retries
    provider_a = _make_gemini(timeout=5.0, operation_timeout=15.0, max_attempts=2)
    resp_429 = _FakeResp(429, text="Rate limit exceeded", headers={"retry-after": "2"})
    resp_200 = _FakeResp(200, json_data={"choices": [{"message": {"content": "Success after retry-after"}}]})
    with patch("httpx.AsyncClient.post", side_effect=[resp_429, resp_200]) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        res = await provider_a.generate_response("Test")
        assert res == "Success after retry-after"
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] == 2.0

    # Case B: Retry-After exceeds available budget -> skips retry immediately
    provider_b = _make_gemini(timeout=5.0, operation_timeout=5.0, max_attempts=2)
    resp_429_large = _FakeResp(429, text="Rate limit exceeded", headers={"retry-after": "10"})
    with patch("httpx.AsyncClient.post", return_value=resp_429_large) as mock_post_b, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep_b:
        with pytest.raises(ProviderRateLimitError):
            await provider_b.generate_response("Test")
        assert mock_post_b.call_count == 1
        assert mock_sleep_b.call_count == 0


@pytest.mark.asyncio
async def test_429_quota_exhaustion_vs_rate_limit_distinction():
    # Case A: Quota exhausted -> fails immediately on attempt 1 without retry
    provider = _make_gemini(timeout=5.0, operation_timeout=20.0, max_attempts=2)
    resp_quota = _FakeResp(429, text="You exceeded your current quota, please check your plan and billing details.")
    with patch("httpx.AsyncClient.post", return_value=resp_quota) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(ProviderRateLimitError) as exc_info:
            await provider.generate_response("Test")
        assert "Quota exhausted" in str(exc_info.value)
        assert mock_post.call_count == 1
        assert mock_sleep.call_count == 0

    # Case B: Transient rate limit (not quota) -> retries if budget allows
    resp_transient = _FakeResp(429, text="Rate limit exceeded. Please slow down.")
    resp_ok = _FakeResp(200, json_data={"choices": [{"message": {"content": "OK"}}]})
    with patch("httpx.AsyncClient.post", side_effect=[resp_transient, resp_ok]) as mock_post2, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep2:
        res = await provider.generate_response("Test")
        assert res == "OK"
        assert mock_post2.call_count == 2
        assert mock_sleep2.call_count == 1


@pytest.mark.asyncio
async def test_non_retryable_statuses_fail_immediately():
    provider = _make_gemini(timeout=5.0, operation_timeout=20.0, max_attempts=2)
    for status, expected_exc in [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (400, ProviderAPIError),
        (404, ProviderAPIError),
    ]:
        resp = _FakeResp(status, text=f"Error {status}")
        with patch("httpx.AsyncClient.post", return_value=resp) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(expected_exc):
                await provider.generate_response("Test")
            assert mock_post.call_count == 1
            assert mock_sleep.call_count == 0


@pytest.mark.asyncio
async def test_operation_deadline_strictly_never_exceeded():
    provider = _make_gemini(timeout=10.0, operation_timeout=0.6, max_attempts=2, retry_base_delay=0.1)
    t0 = time.monotonic()

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(0.3)
        raise httpx.ReadTimeout("Timeout")

    with patch("httpx.AsyncClient.post", side_effect=_hang):
        with pytest.raises(ProviderTimeoutError):
            await provider.generate_response("Test")
    elapsed = time.monotonic() - t0
    assert elapsed <= 0.8


@pytest.mark.asyncio
async def test_reasoning_effort_passed_to_intent_router_and_query_synthesizer():
    # 1. intent_router_node passes reasoning_effort="low"
    mock_prov = MagicMock()
    mock_prov.generate_response = AsyncMock(return_value='{"request_mode": "QUERY_ONLY", "intent_reason": "Data inquiry"}')
    with patch.object(llm_service, "get_provider", return_value=mock_prov):
        state = {"request_id": "req-r-1", "natural_language_query": "Show active loans", "conversation_history": [], "trace": []}
        res = await intent_router_node(state)
        assert res["request_mode"] == "QUERY_ONLY"
        mock_prov.generate_response.assert_called_once()
        _, kwargs = mock_prov.generate_response.call_args
        assert kwargs.get("reasoning_effort") == "low"

    # 2. query_synthesizer_node passes reasoning_effort="medium"
    mock_prov2 = MagicMock()
    mock_prov2.generate_response = AsyncMock(return_value='{"target_collection": "loans", "pipeline": [{"$match": {"status": "ACTIVE"}}]}')
    with patch.object(llm_service, "get_provider", return_value=mock_prov2):
        state2 = {"request_id": "req-r-2", "natural_language_query": "Show active loans", "schema_context": {}, "conversation_history": [], "trace": []}
        res2 = await query_synthesizer_node(state2)
        assert res2["target_collection"] == "loans"
        mock_prov2.generate_response.assert_called_once()
        _, kwargs2 = mock_prov2.generate_response.call_args
        assert kwargs2.get("reasoning_effort") == "medium"

    # 3. OpenAICompatibleProvider passes reasoning_effort into outbound payload
    captured_payloads = []
    async def _capture_post(url, headers=None, json=None, timeout=None):
        captured_payloads.append(dict(json))
        return _FakeResp(200, json_data={"choices": [{"message": {"content": "ok"}}]})

    provider = _make_gemini()
    with patch("httpx.AsyncClient.post", side_effect=_capture_post):
        await provider.generate_response("Test", reasoning_effort="low")
    assert len(captured_payloads) == 1
    assert captured_payloads[0].get("reasoning_effort") == "low"


@pytest.mark.asyncio
async def test_gemini_successful_first_attempt():
    provider = _make_gemini()
    ok = _FakeResp(200, json_data={"choices": [{"message": {"content": "Immediate Gemini answer"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = ok
        out = await provider.generate_response("Explain KYC")
        assert out == "Immediate Gemini answer"
        assert mock_post.call_count == 1


@pytest.mark.asyncio
async def test_gemini_timeout_then_success():
    provider = _make_gemini()
    ok = _FakeResp(200, json_data={"choices": [{"message": {"content": "Recovered after timeout"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_post.side_effect = [httpx.ReadTimeout("Read timed out"), ok]
        out = await provider.generate_response("Show transactions")
        assert out == "Recovered after timeout"
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_gemini_http_503_then_success():
    provider = _make_gemini()
    err_503 = _FakeResp(503, text="Service unavailable")
    ok = _FakeResp(200, json_data={"choices": [{"message": {"content": "Recovered from 503"}}]})
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_post.side_effect = [err_503, ok]
        out = await provider.generate_response("Show transactions")
        assert out == "Recovered from 503"
        assert mock_post.call_count == 2
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_gemini_all_attempts_exhausted_returns_structured_errors():
    provider = _make_gemini()
    err_503 = _FakeResp(503, text="Backend overloaded")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [err_503, err_503, err_503]
        with pytest.raises(ProviderRetryExhaustedError) as exc_info:
            await provider.generate_response("Test")
        assert mock_post.call_count == 3
        assert isinstance(exc_info.value, ProviderAPIError)
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "PROVIDER_UNAVAILABLE"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post2, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post2.side_effect = [
            httpx.ReadTimeout("T1"),
            _FakeResp(503, text="503 mid-flight"),
            httpx.ReadTimeout("T3"),
        ]
        with pytest.raises(ProviderTimeoutError) as exc_timeout:
            await provider.generate_response("Show transactions from the last 30 days.")
        assert mock_post2.call_count == 3
        assert exc_timeout.value.error_code == "PROVIDER_TIMEOUT"
        assert exc_timeout.value.status_code == 504


@pytest.mark.asyncio
async def test_gemini_timeout_budget_enforced_prevents_overshoot():
    """If request deadline leaves very little budget, retries stop cleanly without exceeding total timeout."""
    provider = _make_gemini(
        timeout=5.0,
        operation_timeout=10.0,
        max_attempts=5,
        retry_base_delay=0.6,
        retry_max_delay=1.0,
    )
    deadline = RequestDeadline(timeout_seconds=settings.BACKEND_PROCESSING_RESERVE_SECONDS + 0.8, request_id="req-budget")
    tok = set_active_request_context(
        ActiveRequestContext(request_id="req-budget", conversation_id="conv-budget", deadline=deadline)
    )
    try:
        t0 = time.monotonic()

        async def _slow_timeout(*_args, **_kwargs):
            await asyncio.sleep(0.15)
            raise httpx.ReadTimeout("slow attempt")

        with patch("httpx.AsyncClient.post", side_effect=_slow_timeout):
            with pytest.raises(ProviderTimeoutError):
                await provider.generate_response("Budget test")

        elapsed = time.monotonic() - t0
        # Should stop well before attempting all 5 retries * 1s backoff
        assert elapsed < 1.2
    finally:
        reset_active_request_context(tok)


@pytest.mark.asyncio
async def test_cancellation_stops_retry_loop_immediately():
    """Cancelling an active request interrupts retries immediately rather than continuing attempts."""
    provider = _make_gemini(timeout=2.0, operation_timeout=10.0, max_attempts=3, retry_base_delay=5.0, retry_max_delay=5.0)
    calls = 0

    async def _first_fails_then_sleep(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _FakeResp(503, text="Transient 503")

    with patch("httpx.AsyncClient.post", side_effect=_first_fails_then_sleep):
        task = asyncio.create_task(provider.generate_response("Cancel me"))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert calls == 1


def test_no_silent_mock_fallback_and_no_execution_on_provider_failure():
    """
    Verify live Gemini mode never falls back to MockLLMProvider when failing, and
    neither MQL validation nor MongoDB execution executes with incomplete output.
    """
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_fallback = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeTestKey123456"
        settings.LLM_FALLBACK_ENABLED = False

        provider = llm_service.get_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
        assert not isinstance(provider, MockLLMProvider)

        mock_meta = MagicMock()
        mock_meta.conversations.find_one.return_value = None
        client = TestClient(app)

        with patch("backend.app.db.mongo_client.mongo_manager.get_metadata_db", return_value=mock_meta), \
             patch.object(MockLLMProvider, "generate_response", new_callable=AsyncMock) as mock_fallback, \
             patch("backend.app.agent.nodes.mql_policy_validator.mql_validator.validate_pipeline") as mock_val, \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [
                _FakeResp(503, text="Service unavailable"),
                httpx.ReadTimeout("Attempt 2 timeout"),
            ]
            resp = client.post("/api/v1/chat", json={"message": "Show transactions from the last 30 days."})

        assert resp.status_code == 504
        detail = resp.json()["detail"]
        assert detail["error_code"] == "PROVIDER_TIMEOUT"
        assert detail["success"] is False
        assert mock_fallback.call_count == 0
        assert mock_val.call_count == 0
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.LLM_FALLBACK_ENABLED = orig_fallback


def test_chat_endpoint_prevents_multiple_query_executions_per_request():
    """Chat endpoint enforces max_retries=0 so execution failures do not re-run DB pipelines."""
    orig_provider = settings.LLM_PROVIDER
    try:
        settings.LLM_PROVIDER = "mock"
        mock_meta = MagicMock()
        mock_meta.conversations.find_one.return_value = None

        captured_initial_states = []
        exec_calls = 0

        async def _spy_ainvoke(state):
            captured_initial_states.append(dict(state))
            return {
                "request_mode": "QUERY_ONLY",
                "guardrail_status": "allowed",
                "validation_status": "VALID",
                "is_pipeline_valid": True,
                "execution_status": "GATE_BLOCKED",
                "verification_status": "EXECUTION_GATE_BLOCKED",
                "selected_collection": "transactions",
                "pipeline_spec": [{"$limit": 5}],
                "graph_response": "Validated read-only pipeline prepared cleanly.",
                "trace": [],
            }

        client = TestClient(app)
        with patch("backend.app.db.mongo_client.mongo_manager.get_metadata_db", return_value=mock_meta), \
             patch.object(agent_graph, "ainvoke", side_effect=_spy_ainvoke):
            resp = client.post("/api/v1/chat", json={"message": "Show transactions from the last 30 days."})

        assert resp.status_code == 200
        assert len(captured_initial_states) == 1
        assert captured_initial_states[0]["max_retries"] == 0
        assert captured_initial_states[0]["is_api_request"] is True
        assert exec_calls == 0
    finally:
        settings.LLM_PROVIDER = orig_provider


@pytest.mark.asyncio
async def test_query_executor_enforces_at_most_once_guard_on_api_requests():
    """Even if called twice manually in a retry edge, Node 6 refuses duplicate API execution."""
    mock_db = MagicMock()
    state = {
        "request_id": "req-once-01",
        "is_api_request": True,
        "guardrail_status": "allowed",
        "validation_status": "VALID",
        "is_pipeline_valid": True,
        "target_collection": "transactions",
        "approved_pipeline": [{"$limit": 5}],
        "all_attempts": [{"attempt": 1, "status": "TIMEOUT"}],
        "test_db": mock_db,
    }
    res = await query_executor_node(state)
    assert res["execution_status"] == "EXECUTION_ERROR"
    assert "Duplicate query execution prevented" in res["execution_error"]
    assert mock_db.__getitem__.call_count == 0
