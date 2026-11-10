# Fintech Agent DB — Dataset Documentation

> Synthetic MongoDB banking dataset designed as the foundation for a **Natural-Language-to-MongoDB-Query AI Agent** (B.Tech CSE final-year project).

---

## Table of Contents

1. [Database Overview](#database-overview)
2. [Collections](#collections)
3. [Relationships](#relationships)
4. [Installation](#installation)
5. [Generating the Dataset](#generating-the-dataset)
6. [Validating the Dataset](#validating-the-dataset)
7. [Connecting to MongoDB](#connecting-to-mongodb)
8. [Index Reference](#index-reference)
9. [Changing Dataset Sizes](#changing-dataset-sizes)
10. [Sample MongoDB Queries](#sample-mongodb-queries)
11. [Sample AI-Agent Questions](#sample-ai-agent-questions)
12. [Design Decisions & Assumptions](#design-decisions--assumptions)

---

## Database Overview

| Property | Value |
|---|---|
| **Database name** | `fintech_agent_db` |
| **Collections** | 12 |
| **Default dev size** | ~18,700 documents |
| **Currency** | INR (Indian Rupee) |
| **Locale** | India (`en_IN` Faker locale) |
| **Date range** | 2010 – 2026 |
| **Random seed** | `42` (deterministic) |

---

## Collections

| # | Collection | Purpose | Default Count |
|---|---|---|---|
| 1 | `branches` | Physical bank branches | 20 |
| 2 | `employees` | Bank staff | 100 |
| 3 | `merchants` | Registered merchants | 200 |
| 4 | `customers` | Individual & corporate customers | 1,000 |
| 5 | `accounts` | Bank accounts (savings, current, FD…) | 1,500 |
| 6 | `transactions` | All financial transactions | 10,000 |
| 7 | `cards` | Debit and credit cards | 1,000 |
| 8 | `loans` | Loan records | 500 |
| 9 | `kyc_documents` | KYC identity documents | 1,500 |
| 10 | `support_tickets` | Customer support tickets | 2,000 |
| 11 | `fraud_alerts` | Fraud / suspicious activity alerts | 300 |
| 12 | `investments` | Investment portfolio records | 1,000 |

### Collection Descriptions

**branches** — Seed collection. All other collections that mention a branch reference `branch_id` from here. Contains city, state, branch type (metro/urban/rural/semi-urban), ATM flag, locker facility flag.

**employees** — Referenced as relationship managers, account managers, loan officers, KYC verifiers, and support agents. Some employees manage other employees (self-referential `manager_id`). Managers are back-filled into `branches.manager_id`.

**merchants** — Represents payment destinations (restaurants, petrol pumps, hospitals, etc.). Optionally referenced from `transactions.merchant_id`; null for cash/NEFT/internal transfers.

**customers** — Central entity. Referenced by every other domain collection. Has `kyc_status`, `risk_category`, `customer_type`, `credit_score`, `annual_income`. Includes edge cases: blocked customers, inactive customers, pending/rejected KYC.

**accounts** — One customer can have zero, one, or multiple accounts. Types: savings, current, salary, fixed_deposit, recurring_deposit. Statuses: active, dormant, blocked, closed.

**transactions** — Largest collection. Spans 2023–2026. `customer_id` is denormalised (matches the account's customer) so single-collection queries on customer transactions don't require a `$lookup`. Includes flagged transactions (~2%), failed/pending/reversed transactions.

**cards** — Debit and credit cards. Credit cards have `credit_limit` and `available_credit`; debit cards have both = 0. Cards past their `expiry_date` have `status = 'expired'`.

**loans** — EMI calculated with standard compound-interest formula. Includes active, closed, and defaulted loans. `outstanding_amount` is 0 for closed loans, non-zero for active/defaulted.

**kyc_documents** — A customer may have multiple documents of different types. `verified_by` is null for pending/rejected documents.

**support_tickets** — Spans 2024–2026. `resolved_date` and `satisfaction_rating` are null for open/in-progress tickets.

**fraud_alerts** — Derived from `transactions.is_flagged`. `customer_id` is taken from the referenced transaction's account (not independently randomised) to guarantee referential consistency.

**investments** — Includes mutual funds, FDs, stocks, bonds, PPF. `returns_percentage` can be negative (loss-making investments).

---

## Relationships

```
branches ──────────────────────────────────────────────────┐
    ↑                                                       │
employees.branch_id → branches.branch_id                   │
    ↑                                                       │
branches.manager_id → employees.employee_id                 │
customers.relationship_manager_id → employees.employee_id  │
accounts.account_manager_id → employees.employee_id        │
loans.loan_officer_id → employees.employee_id              │
kyc_documents.verified_by → employees.employee_id          │
support_tickets.assigned_agent_id → employees.employee_id  │
fraud_alerts.reviewed_by → employees.employee_id           │
                                                           │
customers ←────────────────────────────────────────────────┘
    ↑
accounts.customer_id → customers.customer_id
transactions.customer_id → customers.customer_id  (denormalised)
cards.customer_id → customers.customer_id
loans.customer_id → customers.customer_id
kyc_documents.customer_id → customers.customer_id
support_tickets.customer_id → customers.customer_id
fraud_alerts.customer_id → customers.customer_id
investments.customer_id → customers.customer_id

accounts ←─────────────────────────────────────────────────┐
accounts.branch_id → branches.branch_id                    │
    ↑                                                       │
transactions.account_id → accounts.account_id              │
cards.account_id → accounts.account_id                     │
                                                           │
transactions.merchant_id → merchants.merchant_id (nullable)│
fraud_alerts.transaction_id → transactions.transaction_id  │
loans.sanctioning_branch_id → branches.branch_id ──────────┘
```

---

## Installation

### Prerequisites

- Python 3.9+
- MongoDB 6.0+ (local or Atlas)
- pip

### Steps

```bash
# 1. Navigate to the project directory
cd fintech-agent

# 2. (Optional but recommended) Create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Generating the Dataset

### Default (localhost MongoDB)

```bash
python data/generate_dataset.py
```

### Custom MongoDB URI (e.g. MongoDB Atlas)

```bash
set MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
python data/generate_dataset.py
```

```bash
# macOS/Linux
export MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/"
python data/generate_dataset.py
```

### Expected output

```
============================================================
  Fintech Agent DB — Dataset Generator
  MongoDB: mongodb://localhost:27017/  DB: fintech_agent_db
============================================================

[1/12] Dropping existing collections …
  ✓ All collections dropped.
[2/12] Generating 20 branches …
  ✓ 20 branches inserted.
...
  GENERATION SUMMARY
============================================================
  branches               20 documents
  employees             100 documents
  merchants             200 documents
  customers           1,000 documents
  accounts            1,500 documents
  transactions       10,000 documents
  cards               1,000 documents
  loans                 500 documents
  kyc_documents       1,500 documents
  support_tickets     2,000 documents
  fraud_alerts          300 documents
  investments         1,000 documents
============================================================
  Dataset generation complete! ✓
```

---

## Validating the Dataset

```bash
python data/validate_dataset.py
```

The validator checks:
- Collection document counts (non-empty)
- Duplicate primary IDs
- Broken foreign-key references (samples up to 500 docs per check)
- Invalid enum values (exact case matching)
- Invalid numeric ranges (credit_score 300–900, risk_score 0–100, etc.)
- Date logic (opening_date ≤ updated_at, card expiry > issue, etc.)
- Required fields present
- Cross-collection consistency (transaction.customer_id matches account's customer)
- Loan outstanding amounts (≥ 0, 0 for closed loans)

### Expected output

```
  PASS  counts.branches  (20 docs)
  PASS  counts.customers  (1,000 docs)
  ...
  PASS  duplicates.customers
  ...
  PASS  fk.accounts.customer_id→customers  (500 sampled)
  ...
  PASS  enum.customers.status
  ...
  TOTAL PASSED : 75
  TOTAL FAILED : 0
  All checks passed! Dataset is valid. ✓
```

---

## Connecting to MongoDB

### mongosh (CLI)

```bash
mongosh "mongodb://localhost:27017/fintech_agent_db"
```

### Python (pymongo)

```python
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["fintech_agent_db"]

# Quick check
print(db.customers.count_documents({}))
```

### MongoDB Compass

Connect to `mongodb://localhost:27017` and open the `fintech_agent_db` database.

---

## Index Reference

Indexes are created automatically by `generate_dataset.py`. Below is the full list:

```javascript
// Unique primary-key indexes
db.branches.createIndex({ branch_id: 1 }, { unique: true })
db.employees.createIndex({ employee_id: 1 }, { unique: true })
db.merchants.createIndex({ merchant_id: 1 }, { unique: true })
db.customers.createIndex({ customer_id: 1 }, { unique: true })
db.accounts.createIndex({ account_id: 1 }, { unique: true })
db.transactions.createIndex({ transaction_id: 1 }, { unique: true })
db.cards.createIndex({ card_id: 1 }, { unique: true })
db.loans.createIndex({ loan_id: 1 }, { unique: true })
db.kyc_documents.createIndex({ kyc_id: 1 }, { unique: true })
db.support_tickets.createIndex({ ticket_id: 1 }, { unique: true })
db.fraud_alerts.createIndex({ alert_id: 1 }, { unique: true })
db.investments.createIndex({ investment_id: 1 }, { unique: true })

// Foreign-key / filter indexes (non-unique)
db.employees.createIndex({ branch_id: 1 })
db.accounts.createIndex({ customer_id: 1 })
db.accounts.createIndex({ branch_id: 1 })
db.transactions.createIndex({ account_id: 1 })
db.transactions.createIndex({ customer_id: 1 })
db.transactions.createIndex({ transaction_date: 1 })
db.transactions.createIndex({ transaction_type: 1 })
db.transactions.createIndex({ status: 1 })
db.cards.createIndex({ customer_id: 1 })
db.cards.createIndex({ account_id: 1 })
db.loans.createIndex({ customer_id: 1 })
db.loans.createIndex({ sanctioning_branch_id: 1 })
db.loans.createIndex({ status: 1 })
db.kyc_documents.createIndex({ customer_id: 1 })
db.support_tickets.createIndex({ customer_id: 1 })
db.fraud_alerts.createIndex({ transaction_id: 1 })
db.fraud_alerts.createIndex({ customer_id: 1 })
db.investments.createIndex({ customer_id: 1 })
```

---

## Changing Dataset Sizes

Open `data/generate_dataset.py` and edit the `CONFIG` dictionary at the top:

```python
CONFIG = {
    "NUM_BRANCHES":        20,    # ← change these
    "NUM_EMPLOYEES":      100,
    "NUM_MERCHANTS":      200,
    "NUM_CUSTOMERS":     1000,
    "NUM_ACCOUNTS":      1500,
    "NUM_TRANSACTIONS": 10000,
    "NUM_CARDS":         1000,
    "NUM_LOANS":          500,
    "NUM_KYC_DOCS":      1500,
    "NUM_TICKETS":       2000,
    "NUM_FRAUD_ALERTS":   300,
    "NUM_INVESTMENTS":   1000,
    "BATCH_SIZE":         500,    # bulk-insert batch size
    "DROP_EXISTING":     True,    # wipe before regenerating
}
```

Re-run `python data/generate_dataset.py` — no other changes needed.

> **Scaling tip:** For a production-size dataset (e.g. 100k transactions), simply multiply the counts. The random seed ensures deterministic output at any size.

---

## Sample MongoDB Queries

### 1. All active customers from Karnataka

```javascript
db.customers.find({
  status: "Active",
  state:  "Karnataka"
})
```

### 2. Top 5 accounts by balance

```javascript
db.accounts.find({}, { account_id:1, balance:1, account_type:1 })
           .sort({ balance: -1 })
           .limit(5)
```

### 3. Total transaction amount per month (2025)

```javascript
db.transactions.aggregate([
  { $match: {
      transaction_date: {
        $gte: new Date("2025-01-01"),
        $lt:  new Date("2026-01-01")
      }
  }},
  { $group: {
      _id:   { month: { $month: "$transaction_date" } },
      total: { $sum: "$amount" },
      count: { $sum: 1 }
  }},
  { $sort: { "_id.month": 1 } }
])
```

### 4. Customers with defaulted loans (with name)

```javascript
db.loans.aggregate([
  { $match: { status: "defaulted" } },
  { $lookup: {
      from:         "customers",
      localField:   "customer_id",
      foreignField: "customer_id",
      as:           "customer"
  }},
  { $unwind: "$customer" },
  { $project: {
      loan_id:          1,
      loan_type:        1,
      outstanding_amount:1,
      principal_amount: 1,
      "customer.first_name": 1,
      "customer.last_name":  1,
      "customer.credit_score": 1
  }}
])
```

### 5. Branch with highest total sanctioned loan amount

```javascript
db.loans.aggregate([
  { $group: {
      _id:           "$sanctioning_branch_id",
      total_loans:   { $sum: "$principal_amount" },
      count:         { $sum: 1 }
  }},
  { $sort: { total_loans: -1 } },
  { $limit: 1 },
  { $lookup: {
      from:         "branches",
      localField:   "_id",
      foreignField: "branch_id",
      as:           "branch"
  }},
  { $unwind: "$branch" },
  { $project: {
      "branch.branch_name": 1,
      "branch.city":        1,
      total_loans:          1,
      count:                1
  }}
])
```

### 6. Customers with active personal loans who made > 5 transactions in last 3 months

```javascript
// Step 1: Get customer_ids with active personal loans
const activeLoanCusts = db.loans.distinct("customer_id", {
  loan_type: "personal",
  status:    "active"
});

// Step 2: Count their recent transactions
const threeMonthsAgo = new Date();
threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);

db.transactions.aggregate([
  { $match: {
      customer_id:      { $in: activeLoanCusts },
      transaction_date: { $gte: threeMonthsAgo },
      status:           "success"
  }},
  { $group: {
      _id:   "$customer_id",
      count: { $sum: 1 }
  }},
  { $match: { count: { $gt: 5 } } },
  { $lookup: {
      from:         "customers",
      localField:   "_id",
      foreignField: "customer_id",
      as:           "customer"
  }},
  { $unwind: "$customer" },
  { $project: {
      "customer.first_name": 1,
      "customer.last_name":  1,
      count: 1
  }}
])
```

### 7. Customer 360 view

```javascript
db.customers.aggregate([
  { $match: { customer_id: "CUST000001" } },
  { $lookup: { from: "accounts",        localField: "customer_id", foreignField: "customer_id", as: "accounts" }},
  { $lookup: { from: "loans",           localField: "customer_id", foreignField: "customer_id", as: "loans" }},
  { $lookup: { from: "cards",           localField: "customer_id", foreignField: "customer_id", as: "cards" }},
  { $lookup: { from: "support_tickets", localField: "customer_id", foreignField: "customer_id", as: "tickets" }},
  { $lookup: { from: "investments",     localField: "customer_id", foreignField: "customer_id", as: "investments" }},
  { $project: {
      first_name:       1,
      last_name:        1,
      credit_score:     1,
      kyc_status:       1,
      account_count:    { $size: "$accounts" },
      loan_count:       { $size: "$loans" },
      card_count:       { $size: "$cards" },
      open_tickets:     { $size: { $filter: { input: "$tickets", cond: { $in: ["$$this.status", ["open","in_progress"]] }}}},
      investment_count: { $size: "$investments" }
  }}
])
```

---

## Sample AI-Agent Questions

These are drawn from `data/test_questions.json` (55 total, 5 difficulty levels):

| Level | Question | Key Operators |
|---|---|---|
| 1 | Show all active customers | `$match` |
| 1 | List all fraud alerts that are still open | `$match` |
| 2 | Top 10 accounts with highest balance | `$sort`, `$limit` |
| 2 | How many transactions failed in 2024? | `$match`, `$count` |
| 3 | Average balance of savings accounts | `$match`, `$group`, `$avg` |
| 3 | Total transaction amount per month in 2025 | `$group`, `$month`, `$sum` |
| 4 | Which branch sanctioned the highest total loan amount? | `$group`, `$lookup` |
| 4 | Customers who have never taken a loan | `$lookup`, `$match` |
| 5 | Customers with active personal loans who made > 5 txns in last 3 months | `$lookup`, `$group`, `$expr` |
| 5 | Customer 360 view (accounts + loans + cards + tickets) | Multi-`$lookup`, `$size` |

---

## Design Decisions & Assumptions

1. **Referential integrity over convenience** — Foreign keys are always selected from the actual parent collection's ID pool. The fraud alert `customer_id` is derived from `transaction → account → customer`, not randomly assigned.

2. **`customer_id` denormalised in `transactions`** — Avoids a mandatory `$lookup` on every customer-level transaction query. The validator confirms it matches the account's customer.

3. **String IDs, not ObjectIDs** — Using `CUST000001`, `ACC000001` etc. makes `$lookup` join conditions readable and makes the AI agent's generated queries more human-interpretable.

4. **BSON Date objects** — All date fields are stored as proper MongoDB `Date` types so `$month`, `$year`, `$dateToString`, and range queries work correctly without `$dateFromString` conversions.

5. **Configurable counts** — All sizes are in the `CONFIG` dict at the top of `generate_dataset.py`. Scaling from 1k to 100k customers requires changing one number and re-running.

6. **Edge cases are deliberate** — Customers with no accounts/loans/cards, blocked accounts, defaulted loans, expired cards, failed/reversed transactions, and false-positive fraud alerts are intentionally included so the agent can be tested on non-happy-path queries.

7. **All data is synthetic** — No real PAN, Aadhaar, phone numbers, card numbers, or personal financial data. Patterns are obviously fake (e.g. `ACCTNO0000000001`, `XXXX-XXXX-XXXX-4321`).

8. **Amount distributions are realistic** — RTGS transactions are always ≥ ₹2 lakh, salary credits ₹20k–₹3 lakh, rent ₹10k–₹80k, dining ₹150–₹5k. This ensures amount-based filters return meaningful result sets.

9. **Dates span 2010–2026** — Spread across years and months so `$month`, `$year`, quarterly, and YoY aggregations all return non-trivial results.

10. **`schema.json` is the AI agent's ground truth** — It contains every collection's field names, types, allowed categorical values, and the full foreign-key relationship graph. Inject it verbatim into the agent's system prompt.
