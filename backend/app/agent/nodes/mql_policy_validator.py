"""
FinTech Agent — Node 5: MQL Policy Validator — STUB (Phase 5 implementation)
Validates generated MongoDB pipelines against safety and policy rules.

PHASE 4 STATUS: STUB — returns a placeholder indicating Phase 5 is pending.
This stub performs NO validation and executes NO MongoDB explain() calls.
Full implementation planned for Phase 5.
"""

from datetime import datetime, timezone
from typing import Any, Dict


async def mql_policy_validator_stub(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 5 stub: MQL policy validation placeholder.

    In Phase 5 this node will:
    - Validate that generated_pipeline contains only read-only stages.
    - Check pipeline depth, operator allowlist, and prohibited operators.
    - Run MongoDB explain() to verify query plan safety.
    - Populate validation_status and validation_errors.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with stub validation_status.
    """
    trace: list = list(state.get("trace") or [])
    trace.append({
        "node": "mql_policy_validator",
        "status": "stub",
        "detail": "Phase 5 not yet implemented — pipeline validation skipped.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return {
        "validation_status": "stub",
        "validation_errors": [],
        "trace": trace,
    }
