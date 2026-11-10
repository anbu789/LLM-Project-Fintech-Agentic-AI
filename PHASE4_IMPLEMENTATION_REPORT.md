# FinTech Agent — Phase 4 Implementation Report
## Natural Language Understanding, Intent Detection & Conversation Handling

**Course:** INT450 — Large Language Models and Agentic AI  
**Author:** Senior Backend Engineer & LLM Systems Architect  
**Date:** November 10, 2026  
**Implementation Milestone:** Phase 4  
**Status:** COMPLETE — PHASE 4 READY FOR PHASE 5

---

## 1. Executive Summary

Phase 4 of the **FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent for Banking Operations** project has been implemented and verified. The objective of Phase 4 is to establish the stateful LangGraph agentic pipeline, implement deterministic security guardrails (Node 1), structured LLM intent routing (Node 2), multi-turn conversation handling, and safe informational response composition (Node 8), while strictly stubbing future query generation and execution nodes (Nodes 3–7, 9) without database access.

### Key Milestones Achieved
- **LangGraph Agent Pipeline (`backend/app/agent/`):** Full 9-node `StateGraph` compiled and operational.
- **Node 1 (Input Guardrail):** Deterministic, 100% LLM-free safety gate blocking empty queries, oversized payloads (>2,000 chars), prompt injections, credential/secret extraction attempts, and destructive database operations.
- **Node 2 (Request Intent Router):** Structured intent classification supporting all 5 canonical `RequestMode` types (`QUERY_ONLY`, `QUERY_AND_SCHEDULE`, `SCHEDULE_ONLY`, `CLARIFICATION_REQUIRED`, `OUT_OF_SCOPE`) validated with Pydantic (`IntentClassification`). Includes deterministic keyword engine for mock testing and structured JSON prompting for external LLMs.
- **Node 3–7, 9 (Future-Phase Stubs):** Safe interfaces implemented. Strictly verified to perform **no** MongoDB database queries, mutations, or ChromaDB vector operations.
- **Node 8 (Response Composer):** Assembles tailored informational and clarification responses based on detected mode and preserves legacy banking terminology responses.
- **API & Schema Integration (`/api/v1/chat`):** Seamless LangGraph dispatch with backwards-compatible `ChatResponse` schema additions (`intent`, `request_mode`, `guardrail_status`, `intent_reason`).
- **Test Suite Results:**
  - **129/129 backend tests passing** (96 pre-existing tests + 33 new Phase 4 tests).
  - **8/8 frontend tests passing**.
  - **Frontend production build:** Successful (zero errors).
  - **Banking Database Integrity:** Exactly 19,120 documents across 12 collections preserved with 0 mutations.

---

## 2. Architecture & File Inventory

The Phase 4 implementation adheres strictly to `SYSTEM_ARCHITECTURE_UPDATED.md` (Sections 4, 10, 11) and `IMPLEMENTATION_PLAN (1).md`.

### New Agent Module Directory (`backend/app/agent/`)

```
backend/app/agent/
├── __init__.py                      # Agent package initialization
├── state.py                         # AgentState TypedDict, RequestMode, ResultStatus
├── graph.py                         # 9-node StateGraph assembly, compilation & routing
├── nodes/
│   ├── __init__.py
│   ├── input_guardrail.py           # Node 1: Deterministic safety gate (Full)
│   ├── request_intent_router.py     # Node 2: Structured intent router (Full)
│   ├── schema_retriever.py          # Node 3: Schema retrieval placeholder (Stub)
│   ├── query_synthesizer.py         # Node 4: MQL synthesis placeholder (Stub)
│   ├── mql_policy_validator.py      # Node 5: Policy validation placeholder (Stub)
│   ├── query_executor.py            # Node 6: Query executor placeholder (Stub - NO DB ACCESS)
│   ├── result_verifier.py           # Node 7: Semantic verifier placeholder (Stub)
│   ├── response_composer.py         # Node 8: Multi-mode response assembler (Phase 4)
│   └── schedule_planner.py          # Node 9: APScheduler registrar placeholder (Stub)
└── prompts/
    ├── __init__.py
    └── intent_classification.py     # System prompt, prompt builder, mock classification rules
```

### Modified System Files
1. `backend/app/schemas/chat.py`: Added backward-compatible optional fields to `ChatResponse` (`intent`, `intent_reason`, `guardrail_status`, `request_mode`).
2. `backend/app/api/routes/chat.py`: Replaced direct `llm_service.ask()` calls with `agent_graph.ainvoke(initial_state)` dispatch under `RequestDeadline` monitoring, preserving `agent_metadata_db` conversation history persistence and error shielding.
3. `backend/tests/test_phase4_agent.py`: Created 33 comprehensive unit, security, and integration tests.

---

## 3. Node Implementation Details

### Node 1 — Input Guardrail (`input_guardrail.py`)
- **Execution Order:** Always executed first (`START -> input_guardrail`).
- **Nature:** 100% deterministic code; zero LLM calls.
- **Enforcements:**
  1. **Empty/Whitespace Input:** Rejects empty string or whitespace-only messages.
  2. **Length Boundary:** Enforces `settings.MAX_MESSAGE_LENGTH` (2,000 characters).
  3. **Prompt Injection Shielding:** Regex matching for DAN mode, persona adoption ("you are now", "act as", "pretend to be"), system override ("ignore previous instructions", "disregard system"), and jailbreaks.
  4. **Credential Extraction Shielding:** Regex blocking requests for API keys, passwords, database URIs, environment variables, system prompts, or `.env` files.
  5. **Destructive Database Intent:** Regex filtering for collection drops, database deletions, document updates/inserts, and administrative commands (`db.<col>.drop()`, `dropDatabase()`, `deleteMany`, `insert into`).
