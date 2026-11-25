"""
FinTech Agent — LangGraph Agent Graph (Phase 6)
Builds and compiles the 9-node StateGraph pipeline.

Node wiring (Phase 6):
  START -> input_guardrail
  input_guardrail -> [rejected -> END] | [allowed -> intent_router]
  intent_router   -> [OUT_OF_SCOPE | CLARIFICATION_REQUIRED -> response_composer]
                  -> [QUERY_ONLY | QUERY_AND_SCHEDULE | SCHEDULE_ONLY -> schema_retriever]
  schema_retriever -> query_synthesizer
  query_synthesizer -> mql_policy_validator
  mql_policy_validator -> [VALID -> query_executor] | [INVALID/UNSUPPORTED -> response_composer]
  query_executor -> result_verifier
  result_verifier -> response_composer
  response_composer -> END

Node 9 (schedule_planner) remains an inactive stub.
Protected banking database execution is gated via PHASE6_LIVE_EXECUTION_ENABLED.

Usage:
    from backend.app.agent.graph import agent_graph
    final_state = await agent_graph.ainvoke(initial_state)
"""

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple
from langgraph.graph import END, START, StateGraph

from backend.app.agent.nodes.input_guardrail import input_guardrail_node
from backend.app.agent.nodes.mql_policy_validator import mql_policy_validator_node
from backend.app.agent.nodes.query_executor import query_executor_node
from backend.app.agent.nodes.query_synthesizer import query_synthesizer_node
from backend.app.agent.nodes.request_intent_router import intent_router_node
from backend.app.agent.nodes.response_composer import response_composer_node
from backend.app.agent.nodes.result_verifier import result_verifier_node
from backend.app.agent.nodes.schedule_planner import schedule_planner_node
from backend.app.agent.nodes.schema_retriever import schema_retriever_node
from backend.app.agent.state import AgentState
from backend.app.config import settings
from backend.app.core.deadline import get_active_request_context
from backend.app.core.execution_monitor import execution_monitor, resolve_monitor_node_name
from backend.app.core.logging import logger


def _emit_skipped_nodes(
    state: Dict[str, Any],
    nodes: Iterable[str],
    skip_reason: str,
    route: str,
) -> None:
    """Emits genuine NODE_SKIPPED telemetry when conditional routing bypasses downstream nodes."""
    ctx = get_active_request_context()
    request_id = state.get("request_id") or (ctx.request_id if ctx else None)
    if not request_id:
        return
    conv_id = state.get("thread_id") or (ctx.conversation_id if ctx else None)
    for node_name in nodes:
        execution_monitor.emit(
            "NODE_SKIPPED",
            request_id=request_id,
            conversation_id=conv_id,
            node_name=node_name,
            status="SKIPPED",
            elapsed_ms=0.0,
            details={
                "skip_reason": skip_reason,
                "route": route,
            },
        )


def _infer_policy_category(errors: Optional[List[str]]) -> Optional[str]:
    if not errors:
        return None
    joined = " ".join(str(e).lower() for e in errors)
    if "$out" in joined or "$merge" in joined or "$where" in joined or "prohibited" in joined or "disallowed" in joined:
        return "prohibited_operator_or_stage"
    if "collection" in joined or "allowlist" in joined:
        return "collection_allowlist"
    if "limit" in joined:
        return "terminal_limit_enforcement"
    if "unsupported" in joined:
        return "unsupported_concept"
    if "depth" in joined or "stage" in joined:
        return "complexity_budget"
    return "mql_policy_violation"


