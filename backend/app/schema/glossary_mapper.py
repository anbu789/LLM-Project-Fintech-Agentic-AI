"""
FinTech Agent — Banking Glossary Mapper
Maps business terms from BANKING_GLOSSARY.md to MongoDB collections and fields,
incorporating business synonyms, domain rules, and warnings for unsupported concepts.
"""

from typing import Dict, List, Optional
from backend.app.schema.models import GlossaryEntry


CANONICAL_GLOSSARY: List[Dict] = [
    # 1. Customer and Identity Terms
    {
        "term": "Customer",
        "category": "Customer and Identity Terms",
        "meaning": "A person or business entity represented by a customer master record.",
        "implementation_guidance": "Query the 'customers' collection using 'customer_id' as the primary key.",
        "mapped_collections": ["customers"],
        "mapped_fields": ["customers.customer_id", "customers.first_name", "customers.last_name", "customers.city", "customers.state"],
        "synonyms": ["client", "account holder", "individual", "patron", "user"]
    },
    {
        "term": "Customer ID",
        "category": "Customer and Identity Terms",
        "meaning": "Unique domain identifier linking customer profiles to accounts, loans, cards, and transactions.",
        "implementation_guidance": "Always join on domain key 'customer_id' (e.g. CUST000001), never MongoDB '_id'.",
        "mapped_collections": ["customers"],
        "mapped_fields": ["customers.customer_id"],
        "synonyms": ["cust id", "customer identifier", "customer number", "client id"]
    },
    {
        "term": "KYC — Know Your Customer",
        "category": "Customer and Identity Terms",
        "meaning": "Process of verifying customer identity and regulatory documentation.",
        "implementation_guidance": "Check 'customers.kyc_status' on customer profile or query 'kyc_documents' for submitted documents.",
        "mapped_collections": ["customers", "kyc_documents"],
        "mapped_fields": ["customers.kyc_status", "kyc_documents.document_type", "kyc_documents.verification_status"],
        "synonyms": ["kyc", "identity verification", "customer verification", "id verification"]
    },
    {
        "term": "KYC status",
        "category": "Customer and Identity Terms",
        "meaning": "Categorical state of KYC verification (e.g., 'verified', 'pending', 'rejected').",
        "implementation_guidance": "Stored as lowercase categorical string in 'customers.kyc_status'.",
        "mapped_collections": ["customers"],
        "mapped_fields": ["customers.kyc_status"],
        "synonyms": ["verification state", "kyc state", "compliance status"]
    },
    {
        "term": "KYC document",
        "category": "Customer and Identity Terms",
        "meaning": "Identity or address proof record submitted by a customer (e.g. passport, driving licence, utility bill).",
        "implementation_guidance": "Query 'kyc_documents' collection. Contains 'document_type', 'doc_number', 'verification_status', and 'verified_by'.",
        "mapped_collections": ["kyc_documents"],
        "mapped_fields": ["kyc_documents.kyc_id", "kyc_documents.customer_id", "kyc_documents.document_type", "kyc_documents.verification_status"],
        "synonyms": ["id proof", "address proof", "verification document", "identity record"]
    },
    {
        "term": "Verified customer",
        "category": "Customer and Identity Terms",
        "meaning": "A customer who has completed identity verification successfully.",
        "implementation_guidance": "Filter with { 'kyc_status': 'verified' } on the 'customers' collection.",
        "mapped_collections": ["customers"],
        "mapped_fields": ["customers.kyc_status"],
        "synonyms": ["kyc verified customer", "fully verified client", "compliant customer"]
    },

    # 2. Risk and Fraud Terms
    {
        "term": "Risk category",
        "category": "Risk and Fraud Terms",
        "meaning": "Customer risk classification assigned by risk assessment models (e.g., 'low', 'medium', 'high').",
        "implementation_guidance": "Stored as lowercase string in 'customers.risk_category'.",
        "mapped_collections": ["customers"],
        "mapped_fields": ["customers.risk_category"],
        "synonyms": ["risk level", "risk profile", "risk rating", "risk tier"]
    },
    {
        "term": "High-risk customer",
        "category": "Risk and Fraud Terms",
        "meaning": "Customer categorized into the highest risk category.",
        "implementation_guidance": "Filter with { 'risk_category': 'high' } on the 'customers' collection.",
        "mapped_collections": ["customers"],
        "mapped_fields": ["customers.risk_category"],
        "synonyms": ["high risk client", "elevated risk customer"]
    },
    {
        "term": "Fraud alert",
        "category": "Risk and Fraud Terms",
        "meaning": "System-generated flag identifying a suspicious transaction or unusual activity for review.",
        "implementation_guidance": "Query 'fraud_alerts' collection. Contains 'alert_id', 'transaction_id', 'customer_id', 'alert_type', 'risk_score', and 'status'.",
        "mapped_collections": ["fraud_alerts"],
        "mapped_fields": ["fraud_alerts.alert_id", "fraud_alerts.transaction_id", "fraud_alerts.customer_id", "fraud_alerts.alert_type", "fraud_alerts.risk_score", "fraud_alerts.status"],
        "synonyms": ["fraud warning", "suspicious flag", "security alert", "fraud case"]
    },
    {
        "term": "Suspicious transaction",
        "category": "Risk and Fraud Terms",
        "meaning": "A transaction that triggered a fraud alert or has 'is_flagged' set to true.",
        "implementation_guidance": "Filter with { 'is_flagged': True } on 'transactions' or join with 'fraud_alerts'.",
        "mapped_collections": ["transactions", "fraud_alerts"],
        "mapped_fields": ["transactions.is_flagged", "transactions.transaction_id", "fraud_alerts.alert_id"],
        "synonyms": ["flagged transaction", "unusual transaction", "suspicious activity", "flagged payment"]
    },
    {
        "term": "False positive",
        "category": "Risk and Fraud Terms",
        "meaning": "An alert reviewed and determined not to represent fraudulent behavior.",
        "implementation_guidance": "In 'fraud_alerts', status is 'closed' or 'dismissed'. Note: no explicit 'is_false_positive' boolean field exists in database.",
        "mapped_collections": ["fraud_alerts"],
        "mapped_fields": ["fraud_alerts.status"],
        "synonyms": ["cleared alert", "dismissed alert", "benign flag"]
    },
    {
        "term": "AML — Anti-Money Laundering",
        "category": "Risk and Fraud Terms",
        "meaning": "Regulatory compliance processes designed to prevent illegally obtained funds from being disguised.",
        "implementation_guidance": "Relevant to transactions with high amounts or flagged status ('is_flagged') and customer risk category.",
        "mapped_collections": ["transactions", "fraud_alerts", "customers"],
        "mapped_fields": ["transactions.is_flagged", "transactions.amount", "customers.risk_category"],
        "synonyms": ["aml", "money laundering check", "anti money laundering"]
    },

    # 3. Accounts and Transactions
    {
        "term": "Bank account",
        "category": "Accounts and Transactions",
        "meaning": "Deposit or current account held by a customer at a specific bank branch.",
        "implementation_guidance": "Collection 'accounts'. Keys: 'account_id', 'customer_id', 'branch_id', 'account_type', 'balance', 'status'.",
        "mapped_collections": ["accounts"],
        "mapped_fields": ["accounts.account_id", "accounts.account_type", "accounts.balance", "accounts.status", "accounts.branch_id"],
        "synonyms": ["account", "savings account", "current account", "fixed deposit account", "salary account"]
    },
    {
        "term": "Account balance",
        "category": "Accounts and Transactions",
        "meaning": "Current cleared funds available in the bank account.",
        "implementation_guidance": "Stored in 'accounts.balance' as a numeric field in INR.",
        "mapped_collections": ["accounts"],
        "mapped_fields": ["accounts.balance"],
        "synonyms": ["balance", "available balance", "account funds", "ledger balance"]
    },
    {
        "term": "Account status",
        "category": "Accounts and Transactions",
        "meaning": "Operational state of an account ('active', 'dormant', 'frozen', 'closed').",
        "implementation_guidance": "Stored as lowercase string in 'accounts.status'.",
        "mapped_collections": ["accounts"],
        "mapped_fields": ["accounts.status"],
        "synonyms": ["account state", "account condition"]
    },
    {
        "term": "Transaction",
        "category": "Accounts and Transactions",
        "meaning": "Individual financial debit or credit movement on an account.",
        "implementation_guidance": "Collection 'transactions'. Fields: 'transaction_id', 'account_id', 'customer_id' (denormalized), 'amount', 'transaction_date', 'status'.",
        "mapped_collections": ["transactions"],
        "mapped_fields": ["transactions.transaction_id", "transactions.account_id", "transactions.customer_id", "transactions.amount", "transactions.transaction_date", "transactions.status"],
        "synonyms": ["payment", "transfer", "financial activity", "txn", "movement"]
    },
    {
        "term": "Transaction status",
        "category": "Accounts and Transactions",
        "meaning": "Execution status of a transaction ('completed', 'failed', 'pending', 'reversed').",
        "implementation_guidance": "Stored as lowercase string in 'transactions.status'.",
        "mapped_collections": ["transactions"],
        "mapped_fields": ["transactions.status"],
        "synonyms": ["payment status", "transfer status", "txn status"]
    },
    {
        "term": "Transaction date",
        "category": "Accounts and Transactions",
        "meaning": "Timestamp when transaction took place. Stored as BSON Date object.",
        "implementation_guidance": "Use MongoDB date operators ($dateToString, $year, $month) on 'transactions.transaction_date'.",
        "mapped_collections": ["transactions"],
        "mapped_fields": ["transactions.transaction_date"],
        "synonyms": ["date of transaction", "payment date", "txn date", "time of transfer"]
    },
    {
        "term": "Merchant",
        "category": "Accounts and Transactions",
        "meaning": "Commercial entity or merchant receiving payment in commercial transactions.",
        "implementation_guidance": "Collection 'merchants'. Keys: 'merchant_id', 'merchant_name', 'category', 'city'.",
        "mapped_collections": ["merchants", "transactions"],
        "mapped_fields": ["merchants.merchant_id", "merchants.merchant_name", "merchants.category", "transactions.merchant_id"],
        "synonyms": ["vendor", "store", "shop", "seller", "payee", "retailer"]
    },
    {
        "term": "Merchant category",
        "category": "Accounts and Transactions",
        "meaning": "Industry classification of merchant (e.g., 'Groceries', 'Electronics', 'Healthcare', 'Dining').",
        "implementation_guidance": "Stored in 'merchants.category'.",
        "mapped_collections": ["merchants"],
        "mapped_fields": ["merchants.category"],
        "synonyms": ["mcc", "merchant industry", "business category", "retail category"]
    },

    # 4. Loans and Credit
    {
        "term": "Loan",
        "category": "Loans and Credit",
        "meaning": "Credit facility sanctioned to a customer with principal, interest, and repayment terms.",
        "implementation_guidance": "Collection 'loans'. Keys: 'loan_id', 'customer_id', 'sanctioning_branch_id', 'loan_type', 'principal_amount', 'outstanding_amount', 'status'.",
        "mapped_collections": ["loans"],
        "mapped_fields": ["loans.loan_id", "loans.loan_type", "loans.principal_amount", "loans.outstanding_amount", "loans.interest_rate", "loans.status"],
        "synonyms": ["credit facility", "borrowing", "lending", "loan account"]
    },
    {
        "term": "Loan status",
        "category": "Loans and Credit",
        "meaning": "State of loan lifecycle ('active', 'closed', 'defaulted').",
        "implementation_guidance": "Stored as lowercase string in 'loans.status'. Integrity rules: 'closed' implies outstanding_amount=0; 'active' implies outstanding_amount>0.",
        "mapped_collections": ["loans"],
        "mapped_fields": ["loans.status"],
        "synonyms": ["loan state", "repayment state"]
    },
    {
        "term": "Outstanding balance",
        "category": "Loans and Credit",
        "meaning": "Total remaining principal unpaid on a loan facility.",
        "implementation_guidance": "Mapped strictly to 'loans.outstanding_amount'. This is NOT overdue amount.",
        "mapped_collections": ["loans"],
        "mapped_fields": ["loans.outstanding_amount"],
        "synonyms": ["outstanding balance", "remaining balance", "unpaid principal", "loan outstanding", "balance owed"]
    },
    {
        "term": "Overdue amount",
        "category": "Loans and Credit",
        "meaning": "Payment amount past its scheduled due date and unpaid.",
        "implementation_guidance": "CRITICAL: 'overdue_amount' is NOT an existing field in the loans collection. Do not invent this field. Use 'loans.outstanding_amount' for total debt, or check next_due_date and status='defaulted'.",
        "mapped_collections": ["loans"],
        "mapped_fields": ["loans.outstanding_amount", "loans.next_due_date", "loans.status"],
        "synonyms": ["overdue payment", "late payment amount", "arrears", "delinquent amount"]
    },
    {
        "term": "DPD — Days Past Due",
        "category": "Loans and Credit",
        "meaning": "Number of days loan repayment has remained unpaid past due date.",
        "implementation_guidance": "CRITICAL: 'days_past_due' is NOT a field in the loans database. Do not hallucinate this field. Calculate relative to 'loans.next_due_date' if requested.",
        "mapped_collections": ["loans"],
        "mapped_fields": ["loans.next_due_date", "loans.status"],
        "synonyms": ["days past due", "dpd", "late days", "overdue days"]
    },
    {
        "term": "NPA — Non-Performing Asset",
        "category": "Loans and Credit",
        "meaning": "A loan classified as non-performing due to prolonged default.",
        "implementation_guidance": "In current dataset, defaulted loans are represented by { 'status': 'defaulted' } in the 'loans' collection.",
        "mapped_collections": ["loans"],
        "mapped_fields": ["loans.status", "loans.outstanding_amount"],
        "synonyms": ["npa", "bad debt", "defaulted loan", "non-performing loan"]
    },
    {
        "term": "Sanctioning branch",
        "category": "Loans and Credit",
        "meaning": "The physical branch that approved and sanctioned the loan facility.",
        "implementation_guidance": "Foreign key 'loans.sanctioning_branch_id' references 'branches.branch_id'.",
        "mapped_collections": ["loans", "branches"],
        "mapped_fields": ["loans.sanctioning_branch_id", "branches.branch_id"],
        "synonyms": ["originating branch", "lending branch", "loan branch"]
    },

    # 5. Branches, Employees, and Support
    {
        "term": "Branch",
        "category": "Branches, Employees, and Support",
        "meaning": "Physical bank location hosting accounts and sanctioning loans.",
        "implementation_guidance": "Collection 'branches'. Fields: 'branch_id', 'branch_name', 'city', 'state', 'branch_type', 'manager_id'.",
        "mapped_collections": ["branches"],
        "mapped_fields": ["branches.branch_id", "branches.branch_name", "branches.city", "branches.state", "branches.branch_type"],
        "synonyms": ["bank branch", "bank office", "location", "banking centre"]
    },
    {
        "term": "Branch ID",
        "category": "Branches, Employees, and Support",
        "meaning": "Unique branch identifier (e.g. BR00001).",
        "implementation_guidance": "Primary key for 'branches', referenced in 'accounts.branch_id', 'employees.branch_id', and 'loans.sanctioning_branch_id'.",
        "mapped_collections": ["branches"],
        "mapped_fields": ["branches.branch_id"],
        "synonyms": ["branch code", "office id", "branch identifier"]
    },
    {
        "term": "Employee",
        "category": "Branches, Employees, and Support",
        "meaning": "Bank staff member assigned to a branch and department.",
        "implementation_guidance": "Collection 'employees'. Referenced as branch manager, account manager, loan officer, ticket agent, and KYC verifier.",
        "mapped_collections": ["employees"],
        "mapped_fields": ["employees.employee_id", "employees.first_name", "employees.last_name", "employees.department", "employees.designation", "employees.branch_id"],
        "synonyms": ["staff", "bank staff", "banker", "worker", "agent", "officer"]
    },
    {
        "term": "Support ticket",
        "category": "Branches, Employees, and Support",
        "meaning": "Customer service request or complaint filed by a customer.",
        "implementation_guidance": "Collection 'support_tickets'. Fields: 'ticket_id', 'customer_id', 'category', 'priority', 'status', 'assigned_agent_id'.",
        "mapped_collections": ["support_tickets"],
        "mapped_fields": ["support_tickets.ticket_id", "support_tickets.customer_id", "support_tickets.priority", "support_tickets.status", "support_tickets.category"],
        "synonyms": ["service request", "customer ticket", "complaint", "helpdesk ticket"]
    },

    # 6. Cards and Investments
    {
        "term": "Card",
        "category": "Cards and Investments",
        "meaning": "Payment card (debit or credit) issued to an account holder.",
        "implementation_guidance": "Collection 'cards'. Fields: 'card_id', 'customer_id', 'account_id', 'card_type', 'card_network', 'status', 'expiry_date'.",
        "mapped_collections": ["cards"],
        "mapped_fields": ["cards.card_id", "cards.card_type", "cards.card_network", "cards.status", "cards.expiry_date", "cards.account_id"],
        "synonyms": ["debit card", "credit card", "payment card", "atm card"]
    },
    {
        "term": "Investment",
        "category": "Cards and Investments",
        "meaning": "Wealth portfolio asset (mutual funds, fixed deposits, stocks, gold bonds).",
        "implementation_guidance": "Collection 'investments'. Fields: 'investment_id', 'customer_id', 'investment_type', 'principal_amount', 'current_value', 'status'.",
        "mapped_collections": ["investments"],
        "mapped_fields": ["investments.investment_id", "investments.customer_id", "investments.investment_type", "investments.current_value", "investments.status"],
        "synonyms": ["portfolio", "mutual fund", "fixed deposit", "stocks", "bonds", "wealth product"]
    },

    # 7. Query and Analytics Language
    {
        "term": "Active",
        "category": "Query and Analytics Language",
        "meaning": "Entities currently operational and in-service.",
        "implementation_guidance": "Filter with status = 'active' across accounts, loans, cards, customers, or branches.",
        "mapped_collections": ["accounts", "loans", "customers", "cards", "branches"],
        "mapped_fields": ["accounts.status", "loans.status", "customers.status", "cards.status", "branches.status"],
        "synonyms": ["open", "in effect", "current", "operational", "running"]
    },
    {
        "term": "Overdue loan",
        "category": "Query and Analytics Language",
        "meaning": "A loan obligation that has not been serviced by its due date.",
        "implementation_guidance": "In this dataset, overdue/defaulted loans are represented by loans.status = 'defaulted' or next_due_date in the past. Do not use overdue_amount.",
        "mapped_collections": ["loans"],
        "mapped_fields": ["loans.status", "loans.next_due_date", "loans.outstanding_amount"],
        "synonyms": ["delinquent loan", "defaulted loan", "late loan", "non-performing loan"]
    }
]


