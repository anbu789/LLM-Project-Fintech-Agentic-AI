"""
validate_dataset.py  (v2)
==========================
Validates fintech_agent_db against all data_integrity_rules from schema.json v2.

New checks added in v2
-----------------------
* branches.status lowercase
* customers.status lowercase
* Branch manager must work at the same branch
* cards.customer_id must match accounts[account_id].customer_id
* RTGS transactions must have amount >= 200000
* loans: closed -> outstanding=0, next_due=null
         defaulted -> next_due in the past
         active -> next_due not null, in the future
* kyc_documents: non-verified -> verified_by=null, verification_date=null
* support_tickets: non-(resolved|closed) -> resolved_date/notes/rating null
* investments: stocks -> maturity_date=null; others -> maturity_date not null
* fraud_alerts: customer_id matches transaction->account->customer chain
* transactions: customer_id matches account->customer

Usage
-----
    python data/validate_dataset.py
    MONGODB_URI=mongodb://... python data/validate_dataset.py
"""

import os
import sys
from datetime import datetime
from collections import defaultdict
from pymongo import MongoClient

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME     = "fintech_agent_db"
client      = MongoClient(MONGODB_URI)
db          = client[DB_NAME]

NOW = datetime.now()

# ---------------------------------------------------------------------------
# Enum definitions (must exactly match schema.json v2)
# ---------------------------------------------------------------------------
VALID_ENUMS = {
    "branches": {
        "branch_type": {"urban", "rural", "metro", "semi-urban"},
        "status":       {"active", "inactive", "closed"},        # v2: lowercase + expanded
        "region":       {"North", "South", "East", "West", "Central"},
    },
    "employees": {
        "designation":       {"Clerk", "Officer", "Manager", "Senior Manager", "Executive"},
        "department":        {"Retail Banking", "Loans", "Customer Service",
                              "Fraud & Risk", "Operations", "IT"},
        "employment_status": {"active", "on_leave", "resigned"},
    },
    "merchants": {
        "category": {"groceries", "electronics", "fuel", "dining",
                     "travel", "utilities", "healthcare", "entertainment"},
    },
    "customers": {
        "kyc_status":     {"verified", "pending", "rejected"},
        "risk_category":  {"low", "medium", "high"},
        "customer_type":  {"individual", "corporate"},
        "gender":         {"Male", "Female", "Other"},
        "marital_status": {"Single", "Married", "Divorced", "Widowed"},
        "status":         {"active", "inactive", "blocked", "closed"},  # v2: lowercase
        "occupation":     {"Salaried", "Self-Employed", "Business Owner",
                           "Student", "Retired", "Homemaker"},
        "preferred_language": {"English", "Tamil", "Hindi", "Telugu"},  # v2: fixed
        "customer_segment":   {"Regular", "Premium", "HNI", "Student", "Senior"},
    },
    "accounts": {
        "account_type": {"savings", "current", "salary",
                         "fixed_deposit", "recurring_deposit"},
        "status":       {"active", "dormant", "blocked", "closed"},
        "currency":     {"INR"},
    },
    "transactions": {
        "transaction_type": {"debit", "credit"},
        "transaction_mode": {"UPI", "NEFT", "RTGS", "IMPS", "cash", "cheque", "card"},
        "status":           {"success", "failed", "pending", "reversed"},
        "channel":          {"mobile", "web", "atm", "branch", "pos"},
        "currency":         {"INR"},
        "category":         {"groceries", "salary", "rent", "utilities", "transfer",
                             "shopping", "dining", "fuel", "investment", "healthcare",
                             "education", "travel", "entertainment"},
    },
    "cards": {
        "card_type":    {"debit", "credit"},
        "card_network": {"visa", "mastercard", "rupay"},
        "status":       {"active", "blocked", "expired"},
    },
    "loans": {
        "loan_type":       {"home", "personal", "auto", "education", "gold", "business"},
        "status":          {"active", "closed", "defaulted"},
        "collateral_type": {"property", "vehicle", "gold", "fd", "none"},
    },
    "kyc_documents": {
        "document_type":       {"passport", "aadhar", "pan", "voter_id", "driving_license"},
        "verification_status": {"verified", "pending", "rejected"},
    },
    "support_tickets": {
        "category": {"complaint", "query", "request", "fraud_report",
                     "account_issue", "card_issue", "loan_issue"},
        "priority": {"low", "medium", "high", "critical"},
        "status":   {"open", "in_progress", "resolved", "closed"},
        "channel":  {"phone", "email", "chat", "branch"},
    },
    "fraud_alerts": {
        "alert_type":   {"unusual_amount", "velocity", "geo_mismatch",
                         "device_change", "blacklisted_merchant"},
        "status":       {"open", "investigating", "resolved", "false_positive"},
        "action_taken": {"none", "account_frozen",
                         "customer_contacted", "transaction_reversed"},
    },
    "investments": {
        "investment_type": {"mutual_fund", "fixed_deposit", "stocks", "bonds", "ppf"},
        "status":          {"active", "matured", "redeemed"},
        "risk_level":      {"low", "medium", "high"},
    },
}

