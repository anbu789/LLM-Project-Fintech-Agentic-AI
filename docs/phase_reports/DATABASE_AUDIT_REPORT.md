# FinTech Agent — Database Audit Report

> **Project:** FinTech Agent: Natural Language to Sandboxed MongoDB Query Agent  
> **Course:** INT450 — Large Language Models and Agentic AI  
> **Team:** T11 · SASTRA Deemed University  
> **Database:** `fintech_agent_db` (MongoDB 8.0.6 on localhost:27017)  
> **Date:** 2026-11-10  
> **Audit Status:** Verified against `schema.json` v2 and live MongoDB instance

---

## 1. Executive Summary

This report documents the live state, inventory, schema adherence, BSON types, relational integrity, and indexing of the banking database `fintech_agent_db`.

* **Total Collections:** 12
* **Total Documents:** 20,120
* **Relational Integrity Checks:** 22 foreign-key references verified (100% pass)
* **Integrity Constraints:** 202 of 203 validation checks passed
* **Zero-Write Safety:** Enforced via application-level `ReadOnlyDatabaseProxy` and dedicated read-only role architecture.

---

## 2. Collection Inventory and Document Counts

| # | Collection Name | Primary Key | Document Count | Purpose | Status |
|---|---|---|---|---|---|
| 1 | `branches` | `branch_id` | 20 | Bank branch physical locations | Verified |
| 2 | `employees` | `employee_id` | 100 | Bank staff, managers, loan officers | Verified |
| 3 | `merchants` | `merchant_id` | 200 | Merchant commercial directory | Verified |
| 4 | `customers` | `customer_id` | 1,000 | Retail & corporate banking customers | Verified |
| 5 | `accounts` | `account_id` | 1,500 | Savings, Current, FD, RD accounts | Verified |
| 6 | `transactions` | `transaction_id` | 10,000 | Financial transaction ledger | Verified |
| 7 | `cards` | `card_id` | 1,000 | Debit and credit cards | Verified |
| 8 | `loans` | `loan_id` | 500 | Term loans, mortgages, vehicle loans | Verified |
| 9 | `kyc_documents` | `kyc_id` | 1,500 | Identity verification records | Verified |
| 10 | `support_tickets` | `ticket_id` | 2,000 | Customer service inquiries & disputes | Verified |
| 11 | `fraud_alerts` | `alert_id` | 300 | Suspicious activity flags | Verified |
| 12 | `investments` | `investment_id` | 1,000 | Mutual funds, stocks, fixed deposits | Verified |
| **Total** | | | **20,120** | | |

---

## 3. Schema Verification and Special Field Analysis

### 3.1 Field-Level Audit

Every collection was audited against `fintech-agent/data/schema.json` v2. All documented primary keys, foreign keys, and low-cardinality enums match the observed BSON types in the MongoDB instance.

### 3.2 Special Warning Fields — Critical Verification

Per the project instructions and architecture review:
* **`loans.days_past_due`**: **100% ABSENT** (Found on 0 of 500 documents in `loans`).
* **`loans.overdue_amount`**: **100% ABSENT** (Found on 0 of 500 documents in `loans`).
* **Actual Field in Database**: **`loans.outstanding_amount`** (Found on 500 of 500 documents in `loans`, BSON `Double`).
  * Closed loans (218 docs): `outstanding_amount == 0.0`.
  * Active loans (278 docs): `outstanding_amount > 0.0`.
  * Defaulted loans (4 docs): `outstanding_amount > 0.0`.

> **Constraint for Agent Query Generation:** The query generator (Node 4) must NEVER generate queries referencing `loans.days_past_due` or `loans.overdue_amount`. Loan status queries must filter on `loans.status` (`active`, `closed`, `defaulted`) and `loans.outstanding_amount`.

---

## 4. Cross-Collection Relationship Audit

All 22 relationship paths were validated across 100% of documents in the database (42,920 total document references checked) via direct MongoDB membership inspection.

