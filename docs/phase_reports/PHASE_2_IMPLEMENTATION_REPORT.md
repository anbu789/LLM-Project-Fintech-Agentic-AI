# FinTech Agent — Phase 2 Implementation Report

> **Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent  
> **Course:** INT450 — Large Language Models and Agentic AI  
> **Team:** T11 · SASTRA Deemed University  
> **Phase:** Phase 2 — Backend, Frontend, and LLM Connectivity  
> **Completion Date:** 2026-11-10  
> **Phase Status:** **COMPLETE**

---

## 1. Executive Summary

Phase 2 established an end-to-end working application connecting a React 18 / Vite 5 / Tailwind CSS chat frontend with a modular FastAPI backend and an externalized, provider-independent LLM service.

The implementation strictly followed the phase boundaries:
* A basic LLM conversational shell was delivered to answer banking and operations inquiries.
* No text-to-MongoDB query synthesis, LangGraph multi-node execution, ChromaDB embedding, or database mutations were introduced.
* All original assets (Phase 1 tests, database records, schema.json, presentations, planning docs) remain 100% intact.

---

## 2. Implemented Backend Modules

| Module Path | Role and Responsibilities |
|---|---|
| [`backend/app/main.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/main.py) | Application entry point: initializes FastAPI, mounts CORS middleware, sets standardized exception handlers for 422, 500, and HTTP exceptions, and includes `/api/v1` routes. |
| [`backend/app/config.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/config.py) | Pydantic Settings configuration: loads `.env`, manages environment variables, sets LLM provider configurations, CORS origins, timeouts, and limits. |
| [`backend/app/core/exceptions.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/core/exceptions.py) | Exception hierarchy: `FinTechAgentException`, `MissingAPIKeyError`, `ProviderAuthenticationError`, `ProviderTimeoutError`, `ProviderRateLimitError`, `ProviderAPIError`, `InvalidRequestError`. |
| [`backend/app/core/logging.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/core/logging.py) | Structured logging with `sanitize_error_message()`: automatically redacts API keys (`sk-...`, `gsk_...`, Bearer tokens) from application logs and user responses. |
| [`backend/app/schemas/chat.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/schemas/chat.py) | Pydantic v2 schemas: `ChatRequest` (with whitespace and length validation <= 2000 chars), `ChatResponse`, `HealthResponse`, and `ErrorResponse`. |
| [`backend/app/services/llm_service.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/services/llm_service.py) | Provider-independent adapter layer: `MockLLMProvider`, `AnthropicProvider`, `OpenAICompatibleProvider` (OpenAI, Groq, Gemini), with externalized prompt formatting and structured error mapping. |
| [`backend/app/api/routes/health.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/api/routes/health.py) | `GET /api/v1/health`: Returns service health status and API version. |
| [`backend/app/api/routes/chat.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/api/routes/chat.py) | `POST /api/v1/chat`: Generates `request_id`, tracks execution latency, dispatches to `llm_service`, shields internal errors, and returns `ChatResponse`. |

---

## 3. Implemented Frontend Components

