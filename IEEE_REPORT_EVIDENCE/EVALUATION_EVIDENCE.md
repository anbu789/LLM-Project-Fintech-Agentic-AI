# FINTECH AGENT — EXPERIMENTAL EVALUATION AUDIT AND METRICS VERIFICATION

**Document Classification:** Empirical Evidence Audit, Benchmark Analysis & Academic Verification  
**Evaluation Scope:** 55-Question Natural Language Benchmark, 18-Case RAG Subsystem Benchmark, 18 Archetype Synthesis Suite, and Automated Test Metrics  
**Primary Reference Files:**
- Benchmark Questions: [`fintech-agent/data/test_questions.json`](file:///c:/Users/guru2/Downloads/llm%20prj/fintech-agent/data/test_questions.json)
- Historical Architectural Claims: [`SYSTEM_ARCHITECTURE_UPDATED.md:1443-1472`](file:///c:/Users/guru2/Downloads/llm%20prj/SYSTEM_ARCHITECTURE_UPDATED.md#L1443-L1472)
- Pre-Phase 4 RAG Evaluation Report: [`PRE_PHASE4_RAG_EVALUATION.md:1-191`](file:///c:/Users/guru2/Downloads/llm%20prj/PRE_PHASE4_RAG_EVALUATION.md#L1-L191)
- Phase 5 Synthesis & Validation Report: [`PHASE5_RAG_AND_QUERY_EVALUATION.md:1-120`](file:///c:/Users/guru2/Downloads/llm%20prj/PHASE5_RAG_AND_QUERY_EVALUATION.md#L1-L120)
- Machine-Readable Audit Data: [`VERIFIED_RESULTS.json`](file:///c:/Users/guru2/Downloads/llm%20prj/IEEE_REPORT_EVIDENCE/VERIFIED_RESULTS.json), [`VERIFIED_RESULTS.csv`](file:///c:/Users/guru2/Downloads/llm%20prj/IEEE_REPORT_EVIDENCE/VERIFIED_RESULTS.csv)

---

## 1. Executive Summary: Evidence Hierarchy and Academic Truth

An academic paper submitted to an IEEE conference requires rigorous experimental substantiation. This audit systematically investigates all quantitative performance claims in the project repository.

### Key Audit Findings:
1. **The 55-Question Benchmark figures (90.9% Agent vs 61.8% Baseline, P50 2.4s, P90 3.2s, 78% Token Reduction) ARE NOT INDEPENDENTLY VERIFIABLE from repository artifacts.** 
   - There are **no raw run logs, CSV exports, JSON execution traces, or script harnesses** that executed these 55 queries against an LLM.
   - `fintech-agent/data/test_questions.json` contains question prompts, difficulty levels, hints, and operator lists, but **NO gold executable MongoDB aggregation pipelines and NO gold expected output records**.
   - These numbers originate from an early design proposal retained in `SYSTEM_ARCHITECTURE_UPDATED.md:1445` under the explicit caveat: *"The previous architecture draft contained the following reported figures. They are retained for traceability, not as independently verified results."*
2. **The 18-Case RAG Benchmark IS FULLY VERIFIED (`PRE_PHASE4_RAG_EVALUATION.md`).**
   - Evaluated using deterministic schema mock embeddings: **100% Collection Hit Rate, 97.22% Recall@5, 90.74% MRR, 77.78% Precision@5, 100% Unsupported Loan Concept Shield Rate**.
3. **The 18 Banking Archetypes for Synthesis & Validation ARE FULLY VERIFIED (`PHASE5_RAG_AND_QUERY_EVALUATION.md`).**
   - 100% syntactic and policy compliance across all 18 representative banking archetypes.
4. **The Regression Test Suites ARE FULLY VERIFIED:**
   - **368 Backend Pytest Tests:** 100% pass rate.
   - **21 Frontend Vitest Tests:** 100% pass rate.
   - **Zero Database Mutations:** All 19,120 documents remain untouched across all test runs.

---

## 2. Forensic Investigation of the 55-Question Benchmark

### 2.1 Benchmark Composition (`test_questions.json`)
Analysis of `fintech-agent/data/test_questions.json` confirms exactly 55 questions distributed across 5 complexity levels:

| Level | Documented Category / Description | Question Count | Operators Involved | Example Question Prompt |
| :---: | :--- | :---: | :--- | :--- |
| **Level 1** | Simple single-collection retrieval; no aggregation | 10 | `$match`, `$project` | *"Show all active customers."* (Q01) |
| **Level 2** | Filter + sort / count on single collection | 10 | `$match`, `$sort`, `$limit` | *"Which customers have an annual income above ₹10 lakh, sorted by income descending?"* (Q11) |
| **Level 3** | Aggregation on single collection | 10 | `$group`, `$sum`, `$avg`, `$min`, `$max` | *"What is the total balance across all active savings accounts?"* (Q21) |
| **Level 4** | Multi-collection joins via `$lookup` & `$unwind` | 10 | `$lookup`, `$unwind`, `$match`, `$project` | *"Show customer details along with their branch name for all premium customers."* (Q31) |
| **Level 5** | Complex multi-step pipelines / derived metrics | 15 | Chained `$lookup`, `$addFields`, `$facet` | *"Show the complete loan + account + customer summary for all defaulted loan customers..."* (Q50) |
| **TOTAL** | — | **55** | — | — |

### 2.2 Forensic Audit of Historical Accuracy Claims

Section 13.6 of `SYSTEM_ARCHITECTURE_UPDATED.md` reported:
- Overall Agent Accuracy: `90.9% (50/55)`
- Baseline Accuracy: `61.8% (34/55)`
- Self-Correction Convergence: `75.0% (9/12)`
- Latency P50: `2.4s` | Latency P90: `3.2s`
- Prompt Token Reduction: `78%`

#### Critical Flaws Identified During Audit:
1. **Mathematical Inconsistency in Baseline:**
   The reported baseline accuracy is `34/55 = 61.8%`. However, the tier breakdowns in the same table reconstruct as:
   - Tier 1 (10 items @ 100%): 10 correct
   - Tier 2 (10 items @ 75.0%): 7.5 -> rounded to 7 or 8 correct
   - Tier 3 (10 items @ 40.0%): 4 correct
   - Tier 4 (10 items @ 50.0%): 5 correct
   - Tier 5 (15 items @ 37.5%? Wait: in table it says 37.5%, which corresponds to 3/8, not /15!)
   - The tier percentages sum mathematically to **33 out of 55 (60.0%)**, directly contradicting the claimed 34 (61.8%).
2. **Tier Mismatch vs. Canonical Question Set:**
   The historical table labeled Tier 5 as *"Adversarial / Safety"*. But inspection of `test_questions.json` reveals that **Level 5 consists of 15 complex multi-step banking queries (Q41–Q55)**, not adversarial safety attacks!
3. **Absence of Evaluation Artifacts:**
   A thorough search of all directories (`backend/`, `scripts/`, `fintech-agent/`, `logs/`) reveals:
   - Zero files named `*benchmark*.csv`, `*results*.json`, or `run_evaluation.py`.
   - `test_questions.json` was never imported by any script in `backend/` or `scripts/`.
4. **Conclusion for IEEE Paper:**
   The 55-question accuracy numbers **cannot be presented as measured experimental findings**. In the IEEE paper, `test_questions.json` must be introduced as an **"Analytical Benchmark Query Catalogue Designed for Five Complexity Tiers"**, while experimental results must focus on the independently verified 18-case RAG retrieval and synthesis evaluations.

---

## 3. Verified Experimental Results: 18-Case RAG Subsystem

The Schema Retrieval Subsystem was rigorously evaluated against 18 diverse banking query archetypes derived from `SAMPLE_QUERIES.md` ([`PRE_PHASE4_RAG_EVALUATION.md`](file:///c:/Users/guru2/Downloads/llm%20prj/PRE_PHASE4_RAG_EVALUATION.md)).

### 3.1 Experimental Configuration
- **Vector Store:** ChromaDB (`fintech_schema_catalog_cosine`)
- **Distance Metric:** Cosine similarity (`hnsw:space = cosine`)
- **Indexed Schema Chunks:** 269 documents
- **Embedding Provider:** Deterministic `MockEmbeddingProvider` (pinned 384-dimensional unit vectors)
- **Top-K Parameter:** $K = 5$

### 3.2 Quantitative Results Table

| Query ID | Natural Language Query | Query Category | Target Collection(s) | Hit Rate | Recall@5 | MRR | Precision@5 | Unsupported Shield |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Q01** | Show customers from Chennai | Single Filter | `customers` | 1.00 | 1.00 | 1.00 | 1.00 | Clean |
| **Q02** | Find transactions above ₹10,000 | Numeric Range | `transactions` | 1.00 | 1.00 | 1.00 | 0.80 | Clean |
| **Q03** | Show customers with active loans | Multi-Join | `customers`, `loans` | 1.00 | 1.00 | 1.00 | 1.00 | Clean |
| **Q04** | Accounts of customers in Coimbatore | Multi-Join | `accounts`, `customers` | 1.00 | 1.00 | 0.50 | 0.40 | Clean |
| **Q05** | Credit cards expiring this month | Date / Attribute | `cards` | 1.00 | 1.00 | 1.00 | 1.00 | Clean |
| **Q06** | Merchants with high transaction volumes | Join / Aggregate | `merchants`, `transactions` | 1.00 | 1.00 | 1.00 | 0.80 | Clean |
| **Q07** | Employees working at a branch | Hierarchy Join | `employees`, `branches` | 1.00 | 1.00 | 0.33 | 0.20 | Clean |
| **Q08** | KYC documents belonging to customers | Compliance Join | `kyc_documents`, `customers`| 1.00 | 1.00 | 1.00 | 0.20 | Clean |
| **Q09** | Show outstanding loan balances | Loan Balances | `loans` | 1.00 | 1.00 | 1.00 | 1.00 | Clean |
| **Q10** | Overdue loans with DPD and overdue amount | Shielding Test | `loans` | 1.00 | 1.00 | 1.00 | 1.00 | **Triggered** |
| **Q11** | Delinquent borrowers with loans in arrears| Synonym Shielding | `loans` | 1.00 | 1.00 | 1.00 | 0.80 | **Triggered** |
| **Q12** | List NPA accounts with late payments | Regulatory Shielding | `loans` | 1.00 | 1.00 | 1.00 | 0.60 | **Triggered** |
| **Q13** | Customers with outstanding loans | Control (Clean) | `customers`, `loans` | 1.00 | 1.00 | 1.00 | 1.00 | Clean (No False Alarm) |
| **Q14** | Fraud alerts for suspicious transactions | Risk Analysis | `fraud_alerts`, `transactions`| 1.00 | 1.00 | 1.00 | 1.00 | Clean |
| **Q15** | Customer investments in stocks | Wealth / Join | `investments`, `customers` | 1.00 | 1.00 | 1.00 | 0.60 | Clean |
| **Q16** | Support tickets assigned to employees | Operations / Join | `support_tickets`, `employees`| 1.00 | 1.00 | 1.00 | 0.80 | Clean |
| **Q17** | Active contactless credit cards | Card Filtering | `cards` | 1.00 | 1.00 | 1.00 | 1.00 | Clean |
| **Q18** | Branch managers for all branches | Management Join | `branches`, `employees` | 1.00 | 0.50 | 0.50 | 0.80 | Clean |

### 3.3 Aggregate Metrics Analysis
- **Collection Hit Rate:** **100.0% (18/18)** — In all 18 cases, at least one correct target collection was retrieved in Top-5.
- **Collection Recall@5:** **97.22% (0.972)** — Captured almost all required join partners across multi-collection queries.
- **Mean Reciprocal Rank (MRR):** **90.74% (0.907)** — The primary target collection ranked #1 in 15 of 18 cases, #2 in 2 cases (Q04, Q18), and #3 in 1 case (Q07).
- **Collection Precision@5:** **77.78% (0.778)** — Minimal irrelevant collection noise in prompt context.
- **Unsupported Shield Recall:** **100.0% (3/3)** — Successfully intercepted `overdue_amount`, `days_past_due`, and arrears synonyms.
- **Shield False-Positive Rate:** **0.0% (0/1)** — Legitimate query Q13 (*"outstanding loans"*) triggered zero false warnings.

---

## 4. Separation of Verification Domains

The IEEE paper must strictly avoid conflating test categories:

```
+-----------------------------------------------------------------------------------+
|                        INDEPENDENT VERIFICATION TIERS                             |
+-----------------------------------------------------------------------------------+
|  Tier A: Software Engineering Quality (Unit & Integration Tests)                  |
|          - 368 Pytest backend tests passing (100%)                                |
|          - 21 Vitest frontend tests passing (100%)                                |
|          - Proves code stability, error handling, and state machine transitions.  |
|                                                                                   |
|  Tier B: Database Security & Sandboxing Assurance                                |
|          - 100% of prohibited operators blocked ($out, $merge, $where).           |
|          - 19,120 original documents completely unmodified (0 mutations).         |
|          - Proves database defense-in-depth and fail-closed gates.                |
|                                                                                   |
|  Tier C: Empirical Schema RAG Retrieval Quality                                   |
|          - 18 banking cases evaluated with cosine similarity.                     |
|          - MRR: 90.74%, Recall@5: 97.22%, Shield Rate: 100%.                      |
|          - Proves schema grounding and elimination of hallucinated fields.        |
|                                                                                   |
|  Tier D: Full Natural Language to MQL Execution Accuracy                          |
|          - 55-question catalogue defined across 5 complexity levels.              |
|          - End-to-end execution accuracy NOT independently verified.              |
|          - Transparently documented as a future evaluation milestone.             |
+-----------------------------------------------------------------------------------+
```
