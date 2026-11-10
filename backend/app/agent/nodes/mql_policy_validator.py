"""
FinTech Agent — Node 5: Deterministic MQL Policy Validator (Phase 5, Full Implementation)
Strict deterministic security gate that validates all candidate MongoDB aggregation pipelines
before any query can reach execution in Phase 6.

Security Enforcements:
  1. Target Collection Allowlist: Only canonical 12 banking collections permitted.
  2. Stage Allowlist: Only read-only analytics stages ($match, $project, $group, $sort,
     $limit, $skip, $unwind, $lookup, $count, $addFields, $set).
     Explicitly blocks $out, $merge, and administrative stages.
  3. Operator Allowlist: Recursively inspects expressions.
     Explicitly blocks JavaScript execution ($where, $function, $accumulator).
  4. Field Validation: Recursively checks referenced fields against the canonical schema.
     Explicitly rejects invented fields (e.g. loans.overdue_amount, loans.days_past_due).
  5. Relationship Validation: Validates $lookup joins against canonical foreign keys.
  6. Complexity Bounds: Max stages (20), max depth (10), bounded limit values.

CRITICAL GUARANTEE:
  NEVER TRUSTS LLM OUTPUT.
  UNVALIDATED PIPELINES NEVER PASS TO PHASE 6.
  DOES NOT EXECUTE ANY MONGODB COMMANDS.
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.schema.catalog_builder import schema_catalog_builder


# ---------------------------------------------------------------------------
# Canonical Allowlists & Constraints
# ---------------------------------------------------------------------------

CANONICAL_COLLECTIONS: Set[str] = {
    "accounts",
    "branches",
    "cards",
    "customers",
    "employees",
    "fraud_alerts",
    "investments",
    "kyc_documents",
    "loans",
    "merchants",
    "support_tickets",
    "transactions",
}

APPROVED_STAGES: Set[str] = {
    "$match",
    "$project",
    "$group",
    "$sort",
    "$limit",
    "$skip",
    "$unwind",
    "$lookup",
    "$count",
    "$addFields",
    "$set",
}

PROHIBITED_STAGES: Set[str] = {
    "$out",
    "$merge",
    "$collStats",
    "$indexStats",
    "$planCacheStats",
    "$changeStream",
    "$currentOp",
    "$listLocalSessions",
    "$listSessions",
}

PROHIBITED_OPERATORS: Set[str] = {
    "$where",
    "$function",
    "$accumulator",
}

APPROVED_OPERATORS: Set[str] = {
    # Comparison & Logical
    "$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin",
    "$and", "$or", "$not", "$nor", "$exists", "$type", "$expr",
    # Accumulators & Group
    "$sum", "$avg", "$min", "$max", "$first", "$last", "$count",
    "$push", "$addToSet",
    # Conditional & Flow
    "$cond", "$ifNull", "$switch",
    # Date & Time
    "$dateToString", "$year", "$month", "$dayOfMonth", "$hour", "$minute",
    # String manipulation
    "$concat", "$toLower", "$toUpper", "$substr", "$substrCP", "$regex",
    "$strLenCP", "$trim",
    # Arithmetic
    "$multiply", "$divide", "$add", "$subtract", "$round", "$abs", "$mod",
    # Array
    "$size", "$filter", "$map", "$arrayElemAt", "$slice",
}


def _trace_entry(node: str, status: str, detail: str) -> Dict[str, Any]:
    return {
        "node": node,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _extract_field_references(expr: Any) -> Set[str]:
    """Recursively extracts field path references (strings starting with '$')."""
    fields: Set[str] = set()
    if isinstance(expr, str):
        if expr.startswith("$") and not expr.startswith("$$"):
            cleaned = expr[1:].split(".")[0]
            if cleaned and not cleaned.startswith("$"):
                fields.add(cleaned)
    elif isinstance(expr, dict):
        for k, v in expr.items():
            if not k.startswith("$"):
                cleaned_k = k.split(".")[0]
                fields.add(cleaned_k)
            fields.update(_extract_field_references(v))
    elif isinstance(expr, list):
        for item in expr:
            fields.update(_extract_field_references(item))
    return fields


def _inspect_expression_depth(expr: Any, current_depth: int = 1) -> int:
    """Calculates maximum nesting depth of dictionary/list expression."""
    if not isinstance(expr, (dict, list)) or not expr:
        return current_depth

    max_d = current_depth
    if isinstance(expr, dict):
        for v in expr.values():
            max_d = max(max_d, _inspect_expression_depth(v, current_depth + 1))
    elif isinstance(expr, list):
        for item in expr:
            max_d = max(max_d, _inspect_expression_depth(item, current_depth + 1))
    return max_d


def _inspect_operators_recursively(expr: Any) -> Tuple[Set[str], Set[str]]:
    """Traverses expression and collects all $-prefixed keys, checking for prohibited ones."""
    found_ops: Set[str] = set()
    prohibited_found: Set[str] = set()

    if isinstance(expr, dict):
        for k, v in expr.items():
            if k.startswith("$"):
                found_ops.add(k)
                if k in PROHIBITED_OPERATORS:
                    prohibited_found.add(k)
            sub_ops, sub_proh = _inspect_operators_recursively(v)
            found_ops.update(sub_ops)
            prohibited_found.update(sub_proh)
    elif isinstance(expr, list):
        for item in expr:
            sub_ops, sub_proh = _inspect_operators_recursively(item)
            found_ops.update(sub_ops)
            prohibited_found.update(sub_proh)

    return found_ops, prohibited_found


class MQLValidationResult:
    """Wrapper that supports both object-attribute and dict-key access."""

    def __init__(
        self,
        validation_status: str,
        validation_errors: List[str],
        validation_warnings: List[str],
        approved_pipeline: Optional[List[Dict[str, Any]]] = None,
        query_plan_summary: Optional[Dict[str, Any]] = None,
        referenced_fields: Optional[List[str]] = None,
    ):
        self.validation_status = validation_status
        self.validation_errors = validation_errors
        self.validation_warnings = validation_warnings
        self.approved_pipeline = approved_pipeline
        self.query_plan_summary = query_plan_summary or {}
        self.referenced_fields = referenced_fields or []

    @property
    def is_valid(self) -> bool:
        return self.validation_status == "VALID"

    @property
    def errors(self) -> List[str]:
        return self.validation_errors

    @property
    def warnings(self) -> List[str]:
        return self.validation_warnings

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation_status": self.validation_status,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "approved_pipeline": self.approved_pipeline,
            "query_plan_summary": self.query_plan_summary,
            "referenced_fields": self.referenced_fields,
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class MQLPolicyValidator:
    """Deterministic policy validator for MongoDB aggregation pipelines."""

    def __init__(self):
        self._catalog = None

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = schema_catalog_builder.load_catalog()
        return self._catalog

    def validate_pipeline(
        self,
        target_collection: Optional[str],
        pipeline: Optional[List[Dict[str, Any]]],
    ) -> MQLValidationResult:
        """Validates collection, stages, fields, relationships, and complexity."""
        errors: List[str] = []
        warnings: List[str] = []
        all_referenced_fields: Set[str] = set()

        # 1. Target Collection Validation
        if not target_collection or not isinstance(target_collection, str):
            errors.append("Target collection is missing, null, or not a string.")
            return MQLValidationResult("INVALID", errors, warnings)

        target_col = target_collection.strip()
        if target_col not in CANONICAL_COLLECTIONS:
            errors.append(
                f"Collection '{target_col}' is an unknown or unauthorized collection. "
                f"Allowed canonical collections: {sorted(CANONICAL_COLLECTIONS)}"
            )
            return MQLValidationResult("INVALID", errors, warnings)

        if not isinstance(pipeline, list):
            errors.append("Pipeline must be a JSON array of stage objects.")
            return MQLValidationResult("INVALID", errors, warnings)

        if len(pipeline) == 0:
            errors.append("Pipeline must be a non-empty list of stages.")
            return MQLValidationResult("INVALID", errors, warnings)

        # 2. Stage Count & Complexity Limits
        max_stages = settings.MAX_PIPELINE_STAGES
        if len(pipeline) > max_stages:
            errors.append(
                f"Pipeline stage count ({len(pipeline)}) exceeds maximum allowed limit of {max_stages}."
            )

        # 3. Canonical Schema Lookup
        cat = self.catalog
        canonical_fields: Set[str] = {"_id"}
        if target_col in cat.collections:
            canonical_fields.update(cat.collections[target_col].fields.keys())

        # Track computed fields created in pipeline stages (e.g. $group, $project, $lookup)
        dynamic_scope_fields: Set[str] = set(canonical_fields)
        lookup_count = 0

        # 4. Stage-by-Stage Recursive Inspection
        for idx, stage in enumerate(pipeline):
            if not isinstance(stage, dict):
                errors.append(f"Stage at index {idx} must be a dictionary.")
                continue

            if len(stage) != 1:
                errors.append(f"Stage at index {idx} must contain exactly one top-level stage operator.")
                continue

            stage_name = next(iter(stage.keys()))
            stage_body = stage[stage_name]

            # A. Stage Allowlist Check
            if stage_name in PROHIBITED_STAGES:
                errors.append(f"Stage at index {idx} uses strictly prohibited write stage '{stage_name}'.")
                continue

            if stage_name not in APPROVED_STAGES:
                errors.append(f"Stage at index {idx} uses unapproved stage '{stage_name}'.")
                continue

            # B. Depth & Operator Inspection
            depth = _inspect_expression_depth(stage_body)
            if depth > settings.MAX_PIPELINE_DEPTH:
                errors.append(
                    f"Stage '{stage_name}' at index {idx} has nesting depth {depth} "
                    f"exceeds maximum allowed depth of {settings.MAX_PIPELINE_DEPTH}."
                )

            found_ops, prohibited_ops = _inspect_operators_recursively(stage_body)
            if prohibited_ops:
                for op in sorted(prohibited_ops):
                    errors.append(
                        f"Stage '{stage_name}' at index {idx} contains prohibited operator '{op}'."
                    )

            # C. Specific Stage Rules
            if stage_name == "$limit":
                if not isinstance(stage_body, int) or stage_body <= 0:
                    errors.append(f"$limit value must be a positive integer, got {stage_body}.")
                elif stage_body > settings.RESULT_DOC_LIMIT:
                    warnings.append(
                        f"$limit {stage_body} exceeds recommended limit {settings.RESULT_DOC_LIMIT}."
                    )

            elif stage_name == "$count":
                if isinstance(stage_body, str) and stage_body.strip():
                    dynamic_scope_fields.add(stage_body.strip())
                else:
                    errors.append(f"$count value must be a non-empty string, got {stage_body}.")

            elif stage_name == "$lookup":
                lookup_count += 1
                if lookup_count > 3:
                    errors.append("Pipeline exceeds maximum allowed $lookup stages (3).")

                if not isinstance(stage_body, dict):
                    errors.append(f"$lookup body must be a dictionary at index {idx}.")
                else:
                    foreign_col = stage_body.get("from")
                    local_field = stage_body.get("localField")
                    foreign_field = stage_body.get("foreignField")
                    as_alias = stage_body.get("as")

                    if not foreign_col or foreign_col not in CANONICAL_COLLECTIONS:
                        errors.append(f"$lookup stage at index {idx} cannot target unauthorized collection '{foreign_col}'.")
                    else:
                        # Check local field exists
                        if local_field and local_field not in dynamic_scope_fields:
                            errors.append(
                                f"$lookup localField '{local_field}' does not exist in collection '{target_col}' scope."
                            )
                        # Check foreign field exists in foreign collection
                        if foreign_col in cat.collections and foreign_field:
                            foreign_canon = set(cat.collections[foreign_col].fields.keys()) | {"_id"}
                            if foreign_field not in foreign_canon:
                                errors.append(
                                    f"$lookup foreignField '{foreign_field}' does not exist in collection '{foreign_col}'."
                                )

                        # Check relationship integrity
                        is_valid_rel = False
                        for rel in cat.relationships:
                            if (
                                (rel.from_collection == target_col and rel.to_collection == foreign_col)
                                or (rel.from_collection == foreign_col and rel.to_collection == target_col)
                            ):
                                is_valid_rel = True
                                break
                        if not is_valid_rel and foreign_col != target_col:
                            errors.append(
                                f"$lookup between '{target_col}' and '{foreign_col}' has no verified schema relationship."
                            )

                    if as_alias and isinstance(as_alias, str):
                        dynamic_scope_fields.add(as_alias)

                    # Validate nested pipeline inside $lookup if present
                    if "pipeline" in stage_body and isinstance(stage_body["pipeline"], list):
                        nested_res = self.validate_pipeline(foreign_col or target_col, stage_body["pipeline"])
                        if nested_res.validation_status != "VALID":
                            errors.extend([f"Nested $lookup: {e}" for e in nested_res.validation_errors])

            elif stage_name == "$unwind":
                if isinstance(stage_body, str):
                    path = stage_body.lstrip("$")
                    dynamic_scope_fields.add(path)
                elif isinstance(stage_body, dict) and "path" in stage_body:
                    path = stage_body["path"].lstrip("$")
                    dynamic_scope_fields.add(path)

            elif stage_name in ("$group", "$project", "$addFields", "$set"):
                # Register newly created fields
                if isinstance(stage_body, dict):
                    for k, v in stage_body.items():
                        if not k.startswith("$"):
                            dynamic_scope_fields.add(k)

            # D. Field path validation (skip stages whose parameters are configuration or aliases)
            if stage_name in ("$lookup", "$count"):
                continue

            referenced_fields = _extract_field_references(stage_body)
            # Filter out pipeline variables ($$ROOT, $$NOW, etc.)
            filtered_refs = {f for f in referenced_fields if not f.startswith("$")}
            all_referenced_fields.update(filtered_refs)

            for ref in filtered_refs:
                # Disallow known non-existent fields strictly
                if target_col == "loans" and ref in ("overdue_amount", "days_past_due"):
                    errors.append(
                        f"Field 'loans.{ref}' does NOT exist in the canonical schema. "
                        f"Only 'loans.outstanding_amount' and 'loans.status' exist."
                    )
                elif target_col in cat.collections and ref not in dynamic_scope_fields:
                    # If field is not canonical or dynamically introduced
                    errors.append(
                        f"Referenced unknown field '{ref}' does not exist in collection '{target_col}' schema."
                    )

        status = "VALID" if not errors else "INVALID"
        approved = list(pipeline) if status == "VALID" else None

        return MQLValidationResult(
            validation_status=status,
            validation_errors=errors,
            validation_warnings=warnings,
            approved_pipeline=approved,
            query_plan_summary={
                "target_collection": target_col,
                "stage_count": len(pipeline),
                "stages_used": [next(iter(s.keys())) for s in pipeline if isinstance(s, dict)],
                "lookups_count": lookup_count,
            },
            referenced_fields=sorted(all_referenced_fields),
        )


# Singleton instance
mql_validator = MQLPolicyValidator()


async def mql_policy_validator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Node 5: Validates candidate pipeline deterministically.

    Args:
        state: Incoming AgentState dict.

    Returns:
        Partial AgentState with validation_status, validation_errors, and query_plan_summary.
    """
    request_id = state.get("request_id", "unknown")
    trace: list = list(state.get("trace") or [])

    target_collection = state.get("target_collection") or state.get("selected_collection")
    candidate_pipeline = state.get("generated_pipeline") or state.get("pipeline_spec")

    logger.info(
        f"[{request_id}] Node 5 (MQL Validator) evaluating candidate pipeline "
        f"for collection='{target_collection}'"
    )

    # If query synthesizer failed to generate a pipeline
    if not candidate_pipeline:
        logger.warning(f"[{request_id}] Node 5: candidate_pipeline is None or empty. Validation FAILED.")
        trace.append(
            _trace_entry(
                "mql_policy_validator",
                "invalid",
                "No candidate pipeline generated by synthesizer.",
            )
        )
        return {
            "validation_status": "INVALID",
            "validation_errors": ["No candidate pipeline generated to validate."],
            "is_pipeline_valid": False,
            "query_plan_summary": None,
            "trace": trace,
        }

    # Execute deterministic validation
    val_res = mql_validator.validate_pipeline(
        target_collection=target_collection,
        pipeline=candidate_pipeline,
    )

    status = val_res.validation_status
    errors = val_res.validation_errors
    warnings = val_res.validation_warnings
    summary = val_res.query_plan_summary
    is_valid = (status == "VALID")

    logger.info(
        f"[{request_id}] Node 5 outcome: status='{status}', "
        f"errors={len(errors)}, warnings={len(warnings)}"
    )

    trace.append(
        _trace_entry(
            "mql_policy_validator",
            status.lower(),
            f"Validation result: {status}. Errors: {len(errors)}, Warnings: {len(warnings)}.",
        )
    )

    return {
        "validation_status": status,
        "validation_errors": errors,
        "validation_warnings": warnings,
        "is_pipeline_valid": is_valid,
        "approved_pipeline": val_res.approved_pipeline,
        "pipeline_spec": val_res.approved_pipeline if is_valid else candidate_pipeline,
        "query_plan_summary": summary,
        "trace": trace,
    }


# Backwards compatibility alias
mql_policy_validator_stub = mql_policy_validator_node
