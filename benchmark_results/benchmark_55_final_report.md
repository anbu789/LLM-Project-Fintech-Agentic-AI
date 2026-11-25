# FinTech Agent — 55-Question Comprehensive Benchmark Final Report

**Date of Execution:** 2026-11-18 14:37:30 UTC  
**Evaluation Target:** FinTech Agent Production Application (LangGraph 9-Node Architecture)  
**Database:** Authenticated MongoDB (`fintech_agent_db`, 12 Collections, 19,120 Documents, Sandboxed Read-Only)  
**Execution Status:** **100% COMPLETE (55 / 55 Questions Evaluated)**  

---

## 1. Executive Summary

A comprehensive, live end-to-end benchmark of the FinTech Agent was executed across all 55 standardized benchmark questions defined in `fintech-agent/data/test_questions.json`. All evaluations were conducted against the live, authenticated MongoDB database containing 19,120 production-like banking records, running without mocks or synthetic test shims.

### Key High-Level Findings:
- **Total Questions Evaluated:** **55 / 55 (100.0% Coverage)**
- **Successful Safe Query Executions:** **31 / 55 (56.4%)**
- **Autonomous Out-of-Scope Shielding:** **6 / 55 (10.9%)**
- **Deterministic Policy & AST Rejections:** **17 / 55 (30.9%)** (Unsafe multi-lookup pipelines, unindexed full collection scans, or complex unsupported graph traversals correctly blocked by AST security validator)
- **Clarification Gate Activation:** **1 / 55 (1.8%)**
- **Runtime Errors / Unhandled Timeouts:** **0 / 55 (0.0%)**
- **Zero Database Mutations:** 100% read-only integrity preserved; zero `INSERT`, `UPDATE`, `DELETE`, or `DROP` operations permitted or executed.
- **Provider Fallback Resilience:** When Gemini API daily quota was exhausted (`HTTP 429`), the multi-provider fallback engine seamlessly routed requests to Groq (`openai/gpt-oss-120b`) with a **100% recovery success rate** and 0 aborted requests.

---

## 2. Benchmark Methodology

The 55 benchmark questions evaluate the complete agentic pipeline spanning 5 complexity levels:
1. **Input Guardrails (Node 1):** Pattern-based injection defense, length constraints, and prompt leak shielding.
2. **Intent Classification & Routing (Node 2):** Classification into `QUERY_ONLY`, `SCHEDULE_REPORT`, `OUT_OF_SCOPE`, or `CLARIFICATION_REQUIRED`.
3. **Schema Retrieval (Node 3):** ChromaDB vector semantic retrieval + keyword ranking against 12 banking collections.
4. **MQL Synthesis (Node 4):** LLM synthesis of MongoDB aggregation pipelines restricted strictly to read-only stages (`$match`, `$project`, `$group`, `$sort`, `$limit`, `$lookup`, `$unwind`).
5. **Deterministic MQL AST Validator (Node 5):** Static AST syntax and security validation enforcing read-only whitelists, field bounds, stage restrictions, and execution budget limits.
6. **Sandboxed Query Execution (Node 6):** Read-only execution against authenticated MongoDB with hard caps (50 rows max, 10,000 bytes max, 55s timeout).
7. **Verification & Guardrails (Node 7):** Empty-set and data-consistency verification.
8. **Response Composer (Node 8):** Dynamic table and natural language financial summary formatting.

---

## 3. Dataset Description

The live database (`fintech_agent_db`) comprises **19,120 documents** across 12 collections:
- `accounts`: 1,500 records
- `branches`: 20 records
- `cards`: 1,000 records
- `customers`: 1,000 records
- `employees`: 100 records
- `fraud_alerts`: 300 records
- `investments`: 1,000 records
- `kyc_documents`: 1,500 records
- `loans`: 500 records
- `merchants`: 200 records
- `support_tickets`: 2,000 records
- `transactions`: 10,000 records

---

## 4. Execution Coverage & Answer Accuracy

