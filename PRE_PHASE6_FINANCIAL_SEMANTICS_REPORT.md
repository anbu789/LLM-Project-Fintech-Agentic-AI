# Pre-Phase 6 Financial Semantics Report: Loan Health, Delinquency, and Defaults
**Project:** FinTech Agent — Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Course:** INT450 — Large Language Models and Agentic AI  
**Author:** Financial Systems Architect & Financial Domain Quality Reviewer  
**Date:** November 10, 2026  
**Standards Reference:** Basel II / Basel III Credit Risk Framework, IFRS 9 Financial Instruments, Indian Banking Regulations (RBI Master Circular on IRAC Norms)  

---

## 1. Executive Summary

In commercial banking operations, credit risk terminology must be rigorously defined and mapped to canonical database schema fields. Misinterpreting loan delinquency metrics can lead to incorrect provisioning, distorted capital adequacy calculations, and false regulatory filings.

This report documents the resolution of the **Overdue Loan vs. Defaulted Loan Financial Semantic Defect** in the FinTech Agent preceding Phase 6 query execution.

### Key Corrections:
1. **Separation of Concepts:** The system strictly separates **Remaining Loan Principal** (`outstanding_amount`), **Default Status** (`status = "defaulted"`), and **Delinquent/Overdue Debt** (unpaid installments/DPD).
2. **Elimination of Misleading Proxies:** The system no longer synthesizes `status: "defaulted"` as an answer to questions asking for overdue loans, overdue amounts, or days past due (DPD).
3. **Structured Unsupported Handling:** Natural language inquiries for overdue debt return a structured `UNSUPPORTED` status with plain-language guidance explaining that the current dataset lacks overdue installment amounts and delinquency aging schedules.
4. **Legitimate Default Queries Supported:** Inquiries legitimately requesting defaulted loans or their outstanding principal balance continue to be supported, with clear metric labeling.

---

## 2. Canonical Loan Schema Analysis

