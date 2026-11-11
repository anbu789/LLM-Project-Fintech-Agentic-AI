# FINTECH AGENT — SECURITY DEFENSES, GUARDRAILS AND ARCHITECTURAL LIMITATIONS

**Document Classification:** Security Audit, Guardrail Evaluation & Threat Modeling  
**Primary Security Implementation Files:**
- Deterministic Input Guardrail: [`backend/app/agent/nodes/input_guardrail.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/nodes/input_guardrail.py)
- AST MQL Policy Validator: [`backend/app/agent/nodes/mql_policy_validator.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/nodes/mql_policy_validator.py)
- Read-Only Database Proxy: [`backend/app/db/mongo_client.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/db/mongo_client.py)
- Cryptographic Token Authenticator: [`backend/app/core/auth.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/core/auth.py)
- Fail-Closed Query Executor: [`backend/app/agent/nodes/query_executor.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/nodes/query_executor.py)

---

## 1. Comprehensive Safeguard Matrix (25 Defensive Controls)

The FinTech Agent employs defense-in-depth across the entire request lifecycle. Every safeguard is categorized below:

| # | Safeguard | Implementation Mechanism | Enforcement Tier | Source File Reference | Automated Test Evidence | Operational Status |
| :-: | :--- | :--- | :---: | :--- | :--- | :---: |
| 1 | **Input Validation** | Rejects empty strings, whitespace, and inputs > 2,000 characters | **Code** (Deterministic) | `input_guardrail.py:105-120` | `test_node1_oversized_input_rejection` | `VERIFIED` |
| 2 | **Prompt-Injection Defense** | Regex filtering of jailbreak patterns (DAN mode, "ignore previous instructions") | **Code** (Deterministic) | `input_guardrail.py:25-39` | `test_node1_injection_rejection` | `VERIFIED` |
| 3 | **Destructive Command Interception**| Regex interception of database mutations (`drop`, `deleteMany`, `insert`, `remove`) | **Code** (Deterministic) | `input_guardrail.py:53-70` | `test_node1_destructive_db_rejection` | `VERIFIED` |
| 4 | **MQL Policy AST Validator** | Recursive AST traversal of all aggregation pipeline stages and expressions | **Code** (Deterministic) | `mql_policy_validator.py:120-290` | `test_security_mql_blocks_prohibited_operators` | `VERIFIED` |
| 5 | **Pipeline Stage Allowlist** | Only read-only analytical stages allowed (`$match`, `$project`, `$group`, etc.) | **Code** (Deterministic) | `mql_policy_validator.py:75-95` | `test_mql_disallowed_stages_rejected` | `VERIFIED` |
| 6 | **Prohibited Operator Blocking** | Explicitly blocks `$out`, `$merge`, `$where`, `$accumulator`, `$function` | **Code** (Deterministic) | `mql_policy_validator.py:82-89` | `test_mql_prohibited_operators_rejected` | `VERIFIED` |
| 7 | **Collection Allowlist** | Target collections and `$lookup` 'from' targets restricted to 12 canonical tables | **Code** (Deterministic) | `mql_policy_validator.py:130-145` | `test_mql_disallowed_collection_rejected` | `VERIFIED` |
| 8 | **Field Schema Verification** | Recursively verifies every referenced field exists in canonical `schema.json` | **Code** (Deterministic) | `mql_policy_validator.py:165-210` | `test_mql_unknown_field_rejected` | `VERIFIED` |
| 9 | **Nested Pipeline Depth Limits** | Limits `$lookup` sub-pipeline nesting to maximum depth of 10 | **Code** (Deterministic) | `mql_policy_validator.py:215-225` | `test_mql_excessive_depth_rejected` | `VERIFIED` |
| 10 | **Query Complexity Budget** | Total pipeline stages restricted to maximum of 20 (`settings.MAX_PIPELINE_STAGES`) | **Code** (Deterministic) | `mql_policy_validator.py:228-235` | `test_mql_excessive_stages_rejected` | `VERIFIED` |
| 11 | **Read-Only Database Proxy** | Python wrapper intercepts and blocks any PyMongo mutating methods (`insert_one`, etc.) | **Code** (Proxy Tier) | `mongo_client.py:45-120` | `test_security_readonly_proxy_blocks_writes` | `VERIFIED` |
| 12 | **Native MongoDB Authentication** | Server-side auth in `mongod.cfg` with `fintech_analyst_user` read privileges | **Database Server** | `scripts/mongo_init_auth.js` | `test_phase6_canary_rbac.py` (Script exists) | `BLOCKED_BY_CONFIGURATION` |
| 13 | **Production RBAC Separation** | Dedicated unprivileged users (`fintech_analyst_user` vs `metadata_rw_user`) | **Database Server** | `scripts/mongo_init_auth.js` | Script verified; unauthenticated dev in `.env` | `BLOCKED_BY_CONFIGURATION` |
| 14 | **Server-Side Query Timeout** | Injects `maxTimeMS = 15,000` (settings.QUERY_TIMEOUT_MS) into every aggregation | **Database / Driver** | `query_executor.py:140-155` | `test_query_timeout_ms_native_enforcement` | `VERIFIED` |
| 15 | **Result Document & Byte Capping**| Enforces terminal `$limit <= 100`, caps rows at 1,000, bounds payload to 5MB | **Code** (Executor/Validator) | `query_executor.py:160-175` | `test_mql_limit_above_max_rejected` | `VERIFIED` |
| 16 | **Query Plan Preflight Check** | Evaluates index utilization and rejects unbounded collection scans (`COLLSCAN`) | **Code** (Validator) | `mql_policy_validator.py:310-335` | `test_query_plan_inspection` | `VERIFIED` |
| 17 | **Result Verification & Typing** | Sanitizes BSON types; preserves exact `Decimal128` financial precision | **Code** (Deterministic) | `result_verifier.py:30-50` | `test_result_verifier_decimal_preservation` | `VERIFIED` |
| 18 | **Bounded Error Recovery** | Retries transient timeouts up to 3 times without modifying approved pipeline | **Code** (State/Graph) | `graph.py:370-384` | `test_gemini_503_retry_and_recovery` | `VERIFIED` |
| 19 | **PII & Secret Redaction** | Strips API keys, passwords, bearer tokens, and PAN numbers from logs | **Code** (Logging Filter) | `logging.py:40-75` | `test_windows_logging_secret_redaction` | `VERIFIED` |
| 20 | **Human Schedule Approval** | Recurring jobs require explicit approval (`POST /api/v1/schedules/approve`) | **Code** (API / Service) | `schedules.py:95-135` | `test_fastapi_schedules_approve_route` | `VERIFIED` |
| 21 | **Schedule Ownership Verification**| Prevents cross-tenant viewing or approving of other users' schedule previews | **Code** (Cryptographic Auth)| `auth.py:110-145` | `test_task1_tenant_isolation_cross_user_denial`| `VERIFIED` |
| 22 | **Pipeline Integrity Hashing** | SHA-256 hash of approved MQL pipeline stored; verified before background runs | **Code** (Crypto Hash) | `schedule_service.py:75-90` | `test_scheduler_runner_execute_job_drift_detection` | `VERIFIED` |
| 23 | **Runtime Pre-Execution Recheck**| Re-validates MQL policy immediately before scheduled background execution | **Code** (Validator) | `scheduler_runner.py:180-210` | `test_task3_schema_drift_config_failure` | `VERIFIED` |
| 24 | **Consecutive Failure Auto-Pause**| Automatically pauses recurring jobs after 3 consecutive execution failures | **Code** (Scheduler Runner) | `scheduler_runner.py:220-245` | `test_task3_consecutive_failures_auto_pause` | `VERIFIED` |
| 25 | **Fail-Closed Execution Gate** | 7-stage check blocks live execution when auth is absent or gate is disabled | **Code** (Executor) | `query_executor.py:65-105` | `test_execution_gate_fail_closed` | `VERIFIED` |

---

## 2. Deep Dive: Native MongoDB Auth vs. Python Proxy Reality

An essential academic integrity distinction must be maintained regarding database security:

> [!WARNING]
> **Production-Grade Server-Side RBAC is NOT Enabled in the Active Development Runtime.**  
> While the scripts to configure native MongoDB authentication exist (`scripts/mongo_init_auth.js`), in the active repository state:
> - `MONGO_AUTH_ENABLED = False` in `.env`
> - `ALLOW_UNAUTHENTICATED_DEV = True` in `config.py`
> - MongoDB connects via unauthenticated local port: `mongodb://localhost:27017/`
> 
> Therefore, **the system's database security relies entirely on Python application-level defenses:**
> 1. The deterministic AST `MQLPolicyValidator` (which removes or rejects any mutating operator).
> 2. The `ReadOnlyDatabaseProxy` and `ReadOnlyCollectionProxy` (which intercept and throw exceptions on PyMongo mutating methods).
> 3. The Central Fail-Closed Execution Gate in Node 6 (`PHASE6_LIVE_EXECUTION_ENABLED = False`).
> 
> Claims of "hardware-enforced or native database RBAC" must not be made in the IEEE paper. The paper must accurately describe the defenses as **"Deterministic Application-Level Sandboxing with Dual-Layer Proxy Protection"**.

---

## 3. Financial Semantics Resolution: Loan Delinquency vs. Principal Balance

A major semantic vulnerability identified during Pre-Phase 6 audits involved loan health queries:

### The Semantic Problem
In commercial banking:
- **`loans.outstanding_amount`** represents the **Total Remaining Unamortized Principal** on a loan contract.
- **Overdue Debt (Arrears)** represents missed monthly installment payments (EMIs) past their due date.
- In `fintech_agent_db`, the fields `overdue_amount` and `days_past_due` (DPD) **DO NOT EXIST**.
- Early prompt designs erroneously substituted `loans.outstanding_amount` as a proxy for "overdue amount" when filtering by `status = "defaulted"`.
- If a borrower defaulted on a ₹50,00,000 mortgage after missing two ₹40,000 installments, the system reported ₹48,00,000 as the "overdue amount" — an overstatement of **6,000%**.

### The Implemented Remediation ([`PRE_PHASE6_FINANCIAL_SEMANTICS_REPORT.md`](file:///c:/Users/guru2/Downloads/llm%20prj/PRE_PHASE6_FINANCIAL_SEMANTICS_REPORT.md))
1. **Strict Concept Separation:**
   - Queries legitimately requesting defaulted loans or remaining default debt are supported:
     ```json
     [
       {"$match": {"status": "defaulted"}},
       {"$project": {"customer_id": 1, "unrecovered_principal": "$outstanding_amount"}},
       {"$limit": 100}
     ]
     ```
   - Queries requesting "overdue amounts", "arrears", or "days past due" are **intercepted by Node 3 and Node 5 as UNSUPPORTED**.
2. **Plain-Language Regulatory Refusal:**
   The Response Composer explicitly notifies the analyst:
   > *"The current banking schema does not track overdue installment arrears or days past due (DPD). The loans collection records contractual default status (`status = 'defaulted'`) and remaining principal balance (`outstanding_amount`). To analyze credit risk, review unrecovered principal for defaulted loans."*
3. **Automated Verification:** Verified by 7 dedicated test cases in `backend/tests/test_pre_phase6_remediation.py`.

---

## 4. Architectural Limitations & Boundaries

The IEEE conference paper should transparently acknowledge the following technical boundaries:
1. **Read-Only Scope:** The system cannot execute balance adjustments, fund transfers, or KYC approval updates.
2. **Single-Node Execution:** The APScheduler runner is designed as a single-process service coordinating via database leases. It does not provide distributed cluster sharding across multiple data centers.
3. **Synthetic Domain Bounds:** The dataset models Indian retail banking conventions (INR, IFSC, PAN, Aadhaar) and does not cover international trade finance, multi-currency FX swaps, or syndicated corporate debt.
4. **Execution Gate Restraint:** Live aggregation execution against `fintech_agent_db` remains intentionally fail-closed during academic review to prevent accidental data contamination.
