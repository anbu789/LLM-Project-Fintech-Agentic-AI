"""
FinTech Agent — Phase 2 Backend & LLM Integration Test Suite
Verifies FastAPI routing, validation, error shielding, and provider-independent LLM service.
"""

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
import httpx

from backend.app.config import settings
from backend.app.main import app
from backend.app.core.exceptions import (
    MissingAPIKeyError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderAPIError,
)
from backend.app.services.llm_service import (
    MockLLMProvider,
    AnthropicProvider,
    OpenAICompatibleProvider,
    llm_service,
)

client = TestClient(app)


# ------------------------------------------------------------------------------
# 1. Health & Application Lifecycle Tests
# ------------------------------------------------------------------------------

def test_fastapi_starts_and_health_endpoint():
    """Verify FastAPI application starts and /api/v1/health returns 200 healthy."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "fintech-agent-api"
    assert "version" in data


def test_root_endpoint_metadata():
    """Verify root endpoint provides API navigation and metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert data["health"] == "/api/v1/health"


# ------------------------------------------------------------------------------
# 2. Request Validation Tests
# ------------------------------------------------------------------------------

def test_chat_rejects_empty_message():
    """Verify chat endpoint rejects empty message string."""
    response = client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "VALIDATION_ERROR"
    assert "empty" in data["message"].lower()


def test_chat_rejects_whitespace_message():
    """Verify chat endpoint rejects whitespace-only string."""
    response = client.post("/api/v1/chat", json={"message": "   \n\t  "})
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == "VALIDATION_ERROR"


def test_chat_rejects_oversized_message():
    """Verify chat endpoint rejects messages exceeding 2000 characters."""
    oversized = "A" * 2001
    response = client.post("/api/v1/chat", json={"message": oversized})
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert "maximum allowed length" in data["message"]


def test_chat_rejects_malformed_json():
    """Verify chat endpoint rejects invalid JSON payloads."""
    response = client.post(
        "/api/v1/chat",
        content="not-json",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


# ------------------------------------------------------------------------------
# 3. Chat Endpoint & Mock Provider Tests
# ------------------------------------------------------------------------------

def test_chat_success_with_mock_provider():
    """Verify valid chat request succeeds with mock LLM provider."""
    original_provider = settings.LLM_PROVIDER
    try:
        settings.LLM_PROVIDER = "mock"
        response = client.post(
            "/api/v1/chat",
            json={"message": "Explain what an NPA loan means.", "conversation_id": "test-conv-001"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["conversation_id"] == "test-conv-001"
        assert data["request_id"].startswith("req-")
        assert "Non-Performing Asset" in data["message"]
        assert data["provider"] == "mock"
    finally:
        settings.LLM_PROVIDER = original_provider


def test_chat_generates_default_conversation_id():
    """Verify conversation_id is automatically generated when omitted."""
    original_provider = settings.LLM_PROVIDER
    try:
        settings.LLM_PROVIDER = "mock"
        response = client.post("/api/v1/chat", json={"message": "What is KYC?"})
        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"].startswith("conv-")
        assert data["request_id"].startswith("req-")
        assert "Know Your Customer" in data["message"]
    finally:
        settings.LLM_PROVIDER = original_provider


# ------------------------------------------------------------------------------
# 4. LLM Error Shielding & Provider Handling Tests
# ------------------------------------------------------------------------------

def test_missing_api_key_returns_structured_error():
    """Verify missing API key returns structured 400 error without crash."""
    original_provider = settings.LLM_PROVIDER
    original_key = settings.LLM_API_KEY
    try:
        settings.LLM_PROVIDER = "anthropic"
        settings.LLM_API_KEY = None
        response = client.post("/api/v1/chat", json={"message": "Test question"})
        assert response.status_code == 400
        detail = response.json().get("detail", {})
        assert detail["error_code"] == "MISSING_API_KEY"
        assert "LLM_API_KEY" in detail["message"]
    finally:
        settings.LLM_PROVIDER = original_provider
        settings.LLM_API_KEY = original_key


@pytest.mark.asyncio
async def test_anthropic_adapter_auth_failure():
    """Verify Anthropic 401 response raises ProviderAuthenticationError."""
    adapter = AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="sk-ant-invalid-dummy-key")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(401, json={"type": "error", "error": {"message": "Invalid API key"}}, request=httpx.Request("POST", adapter.ENDPOINT))
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderAuthenticationError) as exc_info:
            await adapter.generate_response("hello")
        assert "authentication error" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_openai_adapter_timeout_handling():
    """Verify provider timeout triggers ProviderTimeoutError."""
    adapter = OpenAICompatibleProvider(model="gpt-4o-mini", api_key="test-key", timeout=5)
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
        with pytest.raises(ProviderTimeoutError) as exc_info:
            await adapter.generate_response("hello")
        assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_openai_adapter_rate_limit_handling():
    """Verify provider 429 triggers ProviderRateLimitError."""
    adapter = OpenAICompatibleProvider(model="gpt-4o-mini", api_key="test-key")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(429, text="Rate limit reached", request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderRateLimitError) as exc_info:
            await adapter.generate_response("hello")
        assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_malformed_provider_response_handling():
    """Verify malformed JSON from provider triggers ProviderAPIError."""
    adapter = AnthropicProvider(model="claude-3-5-sonnet", api_key="test-key")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(200, json={"unexpected": "structure"}, request=httpx.Request("POST", adapter.ENDPOINT))
        mock_post.return_value = mock_resp
        with pytest.raises(ProviderAPIError) as exc_info:
            await adapter.generate_response("hello")
        assert "malformed" in str(exc_info.value).lower()


def test_no_api_key_leakage_in_error_responses():
    """Verify that dummy API keys are never echoed back in error responses."""
    secret_key = "sk-test-secret-1234567890abcdef"
    original_provider = settings.LLM_PROVIDER
    original_key = settings.LLM_API_KEY
    try:
        settings.LLM_PROVIDER = "anthropic"
        settings.LLM_API_KEY = secret_key
        with patch.object(AnthropicProvider, "generate_response", side_effect=ProviderAuthenticationError("anthropic", f"Unauthorized with key {secret_key}")):
            response = client.post("/api/v1/chat", json={"message": "Test question"})
            assert response.status_code == 401
            raw_text = response.text
            # Confirm raw secret is not leaked in the HTTP response
            assert secret_key not in raw_text or "[REDACTED]" in raw_text
    finally:
        settings.LLM_PROVIDER = original_provider
        settings.LLM_API_KEY = original_key


def test_cors_preflight_and_headers():
    """Verify CORS headers are returned for allowed frontend origins."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    }
    response = client.options("/api/v1/chat", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "POST" in response.headers.get("access-control-allow-methods", "")

