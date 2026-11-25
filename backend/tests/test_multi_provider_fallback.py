"""
FinTech Agent — Multi-Provider LLM Fallback Verification Tests
Verifies the production-quality, centrally managed LLM provider fallback mechanism:
  Primary: Google Gemini 3.8 Flash
  Fallback 1: Groq — GPT-OSS 120B
  Fallback 2: Local Ollama — K2 Horizon 3.7B Q3_K_M
  Terminal: Controlled Application-Level Error (LLMFallbackExhaustedError)
"""

import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.agent.graph import agent_graph
from backend.app.agent.nodes.query_synthesizer import query_synthesizer_node
from backend.app.agent.nodes.request_intent_router import intent_router_node
from backend.app.agent.state import AgentState
from backend.app.config import settings
from backend.app.core.deadline import ActiveRequestContext, RequestDeadline, get_active_request_context, reset_active_request_context, set_active_request_context
from backend.app.core.exceptions import (
    LLMFallbackExhaustedError,
    MissingAPIKeyError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderRetryExhaustedError,
    ProviderTimeoutError,
)
from backend.app.core.execution_monitor import execution_monitor
from backend.app.main import app
from backend.app.services.llm_service import (
    FallbackProviderManager,
    NormalizedLLMResponse,
    OpenAICompatibleProvider,
    is_recoverable_failure,
    llm_service,
)


