# FinTech Agent — Banking Glossary

> **Purpose:** Shared meaning of banking terms used in natural-language questions, prompts, test cases, and answer explanations.  
> **Important:** This glossary explains business language. It does not prove that a similarly named field exists in MongoDB. Verify field names and values in `schema.json` and the actual dataset.

---

## 1. Customer and Identity Terms

| Term | Meaning in this project | Implementation guidance |
|---|---|---|
| Customer | A person or business represented by a customer record in the `customers` collection. | Use the actual customer identifier and verified fields from `schema.json`. |
| Customer ID | Identifier linking a customer to related records. | The architecture documents `customers.customer_id` as a unique key and as a key used in related collections. Verify exact stored type and format. |
| KYC — Know Your Customer | Process by which a financial institution verifies a customer's identity and relevant details. | The dataset includes `kyc_status` on customer records and a `kyc_documents` collection. Do not infer document contents. |
| KYC status | Dataset-defined state of KYC completion or review. | Known field: `customers.kyc_status`. Allowed values must be read from the dataset; do not assume enum labels. |
| KYC document | A record associated with customer identity verification. | The architecture lists `kyc_documents` and `customer_id`; do not expose actual identity-document values in LLM prompts or demo output. |
| Verified customer | A customer whose KYC state meets the project's configured definition of verified. | Confirm the exact categorical value in the data before using this phrase in a query or benchmark. |

## 2. Risk and Fraud Terms

| Term | Meaning in this project | Implementation guidance |
|---|---|---|
| Risk category | Dataset-defined grouping used to describe a customer's risk classification. | Known field: `customers.risk_category`. Values and ordering must come from the dataset or approved business rules. |
| High-risk customer | A customer whose risk category matches the configured high-risk category. | Do not guess the category spelling or ranking. Use observed values or an explicit glossary mapping. |
| Fraud alert | A record that flags a transaction or customer for suspicious activity review. | The `fraud_alerts` collection documents `alert_id`, `transaction_id`, and `customer_id` as key fields. An alert is not proof that fraud occurred. |
| Suspicious transaction | A transaction associated with a fraud alert or a separately defined risk rule. | Use neutral language such as “flagged” or “associated with an alert”; do not state that a transaction is fraudulent unless verified. |
| False positive | A fraud/risk alert that is later determined not to represent actual fraud. | The current architecture does not specify a final field or resolution taxonomy; verify before querying. |
| AML — Anti-Money Laundering | Controls and processes intended to detect and prevent money laundering. | Treat as domain context only unless the dataset contains explicit AML records or fields. |

## 3. Accounts and Transactions

| Term | Meaning in this project | Implementation guidance |
|---|---|---|
| Bank account | An account associated with a customer and a branch. | Collection: `accounts`; documented key fields include `account_id`, `customer_id`, `branch_id`, and `status`. |
| Account status | Dataset-defined current state of an account. | Known field: `accounts.status`. Discover allowed values from the actual records. |
| Transaction | A financial activity record. | Collection: `transactions`; documented key fields include `transaction_id`, `account_id`, `customer_id`, `transaction_date`, and `status`. |
| Transaction status | Dataset-defined state of a transaction. | Known field: `transactions.status`. Do not assume values such as `SUCCESS`, `FAILED`, or `PENDING` until observed. |
| Transaction date | Date/time associated with a transaction. | Known field: `transactions.transaction_date`. Confirm BSON type and timezone convention before date filtering. |
| Merchant | Business or payment destination associated with payment activity. | Collection: `merchants`; documented fields include `merchant_id` and `merchant_category`. A direct transaction-to-merchant key must be confirmed in `schema.json`. |
| Merchant category | Dataset-defined merchant classification. | Known field: `merchants.merchant_category`; actual categories must be read from the dataset. |

## 4. Loans and Credit

| Term | Meaning in this project | Implementation guidance |
|---|---|---|
| Loan | A credit facility recorded for a customer. | Collection: `loans`; documented key fields include `loan_id`, `customer_id`, `status`, and `sanctioning_branch_id`. |
| Loan status | Dataset-defined state of a loan. | Known field: `loans.status`. Do not assume the complete set of labels. |
| Sanctioning branch | Branch recorded as having sanctioned the loan. | Known field: `loans.sanctioning_branch_id`. Confirm relationship to `branches.branch_id`. |
| Loan sanction | Approval of a loan under the institution's process. | Do not infer approval amount, date, or decision status unless corresponding fields are verified. |
| Outstanding balance | Amount still owed on a credit facility at a point in time. | This is a business concept, not a confirmed field name in the current architecture. Verify whether the dataset stores it or whether it can be derived safely. |
| Overdue amount | Amount past its due date and unpaid. | Do not assume `loans.overdue_amount` exists. The architecture explicitly requires checking this against `schema.json` and generated documents. |
| DPD — Days Past Due | Number of days a payment has remained overdue. | Do not assume `loans.days_past_due` exists. If added, define its calculation and reference date precisely. |
| NPA — Non-Performing Asset | A loan/credit exposure classified as non-performing under applicable banking rules and the institution's policy. | The exact classification can depend on product type, repayment status, applicable rules, and policy. Do not hardcode an NPA threshold without an approved business rule and supporting fields. |

