# FINTECH AGENT — LLM INTEGRATION, QUERY GENERATION & MULTI-PROVIDER FALLBACK EVIDENCE

**Document Classification:** Model Adapter, Prompt Engineering & Generation Reliability Audit  
**Source Code References:**
- LLM Service & Fallback Manager: [`backend/app/services/llm_service.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/services/llm_service.py)
- Configuration & Budget Settings: [`backend/app/config.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/config.py)
- Intent Prompts & Pydantic Schema: [`backend/app/agent/prompts/intent_classification.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/prompts/intent_classification.py)
- Query Synthesis Prompts & Schema: [`backend/app/agent/prompts/query_synthesis.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/prompts/query_synthesis.py)
- Fallback Implementation Report: [`MULTI_PROVIDER_FALLBACK_IMPLEMENTATION_REPORT.md`](file:///c:/Users/guru2/Downloads/llm%20prj/MULTI_PROVIDER_FALLBACK_IMPLEMENTATION_REPORT.md)

---

## 1. Configured Model Inventory and Execution Reality

The FinTech Agent interacts with LLMs through a unified OpenAI-compatible REST interface built with `httpx` (`v0.28.1`).

### Current Active Model Hierarchy (Verified from `.env` and `llm_service.py`):
```
Primary: Google Gemini 3.8 Flash (Cloud)
   │  Base URL: https://generativelanguage.googleapis.com/v1beta/openai
   │  Model ID: gemini-3.8-flash
   ▼  [On Recoverable Failure: HTTP 503, Read Timeout, Connection Drop]
Fallback 1: Groq — GPT-OSS 120B (Cloud)
   │  Base URL: https://api.groq.com/openai/v1
   │  Model ID: openai/gpt-oss-120b
   ▼  [On Recoverable Failure: Groq 503, Missing Key, Timeout]
Fallback 2: Local Ollama — K2 Horizon 3.7B Q3_K_M (Local Loopback / Air-Gapped)
   │  Base URL: http://127.0.0.1:11434/v1
   │  Model ID: hf.co/mradermacher/K2-Horizon-3.7B-i1-GGUF:Q3_K_M
   ▼  [On All Providers Exhausted or Deadline Budget Depleted]
Terminal Controlled Error: LLMFallbackExhaustedError -> HTTP 503 / 504
```

| Hierarchy Tier | Provider | Exact Model Identifier | Base Endpoint URL | Host Type | Auth Headers | Reasoning Effort Parameter |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Primary** | `gemini` | `gemini-3.8-flash` | `https://generativelanguage.googleapis.com/v1beta/openai` | Cloud | `Bearer <KEY>` + `x-goog-api-key` | `low` (Node 2) / `medium` (Node 4) |
| **Fallback 1**| `groq` | `openai/gpt-oss-120b` | `https://api.groq.com/openai/v1` | Cloud | `Bearer <KEY>` + `User-Agent: FinTechAgent/1.0`| N/A |
| **Fallback 2**| `ollama` | `hf.co/mradermacher/K2-Horizon-3.7B-i1-GGUF:Q3_K_M` | `http://127.0.0.1:11434/v1` | Local | None (Local Loopback) | N/A |
| **Testing** | `mock` | `mock-banking-llm` | In-memory | Local | None | None |

> [!NOTE]
> **Documentation vs Config Model Discrepancy:**
> In `backend/app/config.py:34`, the default class field for `LLM_MODEL` is written as `claude-3-5-sonnet-20241022`. However, the active runtime environment (`.env`) explicitly overrides this to `gemini-3.8-flash`. Early test reports referenced Claude 3.5 Sonnet as the design baseline, but the actual deployed cloud provider is Google Gemini via Google AI Studio API.

---

## 2. Shared Deadline Budgeting & Timeout Hierarchy

To guarantee that cascading fallbacks cannot hang the user session or exceed frontend request limits, the multi-provider service enforces strict hierarchical deadline budgeting:

```
[ Frontend Axios Request Timeout: 40.0s ]
      │
      ▼
[ Backend Request Deadline: 30.0s (settings.REQUEST_TIMEOUT_SECONDS) ]
      │
      ▼  (Backend Reserve Buffer: 4.0s for validation, DB execution & formatting)
[ LLM Operation Timeout Ceiling: 24.0s (settings.LLM_OPERATION_TIMEOUT_SECONDS) ]
      │
      ├── Primary Gemini Attempt: 12.0s ceiling (settings.LLM_ATTEMPT_TIMEOUT_SECONDS)
      │     └── If 503/timeout: check remaining budget >= 4.0s (MIN_RETRY_BUDGET_SECONDS)
      ├── Fallback 1 Groq Attempt: min(12.0s, remaining_budget - 1.0s reserve)
      │     └── If failed: check remaining budget >= 4.0s
      └── Fallback 2 Ollama Attempt: remaining_budget - 1.0s reserve
```

### Failure Classification Engine (`is_recoverable_failure`):
The adapter strictly distinguishes between recoverable infrastructure faults and permanent client/auth rejections:
- **Non-Recoverable (Fails immediately without fallback):**
  - `ProviderAuthenticationError` (HTTP 401 / Invalid API key)
  - `MissingAPIKeyError` (Empty API key for primary provider)
  - `asyncio.CancelledError` (User aborted request in frontend)
  - `ProviderQuotaExhaustedError` (HTTP 429 quota exhausted / billing limit)
- **Recoverable (Triggers automatic failover to next provider):**
  - HTTP 503 Service Unavailable / 502 Bad Gateway / 504 Gateway Timeout
  - `httpx.ReadTimeout` / `httpx.ConnectTimeout`
  - `httpx.ConnectError` / Socket reset
  - Transient HTTP 429 concurrency limit (retry-after <= remaining budget)

---

## 3. Prompt Engineering & Structured Output Schemas

LLM generation is restricted exclusively to two specific graph stages:

### 3.1 Node 2: Intent Classification Prompt & Schema
- **Prompt:** [`backend/app/agent/prompts/intent_classification.py:build_intent_classification_prompt`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/prompts/intent_classification.py)
- **System Instructions:** Enforces zero conversational chatter; output must be a single RFC 8259 JSON object conforming to:

```json
{
  "request_mode": "QUERY_ONLY | QUERY_AND_SCHEDULE | SCHEDULE_ONLY | CLARIFICATION_REQUIRED | OUT_OF_SCOPE",
  "intent_reason": "Concise justification for mode selection",
  "query_description": "Clean restatement of banking query intent (null for OUT_OF_SCOPE)",
  "clarification_question": "Required clarification if ambiguous (null otherwise)"
}
```

- **Validation:** Validated via Pydantic model `IntentClassification`. If parsing fails, it safely falls back to `CLARIFICATION_REQUIRED` (never defaults to query execution).

### 3.2 Node 4: Query Synthesis Prompt & Schema
- **Prompt:** [`backend/app/agent/prompts/query_synthesis.py:build_query_synthesis_prompt`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/prompts/query_synthesis.py)
- **System Instructions:** Injects retrieved schema context (collections, fields, join keys). Forbids non-read-only operators (`$out`, `$merge`, `$where`). Explicitly injects warnings for unsupported concepts (e.g. `overdue_amount` -> must use `status == "defaulted"`).
- **Pydantic Contract (`PipelineSynthesisOutput`):**

```python
class PipelineSynthesisOutput(BaseModel):
    target_collection: str
    pipeline: List[Dict[str, Any]]
    explanation: str
    assumptions: List[str] = Field(default_factory=list)
    query_parameters: Dict[str, Any] = Field(default_factory=dict)
```

- **JSON Fence Extraction:** `_extract_json_pipeline` handles leading/trailing conversational text and markdown code fences (` ```json `), extracting only the raw JSON payload for schema validation.

---

## 4. Multi-Turn Conversation Context

Multi-turn context is managed through MongoDB-backed session persistence (`agent_metadata_db.conversations`):
- Node 2 and Node 4 receive up to `MAX_CONVERSATION_HISTORY_TURNS = 10` previous user and assistant turns.
- In follow-up inquiries (e.g., User: *"Filter that to Bangalore"*), the synthesizer merges previous query constraints (e.g., `$match: {status: "active"}`) with new criteria (`$match: {city: "Bangalore"}`).
- Conversation isolation is cryptographically guaranteed: sessions cannot leak across different `user_id` or `session_id` tokens.