def load_glossary_entries() -> List[GlossaryEntry]:
    """Returns validated GlossaryEntry models for all banking terms."""
    return [GlossaryEntry(**item) for item in CANONICAL_GLOSSARY]


def find_glossary_for_term(term: str) -> Optional[GlossaryEntry]:
    """Finds glossary entry matching a natural language term or synonym (case-insensitive)."""
    term_lower = term.strip().lower()
    for item in CANONICAL_GLOSSARY:
        if item["term"].lower() == term_lower:
            return GlossaryEntry(**item)
        if any(syn.lower() == term_lower for syn in item["synonyms"]):
            return GlossaryEntry(**item)
    return None


def validate_glossary_against_schema(schema_dict: Optional[Dict] = None) -> List[str]:
    """
    Validates that every collection and field referenced in the glossary
    actually exists in the provided schema dictionary.
    Returns a list of error strings; empty list indicates 100% validity.
    """
    if schema_dict is None:
        import json
        from pathlib import Path
        from backend.app.config import settings
        schema_path = Path(settings.SCHEMA_SOURCE_PATH)
        if not schema_path.exists():
            return [f"Schema source file not found at {schema_path}"]
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_dict = json.load(f)

    errors: List[str] = []
    collections = schema_dict.get("collections", {})

    for item in CANONICAL_GLOSSARY:
        term = item["term"]
        for col in item.get("mapped_collections", []):
            if col != "general" and col not in collections:
                errors.append(f"Glossary term '{term}' references nonexistent collection '{col}'")

        for field_ref in item.get("mapped_fields", []):
            if "." not in field_ref:
                errors.append(f"Glossary term '{term}' has invalid field format '{field_ref}' (must be collection.field)")
                continue
            col, f = field_ref.split(".", 1)
            if col not in collections:
                errors.append(f"Glossary term '{term}' references nonexistent collection '{col}' in '{field_ref}'")
            elif f not in collections[col].get("fields", {}):
                errors.append(f"Glossary term '{term}' references nonexistent field '{f}' in collection '{col}'")

    return errors