class _FakeResp:
    def __init__(self, status_code: int = 200, json_data: dict = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or json.dumps(self._json_data)
        self.headers = {}

    def json(self):
        return self._json_data


# ------------------------------------------------------------------------------
# 1. Response Normalization Tests
# ------------------------------------------------------------------------------

def test_normalized_llm_response_string_behavior():
    """Verify NormalizedLLMResponse behaves 100% identically to a standard str."""
    raw_json = '{"request_mode": "QUERY_ONLY", "intent_reason": "Data request"}'
    norm = NormalizedLLMResponse(
        raw_json,
        provider="gemini",
        model="gemini-3.8-flash",
        finish_reason="stop",
        latency_ms=150.5,
        is_local=False,
    )

    # Must be an instance of str
    assert isinstance(norm, str)
    assert norm == raw_json
    assert norm.startswith('{"request_mode"')
    assert len(norm) == len(raw_json)

    # Must deserialize with json.loads directly
    data = json.loads(norm)
    assert data["request_mode"] == "QUERY_ONLY"

    # Preserves metadata attributes
    assert norm.provider == "gemini"
    assert norm.model == "gemini-3.8-flash"
    assert norm.finish_reason == "stop"
    assert norm.latency_ms == 150.5
    assert norm.is_local is False


def test_normalized_llm_response_ollama_local_flag():
    """Verify local flag is properly set for Ollama and false for cloud providers."""
    norm_ollama = NormalizedLLMResponse(
        "local output",
        provider="ollama",
        model=settings.OLLAMA_MODEL,
        is_local=True,
    )
    assert norm_ollama.is_local is True
    assert norm_ollama.provider == "ollama"

    norm_groq = NormalizedLLMResponse(
        "groq output",
        provider="groq",
        model=settings.GROQ_MODEL,
        is_local=False,
    )
    assert norm_groq.is_local is False
    assert norm_groq.provider == "groq"


# ------------------------------------------------------------------------------
# 2. Recoverable vs Non-Recoverable Failure Classification Tests
# ------------------------------------------------------------------------------

def test_is_recoverable_failure_classification():
    """Verify strict classification of recoverable vs non-recoverable errors."""
    # Recoverable
    assert is_recoverable_failure(ProviderTimeoutError("gemini", 10.0)) is True
    assert is_recoverable_failure(ProviderRetryExhaustedError("gemini", "exhausted")) is True
    assert is_recoverable_failure(httpx.ReadTimeout("read timeout")) is True
    assert is_recoverable_failure(httpx.ConnectTimeout("connect timeout")) is True
    assert is_recoverable_failure(asyncio.TimeoutError()) is True
    assert is_recoverable_failure(httpx.RequestError("network error")) is True
    assert is_recoverable_failure(ProviderRateLimitError("gemini", message="Rate limit exceeded")) is True
    assert is_recoverable_failure(ProviderRateLimitError("gemini", message="Quota exceeded (billing exhausted)")) is True

    # Ineligible / Non-recoverable
    assert is_recoverable_failure(asyncio.CancelledError()) is False
    assert is_recoverable_failure(ProviderAuthenticationError("gemini", "Invalid API key")) is False
    assert is_recoverable_failure(MissingAPIKeyError("gemini")) is False


# ------------------------------------------------------------------------------
# 3. Fallback Chain Execution Tests (Gemini -> Groq -> Ollama)
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_primary_gemini_succeeds_no_fallback_triggered():
    """When Gemini succeeds on attempt 1, Groq and Ollama are never called."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"
        settings.LLM_FALLBACK_ENABLED = True

        provider = llm_service.get_provider()
        assert isinstance(provider, FallbackProviderManager)

        gemini_payload = {
            "choices": [{"message": {"content": '{"request_mode": "QUERY_ONLY", "intent_reason": "ok"}'}}],
            "usage": {"total_tokens": 42},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _FakeResp(200, json_data=gemini_payload)

            resp = await provider.generate_response(user_message="Show transactions")

            assert isinstance(resp, NormalizedLLMResponse)
            assert resp.provider == "gemini"
            assert resp.model == "gemini-3.8-flash"
            assert mock_post.call_count == 1
            call_url = mock_post.call_args[0][0]
            assert "googleapis.com" in str(call_url)
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


@pytest.mark.asyncio
async def test_fallback_gemini_fails_groq_succeeds():
    """When Gemini fails with 503, Groq (Fallback 1) is invoked and succeeds."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"
        settings.LLM_FALLBACK_ENABLED = True

        provider = llm_service.get_provider()

        groq_payload = {
            "choices": [{"message": {"content": '{"request_mode": "QUERY_ONLY", "intent_reason": "from groq"}'}}],
            "usage": {"total_tokens": 55},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            # Gemini fails with 503; then Groq succeeds with 200
            mock_post.side_effect = [
                _FakeResp(503, text="Service unavailable"),
                _FakeResp(200, json_data=groq_payload),
            ]

            resp = await provider.generate_response(user_message="Show transactions")

            assert isinstance(resp, NormalizedLLMResponse)
            assert resp.provider == "groq"
            assert resp.model == settings.GROQ_MODEL
            assert resp.is_local is False
            assert "from groq" in str(resp)

            # 1 call to Gemini + 1 call to Groq = 2 calls
            assert mock_post.call_count == 2
            groq_call = mock_post.call_args_list[1]
            assert "api.groq.com" in str(groq_call[0][0])
            # Verify User-Agent header is attached to prevent Cloudflare 1010 block
            assert groq_call[1]["headers"].get("User-Agent") == "FinTechAgent/1.0"
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


@pytest.mark.asyncio
async def test_fallback_gemini_and_groq_fail_ollama_succeeds():
    """When Gemini and Groq fail with 503/timeout, Ollama (Fallback 2) succeeds."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"
        settings.LLM_FALLBACK_ENABLED = True

        provider = llm_service.get_provider()

        ollama_payload = {
            "choices": [{"message": {"content": '{"request_mode": "QUERY_ONLY", "intent_reason": "from ollama"}'}}],
            "usage": {"total_tokens": 30},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [
                _FakeResp(503, text="Gemini unavailable"),
                _FakeResp(503, text="Groq unavailable"),
                _FakeResp(200, json_data=ollama_payload),
            ]

            resp = await provider.generate_response(
                user_message="Show transactions",
                reasoning_effort="low",
            )

            assert isinstance(resp, NormalizedLLMResponse)
            assert resp.provider == "ollama"
            assert resp.model == settings.OLLAMA_MODEL
            assert resp.is_local is True
            assert "from ollama" in str(resp)

            # Ollama call must NOT have reasoning_effort parameter (which causes HTTP 400 on Ollama)
            assert mock_post.call_count == 3
            ollama_call = mock_post.call_args_list[2]
            assert "11434" in str(ollama_call[0][0])
            payload = ollama_call[1]["json"]
            assert "reasoning_effort" not in payload
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


@pytest.mark.asyncio
async def test_fallback_all_providers_fail_raises_fallback_exhausted_error():
    """When Gemini, Groq, and Ollama all fail, LLMFallbackExhaustedError is raised."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"
        settings.LLM_FALLBACK_ENABLED = True

        provider = llm_service.get_provider()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [
                _FakeResp(503, text="Gemini down"),
                _FakeResp(503, text="Groq down"),
                httpx.ConnectTimeout("Ollama down"),
            ]

            with pytest.raises(LLMFallbackExhaustedError) as exc_info:
                await provider.generate_response(user_message="Show transactions")

            err = exc_info.value
            assert "gemini" in err.attempted_providers
            assert "groq" in err.attempted_providers
            assert "ollama" in err.attempted_providers
            assert err.status_code == 503
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


# ------------------------------------------------------------------------------
# 4. Strict Guardrails & Edge Cases
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_recoverable_401_aborts_without_fallback():
    """Non-recoverable 401 Authentication error must abort immediately without trying Groq/Ollama."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"
        settings.LLM_FALLBACK_ENABLED = True

        provider = llm_service.get_provider()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = _FakeResp(401, text="API key invalid")

            with pytest.raises(ProviderAuthenticationError):
                await provider.generate_response(user_message="Show transactions")

            # Must not have contacted Groq or Ollama
            assert mock_post.call_count == 1
            assert "googleapis.com" in str(mock_post.call_args[0][0])
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


@pytest.mark.asyncio
async def test_missing_groq_key_skips_cleanly_to_ollama():
    """When GROQ_API_KEY is not configured, Groq is skipped cleanly and Ollama is invoked."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = None  # Missing key
        settings.LLM_FALLBACK_ENABLED = True

        provider = llm_service.get_provider()

        ollama_payload = {
            "choices": [{"message": {"content": '{"request_mode": "QUERY_ONLY", "intent_reason": "ollama skip groq"}'}}],
            "usage": {"total_tokens": 20},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [
                _FakeResp(503, text="Gemini unavailable"),
                _FakeResp(200, json_data=ollama_payload),
            ]

            resp = await provider.generate_response(user_message="Show transactions")

            assert resp.provider == "ollama"
            assert "ollama skip groq" in str(resp)
            # Calls: 1 to Gemini + 1 to Ollama (zero to Groq)
            assert mock_post.call_count == 2
            assert "11434" in str(mock_post.call_args_list[1][0][0])
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


@pytest.mark.asyncio
async def test_insufficient_deadline_budget_skips_fallback():
    """When remaining request budget is < min_retry_budget (4.0s), fallback is skipped."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"
        settings.LLM_FALLBACK_ENABLED = True

        # Provide manager with 5.0s operation timeout, min budget 4.0s
        provider = FallbackProviderManager(
            primary_provider=llm_service._build_single_provider("gemini"),
            fallback_providers=[
                llm_service._build_single_provider("groq"),
                llm_service._build_single_provider("ollama"),
            ],
            operation_timeout=3.5,  # Less than min_retry_budget (4.0s)
            min_retry_budget=4.0,
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_post.side_effect = [
                _FakeResp(503, text="Gemini down"),
                httpx.ReadTimeout("Gemini timeout"),
            ]

            with pytest.raises(LLMFallbackExhaustedError) as exc_info:
                await provider.generate_response(user_message="Show transactions")

            err = exc_info.value
            assert "gemini" in err.attempted_providers
            assert "groq" in err.skipped_providers
            assert "insufficient_budget" in err.skipped_providers["groq"]
            assert "ollama" in err.skipped_providers
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


# ------------------------------------------------------------------------------
# 5. Integration Tests: Chat Route and Agent Nodes with Fallback
# ------------------------------------------------------------------------------

def test_chat_route_attribution_when_groq_fallback_succeeds():
    """Verify chat endpoint returns provider='groq' and model='openai/gpt-oss-120b' on fallback."""
    orig_provider = settings.LLM_PROVIDER
    orig_model = settings.LLM_MODEL
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    orig_fb = settings.LLM_FALLBACK_ENABLED
    try:
        settings.LLM_PROVIDER = "gemini"
        settings.LLM_MODEL = "gemini-3.8-flash"
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"
        settings.LLM_FALLBACK_ENABLED = True

        mock_meta = MagicMock()
        mock_meta.conversations.find_one.return_value = None
        client = TestClient(app)

        groq_intent = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "request_mode": "QUERY_ONLY",
                        "intent_reason": "User requested account balances",
                        "query_description": "List accounts",
                    })
                }
            }]
        }
        groq_synth = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "target_collection": "accounts",
                        "pipeline": [{"$match": {"status": "ACTIVE"}}],
                        "explanation": "Active accounts",
                        "assumptions": [],
                        "unsupported_concepts_identified": [],
                    })
                }
            }]
        }

        with patch("backend.app.db.mongo_client.mongo_manager.get_metadata_db", return_value=mock_meta), \
             patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            # Node 2: Gemini fails (503) -> Groq succeeds
            # Node 4: uses request-scoped preferred provider Groq directly (Gemini is not retried!)
            def post_side_effect(url, **kwargs):
                url_str = str(url)
                if "googleapis.com" in url_str:
                    return _FakeResp(503, text="Gemini down")
                if "groq.com" in url_str:
                    if post_side_effect.groq_count == 0:
                        post_side_effect.groq_count += 1
                        return _FakeResp(200, json_data=groq_intent)
                    return _FakeResp(200, json_data=groq_synth)
                return _FakeResp(404)
            post_side_effect.groq_count = 0
            mock_post.side_effect = post_side_effect

            resp = client.post("/api/v1/chat", json={"message": "Show active accounts"})

            assert resp.status_code == 200
            data = resp.json()
            assert data["provider"] == "groq"
            assert data["model"] == settings.GROQ_MODEL
            assert data["request_mode"] == "QUERY_ONLY"
            assert data["selected_collection"] == "accounts"
            # Exactly 3 calls: 1 to Gemini in Node 2, 1 to Groq in Node 2, and 1 to Groq in Node 4 (Gemini skipped in Node 4!)
            assert mock_post.call_count == 3
    finally:
        settings.LLM_PROVIDER = orig_provider
        settings.LLM_MODEL = orig_model
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
        settings.LLM_FALLBACK_ENABLED = orig_fb


@pytest.mark.asyncio
async def test_provider_health_check_returns_all_configured_providers():
    """Verify check_provider_health inspects Gemini, Groq, and Ollama in parallel."""
    orig_gem_key = settings.GEMINI_API_KEY
    orig_groq_key = settings.GROQ_API_KEY
    try:
        settings.GEMINI_API_KEY = "AIzaSyFakeKey123"
        settings.GROQ_API_KEY = "gsk_fakeKey123"

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            def side_effect(url, **kwargs):
                url_str = str(url)
                if "googleapis.com" in url_str:
                    return _FakeResp(200, json_data={"models": [{"name": "gemini-3.8-flash"}]})
                elif "groq.com" in url_str:
                    return _FakeResp(200, json_data={"data": [{"id": "openai/gpt-oss-120b"}]})
                elif "11434" in url_str:
                    return _FakeResp(200, json_data={"models": [{"name": settings.OLLAMA_MODEL}]})
                return _FakeResp(404)

            mock_get.side_effect = side_effect

            health = await llm_service.check_provider_health()

            assert health["primary_provider"] == settings.LLM_PROVIDER
            assert health["fallback_enabled"] is True
            providers = health["providers"]
            assert providers["gemini"]["status"] == "healthy"
            assert providers["groq"]["status"] == "healthy"
            assert providers["ollama"]["status"] == "healthy"
            assert providers["ollama"]["is_local"] is True
    finally:
        settings.GEMINI_API_KEY = orig_gem_key
        settings.GROQ_API_KEY = orig_groq_key
