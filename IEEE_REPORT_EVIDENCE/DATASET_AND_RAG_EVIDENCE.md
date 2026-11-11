# FINTECH AGENT — DATASET SPECIFICATION AND SCHEMA RAG EVIDENCE

**Document Classification:** Data Engineering, Knowledge Base & Semantic Retrieval Audit  
**Canonical Schema Source:** [`fintech-agent/data/schema.json`](file:///c:/Users/guru2/Downloads/llm%20prj/fintech-agent/data/schema.json)  
**Dataset Generator:** [`fintech-agent/data/generate_dataset.py`](file:///c:/Users/guru2/Downloads/llm%20prj/fintech-agent/data/generate_dataset.py)  
**Static Exports Directory:** [`fintech-agent/data/exports/json/`](file:///c:/Users/guru2/Downloads/llm%20prj/fintech-agent/data/exports/json/)  
**ChromaDB Vector Store:** [`chroma_data/`](file:///c:/Users/guru2/Downloads/llm%20prj/chroma_data/)  
**Index Evidence Artifact:** [`PHASE6_VERIFIED_INDEX_EVIDENCE.json`](file:///c:/Users/guru2/Downloads/llm%20prj/PHASE6_VERIFIED_INDEX_EVIDENCE.json)  

---

## 1. Dataset Origin and Domain Specifications

The FinTech Agent operates on an enterprise-grade synthetic retail and commercial banking dataset designed specifically to benchmark natural-language-to-MQL translation across complex relational structures.

| Dataset Attribute | Documented Specification | Verified Code & Data Reality | Status |
| :--- | :--- | :--- | :---: |
| **Origin / Provenance** | Synthetic Banking Dataset | Generated via `generate_dataset.py` (v2 integrity-hardened) | `VERIFIED` |
| **Generation Library** | Python `Faker` | `Faker("en_IN")` + deterministic random generators | `VERIFIED` |
| **Random Seed** | `42` | `RANDOM_SEED = 42`, `random.seed(42)`, `Faker.seed(42)` | `VERIFIED` |
| **Currency** | Indian Rupee (INR, ₹) | All balances, transactions, and loans denominated in INR | `VERIFIED` |
| **Locale** | India (`en_IN`) | Indian names, cities, IFSC codes, PAN, Aadhaar formats | `VERIFIED` |
| **Temporal Span** | 2010 – 2026 | Historical transactions and loans spanning 16 years | `VERIFIED` |
| **Database Name** | `fintech_agent_db` | Pinned in `config.py` and MongoDB client | `VERIFIED` |
| **Collection Count** | 12 collections | 12 canonical collections defined and verified | `VERIFIED` |
| **Total Documents** | "~18,700" (`README`) / 19,120 (Actual) | **Exactly 19,120 documents** verified in static JSON & DB | `VERIFIED` |

---

## 2. Reconciling Document Counts: 18,700 vs. 19,120

A pervasive discrepancy appears across early documentation:
- `README_DATASET.md:30` cites: `| **Default dev size** | ~18,700 documents |`
- Slide 5 in `build_deck.py:88` cites: `('18,700+', 'default documents')`
- All phase audit reports (Phase 4, 5, 6, 7) cite: `Exactly 19,120 documents`

### Mathematical Resolution:
Inspecting the individual collection configurations in `generate_dataset.py:61-75` and summing the default sizes yields:

$$\sum \text{Documents} = 20 + 100 + 200 + 1000 + 1500 + 10000 + 1000 + 500 + 1500 + 2000 + 300 + 1000 = 19,120$$

Direct physical line count of the exported JSON files in `fintech-agent/data/exports/json/` confirms:

```
accounts.json        :  1,500
branches.json        :     20
cards.json           :  1,000
customers.json       :  1,000
employees.json       :    100
fraud_alerts.json    :    300
investments.json     :  1,000
kyc_documents.json   :  1,500
loans.json           :    500
merchants.json       :    200
support_tickets.json :  2,000
transactions.json    : 10,000
─────────────────────────────
TOTAL                : 19,120 documents
```

**Conclusion:** The figure "18,700" was an approximate rounded estimate written in the dataset README before ticket and KYC document volumes were finalized at 2,000 and 1,500 respectively. **The authoritative, verified document count is exactly 19,120.**

---

## 3. Canonical Collections, Field Structures, and Relationships

The 12 canonical collections form a fully normalized relational graph linked by domain foreign keys:

| # | Collection Name | Verified Count | Primary Key | Key Business Fields | Outgoing Foreign Key Relationships |
| :-: | :--- | :---: | :--- | :--- | :--- |
| 1 | **`branches`** | 20 | `branch_id` | `branch_name`, `branch_code`, `city`, `state`, `branch_type`, `manager_id`, `status` | `manager_id` -> `employees.employee_id` |
| 2 | **`employees`** | 100 | `employee_id` | `first_name`, `last_name`, `designation`, `department`, `branch_id`, `manager_id`, `salary`, `status` | `branch_id` -> `branches.branch_id`<br>`manager_id` -> `employees.employee_id` (Self) |
| 3 | **`merchants`** | 200 | `merchant_id` | `merchant_name`, `category`, `mcc_code`, `city`, `settlement_account_id`, `risk_level` | `settlement_account_id` -> `accounts.account_id` |
| 4 | **`customers`** | 1,000 | `customer_id` | `first_name`, `last_name`, `email`, `phone`, `city`, `annual_income`, `credit_score`, `kyc_status`, `customer_segment`, `status` | `primary_branch_id` -> `branches.branch_id`<br>`relationship_manager_id` -> `employees.employee_id` |
| 5 | **`accounts`** | 1,500 | `account_id` | `account_number`, `customer_id`, `account_type`, `balance`, `currency`, `branch_id`, `account_manager_id`, `status` | `customer_id` -> `customers.customer_id`<br>`branch_id` -> `branches.branch_id`<br>`account_manager_id` -> `employees.employee_id` |
| 6 | **`transactions`** | 10,000 | `transaction_id` | `account_id`, `customer_id`, `amount`, `transaction_type`, `channel`, `merchant_id`, `timestamp`, `status` | `account_id` -> `accounts.account_id`<br>`customer_id` -> `customers.customer_id`<br>`merchant_id` -> `merchants.merchant_id` |
| 7 | **`cards`** | 1,000 | `card_id` | `card_number_masked`, `account_id`, `customer_id`, `card_type`, `card_network`, `credit_limit`, `available_limit`, `expiry_date`, `status` | `account_id` -> `accounts.account_id`<br>`customer_id` -> `customers.customer_id` |
| 8 | **`loans`** | 500 | `loan_id` | `customer_id`, `loan_type`, `principal_amount`, `interest_rate`, `tenure_months`, `emi_amount`, `outstanding_amount`, `status`, `next_due_date` | `customer_id` -> `customers.customer_id`<br>`loan_officer_id` -> `employees.employee_id` |
| 9 | **`kyc_documents`** | 1,500 | `document_id` | `customer_id`, `document_type`, `document_number_masked`, `verification_status`, `verified_by`, `verification_date` | `customer_id` -> `customers.customer_id`<br>`verified_by` -> `employees.employee_id` |
| 10 | **`support_tickets`** | 2,000 | `ticket_id` | `customer_id`, `subject`, `category`, `priority`, `status`, `assigned_to`, `created_at`, `resolved_at`, `satisfaction_rating` | `customer_id` -> `customers.customer_id`<br>`assigned_to` -> `employees.employee_id` |
| 11 | **`fraud_alerts`** | 300 | `alert_id` | `transaction_id`, `customer_id`, `alert_type`, `risk_score`, `detected_at`, `status`, `resolved_by` | `transaction_id` -> `transactions.transaction_id`<br>`customer_id` -> `customers.customer_id`<br>`resolved_by` -> `employees.employee_id` |
| 12 | **`investments`** | 1,000 | `investment_id` | `customer_id`, `account_id`, `investment_type`, `asset_name`, `invested_amount`, `current_value`, `start_date`, `maturity_date`, `status` | `customer_id` -> `customers.customer_id`<br>`account_id` -> `accounts.account_id` |

### Referential Integrity Guarantees (22 Cross-Collection Foreign Keys)
All 22 foreign key relationships are strictly validated at dataset generation time:
1. `cards.customer_id` is derived directly from `accounts.customer_id` (ensuring cards cannot belong to mismatched owners).
2. Branch managers in `branches.manager_id` are guaranteed to be employees whose `branch_id` matches that branch.
3. KYC verifiers in `kyc_documents.verified_by` reference active employees from the Operations or Risk departments.
4. RTGS transactions enforce amounts $\ge ₹2,00,000$.

---

## 4. ChromaDB Vector Store & Schema Grounding (RAG)

The Schema Retrieval Subsystem (`backend/app/rag/`) grounds LLM prompt synthesis by retrieving only relevant collection definitions, fields, and join relationships.

### 4.1 Physical ChromaDB Configuration
- **Storage Directory:** `chroma_data/` (persistent client)
- **Active Collections:**
  - `fintech_schema_catalog_cosine` (269 chunks) — Primary production cosine index
  - `fintech_schema_catalog` (269 chunks) — Preserved baseline index
- **Distance Metric:** Cosine Similarity (`hnsw:space = cosine`)
- **Distance Formula:** Bounded $[0.0, 1.0]$ conversion:

$$\text{similarity} = \max(0.0, \min(1.0, 1.0 - d))$$

- **Embedding Model:** `all-MiniLM-L6-v2` (dimension 384)
- **Embedding Provider in Test Baseline:** Deterministic `MockEmbeddingProvider` (avoids downloading 200MB PyTorch/ONNX models during CI/CD test runs)

### 4.2 Schema Chunking Strategy (269 Total Chunks)
To balance semantic search precision and token efficiency, the schema is chunked at two levels:
1. **12 Collection-Level Chunks (`coll:<name>`):** High-level summary of collection purpose, entity description, primary key, and list of all fields.
2. **257 Field-Level Chunks (`field:<collection>.<field>`):** Granular field definitions containing BSON data type, constraints, allowed enum values, financial description, and foreign-key targets.

### 4.3 Banking Glossary Mapping & Synonym Expansion
`backend/app/schema/glossary_mapper.py` maintains deterministic mappings between colloquial banking terms and canonical schema fields:
- `"savings balance"`, `"checking account"` -> `accounts.balance`, `accounts.account_type`
- `"high earner"`, `"wealthy"` -> `customers.annual_income`, `customers.customer_segment`
- `"NPA"`, `"bad loan"`, `"written off"` -> `loans.status == "defaulted"`
- `"credit card limit"`, `"available balance"` -> `cards.available_limit`

### 4.4 Unsupported Loan Concept Shielding
To prevent the LLM from hallucinating non-existent delinquency fields, `schema_retriever.py` uses word-boundary regex patterns to intercept references to absent concepts:
- Intercepted Terms: `overdue loans`, `overdue debt`, `arrears`, `days past due`, `dpd`, `overdue amount`, `late payments`.
- Structured Emitted Warning: Explains that `overdue_amount` and `days_past_due` do not exist in `loans.json`; instructs the synthesizer to evaluate loan health strictly by filtering `loans.status == "defaulted"` or analyzing `outstanding_amount`.
