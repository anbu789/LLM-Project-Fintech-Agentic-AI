"""
FinTech Agent — LangGraph Agent Graph (Phase 5)
Builds and compiles the 9-node StateGraph pipeline.

Node wiring (Phase 5):
  START -> input_guardrail
  input_guardrail -> [rejected -> END] | [allowed -> intent_router]
  intent_router   -> [OUT_OF_SCOPE | CLARIFICATION_REQUIRED -> response_composer]
                  -> [QUERY_ONLY | QUERY_AND_SCHEDULE | SCHEDULE_ONLY -> schema_retriever]
  schema_retriever -> query_synthesizer
  query_synthesizer -> mql_policy_validator
  mql_policy_validator -> response_composer
  response_composer -> END

Nodes 6, 7, and 9 are present in the node registry as future-phase stubs.
THIS GRAPH EXECUTES ZERO MONGODB QUERIES IN PHASE 5.

Usage:
    from backend.app.agent.graph import agent_graph
    final_state = await agent_graph.ainvoke(initial_state)
"""

from langgraph.graph import END, START, StateGraph

from backend.app.agent.nodes.input_guardrail import input_guardrail_node
from backend.app.agent.nodes.mql_policy_validator import mql_policy_validator_node
from backend.app.agent.nodes.query_executor import query_executor_stub
from backend.app.agent.nodes.query_synthesizer import query_synthesizer_node
from backend.app.agent.nodes.request_intent_router import intent_router_node
from backend.app.agent.nodes.response_composer import response_composer_node
from backend.app.agent.nodes.result_verifier import result_verifier_stub
from backend.app.agent.nodes.schedule_planner import schedule_planner_stub
from backend.app.agent.nodes.schema_retriever import schema_retriever_node
from backend.app.agent.state import AgentState
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


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_agent_graph() -> StateGraph:
    """Construct and compile the 9-node LangGraph agent pipeline for Phase 5.

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
    builder.add_node("query_executor", query_executor_stub)              # Node 6 — Phase 6 stub
    builder.add_node("result_verifier", result_verifier_stub)            # Node 7 — Phase 6 stub
    builder.add_node("response_composer", response_composer_node)        # Node 8 — Phase 5 integrated
    builder.add_node("schedule_planner", schedule_planner_stub)          # Node 9 — future stub

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

    # --- Phase 5 pipeline stages: Schema -> Synthesis -> Validation -> Composer ---
    builder.add_edge("schema_retriever", "query_synthesizer")
    builder.add_edge("query_synthesizer", "mql_policy_validator")
    builder.add_edge("mql_policy_validator", "response_composer")

    # --- Terminal node ------------------------------------------------------
    builder.add_edge("response_composer", END)

    compiled = builder.compile()
    logger.info("FinTech Agent LangGraph pipeline compiled successfully (Phase 5 - Nodes 1-5 active).")
    return compiled


# ---------------------------------------------------------------------------
# Singleton instance — imported by chat route
# ---------------------------------------------------------------------------

agent_graph = build_agent_graph()
