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
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pathlib import Path
from backend.app.config import settings
from backend.app.core.logging import logger
from backend.app.db.indexes import RECOMMENDED_INDEXES
from backend.app.schema.catalog_builder import schema_catalog_builder

def _load_confirmed_unique_index_fields() -> Dict[str, Set[str]]:
    """Loads verified unique index fields from actual index evidence artifact if present,
    falling back to recommended index definitions."""
    evidence_path = Path("PHASE6_VERIFIED_INDEX_EVIDENCE.json")
    if evidence_path.exists():
        try:
            with open(evidence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    col: set(info.get("confirmed_unique_fields", []))
                    for col, info in data.get("collections", {}).items()
                }
        except Exception as e:
            logger.warning(f"Could not load index evidence artifact: {e}")
    return {
        col: {
            fields[0][0]
            for idx in idx_list
            if idx.get("unique") is True
            for fields in [idx.get("fields", [])]
            if len(fields) == 1
        }
        for col, idx_list in RECOMMENDED_INDEXES.items()
    }

# Build canonical index-confirmed unique fields per collection
CONFIRMED_UNIQUE_INDEX_FIELDS: Dict[str, Set[str]] = _load_confirmed_unique_index_fields()


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
    "$push", "$addToSet", "$stdDevPop", "$stdDevSamp",
    # Conditional & Flow
    "$cond", "$ifNull", "$switch",
    # Date & Time
    "$dateToString", "$year", "$month", "$dayOfMonth", "$hour", "$minute",
    "$dateSubtract", "$dateAdd",
    # String manipulation
    "$concat", "$toLower", "$toUpper", "$substr", "$substrCP", "$regex",
    "$strLenCP", "$trim", "$options",
    # Arithmetic
    "$multiply", "$divide", "$add", "$subtract", "$round", "$abs", "$mod",
    # Array
    "$size", "$filter", "$map", "$arrayElemAt", "$slice", "$reduce", "$elemMatch", "$all",
    # Meta
    "$meta",
}

ALLOWED_SYSTEM_VARIABLES: Set[str] = {
    "$$NOW",
    "$$CLUSTER_TIME",
    "$$ROOT",
    "$$CURRENT",
    "$$REMOVE",
    "$$DESCEND",
    "$$PRUNE",
    "$$KEEP",
    "$$this",
    "$$value",
}

DATE_SUBTRACT_ALLOWED_ARGS: Set[str] = {"startDate", "unit", "amount", "timezone"}
DATE_SUBTRACT_REQUIRED_ARGS: Set[str] = {"startDate", "unit", "amount"}
DATE_SUBTRACT_ALLOWED_UNITS: Set[str] = {
    "year",
    "quarter",
    "month",
    "week",
    "day",
    "hour",
    "minute",
    "second",
    "millisecond",
}


def _validate_date_subtract(expr: Any) -> List[str]:
    """Validates the structure, arguments, and units of a $dateSubtract operator."""
    errors: List[str] = []
    if not isinstance(expr, dict):
        return [f"$dateSubtract must take a document argument with fields startDate, unit, amount, got {type(expr).__name__}."]

    keys = set(expr.keys())
    # 1. Reject unknown arguments
    unknown_args = keys - DATE_SUBTRACT_ALLOWED_ARGS
    if unknown_args:
        errors.append(
            f"Invalid or unrecognized argument(s) {sorted(unknown_args)} for $dateSubtract. "
            f"Allowed arguments: {sorted(DATE_SUBTRACT_ALLOWED_ARGS)}."
        )

    # 2. Check required arguments
    missing_req = DATE_SUBTRACT_REQUIRED_ARGS - keys
    if missing_req:
        errors.append(
            f"Missing required argument(s) {sorted(missing_req)} in $dateSubtract expression."
        )

    # 3. Validate unit
    if "unit" in expr:
        unit_val = expr["unit"]
        if isinstance(unit_val, str):
            if unit_val not in DATE_SUBTRACT_ALLOWED_UNITS:
                errors.append(
                    f"Invalid date unit '{unit_val}' in $dateSubtract. "
                    f"Allowed units: {sorted(DATE_SUBTRACT_ALLOWED_UNITS)}."
                )
        elif not isinstance(unit_val, (dict, str)):
            errors.append(
                f"Invalid date unit expression type in $dateSubtract: got {type(unit_val).__name__}."
            )

    # 4. Validate amount
    if "amount" in expr:
        amount_val = expr["amount"]
        if not isinstance(amount_val, (int, float, dict, str)):
            errors.append(
                f"Invalid amount type in $dateSubtract: expected number or expression, got {type(amount_val).__name__}."
            )

    return errors