- **Rejection Path:** Instantly routes to `END` via conditional edge `route_after_guardrail`. The LLM router is never invoked on rejected input.

### Node 2 — Request Intent Router (`request_intent_router.py`)
- **Execution Order:** Executed after Node 1 allows input.
- **Canonical Modes:**
  - `QUERY_ONLY`: User is requesting banking analytics, metrics, or reporting from the database.
  - `QUERY_AND_SCHEDULE`: User requests immediate data query AND recurring schedule/email.
  - `SCHEDULE_ONLY`: User requests future recurring job setup without immediate query.
  - `CLARIFICATION_REQUIRED`: Ambiguous business request, missing filters, or underspecified criteria.
  - `OUT_OF_SCOPE`: Chitchat, greetings, non-banking questions (weather, general knowledge).
- **Validation:** Pydantic model `IntentClassification` strictly validates JSON response schema.
- **Fail-Safe Fallback:** If the LLM generates invalid JSON, times out, or returns an unparseable response, the router falls back to `CLARIFICATION_REQUIRED`. It **never** silently defaults a failed classification to a database query mode.
- **Exception Shielding:** Application errors (`FinTechAgentException`) such as authentication or rate limit errors are re-raised so API middleware returns proper HTTP error codes (400, 401, 429) rather than masking them.
- **Mock Engine:** Fast, deterministic keyword engine for offline local test execution without external API dependencies.

### Nodes 3–7, 9 — Future-Phase Stubs
- Registered in graph topology to complete the 9-node architectural contract.
- Each stub records audit entries in `state["trace"]` explaining that Phase 5/6 implementation is pending.
- **Node 6 (`query_executor.py`):** Verified to contain no PyMongo calls, no database read operations, and no network requests.

### Node 8 — Response Composer (`response_composer.py`)
- Formats appropriate user-facing responses for all 5 `RequestMode` outcomes.
- For `QUERY_ONLY`: Confirms intent, presents query restatement, and explains Phase 5 pipeline generation status.
- For `CLARIFICATION_REQUIRED`: Formats clear prompt asking the user for specific parameters (loan status, branch, time window).
- For `OUT_OF_SCOPE`: Explains system capabilities and suggests valid banking queries.
- Incorporates Phase 2 terminology responses (NPA, KYC, Fraud) when mock provider is active to preserve existing conversational contract.

---

## 4. Agent State Contract

Defined in `backend/app/agent/state.py` using `TypedDict(total=False)`:
```python
class AgentState(TypedDict, total=False):
    request_id: str
    user_id: str
    session_id: str
    thread_id: str
    natural_language_query: str
    request_started_at: str
    request_deadline: str
    remaining_time_ms: int
    retry_count: int
    max_retries: int
    all_attempts: list[dict[str, Any]]
    guardrail_status: str
    rejection_reason: Optional[str]
    request_mode: RequestMode
    intent_reason: str
    query_description: Optional[str]
    schema_context: dict[str, Any]
    collections_identified: list[str]
    schema_version: Optional[str]
    embedding_model: Optional[str]
    generated_pipeline: Optional[list[dict[str, Any]]]
    target_collection: Optional[str]
    query_parameters: dict[str, Any]
    temporal_spec: Optional[dict[str, Any]]
    validation_status: str
    validation_errors: list[str]
    query_plan_summary: Optional[dict[str, Any]]
    raw_results: Optional[list[dict[str, Any]]]
    execution_time_ms: Optional[int]
    result_row_count: Optional[int]
    execution_error: Optional[str]
    result_truncated: bool
    dry_run: bool
    result_status: ResultStatus
    correction_reason: Optional[str]
    semantic_verification: Optional[dict[str, Any]]
    interpretation_summary: Optional[str]
    formatted_response: Optional[str]
    pipeline_explanation: Optional[str]
    safe_result_summary: Optional[dict[str, Any]]
    schedule_spec: Optional[dict[str, Any]]
    schedule_approved: bool
    schedule_job_id: Optional[str]
    cron_expression: Optional[str]
    timezone: Optional[str]
    next_run_times: Optional[list[str]]
    delivery_spec: Optional[dict[str, Any]]
    clarification_question: Optional[str]
    pending_user_input: Optional[str]
    trace: list[dict[str, Any]]
    final_status: str
    error_message: Optional[str]
    conversation_history: list[dict[str, Any]]
    graph_response: Optional[str]
```

---

## 5. Verification Checklist

| Requirement | Status | Evidence |
| :--- | :--- | :--- |
| Deterministic guardrail runs before LLM intent router | ✅ VERIFIED | Node 1 is entry point from START; rejects route straight to END |
| Input guardrail blocks injection, credentials, and drops | ✅ VERIFIED | Tested in `test_phase4_agent.py` across 14 security cases |
| Pydantic-validated structured intent routing | ✅ VERIFIED | `IntentClassification` schema validation verified |
| Ambiguous queries trigger clarification | ✅ VERIFIED | "Show me the loans" routes to `CLARIFICATION_REQUIRED` |
| Safe fallback on LLM parsing error | ✅ VERIFIED | Falls back to `CLARIFICATION_REQUIRED`, never to `QUERY_ONLY` |
| Multi-turn conversation context preserved | ✅ VERIFIED | Context passed to graph and turns persisted in `agent_metadata_db` |
| Zero MongoDB queries in future-phase stubs | ✅ VERIFIED | Verified via Node 6 code audit and test suite |
| All pre-existing tests pass | ✅ VERIFIED | 96/96 original backend tests pass; 129/129 total pass |
| Frontend test suite and production build pass | ✅ VERIFIED | 8/8 tests pass; Vite production build succeeds |
| Banking database unchanged | ✅ VERIFIED | Exactly 19,120 documents across 12 collections verified |