| Source Field | Target Collection & Key | Total Docs | Nulls (Allowed) | Matched Docs | Orphaned Docs | Status |
|---|---|---|---|---|---|---|
| `employees.branch_id` | `branches.branch_id` | 100 | 0 | 100 | 0 | **PASS** |
| `branches.manager_id` | `employees.employee_id` | 20 | 0 | 20 | 0 | **PASS** |
| `customers.relationship_manager_id` | `employees.employee_id` | 1,000 | 0 | 1,000 | 0 | **PASS** |
| `accounts.customer_id` | `customers.customer_id` | 1,500 | 0 | 1,500 | 0 | **PASS** |
| `accounts.branch_id` | `branches.branch_id` | 1,500 | 0 | 1,500 | 0 | **PASS** |
| `accounts.account_manager_id` | `employees.employee_id` | 1,500 | 0 | 1,500 | 0 | **PASS** |
| `transactions.account_id` | `accounts.account_id` | 10,000 | 0 | 10,000 | 0 | **PASS** |
| `transactions.customer_id` | `customers.customer_id` | 10,000 | 0 | 10,000 | 0 | **PASS** |
| `transactions.merchant_id` | `merchants.merchant_id` | 10,000 | 3,491 | 6,509 | 0 | **PASS** |
| `cards.customer_id` | `customers.customer_id` | 1,000 | 0 | 1,000 | 0 | **PASS** |
| `cards.account_id` | `accounts.account_id` | 1,000 | 0 | 1,000 | 0 | **PASS** |
| `loans.customer_id` | `customers.customer_id` | 500 | 0 | 500 | 0 | **PASS** |
| `loans.sanctioning_branch_id` | `branches.branch_id` | 500 | 0 | 500 | 0 | **PASS** |
| `loans.loan_officer_id` | `employees.employee_id` | 500 | 0 | 500 | 0 | **PASS** |
| `kyc_documents.customer_id` | `customers.customer_id` | 1,500 | 0 | 1,500 | 0 | **PASS** |
| `kyc_documents.verified_by` | `employees.employee_id` | 1,500 | 442 | 1,058 | 0 | **PASS** |
| `support_tickets.customer_id` | `customers.customer_id` | 2,000 | 0 | 2,000 | 0 | **PASS** |
| `support_tickets.assigned_agent_id` | `employees.employee_id` | 2,000 | 0 | 2,000 | 0 | **PASS** |
| `fraud_alerts.transaction_id` | `transactions.transaction_id` | 300 | 0 | 300 | 0 | **PASS** |
| `fraud_alerts.customer_id` | `customers.customer_id` | 300 | 0 | 300 | 0 | **PASS** |
| `fraud_alerts.reviewed_by` | `employees.employee_id` | 300 | 120 | 180 | 0 | **PASS** |
| `investments.customer_id` | `customers.customer_id` | 1,000 | 0 | 1,000 | 0 | **PASS** |
| **Total** | | **42,920** | **4,053** | **38,867** | **0** | **100% PASS** |

---

## 5. Investigation of validate_dataset.py Exit Code 1

When `python fintech-agent/data/validate_dataset.py` was executed, it completed 202 checks successfully and failed 1 check, causing `sys.exit(1)`.

### Exact Failure Trace
* **Failing Check:** `integrity.loans.active_next_due_future` (lines 394–402 of `validate_dataset.py`)
* **Assertion:**
  ```python
  count = db["loans"].count_documents({
      "status": "active",
      "next_due_date": {"$lte": NOW}
  })
  if count:
      fail("integrity.loans.active_next_due_future", f"{count} active loans with past/present next_due_date")
  ```
* **Observed Count:** 214 active loans flagged.
* **Root Cause Analysis:**
  1. The synthetic dataset generator created active loans with `next_due_date` values scheduled within a 60-day window following the generation timestamp (`2026-09-25`). Specifically, active loan due dates range from `2026-09-27` to `2026-11-24`.
  2. `validate_dataset.py` defines `NOW = datetime.now()`, which evaluates dynamically to the current wall-clock date (`2026-11-10`).
  3. Because 46 days have elapsed since data generation, 214 of the 278 active loans have due dates that are now in the past relative to `2026-11-10`, while 64 remain in the future.
  4. The data generator and schema rules correctly created future dates at generation time; the failure is solely due to wall-clock time advancement.
* **Resolution:** Per Phase 1 strict preservation rules, **the dataset was NOT modified or regenerated**, nor was the validation script altered. Future query pipelines must compute temporal queries dynamically.

---

## 6. Index Inventory and Performance Audit

### 6.1 Existing Indexes

| Collection | Index Name | Key Fields | Unique |
|---|---|---|---|
| `accounts` | `_id_` | `_id: 1` | True |
| | `account_id_1` | `account_id: 1` | True |
| | `customer_id_1` | `customer_id: 1` | False |
| | `branch_id_1` | `branch_id: 1` | False |
| | `status_1` | `status: 1` | False |
| `branches` | `_id_` | `_id: 1` | True |
| | `branch_id_1` | `branch_id: 1` | True |
| `cards` | `_id_` | `_id: 1` | True |
| | `card_id_1` | `card_id: 1` | True |
| | `customer_id_1` | `customer_id: 1` | False |
| | `account_id_1` | `account_id: 1` | False |
| `customers` | `_id_` | `_id: 1` | True |
| | `customer_id_1` | `customer_id: 1` | True |
| | `status_1` | `status: 1` | False |
| | `risk_category_1` | `risk_category: 1` | False |
| `employees` | `_id_` | `_id: 1` | True |
| | `employee_id_1` | `employee_id: 1` | True |
| | `branch_id_1` | `branch_id: 1` | False |
| `fraud_alerts` | `_id_` | `_id: 1` | True |
| | `alert_id_1` | `alert_id: 1` | True |
| | `transaction_id_1` | `transaction_id: 1` | False |
| | `customer_id_1` | `customer_id: 1` | False |
| `investments` | `_id_` | `_id: 1` | True |
| | `investment_id_1` | `investment_id: 1` | True |
| | `customer_id_1` | `customer_id: 1` | False |
| `kyc_documents` | `_id_` | `_id: 1` | True |
| | `kyc_id_1` | `kyc_id: 1` | True |
| | `customer_id_1` | `customer_id: 1` | False |
| `loans` | `_id_` | `_id: 1` | True |
| | `loan_id_1` | `loan_id: 1` | True |
| | `customer_id_1` | `customer_id: 1` | False |
| | `sanctioning_branch_id_1` | `sanctioning_branch_id: 1` | False |
| | `status_1` | `status: 1` | False |
| `merchants` | `_id_` | `_id: 1` | True |
| | `merchant_id_1` | `merchant_id: 1` | True |
| `support_tickets` | `_id_` | `_id: 1` | True |
| | `ticket_id_1` | `ticket_id: 1` | True |
| | `customer_id_1` | `customer_id: 1` | False |
| | `status_1` | `status: 1` | False |
| `transactions` | `_id_` | `_id: 1` | True |
| | `transaction_id_1` | `transaction_id: 1` | True |
| | `account_id_1` | `account_id: 1` | False |
| | `customer_id_1` | `customer_id: 1` | False |
| | `transaction_date_1` | `transaction_date: 1` | False |
| | `transaction_mode_1` | `transaction_mode: 1` | False |
| | `status_1` | `status: 1` | False |
| | `is_flagged_1` | `is_flagged: 1` | False |