def _trace_entry(node: str, status: str, detail: str) -> Dict[str, Any]:
    return {
        "node": node,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _extract_field_references(expr: Any, in_expr_context: bool = False) -> Set[str]:
    """Recursively extracts field path references (strings starting with '$' or filter keys).
    
    Distinguishes between query/match filter context and aggregation expression context.
    - In filter context (in_expr_context=False): dictionary keys that do not start with '$'
      are document field names (e.g. {'status': 'active'}).
    - In expression context (in_expr_context=True): dictionary keys (such as 'startDate', 'unit',
      'amount' in $dateSubtract, or 'input', 'as' in $filter, or embedded document keys) are
      operator arguments or object keys, NOT collection fields.
    - In expression context, collection fields are referenced by string values starting with single '$'
      (e.g. '$transaction_date').
    - Strings starting with '$$' are system/pipeline variables and are never treated as collection fields.
    """
    fields: Set[str] = set()
    if isinstance(expr, str):
        if expr.startswith("$$"):
            return fields
        if expr.startswith("$"):
            cleaned = expr[1:].split(".")[0]
            if cleaned and not cleaned.startswith("$"):
                fields.add(cleaned)
    elif isinstance(expr, dict):
        for k, v in expr.items():
            if k == "$expr":
                fields.update(_extract_field_references(v, in_expr_context=True))
            elif k.startswith("$"):
                # Operator: if already in expression context, stay in it.
                # If in filter context, logical operators remain filter context; expression operators become expr context.
                next_in_expr = in_expr_context or (k not in ("$and", "$or", "$nor", "$not"))
                fields.update(_extract_field_references(v, in_expr_context=next_in_expr))
            else:
                if not in_expr_context:
                    cleaned_k = k.split(".")[0]
                    fields.add(cleaned_k)
                    fields.update(_extract_field_references(v, in_expr_context=False))
                else:
                    fields.update(_extract_field_references(v, in_expr_context=True))
    elif isinstance(expr, list):
        for item in expr:
            fields.update(_extract_field_references(item, in_expr_context=in_expr_context))
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


def _inspect_ast_recursively(
    expr: Any,
    stage_name: str,
    stage_idx: int,
) -> Tuple[Set[str], Set[str], List[str]]:
    """Recursively audits an expression tree for:
      1. All operators used (keys starting with '$')
      2. Prohibited operators ($where, $function, $accumulator)
      3. Specific operator structure/argument validity (e.g. $dateSubtract)
      4. System variables ($$NOW, etc.)
    Returns:
      (found_ops, prohibited_ops, validation_errors)
    """
    found_ops: Set[str] = set()
    prohibited_ops: Set[str] = set()
    errors: List[str] = []

    if isinstance(expr, str):
        if expr.startswith("$$"):
            base_var = expr.split(".")[0]
            if base_var not in ALLOWED_SYSTEM_VARIABLES:
                errors.append(
                    f"Stage '{stage_name}' at index {stage_idx} contains "
                    f"unrecognized or unauthorized system variable '{expr}'."
                )
    elif isinstance(expr, dict):
        for k, v in expr.items():
            if k.startswith("$"):
                found_ops.add(k)
                if k in PROHIBITED_OPERATORS:
                    prohibited_ops.add(k)
                elif k not in APPROVED_OPERATORS and k not in APPROVED_STAGES:
                    errors.append(
                        f"Stage '{stage_name}' at index {stage_idx} contains "
                        f"unsupported operator '{k}'."
                    )

                # Operator-specific structural validations
                if k == "$dateSubtract":
                    ds_errors = _validate_date_subtract(v)
                    for err in ds_errors:
                        errors.append(f"Stage '{stage_name}' at index {stage_idx}: {err}")

            sub_ops, sub_proh, sub_errs = _inspect_ast_recursively(v, stage_name, stage_idx)
            found_ops.update(sub_ops)
            prohibited_ops.update(sub_proh)
            errors.extend(sub_errs)

    elif isinstance(expr, list):
        for item in expr:
            sub_ops, sub_proh, sub_errs = _inspect_ast_recursively(item, stage_name, stage_idx)
            found_ops.update(sub_ops)
            prohibited_ops.update(sub_proh)
            errors.extend(sub_errs)

    return found_ops, prohibited_ops, errors


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


def _inspect_aggregations_on_alias(expr: Any, alias: str) -> List[str]:
    """Recursively audits expressions for operations that aggregate or count over a bounded join."""
    violations: List[str] = []
    if isinstance(expr, dict):
        for op, val in expr.items():
            if op in ("$size", "$reduce", "$map", "$sum", "$avg", "$min", "$max"):
                val_str = json.dumps(val, default=str)
                if (
                    f"${alias}" in val_str
                    or f"\"{alias}\"" in val_str
                    or f"\"{alias}." in val_str
                    or f"${alias}." in val_str
                ):
                    violations.append(op)
            violations.extend(_inspect_aggregations_on_alias(val, alias))
    elif isinstance(expr, list):
        for item in expr:
            violations.extend(_inspect_aggregations_on_alias(item, alias))
    return violations


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
        require_terminal_limit: bool = False,
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
        bounded_1_to_n_aliases: Dict[str, int] = {}
        unwound_bounded_aliases: Dict[str, int] = {}

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

            found_ops, prohibited_ops, ast_errors = _inspect_ast_recursively(stage_body, stage_name, idx)
            if prohibited_ops:
                for op in sorted(prohibited_ops):
                    errors.append(
                        f"Stage '{stage_name}' at index {idx} contains prohibited operator '{op}'."
                    )
            if ast_errors:
                errors.extend(ast_errors)

            # C. Specific Stage Rules
            if stage_name == "$limit":
                if not isinstance(stage_body, int) or stage_body <= 0:
                    errors.append(f"$limit value must be a positive integer, got {stage_body}.")
                elif stage_body > settings.RESULT_DOC_LIMIT:
                    errors.append(
                        f"$limit value {stage_body} exceeds maximum allowed result limit of {settings.RESULT_DOC_LIMIT}."
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
                    sub_pipe = stage_body.get("pipeline")

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

                        # Bounding analysis: 1:1 vs 1:N join
                        # A lookup is inherently one-to-one ONLY if its foreignField is genuinely unique
                        # (i.e. '_id' or confirmed unique index). Do not assume a field is unique merely
                        # because schema catalog labels it a primary key.
                        confirmed_uniques = CONFIRMED_UNIQUE_INDEX_FIELDS.get(foreign_col, set())
                        is_genuinely_unique = (foreign_field == "_id") or (foreign_field in confirmed_uniques)

                        if not is_genuinely_unique:
                            # 1:N join requires bounded inner pipeline
                            if not sub_pipe or not isinstance(sub_pipe, list):
                                errors.append(
                                    f"$lookup stage at index {idx} joins multiple documents from '{foreign_col}' on non-primary/non-unique field '{foreign_field}' without an inner pipeline $limit <= {settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT}; unbounded joined document volume is prohibited."
                                )
                            else:
                                inner_limits = [s.get("$limit") for s in sub_pipe if isinstance(s, dict) and "$limit" in s]
                                if not inner_limits:
                                    errors.append(
                                        f"$lookup stage at index {idx} on collection '{foreign_col}' lacks an inner $limit stage (must be <= {settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT}) to bound joined documents."
                                    )
                                else:
                                    for lim_val in inner_limits:
                                        if not isinstance(lim_val, int) or lim_val <= 0 or lim_val > settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT:
                                            errors.append(
                                                f"Nested $lookup in stage {idx} has inner $limit of {lim_val}, exceeding maximum allowed limit of {settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT} per parent document."
                                            )
                            if as_alias and isinstance(as_alias, str):
                                bounded_1_to_n_aliases[as_alias] = idx
                        else:
                            # 1:1 join with custom sub-pipeline: validate limits if present
                            if sub_pipe and isinstance(sub_pipe, list):
                                inner_limits = [s.get("$limit") for s in sub_pipe if isinstance(s, dict) and "$limit" in s]
                                for lim_val in inner_limits:
                                    if not isinstance(lim_val, int) or lim_val <= 0 or lim_val > settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT:
                                        errors.append(
                                            f"Nested $lookup in stage {idx} has inner $limit of {lim_val}, exceeding maximum allowed limit of {settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT} per parent document."
                                        )

                    if as_alias and isinstance(as_alias, str):
                        dynamic_scope_fields.add(as_alias)

                    # Validate nested pipeline inside $lookup if present
                    if "pipeline" in stage_body and isinstance(stage_body["pipeline"], list):
                        nested_res = self.validate_pipeline(foreign_col or target_col, stage_body["pipeline"])
                        if nested_res.validation_status != "VALID":
                            errors.extend([f"Nested $lookup: {e}" for e in nested_res.validation_errors])

            elif stage_name == "$unwind":
                path_str = ""
                if isinstance(stage_body, str):
                    path_str = stage_body.lstrip("$")
                elif isinstance(stage_body, dict) and "path" in stage_body:
                    path_str = str(stage_body["path"]).lstrip("$")

                if path_str:
                    dynamic_scope_fields.add(path_str)
                    for alias in bounded_1_to_n_aliases:
                        if path_str == alias or path_str.startswith(f"{alias}."):
                            unwound_bounded_aliases[alias] = idx

            elif stage_name == "$group":
                # Check downstream aggregate correctness: calculating aggregates over truncated joined array produces financially incorrect results
                for alias, u_idx in unwound_bounded_aliases.items():
                    if idx > u_idx and isinstance(stage_body, dict):
                        acc_ops = {"$sum", "$avg", "$min", "$max", "$stdDevPop", "$stdDevSamp"}
                        for g_field, g_expr in stage_body.items():
                            if g_field == "_id":
                                continue
                            if isinstance(g_expr, dict):
                                used_accs = acc_ops.intersection(g_expr.keys())
                                if used_accs:
                                    errors.append(
                                        f"Joined array '{alias}' (bounded to {settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT} items) is unwound at stage {u_idx} and aggregated with {sorted(used_accs)} at stage {idx}. "
                                        f"Calculating financial aggregates over a truncated join produces incomplete and mathematically incorrect results."
                                    )
                # Register newly created fields
                if isinstance(stage_body, dict):
                    for k, v in stage_body.items():
                        if not k.startswith("$"):
                            dynamic_scope_fields.add(k)

            elif stage_name in ("$project", "$addFields", "$set"):
                # Check for aggregations or counts over bounded 1:N joined arrays
                for alias in bounded_1_to_n_aliases:
                    violations = _inspect_aggregations_on_alias(stage_body, alias)
                    if violations:
                        errors.append(
                            f"Joined array '{alias}' (bounded to {settings.MAX_LOOKUP_RESULTS_PER_DOCUMENT} items) is aggregated using {sorted(set(violations))} in stage '{stage_name}' at index {idx}. "
                            f"Calculating financial aggregates or counts over a truncated join produces incomplete and mathematically incorrect results."
                        )
                # Register newly created fields
                if isinstance(stage_body, dict):
                    for k, v in stage_body.items():
                        if not k.startswith("$"):
                            dynamic_scope_fields.add(k)

            # D. Field path validation (skip stages whose parameters are configuration or aliases)
            if stage_name in ("$lookup", "$count"):
                continue

            if stage_name in ("$project", "$addFields", "$set", "$group"):
                referenced_fields = set()
                if isinstance(stage_body, dict):
                    for k, v in stage_body.items():
                        referenced_fields.update(_extract_field_references(v, in_expr_context=True))
            elif stage_name == "$match":
                referenced_fields = _extract_field_references(stage_body, in_expr_context=False)
            elif stage_name == "$sort":
                referenced_fields = _extract_field_references(stage_body, in_expr_context=False)
            elif stage_name == "$unwind":
                referenced_fields = _extract_field_references(stage_body, in_expr_context=True)
            else:
                referenced_fields = _extract_field_references(stage_body, in_expr_context=False)

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

        # 5. Result-Volume Policy and Limit Analysis
        limit_stages = [(i, s["$limit"]) for i, s in enumerate(pipeline) if isinstance(s, dict) and "$limit" in s]
        unwind_stages = [i for i, s in enumerate(pipeline) if isinstance(s, dict) and "$unwind" in s]
        sort_stages = [i for i, s in enumerate(pipeline) if isinstance(s, dict) and "$sort" in s]
        skip_stages = [i for i, s in enumerate(pipeline) if isinstance(s, dict) and "$skip" in s]
        group_stages = [i for i, s in enumerate(pipeline) if isinstance(s, dict) and "$group" in s]

        # Check limit consistency if multiple limits exist
        if len(limit_stages) > 1:
            for k in range(len(limit_stages) - 1):
                idx1, val1 = limit_stages[k]
                idx2, val2 = limit_stages[k + 1]
                if isinstance(val1, int) and isinstance(val2, int) and val2 > val1:
                    errors.append(
                        f"Inconsistent $limit stages: stage {idx2} ($limit: {val2}) cannot expand earlier stage {idx1} ($limit: {val1})."
                    )

        # Check $unwind after $limit without a subsequent $limit
        if limit_stages and unwind_stages:
            first_limit_idx = limit_stages[0][0]
            last_limit_idx = limit_stages[-1][0]
            for u_idx in unwind_stages:
                if u_idx > first_limit_idx and u_idx >= last_limit_idx:
                    errors.append(
                        f"$limit stage at index {first_limit_idx} is followed by $unwind at index {u_idx} without a subsequent $limit; array expansion can produce unbounded document volume."
                    )

        # Check limit before sort: REJECT ($sort must precede $limit for safe top-N)
        if limit_stages and sort_stages:
            for l_idx, _ in limit_stages:
                for s_idx in sort_stages:
                    if l_idx < s_idx:
                        errors.append(
                            f"$limit at stage {l_idx} precedes $sort at stage {s_idx}. Semantically invalid: sorting after $limit orders an arbitrarily pre-truncated subset rather than producing true top-N results."
                        )

        # Check skip before sort: REJECT ($sort must precede $skip for deterministic pagination)
        if skip_stages and sort_stages:
            for k_idx in skip_stages:
                for s_idx in sort_stages:
                    if k_idx < s_idx:
                        errors.append(
                            f"$skip at stage {k_idx} precedes $sort at stage {s_idx}. Semantically invalid: skipping before sorting produces non-deterministic pagination."
                        )

        # Check limit before group
        if limit_stages and group_stages:
            for l_idx, _ in limit_stages:
                for g_idx in group_stages:
                    if l_idx < g_idx:
                        warnings.append(
                            f"$limit at stage {l_idx} precedes $group at stage {g_idx}. Aggregating after limit calculates metrics on partial data."
                        )

        # Terminal limit requirement
        if require_terminal_limit:
            last_stage = pipeline[-1]
            last_stage_name = next(iter(last_stage.keys())) if isinstance(last_stage, dict) else ""
            is_count = (last_stage_name == "$count")
            is_scalar_group = False
            if last_stage_name == "$group" and isinstance(last_stage.get("$group"), dict):
                group_id = last_stage["$group"].get("_id")
                if group_id is None:
                    is_scalar_group = True

            has_effective_terminal_limit = False
            if last_stage_name == "$limit":
                has_effective_terminal_limit = True
            elif len(pipeline) >= 2 and last_stage_name == "$project":
                penultimate = pipeline[-2]
                if isinstance(penultimate, dict) and "$limit" in penultimate:
                    has_effective_terminal_limit = True

            if not is_count and not is_scalar_group and not has_effective_terminal_limit:
                errors.append(
                    f"Pipeline lacks an effective terminal $limit stage (must be <= {settings.RESULT_DOC_LIMIT}) to bound final result volume."
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

    # Check if query synthesizer identified unsupported banking concepts
    query_params = state.get("query_parameters") or {}
    unsupported_concepts = query_params.get("unsupported_concepts") or []
    if unsupported_concepts and (not candidate_pipeline or len(candidate_pipeline) == 0):
        logger.info(f"[{request_id}] Node 5: Unsupported banking concepts identified: {unsupported_concepts}.")
        trace.append(
            _trace_entry(
                "mql_policy_validator",
                "unsupported",
                f"Requested banking concepts {unsupported_concepts} are unsupported by canonical schema.",
            )
        )
        return {
            "validation_status": "UNSUPPORTED",
            "validation_errors": [
                f"Requested concept '{c}' is unsupported by canonical schema." for c in unsupported_concepts
            ],
            "validation_warnings": [],
            "is_pipeline_valid": False,
            "approved_pipeline": None,
            "pipeline_spec": None,
            "query_plan_summary": None,
            "trace": trace,
        }

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

    # Execute deterministic validation with strict terminal limit enforcement
    val_res = mql_validator.validate_pipeline(
        target_collection=target_collection,
        pipeline=candidate_pipeline,
        require_terminal_limit=True,
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
