"""
FinTech Agent — Node 4: MongoDB Query Synthesizer (Phase 5, Full Implementation)
Translates natural-language banking requests into candidate MongoDB aggregation pipelines
using strictly the schema context retrieved by Node 3.

Responsibilities:
  1. Receive query description, schema context, and conversation history.
  2. Synthesize candidate aggregation pipeline (via mock engine or LLM).
  3. Validate output shape with Pydantic model (PipelineSynthesisOutput).
  4. Ensure output is pure JSON-compatible dictionaries and lists.
  5. Populate generated_pipeline, target_collection, pipeline_explanation, and query_parameters.
  6. Record audit trace.

CRITICAL SAFETY GUARANTEE:
  THIS NODE NEVER CONNECTS TO OR QUERIES THE BANKING DATABASE.
  No aggregate(), find(), or collection operations are executed.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from backend.app.agent.prompts.query_synthesis import (
    PipelineSynthesisOutput,
    QUERY_SYNTHESIS_SYSTEM_PROMPT,
    build_query_synthesis_prompt,
    mock_synthesize_query,
)
from backend.app.config import settings
from backend.app.core.deadline import (
    get_request_preferred_provider,
    set_request_preferred_provider,
)
from backend.app.core.exceptions import FinTechAgentException
from backend.app.core.logging import logger
from backend.app.services.llm_service import llm_service


def _trace_entry(node: str, status: str, detail: str) -> Dict[str, Any]:
    return {
        "node": node,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _extract_json_pipeline(raw_text: str) -> Optional[PipelineSynthesisOutput]:
    """Parses JSON text into PipelineSynthesisOutput, handling markdown fences."""
    text = raw_text.strip()
    if "```" in text:
        lines = text.splitlines()
        inside = False
        json_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                inside = not inside
                continue
            if inside:
                json_lines.append(line)
        text = "\n".join(json_lines).strip()

    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None

    try:
        data = json.loads(text[start:end])
        return PipelineSynthesisOutput(**data)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


# Exported alias for testing and backwards compatibility
_parse_synthesis_output = _extract_json_pipeline


async def query_synthesizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 4: Synthesize candidate MongoDB aggregation pipeline from schema context.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with generated_pipeline, target_collection,
        pipeline_explanation, and query_parameters.
    """
    request_id = state.get("request_id", "unknown")
    trace: list = list(state.get("trace") or [])

    query: str = (
        state.get("query_description")
        or state.get("natural_language_query")
        or ""
    ).strip()
    schema_context: Dict[str, Any] = state.get("schema_context") or {}
    conversation_history: List[Dict[str, Any]] = state.get("conversation_history") or []

    preferred_provider = (
        state.get("selected_provider")
        or state.get("llm_provider")
        or get_request_preferred_provider()
    )
    provider_name = (settings.LLM_PROVIDER or "mock").lower().strip()
    effective_provider = preferred_provider or provider_name
    logger.info(
        f"[{request_id}] Node 4 (Query Synthesizer) starting — provider='{effective_provider}'"
    )

    # -----------------------------------------------------------------------
    # Path A: Mock provider — deterministic offline synthesis for tests
    # -----------------------------------------------------------------------
    if provider_name == "mock":
        output = mock_synthesize_query(
            query=query,
            schema_context=schema_context,
            conversation_history=conversation_history,
        )
        logger.info(
            f"[{request_id}] Mock synthesized pipeline for collection '{output.target_collection}' "
            f"with {len(output.pipeline)} stages."
        )
        trace.append(
            _trace_entry(
                "query_synthesizer",
                "mock",
                f"Generated pipeline for '{output.target_collection}' with {len(output.pipeline)} stages.",
            )
        )
        return {
            "target_collection": output.target_collection,
            "selected_collection": output.target_collection,
            "generated_pipeline": output.pipeline,
            "pipeline_spec": output.pipeline,
            "pipeline_explanation": output.explanation,
            "query_explanation": output.explanation,
            "assumptions_made": output.assumptions,
            "query_parameters": {
                "unsupported_concepts": output.unsupported_concepts_identified,
                "assumptions": output.assumptions,
            },
            "llm_provider": "mock",
            "llm_model": "mock",
            "trace": trace,
        }

    # -----------------------------------------------------------------------
    # Path B: Live LLM provider — structured prompt execution
    # -----------------------------------------------------------------------
    user_prompt = build_query_synthesis_prompt(
        query=query,
        schema_context=schema_context,
        conversation_history=conversation_history,
    )
    preferred_provider = (
        state.get("selected_provider")
        or state.get("llm_provider")
        or get_request_preferred_provider()
    )
    logger.info(
        f"[{request_id}] Node 4 (Query Synthesizer) starting — "
        f"preferred_provider='{preferred_provider or 'default'}'"
    )

    try:
        raw_response = await llm_service.get_provider().generate_response(
            user_message=user_prompt,
            conversation_history=None,  # History is already embedded in user_prompt
            system_prompt=QUERY_SYNTHESIS_SYSTEM_PROMPT,
            reasoning_effort="medium",
            preferred_provider=preferred_provider,
        )

        actual_provider = getattr(raw_response, "provider", provider_name)
        actual_model = getattr(raw_response, "model", getattr(settings, "LLM_MODEL", "unknown"))
        set_request_preferred_provider(actual_provider)

        parsed_output = _extract_json_pipeline(raw_response)
        if parsed_output is None:
            logger.warning(
                f"[{request_id}] Query synthesizer: failed to parse JSON from LLM output. "
                f"Raw excerpt: {raw_response[:200]!r}"
            )
            trace.append(
                _trace_entry(
                    "query_synthesizer",
                    "parse_error",
                    "LLM response could not be parsed into a valid PipelineSynthesisOutput.",
                )
            )
            return {
                "target_collection": None,
                "generated_pipeline": None,
                "pipeline_explanation": "Failed to synthesize pipeline: model produced invalid JSON format.",
                "query_parameters": {"error": "unparseable_output"},
                "selected_provider": actual_provider,
                "llm_provider": actual_provider,
                "llm_model": actual_model,
                "trace": trace,
            }

        logger.info(
            f"[{request_id}] LLM synthesized pipeline for collection '{parsed_output.target_collection}' "
            f"with {len(parsed_output.pipeline)} stages (provider='{actual_provider}')."
        )
        trace.append(
            _trace_entry(
                "query_synthesizer",
                "success",
                f"Generated pipeline for '{parsed_output.target_collection}' with {len(parsed_output.pipeline)} stages via {actual_provider}.",
            )
        )
        return {
            "target_collection": parsed_output.target_collection,
            "selected_collection": parsed_output.target_collection,
            "generated_pipeline": parsed_output.pipeline,
            "pipeline_spec": parsed_output.pipeline,
            "pipeline_explanation": parsed_output.explanation,
            "query_explanation": parsed_output.explanation,
            "assumptions_made": parsed_output.assumptions,
            "query_parameters": {
                "unsupported_concepts": parsed_output.unsupported_concepts_identified,
                "assumptions": parsed_output.assumptions,
            },
            "selected_provider": actual_provider,
            "llm_provider": actual_provider,
            "llm_model": actual_model,
            "trace": trace,
        }

    except FinTechAgentException:
        raise
    except Exception as exc:
        safe_msg = str(exc)[:200]
        logger.warning(f"[{request_id}] Query synthesizer exception: {safe_msg}")
        trace.append(
            _trace_entry(
                "query_synthesizer",
                "error",
                f"Synthesis failed: {safe_msg}",
            )
        )
        return {
            "target_collection": None,
            "generated_pipeline": None,
            "pipeline_explanation": f"Pipeline synthesis failed due to provider error: {safe_msg}",
            "query_parameters": {"error": safe_msg},
            "trace": trace,
        }


# Backwards compatibility alias
query_synthesizer_stub = query_synthesizer_node
