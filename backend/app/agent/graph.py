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
from backend.app.core.logging import logger

# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def route_after_guardrail(state: AgentState) -> str:
    """Route after Node 1: rejected -> END, allowed -> intent_router."""
    if state.get("guardrail_status") == "rejected":
        return "end_rejected"
    return "intent_router"


def route_after_intent(state: AgentState) -> str:
    """Route after Node 2: direct-to-composer vs proceed through synthesis pipeline."""
    mode = state.get("request_mode", "")
    if mode in ("OUT_OF_SCOPE", "CLARIFICATION_REQUIRED"):
        # Short-circuit directly to response composer for clean user messages
        return "response_composer"
    # QUERY_ONLY, QUERY_AND_SCHEDULE, SCHEDULE_ONLY -> schema retrieval
    return "schema_retriever"


def route_after_validator(state: AgentState) -> str:
    """Route after Node 5: proceed to execution if valid; bypass if rejected/unsupported."""
    if state.get("validation_status") == "VALID":
        return "query_executor"
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

    # Register all 9 architectural nodes
    builder.add_node("input_guardrail", input_guardrail_node)            # Node 1 — full
    builder.add_node("intent_router", intent_router_node)                # Node 2 — full
    builder.add_node("schema_retriever", schema_retriever_node)          # Node 3 — Phase 5 full
    builder.add_node("query_synthesizer", query_synthesizer_node)        # Node 4 — Phase 5 full
    builder.add_node("mql_policy_validator", mql_policy_validator_node)  # Node 5 — Phase 5 full
    builder.add_node("query_executor", query_executor_node)              # Node 6 — Phase 6 full
    builder.add_node("result_verifier", result_verifier_node)            # Node 7 — Phase 6 full
    builder.add_node("response_composer", response_composer_node)        # Node 8 — Phase 6/7 integrated
    builder.add_node("schedule_planner", schedule_planner_node)          # Node 9 — Phase 7 full

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