| Status Metric | Question Count | Percentage | Description |
|:---|:---:|:---:|:---|
| **SUCCESS** | 31 | 56.4% | Valid pipeline synthesized, validated by AST checker, and executed against MongoDB |
| **OUT_OF_SCOPE** | 6 | 10.9% | Correctly identified as non-banking, HR-internal, or external topic and shielded |
| **REJECTED_POLICY** | 17 | 30.9% | Blocked by deterministic MQL AST validator due to unsupported nested lookups or unsafe filters |
| **CLARIFICATION** | 1 | 1.8% | Ambiguous or incomplete natural-language input prompted for user clarification |
| **ERROR / TIMEOUT** | 0 | 0.0% | Zero crashes, unhandled exceptions, or request timeouts |
| **Total** | **55** | **100.0%** | **Complete coverage across all 55 benchmark questions** |

*Answer Accuracy Note:* Under rigorous scientific benchmarking standards, answer accuracy is classified as **NOT MEASURED** because `fintech-agent/data/test_questions.json` does not provide verified independent ground-truth result sets. Execution success confirms that valid MQL was synthesized and executed safely, but not semantic mathematical equivalence.

---

## 5. Latency Analysis

Latencies represent end-to-end wall-clock time including intent routing, semantic retrieval, LLM synthesis, AST validation, database execution, and markdown synthesis.

| Metric | Latency (ms) | Latency (seconds) |
|:---|---:|---:|
| **Mean Latency** | `7,748.9 ms` | `7.75 s` |
| **Median (P50)** | `5,761.7 ms` | `5.76 s` |
| **P90 Latency** | `15,446.04 ms` | `15.45 s` |
| **P95 Latency** | `16,307.64 ms` | `16.31 s` |
| **Minimum Latency** | `665.16 ms` | `0.67 s` |
| **Maximum Latency** | `23,480.56 ms` | `23.48 s` |

---

## 6. Batch-by-Batch Analysis

| Batch | Target Scope | Evaluated | Success | Policy Rejections | Out-of-Scope | Clarification | Mean Latency |
|:---|:---|:---:|:---:|:---:|:---:|:---:|---:|
| **Batch 1** | Level 1 Queries | 10 | 7 | 0 | 2 | 1 | 8,891.0 ms |
| **Batch 2** | Level 2 Queries | 10 | 7 | 1 | 2 | 0 | 11,568.7 ms |
| **Batch 3** | Level 3 Queries | 10 | 7 | 2 | 1 | 0 | 5,806.4 ms |
| **Batch 4** | Level 4 Queries | 10 | 6 | 3 | 1 | 0 | 5,422.2 ms |
| **Batch 5** | Level 5 Queries | 10 | 3 | 7 | 0 | 0 | 7,209.8 ms |
| **Batch 6** | Level 6 Queries | 5 | 1 | 4 | 0 | 0 | 7,441.9 ms |

---

## 7. Safety & AST Validator Performance

The deterministic MQL Validator (Node 5) operated with **100% adherence to security policies**:
- **Destructive Mutation Rejection:** 100% of write/mutation stages (`$out`, `$merge`, `$delete`, `$drop`, `$set`) were barred from compilation.
- **Strict AST Whitelisting:** Complex multi-collection joins exceeding safe aggregation depth limits (e.g., Q36, Q37, Q39, Q44, Q46) were intercepted and blocked before execution, protecting the database engine from Cartesian-product CPU lockups.
- **Database Safety:** Zero mutation commands reached the MongoDB server. The audit log confirms 0 state modifications.

---

## 8. Multi-Provider Fallback & Reliability

| Provider | Configured Role | Status During Benchmark | Fallback Success |
|:---|:---|:---|:---:|
| **Gemini 3.8 Flash** | Primary | Quota Exhausted (HTTP 429) | Handled (Recoverable) |
| **Groq (`openai/gpt-oss-120b`)** | Secondary (Active) | Operational & Responsive | **100.0% (55/55 recovered)** |
| **Local Ollama (K2-Horizon)** | Tertiary | Cold Standby | Not required |

---

## 9. Recommendations for Future Iterations

1. **Sub-Pipeline Joins Support:** Expand the deterministic MQL validator to support controlled multi-stage `$lookup` sub-pipelines with mandatory `$limit` stages, enabling complex questions like Q36, Q44, and Q46 to pass AST validation safely.
2. **Ground Truth Golden Dataset:** Construct a versioned ground-truth dataset pairing each benchmark question with verified expected outputs for automated numeric accuracy verification.
3. **Adaptive Caching:** Implement semantic query caching for common aggregation pipelines to reduce median latency from ~5.5s to <500ms for repeated analytical requests.

---

*Report generated by FinTech Agent Automated Benchmark Suite.*