## 5. Branches, Employees, and Support

| Term | Meaning in this project | Implementation guidance |
|---|---|---|
| Branch | Physical bank office/location. | Collection: `branches`; documented fields include `branch_id`, `city`, and `state`. |
| Branch ID | Identifier for a branch. | `branches.branch_id` is documented as unique. Confirm all relationship key types match. |
| Employee | Bank staff member. | Collection: `employees`; documented fields include `employee_id`, `branch_id`, and `department`. |
| Department | Organizational department associated with an employee. | Known field: `employees.department`; values are dataset-defined. |
| Support ticket | A customer service issue/request. | Collection: `support_tickets`; documented keys include `ticket_id`, `customer_id`, and `priority`. |
| Ticket priority | Dataset-defined urgency or priority classification. | Known field: `support_tickets.priority`. Confirm possible values before filtering. |

## 6. Cards and Investments

| Term | Meaning in this project | Implementation guidance |
|---|---|---|
| Card | Debit or credit card record associated with a customer/account. | Collection: `cards`; documented keys include `card_id`, `customer_id`, and `account_id`. Do not expose full card numbers or secrets. |
| Investment | Customer portfolio/investment record. | Collection: `investments`; documented keys include `investment_id` and `customer_id`. Verify product, value, and date fields before asking detailed analytics. |

## 7. Query and Analytics Language

| Phrase | Intended interpretation | Clarification rule |
|---|---|---|
| Show / list / find | Return matching records. | Apply result caps and avoid returning sensitive fields unnecessarily. |
| How many / count | Count records matching the condition. | Ensure the counted entity is clear: customers, accounts, loans, transactions, alerts, etc. |
| Group by | Aggregate records into categories. | Confirm the grouping field exists and the output meaning is clear. |
| Top N | Sort by a specified metric and return the first N. | Ask which metric if “top” is ambiguous. Do not invent a numeric metric field. |
| Last N days | Relative date range ending at the current time. | Use the request's IANA timezone. For scheduled jobs, resolve the range at each run, not when the job is created. |
| This month / last month | Calendar-month window. | Define the timezone and inclusive/exclusive boundaries consistently. |
| Active | State that is currently in effect. | Do not infer the matching status string; inspect collection values or approved mapping. |
| Overdue | A payment obligation is beyond its due date. | Requires verified due-date/payment fields or an approved derived rule. Do not infer from loan status alone. |
| NPA | Non-performing asset classification. | Requires approved classification rules and necessary data fields. If unavailable, ask for clarification or explain the data limitation. |

## 8. Canonical Field and Collection Reference

This is a compact reference to fields explicitly documented in the architecture. It is not the full schema.

| Collection | Documented fields |
|---|---|
| `branches` | `branch_id`, `city`, `state` |
| `employees` | `employee_id`, `branch_id`, `department` |
| `merchants` | `merchant_id`, `merchant_category` |
| `customers` | `customer_id`, `kyc_status`, `risk_category` |
| `accounts` | `account_id`, `customer_id`, `branch_id`, `status` |
| `transactions` | `transaction_id`, `account_id`, `customer_id`, `transaction_date`, `status` |
| `cards` | `card_id`, `customer_id`, `account_id` |
| `loans` | `loan_id`, `customer_id`, `status`, `sanctioning_branch_id` |
| `kyc_documents` | `kyc_id`, `customer_id` |
| `support_tickets` | `ticket_id`, `customer_id`, `priority` |
| `fraud_alerts` | `alert_id`, `transaction_id`, `customer_id` |
| `investments` | `investment_id`, `customer_id` |

## 9. LLM and Agent Interpretation Rules

1. The glossary explains meanings; `schema.json` defines the actual database structure.
2. Do not turn a business term into a guessed MongoDB field name.
3. Use observed categorical values or a versioned, approved mapping. Do not invent enum values.
4. If a term such as “overdue”, “NPA”, “active”, or “high risk” has no approved data definition, ask a clarification or explain the limitation.
5. A fraud alert is an indicator for review, not conclusive proof of fraud.
6. Use INR formatting for currency only when the actual value is a currency amount and the source data supports that interpretation.
7. Do not expose identity documents, secrets, full card data, or unnecessary personal information in responses or LLM prompts.
8. A successful query execution does not prove that the interpretation was semantically correct.

---

## 10. Items Requiring Dataset Confirmation

Before treating these as executable definitions, verify them against `schema.json` and actual documents:

- Exact categorical values for KYC status, risk category, account status, transaction status, loan status, merchant category, ticket priority, and fraud-alert status.
- BSON types and timezone convention for `transactions.transaction_date`.
- Whether transactions contain a merchant reference and its exact field name.
- Whether loan records contain due dates, payment history, overdue amounts, DPD, outstanding balance, or NPA classification.
- Whether employees contain a manager reference and its exact field name.
- Whether all cross-collection keys use matching BSON types.

