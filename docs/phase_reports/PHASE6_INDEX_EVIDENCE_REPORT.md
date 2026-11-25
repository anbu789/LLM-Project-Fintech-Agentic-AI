# Phase 6 Actual MongoDB Unique-Index Evidence Report
**Metadata Inspection of the 12 Canonical Banking Collections & MQL Join Validation Rules**

**Project:** FinTech Agent — Natural Language to Sandboxed MongoDB Query Agent for Banking Operations  
**Course:** INT450 — Large Language Models and Agentic AI  
**Inspection Date:** November 11, 2026  
**Auditor Roles:** Principal MongoDB Specialist, AI Data Architect & Security Engineer  
**Database Inspected:** `fintech_agent_db` (Read-only metadata inspection via `listIndexes`)  
**Data Retrieval Attestation:** ZERO banking documents were read, queried, sampled, or modified.  
**Machine-Readable Evidence:** [`PHASE6_VERIFIED_INDEX_EVIDENCE.json`](file:///c:/Users/guru2/Downloads/llm%20prj/PHASE6_VERIFIED_INDEX_EVIDENCE.json)  

---

## 1. Executive Summary

To eliminate unverified assumptions regarding database index uniqueness, a direct read-only metadata inspection was conducted across all 12 canonical banking collections in `fintech_agent_db`.

The investigation established that:
1. Every collection possesses an engine-enforced unique index on `_id` (`_id_`).
2. Every collection possesses an engine-enforced single-field unique index on its primary domain key (e.g. `customer_id` on `customers`, `account_id` on `accounts`).
3. None of the primary domain unique indexes are compound, sparse, partial, or collation-restricted.
4. All foreign key fields (e.g. `customer_id` on `accounts`, `customer_id` on `transactions`, `account_id` on `transactions`) are explicitly indexed with **`unique: false`**.
5. The confirmed uniqueness catalogue has been directly integrated into [`mql_policy_validator.py`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/agent/nodes/mql_policy_validator.py) via `_load_confirmed_unique_index_fields()`, ensuring that joins are treated as inherently 1:1 *only* when uniqueness is proven by verified database index metadata.

---

## 2. Collection-by-Collection Index Evidence Table

| Collection Name | Index Name | Key Fields & Order | Unique Flag | Sparse | Partial Filter | Collation | Verified Uniqueness Status |
|---|---|---|---|---|---|---|---|
| `accounts` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `accounts` | `account_id_1` | `account_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `accounts` | `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `accounts` | `branch_id_1` | `branch_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `accounts` | `status_1` | `status: 1` | False | False | None | None | Non-Unique (Filter) |
| `branches` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `branches` | `branch_id_1` | `branch_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `cards` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `cards` | `card_id_1` | `card_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `cards` | `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `cards` | `account_id_1` | `account_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `customers` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `customers` | `customer_id_1` | `customer_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `customers` | `status_1` | `status: 1` | False | False | None | None | Non-Unique (Filter) |
| `customers` | `risk_category_1` | `risk_category: 1` | False | False | None | None | Non-Unique (Filter) |
| `employees` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `employees` | `employee_id_1` | `employee_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `employees` | `branch_id_1` | `branch_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `fraud_alerts` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `fraud_alerts` | `alert_id_1` | `alert_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `fraud_alerts` | `transaction_id_1`| `transaction_id: 1`| False | False | None | None | Non-Unique (1:N FK) |
| `fraud_alerts` | `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `investments` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `investments` | `investment_id_1`| `investment_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `investments` | `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `kyc_documents` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `kyc_documents` | `kyc_id_1` | `kyc_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `kyc_documents` | `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `loans` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `loans` | `loan_id_1` | `loan_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `loans` | `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `loans` | `sanctioning_branch_id_1`| `sanctioning_branch_id: 1`| False | False | None | None | Non-Unique (1:N FK) |
| `loans` | `status_1` | `status: 1` | False | False | None | None | Non-Unique (Filter) |
| `merchants` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `merchants` | `merchant_id_1` | `merchant_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `support_tickets`| `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `support_tickets`| `ticket_id_1` | `ticket_id: 1` | **True** | False | None | None | **Confirmed Unique** |
| `support_tickets`| `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `support_tickets`| `status_1` | `status: 1` | False | False | None | None | Non-Unique (Filter) |
| `transactions` | `_id_` | `_id: 1` | Inherently True | False | None | None | Genuinely Unique |
| `transactions` | `transaction_id_1`| `transaction_id: 1`| **True** | False | None | None | **Confirmed Unique** |
| `transactions` | `account_id_1` | `account_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `transactions` | `customer_id_1` | `customer_id: 1` | False | False | None | None | Non-Unique (1:N FK) |
| `transactions` | `transaction_date_1`| `transaction_date: 1`| False | False | None | None | Non-Unique (Filter) |
| `transactions` | `transaction_mode_1`| `transaction_mode: 1`| False | False | None | None | Non-Unique (Filter) |
| `transactions` | `status_1` | `status: 1` | False | False | None | None | Non-Unique (Filter) |
| `transactions` | `is_flagged_1` | `is_flagged: 1` | False | False | None | None | Non-Unique (Filter) |

---

## 3. Confirmed Uniqueness Catalogue for MQL Validation

Based strictly on verified database metadata:
- **`accounts`:** `_id`, `account_id`
- **`branches`:** `_id`, `branch_id`
- **`cards`:** `_id`, `card_id`
- **`customers`:** `_id`, `customer_id`
- **`employees`:** `_id`, `employee_id`
- **`fraud_alerts`:** `_id`, `alert_id`
- **`investments`:** `_id`, `investment_id`
- **`kyc_documents`:** `_id`, `kyc_id`
- **`loans`:** `_id`, `loan_id`
- **`merchants`:** `_id`, `merchant_id`
- **`support_tickets`:** `_id`, `ticket_id`
- **`transactions`:** `_id`, `transaction_id`

### 3.1 Architectural Impact on Join Bounding
1. **Inherently 1:1 / N:1 Joins (No inner limit required):**
   When `accounts` joins `customers` with `foreignField: "customer_id"`, `customer_id` is a confirmed unique field in `customers`. The engine will join at most one document per account, making unbounded array expansion impossible.
2. **Inherently 1:N Joins (Inner pipeline `$limit <= 100` strictly required):**
   When `customers` joins `transactions` with `foreignField: "customer_id"`, `customer_id` has `unique: false` in `transactions`. The engine could join thousands of documents per customer, risking memory exhaustion. Node 5 strictly enforces an inner `$limit <= 100`.
3. **Conservative Fallback:**
   If a field is not listed in `CONFIRMED_UNIQUE_INDEX_FIELDS` (or `_id`), Node 5 assumes 1:N cardinality and requires an inner pipeline limit.