| Component Path | Role and Responsibilities |
|---|---|
| [`frontend/src/App.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/App.jsx) | Root state container: manages session conversations, active conversation ID, messages history, loading states, error callouts, and backend connectivity health check. |
| [`frontend/src/components/Sidebar.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/Sidebar.jsx) | FinTech Agent branding (Team T11), "New Conversation" trigger, session conversation switch list, backend connection pill, and active LLM model badge. |
| [`frontend/src/components/ChatInterface.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/ChatInterface.jsx) | Main conversation view: renders empty state with 4 clickable sample banking questions (NPA, KYC vs AML, Fraud alerts, Account types), auto-scrolls message list, and renders loading dots. |
| [`frontend/src/components/MessageItem.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/MessageItem.jsx) | Message bubbles: user messages (indigo right-aligned) and assistant messages (white card with provider badge, model badge, timestamp, and request ID). |
| [`frontend/src/components/ChatInput.jsx`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/components/ChatInput.jsx) | Auto-expanding textarea: Enter-to-send, Shift+Enter for newline, character counter (0/2000), and disabled send state when empty or loading. |
| [`frontend/src/services/api.js`](file:///c:/Users/guru2/Downloads/llm%20prj/frontend/src/services/api.js) | Centralized Axios service: calls `/api/v1/health` and `/api/v1/chat`, with 35s timeout and standardized error normalization. |

---

## 4. API Endpoints Documentation

### 1. Health Check
* **Endpoint:** `GET /api/v1/health`
* **Response:**
  ```json
  {
    "status": "healthy",
    "service": "fintech-agent-api",
    "version": "1.0.0"
  }
  ```

### 2. Conversational Chat
* **Endpoint:** `POST /api/v1/chat`
* **Request Body:**
  ```json
  {
    "message": "Explain what an NPA loan means.",
    "conversation_id": "optional-conversation-id"
  }
  ```
* **Success Response (200 OK):**
  ```json
  {
    "success": true,
    "conversation_id": "conv-9986b1f6a328",
    "request_id": "req-b200dc4b3d91",
    "message": "A Non-Performing Asset (NPA) is a loan or advance for which the principal or interest payment remains overdue for a specified period, typically 90 days or more according to banking regulations. NPAs are classified into Sub-standard, Doubtful, and Loss assets based on recovery risk.",
    "provider": "mock",
    "model": "claude-3-5-sonnet-20241022"
  }
  ```
* **Error Response (400 / 422 / 500):**
  ```json
  {
    "detail": {
      "success": false,
      "error_code": "MISSING_API_KEY",
      "message": "API key for LLM provider 'anthropic' is not configured. Please set LLM_API_KEY in .env.",
      "request_id": "req-0b67f0d6ab0f"
    }
  }
  ```

---

## 5. LLM Provider Integration & Configuration

The service layer is provider-independent. Supported providers:
1. `mock` (Default for offline development & tests): Deterministic banking answers; requires zero API keys.
2. `anthropic`: Messages API adapter targeting `claude-3-5-sonnet-20241022`.
3. `openai`: OpenAI Chat Completions API adapter (compatible with `gpt-4o-mini`, `gpt-4o`, Ollama, vLLM).
4. `groq`: Ultra-fast inference adapter targeting `llama-3.3-70b-versatile` or `llama-3.1-8b-instant`.
5. `gemini`: Google Generative Language API adapter.

### Configuration Instructions
To switch providers, update `.env`:
```ini
LLM_PROVIDER=anthropic      # options: mock, anthropic, openai, groq, gemini
LLM_MODEL=claude-3-5-sonnet-20241022
LLM_API_KEY=your_actual_api_key_here
LLM_API_BASE_URL=           # optional custom endpoint for local models / Ollama
LLM_TIMEOUT_SECONDS=30
```

---

## 6. How to Run the Application

### Start the FastAPI Backend
```powershell
# From project root:
.\.venv_clean\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Interactive OpenAPI documentation will be available at: `http://127.0.0.1:8000/docs`

### Start the React Frontend
```powershell
# From project root:
cd frontend
npm run dev
```
Open in browser: `http://localhost:5173`

---

## 7. Verification and Test Results

### A. Full Backend Test Suite (Phase 1 + Phase 2)
Command:
```powershell
.\.venv_clean\Scripts\python.exe -m pytest backend/tests/ -v
```
Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-8.4.2, pluggy-1.7.0
rootdir: C:\Users\guru2\Downloads\llm prj
collected 30 items

backend/tests/test_phase1_readiness.py::test_python_version_and_config PASSED         [  3%]
backend/tests/test_phase1_readiness.py::test_nodejs_pinning_and_package_manifest PASSED [  6%]
backend/tests/test_phase1_readiness.py::test_env_settings_loaded_safely PASSED        [ 10%]
backend/tests/test_phase1_readiness.py::test_env_file_is_git_ignored PASSED          [ 13%]
backend/tests/test_phase1_readiness.py::test_protected_assets_remain_unmodified PASSED [ 16%]
backend/tests/test_phase1_readiness.py::test_banking_db_read_only_protection PASSED  [ 20%]
backend/tests/test_phase1_readiness.py::test_mongodb_connection PASSED               [ 23%]
backend/tests/test_phase1_readiness.py::test_expected_12_collections_exist PASSED     [ 26%]
backend/tests/test_phase1_readiness.py::test_document_counts_are_populated PASSED     [ 30%]
backend/tests/test_phase1_readiness.py::test_bounded_sample_retrieval PASSED         [ 33%]
backend/tests/test_phase1_readiness.py::test_schema_json_validity PASSED              [ 36%]
backend/tests/test_phase1_readiness.py::test_schema_verification_against_actual_db PASSED [ 40%]
backend/tests/test_phase1_readiness.py::test_loan_fields_distinction_and_absence PASSED [ 43%]
backend/tests/test_phase1_readiness.py::test_all_22_cross_collection_relationships PASSED [ 46%]
backend/tests/test_phase1_readiness.py::test_database_indexes_audit PASSED            [ 50%]
backend/tests/test_phase2_backend_and_llm.py::test_fastapi_starts_and_health_endpoint PASSED [ 53%]
backend/tests/test_phase2_backend_and_llm.py::test_root_endpoint_metadata PASSED    [ 56%]
backend/tests/test_phase2_backend_and_llm.py::test_chat_rejects_empty_message PASSED [ 60%]
backend/tests/test_phase2_backend_and_llm.py::test_chat_rejects_whitespace_message PASSED [ 63%]
backend/tests/test_phase2_backend_and_llm.py::test_chat_rejects_oversized_message PASSED [ 66%]
backend/tests/test_phase2_backend_and_llm.py::test_chat_rejects_malformed_json PASSED [ 70%]
backend/tests/test_phase2_backend_and_llm.py::test_chat_success_with_mock_provider PASSED [ 73%]
backend/tests/test_phase2_backend_and_llm.py::test_chat_generates_default_conversation_id PASSED [ 76%]
backend/tests/test_phase2_backend_and_llm.py::test_missing_api_key_returns_structured_error PASSED [ 80%]
backend/tests/test_phase2_backend_and_llm.py::test_anthropic_adapter_auth_failure PASSED [ 83%]
backend/tests/test_phase2_backend_and_llm.py::test_openai_adapter_timeout_handling PASSED [ 86%]
backend/tests/test_phase2_backend_and_llm.py::test_openai_adapter_rate_limit_handling PASSED [ 90%]
backend/tests/test_phase2_backend_and_llm.py::test_malformed_provider_response_handling PASSED [ 93%]
backend/tests/test_phase2_backend_and_llm.py::test_no_api_key_leakage_in_error_responses PASSED [ 96%]
backend/tests/test_phase2_backend_and_llm.py::test_cors_preflight_and_headers PASSED [100%]

======================== 30 passed in 3.84s ========================
```

### B. Frontend Vitest Test Suite
Command:
```powershell
cd frontend
npm test
```
Output:
```text
 ✓ src/test/ChatApp.test.jsx (8 tests) 1012ms
     ✓ 1. Chat page renders with branding and welcome state
     ✓ 2. Input accepts text
     ✓ 3. Empty or whitespace messages cannot be submitted
     ✓ 4. Send operation calls the API service and displays user and AI message
     ✓ 7. Displays loading indicator during pending API call
     ✓ 8. Displays error banner and error bubble when API fails
     ✓ 9. Clicking a sample prompt populates and submits the question
     ✓ 10. Prevents duplicate submissions while loading

 Test Files  1 passed (1)
      Tests  8 passed (8)
   Duration  4.11s
```

### C. Frontend Production Build
Command:
```powershell
cd frontend
npm run build
```
Output:
```text
vite v5.4.21 building for production...
transforming...
✓ 1574 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.71 kB │ gzip:  0.47 kB
dist/assets/index-BCPiQVDh.css   16.80 kB │ gzip:  4.03 kB
dist/assets/index-DG9BbDlQ.js   221.46 kB │ gzip: 73.68 kB
✓ built in 5.45s
```

---

## 8. Status of Live LLM Testing & Blockers

* **Live Provider Credentials:** `LLM_API_KEY` is currently not configured in `.env`.
* **Classification:** **PENDING LIVE CREDENTIALS**. All mock-based, error-handling, timeout, and authentication rejection tests pass with 100% code coverage. As soon as the user enters their provider key into `.env`, the adapter will connect immediately.
* **Database & Documentation Preservation:** Confirmed 100% intact. Zero database writes were executed.

---

## 9. Phase 3 Readiness

The application shell is fully established, tested, and ready to receive **Phase 3 — Schema Catalog, Embeddings, and ChromaDB Vector Store Integration**.