According to the canonical schema source of truth ([`fintech-agent/data/schema.json`](file:///c:/Users/guru2/Downloads/llm%20prj/fintech-agent/data/schema.json)), the `loans` collection contains the following verified fields:

| Field Name | Type | Allowed Values / Constraints | Financial Meaning |
|---|---|---|---|
| `loan_id` | string | Primary key (e.g., `LOAN000001`) | Unique contract identifier |
| `customer_id` | string | Foreign key -> `customers.customer_id` | Borrowing entity |
| `loan_type` | string | `home`, `personal`, `auto`, `education`, `gold`, `business` | Credit facility type |
| `principal_amount` | number | INR currency value | Original disbursed principal |
| `interest_rate` | number | Annual percentage | Contractual interest rate |
| `tenure_months` | integer | Term duration | Facility amortization period |
| `emi_amount` | number | INR currency value | Equated monthly installment |
| `disbursement_date` | date | ISO date | Date loan funds were released |
| `status` | string | `active`, `closed`, `defaulted` | Current loan portfolio state |
| `outstanding_amount` | number | 0 when closed; >0 when active or defaulted | Total remaining principal balance |
| `next_due_date` | date | Null when closed; past date when defaulted; future when active | Next contractual installment date |

### Missing Regulatory Fields in Schema:
- **`loans.overdue_amount`:** **DOES NOT EXIST**.
- **`loans.days_past_due` (DPD):** **DOES NOT EXIST**.
- **Delinquency Aging Buckets (SMA-0, SMA-1, SMA-2):** **DOES NOT EXIST**.

---

## 3. Financial Distinctions: Principal Balance vs. Overdue Debt

In commercial lending and banking accounting:

```
+---------------------------------------------------------------------------------------+
|                                    LOAN BALANCE CONCEPTS                              |
+---------------------------------------------------------------------------------------+
|  1. Principal Amount:                                                                 |
|     The original loan principal disbursed to the borrower at contract inception.      |
|                                                                                       |
|  2. Outstanding Amount (Remaining Principal Balance):                                 |
|     The total unpaid principal remaining on the loan account at a point in time.      |
|     - For an active loan: standard performing principal balance.                      |
|     - For a defaulted loan: total unrecovered principal balance subject to recovery.  |
|                                                                                       |
|  3. Overdue Amount (Arrears):                                                         |
|     The sum of past-due EMI installments that the borrower has failed to pay by the   |
|     due date. Includes missed principal installments, accrued overdue interest, and   |
|     late payment penalties.                                                           |
|                                                                                       |
|  4. Days Past Due (DPD):                                                              |
|     The elapsed count of days since the oldest unpaid installment was due.             |
|     (e.g., DPD 1-30: SMA-0; DPD 31-60: SMA-1; DPD 61-90: SMA-2; DPD >90: NPA/Default)|
+---------------------------------------------------------------------------------------+
```

### Why Substituting Outstanding Principal as Overdue Debt is False:
- If a customer has a ₹50,00,000 home loan and defaults after missing 3 monthly EMI payments of ₹50,000:
  - **Actual Overdue Arrears:** ₹1,50,000 (3 missed EMIs) + penalties.
  - **Total Outstanding Principal Balance:** ₹46,50,000 (remaining loan debt).
- If an agent reports ₹46,50,000 as the "overdue amount", it overstates the customer's immediate overdue arrears by more than **3,000%**!
- In banking operations, this distortion would corrupt collection workflows and misinform credit committees.

---

## 4. Remediation Behavior Matrix

| Natural Language Query | Old (Defective) Behavior | New (Remediated) Behavior | Pipeline Synthesized | Response Classification |
|---|---|---|---|---|
| *"Show defaulted loans"* | Synthesized `status: "defaulted"` | Synthesized `status: "defaulted"` | `[{"$match": {"status": "defaulted"}}, ...]` | **SUPPORTED** (`QUERY_ONLY`) |
| *"Calculate outstanding principal of defaulted loans"* | Synthesized `outstanding_amount` | Synthesized sum of `outstanding_amount` labeled strictly as "Total outstanding principal of defaulted loans" | `[{"$match": {"status": "defaulted"}}, {"$group": {"_id": None, "total_defaulted_principal": {"$sum": "$outstanding_amount"}}}]` | **SUPPORTED** (`QUERY_ONLY`) |
| *"Show overdue loans"* | Filtered `status: "defaulted"` (False proxy) | Refuses substitution; marks `UNSUPPORTED` | `[]` (No pipeline) | **UNSUPPORTED** (`UNSUPPORTED`) |
| *"Show overdue amount"* | Calculated `sum(outstanding_amount)` (False proxy) | Refuses substitution; marks `UNSUPPORTED` | `[]` (No pipeline) | **UNSUPPORTED** (`UNSUPPORTED`) |
| *"Show loans with more than 30 days past due"* | Filtered `status: "defaulted"` (False proxy) | Refuses substitution; marks `UNSUPPORTED` | `[]` (No pipeline) | **UNSUPPORTED** (`UNSUPPORTED`) |

---

## 5. User-Facing Guidance Template

When an unsupported overdue query is submitted, Node 8 formats the response using the newly established template:

```markdown
[UNSUPPORTED] **Unsupported Banking Concept**

- Requested concept 'overdue_amount' is not present in schema.
- Requested concept 'days_past_due' is not present in schema.

**Canonical Schema Guidance:**
- `loans.outstanding_amount` exists and represents remaining principal balance.
- `loans.overdue_amount` and `loans.days_past_due` do NOT exist in the banking dataset.
- In commercial banking, total remaining principal on a defaulted loan is fundamentally distinct from overdue installments, interest arrears, or late penalties.
- To analyze defaulted loans, please submit a separate query such as:
  - "Show defaulted loans"
  - "Calculate total outstanding principal of defaulted loans"
```

---
*Financial semantics report certified by Banking Systems Quality Engineer.*
