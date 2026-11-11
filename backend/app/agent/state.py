"""
FinTech Agent — LangGraph Agent State (Phase 4)
Defines the shared TypedDict state passed through all 9 pipeline nodes,
plus RequestMode and ResultStatus Literal types from the system architecture.

Reference: SYSTEM_ARCHITECTURE_UPDATED.md Section 10 — Agent State Definition.
"""

from typing import Any, Literal, Optional, TypedDict

# ---------------------------------------------------------------------------
# Canonical mode constants (Section 2.2 of architecture doc)
# ---------------------------------------------------------------------------

RequestMode = Literal[
    "QUERY_ONLY",
    "QUERY_AND_SCHEDULE",
    "SCHEDULE_ONLY",
    "CLARIFICATION_REQUIRED",
    "OUT_OF_SCOPE",
]

ResultStatus = Literal[
    "VALID_WITH_DATA",
    "VALID_EMPTY",
    "RETRYABLE_ERROR",
    "TERMINAL_FAILURE",
    "EXECUTION_GATE_BLOCKED",
    "SUCCESS_WITH_DATA",
    "SUCCESS_EMPTY",
    "SUCCESS_LIMITED",
    "RESULT_OVERSIZED",
    "TIMEOUT",
    "CONNECTION_ERROR",
    "AUTH_ERROR",
    "UNSUPPORTED",
    "VALIDATION_FAILED",
    "INVALID_RESULT",
    "stub",
]


# ---------------------------------------------------------------------------
# Full agent state — all 9 nodes share this structure
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """Shared mutable state passed through the LangGraph pipeline.

    Fields are populated progressively by each node.  total=False means no
    field is required at construction time — nodes must guard against missing
    keys with .get().
    """

    # ---- Request identity and input ----------------------------------------
    request_id: str
    user_id: str
    session_id: str
    thread_id: str
    natural_language_query: str

    # ---- Shared timing and retry -------------------------------------------
    request_started_at: str           # ISO 8601 UTC string
    request_deadline: str             # ISO 8601 UTC deadline string
    remaining_time_ms: int
    retry_count: int
    max_retries: int
    all_attempts: list[dict[str, Any]]

    # ---- Node 1 — Input Guardrail ------------------------------------------
    guardrail_status: str             # "allowed" | "rejected"
    rejection_reason: Optional[str]

    # ---- Node 2 — Request Intent Router ------------------------------------
    request_mode: RequestMode
    intent_reason: str
    query_description: Optional[str]

    # ---- Node 3 — Schema Retriever -----------------------------------------
    schema_context: dict[str, Any]
    collections_identified: list[str]
    schema_version: Optional[str]
    embedding_model: Optional[str]

    # ---- Node 4 — Query Synthesizer ----------------------------------------
    generated_pipeline: Optional[list[dict[str, Any]]]
    target_collection: Optional[str]
    selected_collection: Optional[str]
    pipeline_spec: Optional[list[dict[str, Any]]]
    query_parameters: dict[str, Any]
    temporal_spec: Optional[dict[str, Any]]
    query_explanation: Optional[str]
    assumptions_made: list[str]

    # ---- Node 5 — MQL Policy Validator -------------------------------------
    validation_status: str
    validation_errors: list[str]
    validation_warnings: list[str]
    is_pipeline_valid: bool
    query_plan_summary: Optional[dict[str, Any]]

    # ---- Node 6 — Read-only Query Executor ---------------------------------
    raw_results: Optional[list[dict[str, Any]]]
    execution_time_ms: Optional[int]
    result_row_count: Optional[int]
    execution_error: Optional[str]
    execution_status: Optional[str]
    result_truncated: bool
    dry_run: bool
    test_db: Optional[Any]
    mock_db: Optional[Any]

    # ---- Node 7 — Result Verifier and Recovery -----------------------------
    result_status: ResultStatus
    verification_status: Optional[str]
    verified_results: Optional[list[dict[str, Any]]]
    correction_reason: Optional[str]
    semantic_verification: Optional[dict[str, Any]]
    interpretation_summary: Optional[str]

    # ---- Node 8 — Response Composer ----------------------------------------
    formatted_response: Optional[str]
    final_response: Optional[str]
    pipeline_explanation: Optional[str]
    safe_result_summary: Optional[dict[str, Any]]

    # ---- Node 9 — Schedule Planner and Registrar ---------------------------
    schedule_spec: Optional[dict[str, Any]]
    schedule_approved: bool
    schedule_job_id: Optional[str]
    preview_id: Optional[str]
    schedule_preview: Optional[dict[str, Any]]
    cron_expression: Optional[str]
    timezone: Optional[str]
    next_run_times: Optional[list[str]]
    delivery_spec: Optional[dict[str, Any]]
    idempotency_key: Optional[str]
    is_api_request: Optional[bool]
    is_untrusted: Optional[bool]

    # ---- Clarification handling --------------------------------------------
    clarification_question: Optional[str]
    pending_user_input: Optional[str]

    # ---- Audit trail -------------------------------------------------------
    trace: list[dict[str, Any]]
    final_status: str
    error_message: Optional[str]

    # ---- Conversation context (Phase 4 addition) ---------------------------
    conversation_history: list[dict[str, Any]]

    # ---- Provider attribution (Multi-provider fallback) -------------------
    selected_provider: Optional[str]
    llm_provider: Optional[str]
    llm_model: Optional[str]

    # ---- Final graph response (populated by Node 8) -----------------------
    graph_response: Optional[str]