### 6.2 Missing Index Recommendations (For User Approval)

The current indexing covers 100% of primary keys and primary foreign keys. For optimal aggregation pipeline performance in Phase 4+, the following compound indexes are recommended for future creation:
1. `transactions`: Compound index `{"account_id": 1, "transaction_date": -1}` for fast timeline queries.
2. `transactions`: Compound index `{"customer_id": 1, "transaction_date": -1}` for customer statement queries.
3. `branches`: Index on `{"city": 1}` for regional filtering.

Per Phase 1 safety rules, **no indexes were created without explicit prior approval**.

---

## 7. Security and Access Separation Status

### 7.1 Server-Side Authentication Verification
* **Current State:** MongoDB 8.0.6 is operating in **unauthenticated local development mode** (`security.authorization: disabled`, `#security:` commented out in `C:\Program Files\MongoDB\Server\8.0\bin\mongod.cfg`).
* **Server-Level Privileges:** Because `--auth` is disabled on the server, raw TCP client connections to `mongodb://localhost:27017/` connect with unrestricted administrative privileges at the wire protocol level.

### 7.2 Application-Level Read-Only Enforcement
* **Implementation:** Zero-write protection for `fintech_agent_db` is currently enforced deterministically by the Python application layer using [`ReadOnlyDatabaseProxy`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/db/mongo_client.py#L14-L63).
* **Guarantees:** The proxy intercepts any call to `insert_one`, `insert_many`, `update_one`, `update_many`, `replace_one`, `delete_one`, `delete_many`, `drop`, or collection creation/modification, immediately raising a Python `PermissionError`.
* **Testing:** Verified by automated unit tests in `backend/tests/test_phase1_readiness.py`.

### 7.3 Database Separation
* **Banking DB:** `fintech_agent_db` (Contains 12 banking collections).
* **Metadata DB:** `agent_metadata_db` (Target for `query_history`, `scheduled_jobs`, `job_runs`).
* Decoupled connection builders [`get_banking_uri()`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/config.py#L40) and [`get_metadata_uri()`](file:///c:/Users/guru2/Downloads/llm%20prj/backend/app/config.py#L47) guarantee that application writes can never target `fintech_agent_db`.

### 7.4 Required DBA Configuration for Production Server-Side Authentication
To enable database-enforced permissions on MongoDB Server (requires administrative approval and service restart):

1. **Create the Users in MongoDB:**
   ```javascript
   // Run in mongosh or MongoDB Compass as admin:
   use admin;
   db.createUser({
     user: "adminUser",
     pwd: "REPLACE_WITH_SECURE_ADMIN_PASSWORD",
     roles: [{ role: "userAdminAnyDatabase", db: "admin" }, { role: "readWriteAnyDatabase", db: "admin" }]
   });

   use fintech_agent_db;
   db.createUser({
     user: "fintech_reader",
     pwd: "REPLACE_WITH_SECURE_READONLY_PASSWORD",
     roles: [{ role: "read", db: "fintech_agent_db" }]
   });

   use agent_metadata_db;
   db.createUser({
     user: "agent_metadata_writer",
     pwd: "REPLACE_WITH_SECURE_METADATA_PASSWORD",
     roles: [{ role: "readWrite", db: "agent_metadata_db" }]
   });
   ```

2. **Enable Authorization in `mongod.cfg`:**
   In `C:\Program Files\MongoDB\Server\8.0\bin\mongod.cfg`:
   ```yaml
   security:
     authorization: enabled
   ```

3. **Restart the MongoDB Windows Service:**
   ```powershell
   Restart-Service -Name MongoDB
   ```

4. **Update `.env`:**
   Set `MONGO_READONLY_USERNAME`, `MONGO_READONLY_PASSWORD`, `MONGO_METADATA_USERNAME`, and `MONGO_METADATA_PASSWORD`.