def _extract_node_details(canonical_node: str, state: Dict[str, Any], result: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Extracts privacy-safe diagnostic details for the completed node without leaking data rows."""
    res = result or {}
    if canonical_node == "input_guardrail":
        g_status = res.get("guardrail_status") or state.get("guardrail_status") or "allowed"
        return (
            "REJECTED" if g_status == "rejected" else "ALLOWED",
            {
                "guardrail_result": g_status,
                "final_status": res.get("final_status"),
                "rejection_reason": res.get("rejection_reason"),
            },
        )

    if canonical_node == "request_intent_router":
        req_mode = res.get("request_mode") or state.get("request_mode")
        route = "response_composer" if req_mode in ("OUT_OF_SCOPE", "CLARIFICATION_REQUIRED") else "schema_retriever"
        return (
            "COMPLETED",
            {
                "intent_classification": req_mode,
                "intent_reason": res.get("intent_reason"),
                "selected_route": route,
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
            },
        )

    if canonical_node == "schema_retriever":
        schema_ctx = res.get("schema_context") or {}
        cols = res.get("collections_identified") or schema_ctx.get("relevant_collections") or []
        hits = schema_ctx.get("total_hits")
        if hits is None and isinstance(schema_ctx.get("retrieved_documents"), list):
            hits = len(schema_ctx["retrieved_documents"])
        return (
            "COMPLETED",
            {
                "retrieval_status": schema_ctx.get("status", "ok"),
                "selected_collections": [str(c) for c in cols],
                "retrieved_entries_count": hits if hits is not None else len(cols),
            },
        )

    if canonical_node == "query_synthesizer":
        target_col = res.get("target_collection") or res.get("selected_collection")
        pipeline = res.get("generated_pipeline") or res.get("pipeline_spec")
        has_pipeline = isinstance(pipeline, list) and len(pipeline) > 0
        return (
            "COMPLETED",
            {
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
                "synthesis_status": "CANDIDATE_GENERATED" if has_pipeline else "NO_PIPELINE",
                "target_collection": target_col,
                "pipeline_stage_count": len(pipeline) if isinstance(pipeline, list) else 0,
                "is_executable": False,
            },
        )

    if canonical_node == "mql_policy_validator":
        v_status = res.get("validation_status") or "INVALID"
        errors = res.get("validation_errors") or []
        allowed = bool(res.get("is_pipeline_valid") or v_status == "VALID")
        gate_open = bool(settings.PHASE6_LIVE_EXECUTION_ENABLED)
        return (
            v_status,
            {
                "validation_result": v_status,
                "allowed": allowed,
                "rejection_reason": errors[0] if errors else None,
                "policy_category": _infer_policy_category(errors),
                "execution_gate_status": "LIVE_EXECUTION_ENABLED" if gate_open else "GATED_DISABLED",
                "is_executable": bool(allowed and gate_open),
            },
        )

    if canonical_node == "query_executor":
        exec_status = res.get("execution_status") or "UNKNOWN"
        gate_blocked = exec_status in ("GATE_BLOCKED", "SKIPPED", "UNSUPPORTED", "VALIDATION_FAILED")
        executed_db = exec_status in (
            "SUCCESS",
            "SUCCESS_LIMITED",
            "TIMEOUT",
            "CONNECTION_ERROR",
            "AUTH_ERROR",
            "RESULT_OVERSIZED",
            "EXECUTION_ERROR",
        )
        return (
            exec_status,
            {
                "execution_status": exec_status,
                "execution_gate_permitted": not gate_blocked,
                "executed_against_db": executed_db,
                "db_execution_duration_ms": res.get("execution_time_ms"),
                "result_count": res.get("result_row_count"),
                "result_truncated": bool(res.get("result_truncated", False)),
                "skipped_or_blocked_reason": res.get("execution_error") if gate_blocked else None,
            },
        )

    if canonical_node == "result_verifier":
        v_status = res.get("verification_status") or "UNKNOWN"
        r_status = res.get("result_status") or "UNKNOWN"
        accepted = r_status in ("VALID_WITH_DATA", "VALID_EMPTY")
        return (
            v_status,
            {
                "verification_status": v_status,
                "result_status": r_status,
                "accepted": accepted,
                "result_count": res.get("result_row_count"),
                "recovery_or_failure_reason": res.get("interpretation_summary"),
            },
        )

    if canonical_node == "schedule_planner":
        preview = res.get("schedule_preview") or {}
        return (
            "COMPLETED",
            {
                "preview_id": res.get("preview_id") or preview.get("preview_id"),
                "dry_run_status": preview.get("dry_run_status"),
                "phase7_scheduler_enabled": settings.PHASE7_SCHEDULER_ENABLED,
                "phase7_live_registration_enabled": settings.PHASE7_LIVE_REGISTRATION_ENABLED,
            },
        )

    if canonical_node == "response_composer":
        composed = res.get("graph_response") or res.get("formatted_response") or res.get("final_response") or ""
        return (
            "COMPLETED",
            {
                "final_status": res.get("final_status") or state.get("final_status") or "success",
                "response_length": len(str(composed)),
            },
        )

    return ("COMPLETED", {})


def _instrument_node(
    graph_node_name: str,
    node_fn: Callable[[AgentState], Awaitable[Dict[str, Any]]],
) -> Callable[[AgentState], Awaitable[Dict[str, Any]]]:
    """Wraps a real LangGraph node with non-blocking lifecycle instrumentation & deadline check."""
    canonical_node = resolve_monitor_node_name(graph_node_name)

    async def _wrapped(state: AgentState) -> Dict[str, Any]:
        ctx = get_active_request_context()
        request_id = state.get("request_id") or (ctx.request_id if ctx else None)
        conv_id = state.get("thread_id") or (ctx.conversation_id if ctx else None)

        if ctx and ctx.deadline:
            ctx.deadline.check_deadline(canonical_node)

        if request_id:
            execution_monitor.emit(
                "NODE_STARTED",
                request_id=request_id,
                conversation_id=conv_id,
                node_name=canonical_node,
                status="STARTED",
                details={"graph_node": graph_node_name},
            )

        t0 = time.monotonic()
        try:
            result = await node_fn(state)
            elapsed_ms = (time.monotonic() - t0) * 1000
            if request_id:
                status_label, details = _extract_node_details(canonical_node, state, result)
                execution_monitor.emit(
                    "NODE_COMPLETED",
                    request_id=request_id,
                    conversation_id=conv_id,
                    node_name=canonical_node,
                    status=status_label,
                    elapsed_ms=elapsed_ms,
                    details=details,
                )
            return result
        except asyncio.CancelledError:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if request_id:
                execution_monitor.emit(
                    "NODE_FAILED",
                    request_id=request_id,
                    conversation_id=conv_id,
                    node_name=canonical_node,
                    status="CANCELLED",
                    elapsed_ms=elapsed_ms,
                    details={"error_code": "REQUEST_CANCELLED", "error_message": "Execution cancelled."},
                )
            raise
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            if request_id:
                execution_monitor.emit(
                    "NODE_FAILED",
                    request_id=request_id,
                    conversation_id=conv_id,
                    node_name=canonical_node,
                    status="FAILED",
                    elapsed_ms=elapsed_ms,
                    details={
                        "error_code": getattr(exc, "error_code", type(exc).__name__),
                        "error_message": str(exc)[:300],
                    },
                )
            raise

    _wrapped.__name__ = getattr(node_fn, "__name__", graph_node_name)
    return _wrapped


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_guardrail(state: AgentState) -> str:
    """Route after Node 1: rejected -> END, allowed -> intent_router."""
    if state.get("guardrail_status") == "rejected":
        reason = state.get("rejection_reason") or "Request rejected by input guardrail."
        _emit_skipped_nodes(
            state,
            (
                "request_intent_router",
                "schema_retriever",
                "query_synthesizer",
                "mql_policy_validator",
                "query_executor",
                "result_verifier",
                "schedule_planner",
                "response_composer",
            ),
            skip_reason=reason,
            route="end_rejected",
        )
        return "end_rejected"
    return "intent_router"


def route_after_intent(state: AgentState) -> str:
    """Route after Node 2: direct-to-composer vs proceed through synthesis pipeline."""
    mode = state.get("request_mode", "")
    if mode in ("OUT_OF_SCOPE", "CLARIFICATION_REQUIRED"):
        _emit_skipped_nodes(
            state,
            (
                "schema_retriever",
                "query_synthesizer",
                "mql_policy_validator",
                "query_executor",
                "result_verifier",
                "schedule_planner",
            ),
            skip_reason=f"Direct composition route for intent '{mode}'",
            route="response_composer",
        )
        # Short-circuit directly to response composer for clean user messages
        return "response_composer"
    # QUERY_ONLY, QUERY_AND_SCHEDULE, SCHEDULE_ONLY -> schema retrieval
    return "schema_retriever"


def route_after_validator(state: AgentState) -> str:
    """Route after Node 5: proceed to execution if valid; bypass if rejected/unsupported.
    SCHEDULE_ONLY requests bypass immediate query execution and proceed directly to schedule_planner.
    """
    if state.get("validation_status") == "VALID":
        mode = state.get("request_mode", "")
        if mode == "SCHEDULE_ONLY":
            _emit_skipped_nodes(
                state,
                ("query_executor", "result_verifier"),
                skip_reason="SCHEDULE_ONLY request bypasses immediate database query execution",
                route="schedule_planner",
            )
            return "schedule_planner"
        return "query_executor"
    v_status = state.get("validation_status") or "INVALID"
    _emit_skipped_nodes(
        state,
        ("query_executor", "result_verifier", "schedule_planner"),
        skip_reason=f"Bypassed execution because MQL validation status is '{v_status}'",
        route="response_composer",
    )
    return "response_composer"


def route_after_verifier(state: AgentState) -> str:
    """Route after Node 7:
    If retryable error (transient connection error or timeout) and retry budget remains -> query_executor.
    If schedule mode (SCHEDULE_ONLY or QUERY_AND_SCHEDULE) -> schedule_planner (Node 9).
    Otherwise (QUERY_ONLY, terminal error, or retries exhausted) -> response_composer.
    Guarantees bounded retry without altering the already-validated read-only pipeline.
    """
    result_status = state.get("result_status")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", settings.MAX_RETRY_ATTEMPTS)

    if result_status == "RETRYABLE_ERROR" and retry_count <= max_retries:
        return "query_executor"

    mode = state.get("request_mode", "")
    if mode in ("SCHEDULE_ONLY", "QUERY_AND_SCHEDULE"):
        return "schedule_planner"

    _emit_skipped_nodes(
        state,
        ("schedule_planner",),
        skip_reason=f"Not a scheduled report request (request_mode='{mode or 'QUERY_ONLY'}')",
        route="response_composer",
    )
    return "response_composer"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_agent_graph() -> StateGraph:
    """Construct and compile the 9-node LangGraph agent pipeline for Phase 7.

    Returns:
        A compiled StateGraph ready for ainvoke().
    """
    builder = StateGraph(AgentState)

    # Register all 9 architectural nodes wrapped with genuine execution telemetry
    builder.add_node("input_guardrail", _instrument_node("input_guardrail", input_guardrail_node))
    builder.add_node("intent_router", _instrument_node("intent_router", intent_router_node))
    builder.add_node("schema_retriever", _instrument_node("schema_retriever", schema_retriever_node))
    builder.add_node("query_synthesizer", _instrument_node("query_synthesizer", query_synthesizer_node))
    builder.add_node("mql_policy_validator", _instrument_node("mql_policy_validator", mql_policy_validator_node))
    builder.add_node("query_executor", _instrument_node("query_executor", query_executor_node))
    builder.add_node("result_verifier", _instrument_node("result_verifier", result_verifier_node))
    builder.add_node("response_composer", _instrument_node("response_composer", response_composer_node))
    builder.add_node("schedule_planner", _instrument_node("schedule_planner", schedule_planner_node))

    # --- Entry point --------------------------------------------------------
    builder.add_edge(START, "input_guardrail")

    # --- Node 1 routing -----------------------------------------------------
    builder.add_conditional_edges(
        "input_guardrail",
        route_after_guardrail,
        {
            "end_rejected": END,
            "intent_router": "intent_router",
        },
    )

    # --- Node 2 routing -----------------------------------------------------
    builder.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {
            "response_composer": "response_composer",  # OUT_OF_SCOPE / CLARIFICATION
            "schema_retriever": "schema_retriever",    # Data / schedule queries
        },
    )

    # --- Phase 6 & 7 pipeline stages: Schema -> Synthesis -> Validation -> Execution -> Verification -> Schedule -> Composer ---
    builder.add_edge("schema_retriever", "query_synthesizer")
    builder.add_edge("query_synthesizer", "mql_policy_validator")
    builder.add_conditional_edges(
        "mql_policy_validator",
        route_after_validator,
        {
            "query_executor": "query_executor",
            "schedule_planner": "schedule_planner",
            "response_composer": "response_composer",
        },
    )
    builder.add_edge("query_executor", "result_verifier")
    builder.add_conditional_edges(
        "result_verifier",
        route_after_verifier,
        {
            "query_executor": "query_executor",
            "schedule_planner": "schedule_planner",
            "response_composer": "response_composer",
        },
    )
    builder.add_edge("schedule_planner", "response_composer")

    # --- Terminal node ------------------------------------------------------
    builder.add_edge("response_composer", END)

    compiled = builder.compile()
    logger.info("FinTech Agent LangGraph pipeline compiled successfully (Phase 7 - All 9 Nodes active).")
    return compiled


# ---------------------------------------------------------------------------
# Singleton instance — imported by chat route
# ---------------------------------------------------------------------------

agent_graph = build_agent_graph()