REQUIRED_FIELDS = {
    "branches":        ["branch_id", "branch_name", "city", "state", "branch_type", "status"],
    "employees":       ["employee_id", "first_name", "last_name", "designation",
                        "department", "branch_id", "employment_status", "salary"],
    "merchants":       ["merchant_id", "merchant_name", "category", "mcc_code", "is_verified"],
    "customers":       ["customer_id", "first_name", "last_name", "kyc_status",
                        "risk_category", "customer_type", "annual_income", "credit_score", "status"],
    "accounts":        ["account_id", "customer_id", "branch_id", "account_type",
                        "balance", "status", "currency"],
    "transactions":    ["transaction_id", "account_id", "customer_id", "transaction_type",
                        "amount", "currency", "transaction_date", "transaction_mode", "status"],
    "cards":           ["card_id", "customer_id", "account_id", "card_type",
                        "card_network", "status", "credit_limit"],
    "loans":           ["loan_id", "customer_id", "loan_type", "principal_amount",
                        "interest_rate", "tenure_months", "emi_amount", "status", "outstanding_amount"],
    "kyc_documents":   ["kyc_id", "customer_id", "document_type", "verification_status"],
    "support_tickets": ["ticket_id", "customer_id", "category", "priority", "status"],
    "fraud_alerts":    ["alert_id", "transaction_id", "customer_id",
                        "alert_type", "risk_score", "status"],
    "investments":     ["investment_id", "customer_id", "investment_type",
                        "amount_invested", "current_value", "status"],
}

PRIMARY_ID = {
    "branches": "branch_id", "employees": "employee_id", "merchants": "merchant_id",
    "customers": "customer_id", "accounts": "account_id", "transactions": "transaction_id",
    "cards": "card_id", "loans": "loan_id", "kyc_documents": "kyc_id",
    "support_tickets": "ticket_id", "fraud_alerts": "alert_id", "investments": "investment_id",
}

passed = 0
failed = 0
errors_detail = defaultdict(list)


def ok(label: str):
    global passed
    passed += 1
    print(f"  PASS  {label}")


def fail(label: str, detail: str = ""):
    global failed
    failed += 1
    msg = f"  FAIL  {label}"
    if detail:
        msg += f"\n         -> {detail}"
    print(msg)
    errors_detail[label].append(detail)


def load_ids(coll: str, field: str) -> set:
    return {d[field] for d in db[coll].find({}, {field: 1, "_id": 0}) if field in d}


# ---------------------------------------------------------------------------
# CHECK 1: Collection counts
# ---------------------------------------------------------------------------
def check_counts():
    print("\n-- 1. Collection Counts ---------------------------------------------")
    for c in PRIMARY_ID:
        count = db[c].count_documents({})
        if count == 0:
            fail(f"counts.{c}", "Collection is EMPTY")
        else:
            ok(f"counts.{c}  ({count:,} docs)")


# ---------------------------------------------------------------------------
# CHECK 2: Duplicate primary IDs
# ---------------------------------------------------------------------------
def check_duplicates():
    print("\n-- 2. Duplicate Primary IDs -----------------------------------------")
    for coll, id_field in PRIMARY_ID.items():
        pipeline = [
            {"$group": {"_id": f"${id_field}", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
            {"$limit": 3},
        ]
        dupes = list(db[coll].aggregate(pipeline))
        if dupes:
            fail(f"duplicates.{coll}", f"{len(dupes)} duplicate {id_field} values, e.g. {dupes[0]['_id']}")
        else:
            ok(f"duplicates.{coll}")


# ---------------------------------------------------------------------------
# CHECK 3: Foreign-key integrity
# ---------------------------------------------------------------------------
def check_foreign_keys():
    print("\n-- 3. Foreign-Key Integrity -----------------------------------------")

    branch_ids   = load_ids("branches",     "branch_id")
    emp_ids      = load_ids("employees",    "employee_id")
    merch_ids    = load_ids("merchants",    "merchant_id")
    cust_ids     = load_ids("customers",    "customer_id")
    acct_ids     = load_ids("accounts",     "account_id")
    txn_ids      = load_ids("transactions", "transaction_id")

    SAMPLE = 1000

    def fk(child, field, parent_set, parent_name, allow_null=False):
        broken = 0
        total  = 0
        for doc in db[child].find({}, {field: 1, "_id": 0}, limit=SAMPLE):
            val = doc.get(field)
            if val is None:
                if not allow_null:
                    broken += 1
            elif val not in parent_set:
                broken += 1
            total += 1
        label = f"fk.{child}.{field} -> {parent_name}"
        if broken:
            fail(label, f"{broken}/{total} sampled docs invalid")
        else:
            ok(f"{label} ({total} sampled)")

    fk("employees",       "branch_id",             branch_ids, "branches")
    fk("branches",        "manager_id",            emp_ids,    "employees",     allow_null=True)
    fk("customers",       "relationship_manager_id", emp_ids,  "employees",     allow_null=True)
    fk("accounts",        "customer_id",           cust_ids,   "customers")
    fk("accounts",        "branch_id",             branch_ids, "branches")
    fk("accounts",        "account_manager_id",    emp_ids,    "employees",     allow_null=True)
    fk("transactions",    "account_id",            acct_ids,   "accounts")
    fk("transactions",    "customer_id",           cust_ids,   "customers")
    fk("transactions",    "merchant_id",           merch_ids,  "merchants",     allow_null=True)
    fk("cards",           "customer_id",           cust_ids,   "customers")
    fk("cards",           "account_id",            acct_ids,   "accounts")
    fk("loans",           "customer_id",           cust_ids,   "customers")
    fk("loans",           "sanctioning_branch_id", branch_ids, "branches")
    fk("loans",           "loan_officer_id",       emp_ids,    "employees")
    fk("kyc_documents",   "customer_id",           cust_ids,   "customers")
    fk("kyc_documents",   "verified_by",           emp_ids,    "employees",     allow_null=True)
    fk("support_tickets", "customer_id",           cust_ids,   "customers")
    fk("support_tickets", "assigned_agent_id",     emp_ids,    "employees")
    fk("fraud_alerts",    "transaction_id",        txn_ids,    "transactions")
    fk("fraud_alerts",    "customer_id",           cust_ids,   "customers")
    fk("fraud_alerts",    "reviewed_by",           emp_ids,    "employees",     allow_null=True)
    fk("investments",     "customer_id",           cust_ids,   "customers")


# ---------------------------------------------------------------------------
# CHECK 4: Enum values
# ---------------------------------------------------------------------------
def check_enums():
    print("\n-- 4. Enum Value Consistency ----------------------------------------")
    for coll, field_enums in VALID_ENUMS.items():
        for field, valid_set in field_enums.items():
            result = list(db[coll].aggregate([
                {"$match": {field: {"$exists": True, "$nin": list(valid_set)}}},
                {"$limit": 1},
                {"$project": {field: 1, "_id": 0}},
            ]))
            if result:
                fail(f"enum.{coll}.{field}",
                     f"Invalid value: '{result[0].get(field)}'. Allowed: {sorted(valid_set)}")
            else:
                ok(f"enum.{coll}.{field}")


# ---------------------------------------------------------------------------
# CHECK 5: Numeric ranges
# ---------------------------------------------------------------------------
def check_numeric_ranges():
    print("\n-- 5. Numeric Range Validation --------------------------------------")

    def range_check(coll, field, lo=None, hi=None, label=None):
        label = label or f"range.{coll}.{field} [{lo}-{hi}]"
        conditions = []
        if lo is not None:
            conditions.append({field: {"$lt": lo}})
        if hi is not None:
            conditions.append({field: {"$gt": hi}})
        if not conditions:
            ok(label + " (no bounds)")
            return
        count = db[coll].count_documents({"$or": conditions, field: {"$ne": None}})
        if count:
            fail(label, f"{count} out-of-range docs")
        else:
            ok(label)

    range_check("customers",    "credit_score",     300,  900)
    range_check("customers",    "annual_income",     0,    None)
    range_check("accounts",     "balance",           0,    None)
    range_check("transactions", "amount",            1,    None)
    range_check("fraud_alerts", "risk_score",        0,    100)
    range_check("employees",    "performance_rating",2.0,  5.0)
    range_check("investments",  "amount_invested",   0,    None)
    range_check("support_tickets","satisfaction_rating",1, 5,
                label="range.support_tickets.satisfaction_rating [1-5] (non-null only)")


# ---------------------------------------------------------------------------
# CHECK 6: Required fields
# ---------------------------------------------------------------------------
def check_required_fields():
    print("\n-- 6. Required Fields -----------------------------------------------")
    for coll, fields in REQUIRED_FIELDS.items():
        for field in fields:
            count = db[coll].count_documents({field: {"$exists": False}})
            if count:
                fail(f"required.{coll}.{field}", f"{count} docs missing field")
            else:
                ok(f"required.{coll}.{field}")


# ---------------------------------------------------------------------------
# CHECK 7: RTGS amount >= 200000  (v2 data_integrity_rule)
# ---------------------------------------------------------------------------
def check_rtgs_floor():
    print("\n-- 7. RTGS Amount Floor (>= 200000) --------------------------------")
    count = db["transactions"].count_documents({
        "transaction_mode": "RTGS",
        "amount": {"$lt": 200000}
    })
    if count:
        fail("integrity.transactions.RTGS_amount_floor",
             f"{count} RTGS transactions have amount < 200000")
    else:
        ok("integrity.transactions.RTGS_amount_floor (all RTGS >= 200000)")


# ---------------------------------------------------------------------------
# CHECK 8: Loan null-field rules  (v2)
# ---------------------------------------------------------------------------
def check_loan_rules():
    print("\n-- 8. Loan Status Null-Field Rules ----------------------------------")

    # closed -> outstanding_amount == 0
    count = db["loans"].count_documents({
        "status": "closed",
        "outstanding_amount": {"$ne": 0}
    })
    if count:
        fail("integrity.loans.closed_outstanding=0", f"{count} closed loans with outstanding != 0")
    else:
        ok("integrity.loans.closed: outstanding_amount = 0")

    # closed -> next_due_date == null
    count = db["loans"].count_documents({
        "status": "closed",
        "next_due_date": {"$ne": None, "$exists": True}
    })
    if count:
        fail("integrity.loans.closed_next_due=null", f"{count} closed loans with next_due_date != null")
    else:
        ok("integrity.loans.closed: next_due_date = null")

    # defaulted -> next_due_date in the past
    count = db["loans"].count_documents({
        "status": "defaulted",
        "next_due_date": {"$gte": NOW}
    })
    if count:
        fail("integrity.loans.defaulted_next_due_past",
             f"{count} defaulted loans with future next_due_date")
    else:
        ok("integrity.loans.defaulted: next_due_date in the past")

    # active -> next_due_date not null and in the future
    count = db["loans"].count_documents({
        "status": "active",
        "next_due_date": None
    })
    if count:
        fail("integrity.loans.active_next_due_not_null", f"{count} active loans with null next_due_date")
    else:
        ok("integrity.loans.active: next_due_date not null")

    count = db["loans"].count_documents({
        "status": "active",
        "next_due_date": {"$lte": NOW}
    })
    if count:
        fail("integrity.loans.active_next_due_future",
             f"{count} active loans with past/present next_due_date")
    else:
        ok("integrity.loans.active: next_due_date in the future")


# ---------------------------------------------------------------------------
# CHECK 9: KYC null-field rules  (v2)
# ---------------------------------------------------------------------------
def check_kyc_rules():
    print("\n-- 9. KYC Null-Field Rules ------------------------------------------")

    # non-verified -> verified_by must be null
    count = db["kyc_documents"].count_documents({
        "verification_status": {"$ne": "verified"},
        "verified_by": {"$ne": None, "$exists": True}
    })
    if count:
        fail("integrity.kyc.non-verified_verified_by_null",
             f"{count} non-verified KYC docs have non-null verified_by")
    else:
        ok("integrity.kyc: non-verified docs have verified_by = null")

    # non-verified -> verification_date must be null
    count = db["kyc_documents"].count_documents({
        "verification_status": {"$ne": "verified"},
        "verification_date": {"$ne": None, "$exists": True}
    })
    if count:
        fail("integrity.kyc.non-verified_verification_date_null",
             f"{count} non-verified KYC docs have non-null verification_date")
    else:
        ok("integrity.kyc: non-verified docs have verification_date = null")

    # verified -> verified_by and verification_date should not be null
    count = db["kyc_documents"].count_documents({
        "verification_status": "verified",
        "$or": [{"verified_by": None}, {"verification_date": None}]
    })
    if count:
        fail("integrity.kyc.verified_has_verifier",
             f"{count} verified KYC docs missing verified_by or verification_date")
    else:
        ok("integrity.kyc: verified docs have verified_by and verification_date")


# ---------------------------------------------------------------------------
# CHECK 10: Support ticket null-field rules  (v2)
# ---------------------------------------------------------------------------
def check_ticket_rules():
    print("\n-- 10. Support Ticket Null-Field Rules ------------------------------")
    UNRESOLVED = {"open", "in_progress"}

    fields = ["resolved_date", "resolution_notes", "satisfaction_rating"]
    for f in fields:
        count = db["support_tickets"].count_documents({
            "status": {"$in": list(UNRESOLVED)},
            f: {"$ne": None, "$exists": True}
        })
        if count:
            fail(f"integrity.tickets.unresolved_{f}_null",
                 f"{count} open/in_progress tickets have non-null {f}")
        else:
            ok(f"integrity.tickets: open/in_progress have {f} = null")

    # resolved/closed should have resolution fields populated
    for f in fields:
        count = db["support_tickets"].count_documents({
            "status": {"$in": ["resolved", "closed"]},
            f: None
        })
        if count:
            fail(f"integrity.tickets.resolved_{f}_not_null",
                 f"{count} resolved/closed tickets have null {f}")
        else:
            ok(f"integrity.tickets: resolved/closed have {f} populated")


# ---------------------------------------------------------------------------
# CHECK 11: Investment maturity_date rules  (v2)
# ---------------------------------------------------------------------------
def check_investment_rules():
    print("\n-- 11. Investment Maturity Date Rules -------------------------------")

    # stocks -> maturity_date must be null
    count = db["investments"].count_documents({
        "investment_type": "stocks",
        "maturity_date": {"$ne": None, "$exists": True}
    })
    if count:
        fail("integrity.investments.stocks_maturity_null",
             f"{count} stock investments have non-null maturity_date")
    else:
        ok("integrity.investments: stocks have maturity_date = null")

    # non-stocks -> maturity_date must not be null
    count = db["investments"].count_documents({
        "investment_type": {"$ne": "stocks"},
        "maturity_date": None
    })
    if count:
        fail("integrity.investments.non_stocks_maturity_not_null",
             f"{count} non-stock investments have null maturity_date")
    else:
        ok("integrity.investments: non-stocks have maturity_date populated")


# ---------------------------------------------------------------------------
# CHECK 12: transactions.customer_id matches account's customer  (v2)
# ---------------------------------------------------------------------------
def check_txn_customer_derived():
    print("\n-- 12. Transaction customer_id Derivation --------------------------")

    acct_cust = {
        d["account_id"]: d["customer_id"]
        for d in db["accounts"].find({}, {"account_id": 1, "customer_id": 1, "_id": 0})
    }
    broken = total = 0
    for doc in db["transactions"].find(
        {}, {"account_id": 1, "customer_id": 1, "_id": 0}, limit=2000
    ):
        expected = acct_cust.get(doc.get("account_id"))
        if expected and doc.get("customer_id") != expected:
            broken += 1
        total += 1

    label = f"integrity.transactions.customer_id == account.customer_id ({total} sampled)"
    if broken:
        fail(label, f"{broken} mismatches")
    else:
        ok(label)


# ---------------------------------------------------------------------------
# CHECK 13: cards.customer_id matches account's customer  (v2)
# ---------------------------------------------------------------------------
def check_card_customer_derived():
    print("\n-- 13. Card customer_id Derivation ---------------------------------")

    acct_cust = {
        d["account_id"]: d["customer_id"]
        for d in db["accounts"].find({}, {"account_id": 1, "customer_id": 1, "_id": 0})
    }
    broken = total = 0
    for doc in db["cards"].find(
        {}, {"account_id": 1, "customer_id": 1, "_id": 0}
    ):
        expected = acct_cust.get(doc.get("account_id"))
        if expected and doc.get("customer_id") != expected:
            broken += 1
        total += 1

    label = f"integrity.cards.customer_id == account.customer_id ({total} cards)"
    if broken:
        fail(label, f"{broken} mismatches")
    else:
        ok(label)


# ---------------------------------------------------------------------------
# CHECK 14: Branch manager works at the same branch  (v2)
# ---------------------------------------------------------------------------
def check_branch_manager_same_branch():
    print("\n-- 14. Branch Manager Same-Branch Constraint -----------------------")

    emp_branch = {
        d["employee_id"]: d["branch_id"]
        for d in db["employees"].find({}, {"employee_id": 1, "branch_id": 1, "_id": 0})
    }
    broken = total = 0
    for doc in db["branches"].find({}, {"branch_id": 1, "manager_id": 1, "_id": 0}):
        mgr_id = doc.get("manager_id")
        if mgr_id is None:
            continue
        mgr_branch = emp_branch.get(mgr_id)
        if mgr_branch != doc["branch_id"]:
            broken += 1
        total += 1

    label = f"integrity.branches.manager works at same branch ({total} branches)"
    if broken:
        fail(label, f"{broken} branches have manager from a different branch")
    else:
        ok(label)


# ---------------------------------------------------------------------------
# CHECK 15: fraud_alerts.customer_id derived from transaction chain  (v2)
# ---------------------------------------------------------------------------
def check_fraud_alert_customer_derived():
    print("\n-- 15. Fraud Alert customer_id Derivation --------------------------")

    txn_cust = {
        d["transaction_id"]: d["customer_id"]
        for d in db["transactions"].find(
            {}, {"transaction_id": 1, "customer_id": 1, "_id": 0}, limit=15000
        )
    }
    broken = total = 0
    for doc in db["fraud_alerts"].find(
        {}, {"transaction_id": 1, "customer_id": 1, "_id": 0}
    ):
        expected = txn_cust.get(doc.get("transaction_id"))
        if expected and doc.get("customer_id") != expected:
            broken += 1
        total += 1

    label = f"integrity.fraud_alerts.customer_id == txn.customer_id ({total} alerts)"
    if broken:
        fail(label, f"{broken} mismatches")
    else:
        ok(label)


# ---------------------------------------------------------------------------
# CHECK 16: loans.outstanding_amount >= 0 always
# ---------------------------------------------------------------------------
def check_outstanding_non_negative():
    print("\n-- 16. Loan Outstanding Amount >= 0 --------------------------------")
    count = db["loans"].count_documents({"outstanding_amount": {"$lt": 0}})
    if count:
        fail("range.loans.outstanding_amount >= 0", f"{count} negative values")
    else:
        ok("range.loans.outstanding_amount >= 0")


# ---------------------------------------------------------------------------
# CHECK 17: Date sanity
# ---------------------------------------------------------------------------
def check_dates():
    print("\n-- 17. Date Sanity --------------------------------------------------")

    # accounts: opening_date <= updated_at
    count = db["accounts"].count_documents({
        "$expr": {"$gt": ["$opening_date", "$updated_at"]}
    })
    if count:
        fail("dates.accounts opening_date > updated_at", f"{count} docs")
    else:
        ok("dates.accounts: opening_date <= updated_at")

    # cards: expiry > issue
    count = db["cards"].count_documents({
        "$expr": {"$lte": ["$expiry_date", "$issue_date"]}
    })
    if count:
        fail("dates.cards expiry_date <= issue_date", f"{count} docs")
    else:
        ok("dates.cards: expiry_date > issue_date")

    # transactions: dates not in future beyond today
    count = db["transactions"].count_documents({
        "transaction_date": {"$gt": NOW}
    })
    if count:
        fail("dates.transactions: future dates", f"{count} docs past {NOW}")
    else:
        ok("dates.transactions: all dates <= now")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 65)
    print("  Fintech Agent DB -- Dataset Validator  (v2)")
    print(f"  URI: {MONGODB_URI}   DB: {DB_NAME}")
    print("=" * 65)

    check_counts()
    check_duplicates()
    check_foreign_keys()
    check_enums()
    check_numeric_ranges()
    check_required_fields()
    check_rtgs_floor()
    check_loan_rules()
    check_kyc_rules()
    check_ticket_rules()
    check_investment_rules()
    check_txn_customer_derived()
    check_card_customer_derived()
    check_branch_manager_same_branch()
    check_fraud_alert_customer_derived()
    check_outstanding_non_negative()
    check_dates()

    print("\n" + "=" * 65)
    print(f"  TOTAL PASSED : {passed}")
    print(f"  TOTAL FAILED : {failed}")
    print("=" * 65)

    if failed:
        print("\nFailed check details:")
        for label, details in errors_detail.items():
            for d in details:
                print(f"  X {label}: {d}")
        client.close()
        sys.exit(1)
    else:
        print("\n  All checks passed! Dataset is valid. v2 integrity rules confirmed.")
        client.close()


if __name__ == "__main__":
    main()
