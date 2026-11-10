"""
generate_dataset.py  (v2 — integrity-hardened)
================================================
Synthetic Fintech MongoDB Dataset Generator
Database  : fintech_agent_db
Collections: branches, employees, merchants, customers, accounts,
             transactions, cards, loans, kyc_documents,
             support_tickets, fraud_alerts, investments

v2 changes vs v1
-----------------
* Removed employees.role_level  (redundant with designation)
* All status fields normalised to lowercase throughout every collection
* branches.status  -> ["active", "inactive", "closed"]
* customers.status -> ["active", "inactive", "blocked", "closed"]
* preferred_language constrained to fixed allowed_values
* Branch manager now ALWAYS references an employee whose branch_id
  matches that branch (enforced at generation time, not just documented)
* cards.customer_id derived from account_map[account_id]["customer_id"]
  — never independently assigned — so cards.customer_id is always
  consistent with the referenced account
* RTGS transactions enforced >= 200,000 in the amount generator
* loans.status rules enforced in code:
    closed    -> outstanding_amount=0,    next_due_date=null
    defaulted -> outstanding_amount > 0,  next_due_date in the past
    active    -> outstanding_amount > 0,  next_due_date in the future
* kyc_documents: verification_status != verified
    -> verified_by=null, verification_date=null
* support_tickets: status not in (resolved, closed)
    -> resolved_date=null, resolution_notes=null, satisfaction_rating=null
* investments: investment_type=stocks -> maturity_date=null
  all other types must have a maturity_date
* data_integrity_rules in schema.json serve as single source of truth for
  the same rules applied here

Usage
-----
    pip install -r requirements.txt
    python data/generate_dataset.py
    MONGODB_URI=mongodb+srv://... python data/generate_dataset.py
"""

import os
import random
import math
from datetime import datetime, timedelta
from faker import Faker
from pymongo import MongoClient, ASCENDING
from pymongo.errors import BulkWriteError

# ---------------------------------------------------------------------------
# 0. SEED & LOCALE
# ---------------------------------------------------------------------------
RANDOM_SEED = 42
random.seed(RANDOM_SEED)
fake = Faker("en_IN")
Faker.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# 1. CONFIGURABLE DATASET SIZES  <-- edit here to scale up
# ---------------------------------------------------------------------------
CONFIG = {
    "NUM_BRANCHES":        20,
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
    "BATCH_SIZE":         500,
    "DROP_EXISTING":     True,
}

# ---------------------------------------------------------------------------
# 2. MONGODB CONNECTION
# ---------------------------------------------------------------------------
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "fintech_agent_db"
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

# ---------------------------------------------------------------------------
# 3. ENUM CONSTANTS  (single source of truth — matches schema.json exactly)
# ---------------------------------------------------------------------------
# Note: every status-like field is lowercase throughout
BRANCH_TYPES         = ["urban", "rural", "metro", "semi-urban"]
BRANCH_STATUSES      = ["active", "inactive", "closed"]          # v2: expanded + lowercase

EMP_DEPARTMENTS      = ["Retail Banking", "Loans", "Customer Service",
                         "Fraud & Risk", "Operations", "IT"]
EMP_DESIGNATIONS     = ["Clerk", "Officer", "Manager", "Senior Manager", "Executive"]
EMP_STATUSES         = ["active", "on_leave", "resigned"]        # lowercase

MERCHANT_CATEGORIES  = ["groceries", "electronics", "fuel", "dining",
                         "travel", "utilities", "healthcare", "entertainment"]
MCC_MAP = {
    "groceries":     ["5411", "5412", "5441"],
    "electronics":   ["5732", "5734", "5065"],
    "fuel":          ["5541", "5542"],
    "dining":        ["5812", "5814", "5811"],
    "travel":        ["4111", "4411", "4511", "7011"],
    "utilities":     ["4900", "4911", "4941"],
    "healthcare":    ["5912", "8011", "8049"],
    "entertainment": ["7832", "7922", "7941"],
}

CUST_OCCUPATIONS     = ["Salaried", "Self-Employed", "Business Owner",
                         "Student", "Retired", "Homemaker"]
CUST_KYC_STATUSES    = ["verified", "pending", "rejected"]
CUST_RISK_CATEGORIES = ["low", "medium", "high"]
CUST_TYPES           = ["individual", "corporate"]
CUST_SEGMENTS        = ["Regular", "Premium", "HNI", "Student", "Senior"]
CUST_MARITAL         = ["Single", "Married", "Divorced", "Widowed"]
CUST_LANGUAGES       = ["English", "Tamil", "Hindi", "Telugu"]   # v2: fixed set
CUST_STATUSES        = ["active", "inactive", "blocked", "closed"] # v2: lowercase

ACCT_TYPES           = ["savings", "current", "salary", "fixed_deposit", "recurring_deposit"]
ACCT_STATUSES        = ["active", "dormant", "blocked", "closed"]

TXN_TYPES            = ["debit", "credit"]
TXN_MODES            = ["UPI", "NEFT", "RTGS", "IMPS", "cash", "cheque", "card"]
TXN_STATUSES         = ["success", "failed", "pending", "reversed"]
TXN_CHANNELS         = ["mobile", "web", "atm", "branch", "pos"]
TXN_CATEGORIES       = ["groceries", "salary", "rent", "utilities", "transfer",
                         "shopping", "dining", "fuel", "investment", "healthcare",
                         "education", "travel", "entertainment"]

CARD_TYPES           = ["debit", "credit"]
CARD_NETWORKS        = ["visa", "mastercard", "rupay"]
CARD_STATUSES        = ["active", "blocked", "expired"]

LOAN_TYPES           = ["home", "personal", "auto", "education", "gold", "business"]
LOAN_STATUSES        = ["active", "closed", "defaulted"]
COLLATERAL_MAP       = {
    "home":      "property",
    "auto":      "vehicle",
    "gold":      "gold",
    "education": "none",
    "personal":  "none",
    "business":  "fd",
}

KYC_DOC_TYPES        = ["passport", "aadhar", "pan", "voter_id", "driving_license"]
KYC_STATUSES         = ["verified", "pending", "rejected"]

TICKET_CATEGORIES    = ["complaint", "query", "request", "fraud_report",
                         "account_issue", "card_issue", "loan_issue"]
TICKET_PRIORITIES    = ["low", "medium", "high", "critical"]
TICKET_STATUSES      = ["open", "in_progress", "resolved", "closed"]
TICKET_CHANNELS      = ["phone", "email", "chat", "branch"]
TICKET_RESOLVED      = {"resolved", "closed"}   # statuses where resolution fields are populated

ALERT_TYPES          = ["unusual_amount", "velocity", "geo_mismatch",
                         "device_change", "blacklisted_merchant"]
ALERT_STATUSES       = ["open", "investigating", "resolved", "false_positive"]
ALERT_ACTIONS        = ["none", "account_frozen", "customer_contacted", "transaction_reversed"]

INVEST_TYPES         = ["mutual_fund", "fixed_deposit", "stocks", "bonds", "ppf"]
INVEST_STATUSES      = ["active", "matured", "redeemed"]
INVEST_RISK_LEVELS   = ["low", "medium", "high"]

INDIAN_STATES = [
    "Maharashtra", "Karnataka", "Tamil Nadu", "Delhi", "Gujarat",
    "Rajasthan", "Uttar Pradesh", "West Bengal", "Telangana",
    "Kerala", "Madhya Pradesh", "Punjab", "Haryana", "Bihar",
    "Odisha", "Assam", "Jharkhand", "Uttarakhand", "Goa", "Himachal Pradesh",
]
STATE_REGION = {
    "Maharashtra": "West",  "Karnataka": "South", "Tamil Nadu": "South",
    "Delhi": "North",       "Gujarat": "West",    "Rajasthan": "North",
    "Uttar Pradesh": "North","West Bengal": "East","Telangana": "South",
    "Kerala": "South",      "Madhya Pradesh": "Central","Punjab": "North",
    "Haryana": "North",     "Bihar": "East",      "Odisha": "East",
    "Assam": "East",        "Jharkhand": "East",  "Uttarakhand": "North",
    "Goa": "West",          "Himachal Pradesh": "North",
}
CITY_STATE = [
    ("Mumbai","Maharashtra"), ("Bangalore","Karnataka"), ("Chennai","Tamil Nadu"),
    ("Delhi","Delhi"),        ("Hyderabad","Telangana"), ("Pune","Maharashtra"),
    ("Ahmedabad","Gujarat"),  ("Kolkata","West Bengal"), ("Jaipur","Rajasthan"),
    ("Lucknow","Uttar Pradesh"),("Kochi","Kerala"),      ("Chandigarh","Punjab"),
    ("Bhopal","Madhya Pradesh"),("Bhubaneswar","Odisha"),("Patna","Bihar"),
    ("Guwahati","Assam"),     ("Ranchi","Jharkhand"),   ("Dehradun","Uttarakhand"),
    ("Panaji","Goa"),         ("Shimla","Himachal Pradesh"),
]

# ---------------------------------------------------------------------------
# 4. REFERENCE POOLS  (populated as each collection is generated)
# ---------------------------------------------------------------------------
branch_ids       = []            # list of branch_id strings
employee_ids     = []            # list of all employee_id strings
branch_emp_map   = {}            # branch_id -> [employee_id, ...]
branch_mgr_map   = {}            # branch_id -> [manager-level employee_id, ...]
merchant_ids     = []
customer_ids     = []
account_ids      = []
account_map      = {}            # account_id -> {"customer_id": ..., "branch_id": ...}
txn_map          = {}            # transaction_id -> {"account_id":..., "customer_id":...}
flagged_txn_ids  = []

# ---------------------------------------------------------------------------
# 5. HELPERS
# ---------------------------------------------------------------------------

def rand_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return start
    return start + timedelta(seconds=random.randint(0, seconds))


def wc(options, weights):
    """weighted_choice shorthand"""
    return random.choices(options, weights=weights, k=1)[0]


def batch_insert(collection, docs, batch_size=CONFIG["BATCH_SIZE"]):
    total = 0
    for i in range(0, len(docs), batch_size):
        chunk = docs[i: i + batch_size]
        if not chunk:
            continue
        try:
            collection.insert_many(chunk, ordered=False)
            total += len(chunk)
        except BulkWriteError as bwe:
            total += bwe.details.get("nInserted", 0)
    return total


def masked_card() -> str:
    return f"XXXX-XXXX-XXXX-{random.randint(1000,9999)}"


def masked_aadhar() -> str:
    return f"XXXX-XXXX-{random.randint(1000,9999)}"


def masked_pan() -> str:
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return f"{''.join(random.choices(L,k=5))}{random.randint(1000,9999)}{random.choice(L)}"


def masked_doc(doc_type: str) -> str:
    L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if doc_type == "passport":
        return f"{random.choice(L)}{random.randint(1000000,9999999)}"
    if doc_type == "aadhar":
        return masked_aadhar()
    if doc_type == "pan":
        return masked_pan()
    if doc_type == "voter_id":
        return f"{''.join(random.choices(L,k=3))}{random.randint(100000,999999)}"
    if doc_type == "driving_license":
        st = random.choice(["MH","KA","TN","DL","GJ"])
        return f"{st}{random.randint(10,99)}{random.randint(10000000000,99999999999)}"
    return "MASKED"

# ---------------------------------------------------------------------------
# 6. GENERATORS
# ---------------------------------------------------------------------------

# ── 6.1  BRANCHES  (generated without manager_id; filled after employees) ──
def generate_branches(n: int) -> list:
    docs = []
    for i in range(1, n + 1):
        city, state = CITY_STATE[(i - 1) % len(CITY_STATE)]
        b_type  = wc(BRANCH_TYPES, [4, 1, 3, 2])
        b_status = wc(BRANCH_STATUSES, [85, 10, 5])   # mostly active
        open_dt = rand_date(datetime(2010, 1, 1), datetime(2022, 12, 31))
        doc = {
            "branch_id":           f"BR{i:05d}",
            "branch_name":         f"{city} {b_type.title()} Branch {i}",
            "ifsc_code":           f"FNTK{i:07d}",
            "address":             fake.street_address(),
            "city":                city,
            "state":               state,
            "pincode":             str(random.randint(100000, 999999)),
            "region":              STATE_REGION.get(state, "Central"),
            "branch_type":         b_type,
            "manager_id":          None,          # filled after employees
            "contact_number":      f"+91{random.randint(7000000000,9999999999)}",
            "opening_date":        open_dt,
            "working_hours":       "9:00 AM - 5:00 PM",
            "has_atm":             random.random() < 0.85,
            "has_locker_facility": random.random() < 0.60,
            "employee_count":      random.randint(5, 50),
            "status":              b_status,      # v2: lowercase
            "created_at":          open_dt,
        }
        docs.append(doc)
    return docs


# ── 6.2  EMPLOYEES  ─────────────────────────────────────────────────────────
# v2: ensures every branch has >=1 manager-level employee so
#     branch.manager_id can always reference someone at the same branch.
def generate_employees(n: int, br_ids: list) -> list:
    global branch_emp_map, branch_mgr_map

    branch_emp_map = {bid: [] for bid in br_ids}
    branch_mgr_map = {bid: [] for bid in br_ids}
    docs = []
    counter = 0

    # Salary bands by designation
    salary_range = {
        "Clerk":          (250000,  450000),
        "Officer":        (450000,  700000),
        "Manager":        (700000, 1200000),
        "Senior Manager": (1200000, 2000000),
        "Executive":      (2000000, 5000000),
    }
    MANAGER_DESIGS = {"Manager", "Senior Manager", "Executive"}

    def make_emp(idx, desig, branch):
        lo, hi = salary_range[desig]
        doj = rand_date(datetime(2010, 1, 1), datetime(2024, 1, 1))
        return {
            "employee_id":       f"EMP{idx:06d}",
            "first_name":        fake.first_name(),
            "last_name":         fake.last_name(),
            "designation":       desig,
            "department":        random.choice(EMP_DEPARTMENTS),
            "branch_id":         branch,
            "email":             f"emp{idx:06d}@fintechbank.in",
            "phone":             f"+91{random.randint(7000000000,9999999999)}",
            "date_of_joining":   doj,
            "salary":            round(random.uniform(lo, hi), 2),
            "manager_id":        None,   # back-filled below
            # role_level removed in v2
            "employment_status": wc(EMP_STATUSES, [85, 10, 5]),
            "performance_rating":round(random.uniform(2.0, 5.0), 1),
            "created_at":        doj,
        }

    # Pass 1: guarantee at least one Manager per branch
    for branch in br_ids:
        counter += 1
        desig = wc(["Manager", "Senior Manager"], [60, 40])
        doc = make_emp(counter, desig, branch)
        docs.append(doc)
        branch_emp_map[branch].append(doc["employee_id"])
        branch_mgr_map[branch].append(doc["employee_id"])

    # Pass 2: distribute remaining employees randomly
    remaining = max(0, n - len(br_ids))
    for _ in range(remaining):
        counter += 1
        desig  = wc(EMP_DESIGNATIONS, [30, 35, 20, 10, 5])
        branch = random.choice(br_ids)
        doc    = make_emp(counter, desig, branch)
        docs.append(doc)
        branch_emp_map[branch].append(doc["employee_id"])
        if desig in MANAGER_DESIGS:
            branch_mgr_map[branch].append(doc["employee_id"])

    # Back-fill manager_id (reports to a manager in the same branch where possible)
    all_ids = [d["employee_id"] for d in docs]
    for doc in docs:
        branch   = doc["branch_id"]
        mgrs     = [m for m in branch_mgr_map[branch]
                    if m != doc["employee_id"]]
        # If the branch has no other manager, use any manager in the system
        if not mgrs:
            mgrs = [d2["employee_id"] for d2 in docs
                    if d2["designation"] in MANAGER_DESIGS
                    and d2["employee_id"] != doc["employee_id"]]
        # Executives and Senior Managers may have no manager
        if doc["designation"] in ("Executive",) or not mgrs:
            doc["manager_id"] = None
        else:
            doc["manager_id"] = random.choice(mgrs)

    return docs


# ── 6.3  MERCHANTS  ─────────────────────────────────────────────────────────
def generate_merchants(n: int) -> list:
    docs = []
    avg_txn_ranges = {
        "groceries":     (200,  3000),
        "electronics":   (2000, 80000),
        "fuel":          (500,  5000),
        "dining":        (150,  5000),
        "travel":        (1000, 50000),
        "utilities":     (500,  10000),
        "healthcare":    (500,  20000),
        "entertainment": (200,  8000),
    }
    for i in range(1, n + 1):
        cat     = random.choice(MERCHANT_CATEGORIES)
        lo, hi  = avg_txn_ranges[cat]
        reg_dt  = rand_date(datetime(2015, 1, 1), datetime(2024, 1, 1))
        doc = {
            "merchant_id":               f"MER{i:06d}",
            "merchant_name":             fake.company(),
            "category":                  cat,
            "mcc_code":                  random.choice(MCC_MAP[cat]),
            "city":                      fake.city(),
            "state":                     random.choice(INDIAN_STATES),
            "registration_date":         reg_dt,
            "is_verified":               random.random() < 0.90,
            "average_transaction_value": round(random.uniform(lo, hi), 2),
            "total_transactions":        random.randint(100, 50000),
            "created_at":                reg_dt,
        }
        docs.append(doc)
    return docs


# ── 6.4  CUSTOMERS  ─────────────────────────────────────────────────────────
def generate_customers(n: int, emp_ids: list) -> list:
    docs = []
    income_range = {
        "Salaried":       (300000,  2000000),
        "Self-Employed":  (200000,  3000000),
        "Business Owner": (500000, 10000000),
        "Student":        (0,        300000),
        "Retired":        (100000,  1000000),
        "Homemaker":      (0,        200000),
    }
    for i in range(1, n + 1):
        occ      = wc(CUST_OCCUPATIONS, [40, 20, 15, 8, 10, 7])
        gender   = wc(["Male","Female","Other"], [52, 46, 2])
        first    = fake.first_name_male() if gender=="Male" else fake.first_name_female()
        dob      = rand_date(datetime(1955,1,1), datetime(2005,12,31))
        age      = (datetime.now() - dob).days // 365
        reg_dt   = rand_date(datetime(2015,1,1), datetime(2025,6,1))
        status   = wc(CUST_STATUSES, [80, 10, 6, 4])  # v2: lowercase
        lo, hi   = income_range[occ]
        doc = {
            "customer_id":             f"CUST{i:06d}",
            "first_name":              first,
            "last_name":               fake.last_name(),
            "dob":                     dob,
            "age":                     age,
            "gender":                  gender,
            "email":                   f"cust{i:06d}@mailsim.in",
            "phone":                   f"+91{random.randint(7000000000,9999999999)}",
            "address_line1":           fake.street_address(),
            "city":                    fake.city(),
            "state":                   random.choice(INDIAN_STATES),
            "pincode":                 str(random.randint(100000, 999999)),
            "country":                 "India",
            "pan_number":              masked_pan(),
            "aadhar_masked":           masked_aadhar(),
            "occupation":              occ,
            "annual_income":           round(random.uniform(lo, hi), 2),
            "marital_status":          random.choice(CUST_MARITAL),
            "nationality":             "Indian",
            "kyc_status":              wc(CUST_KYC_STATUSES, [75, 18, 7]),
            "risk_category":           wc(CUST_RISK_CATEGORIES, [55, 35, 10]),
            "account_opening_date":    reg_dt,
            "preferred_language":      random.choice(CUST_LANGUAGES),  # v2: fixed set
            "customer_segment":        wc(CUST_SEGMENTS, [50, 25, 10, 8, 7]),
            "customer_type":           wc(CUST_TYPES, [85, 15]),
            "credit_score":            random.randint(300, 900),
            "relationship_manager_id": random.choice(emp_ids),
            "is_active":               status == "active",
            "status":                  status,   # v2: lowercase
            "created_at":              reg_dt,
            "updated_at":              rand_date(reg_dt, datetime(2026, 9, 1)),
        }
        docs.append(doc)
    return docs


# ── 6.5  ACCOUNTS  ──────────────────────────────────────────────────────────
def generate_accounts(n: int, cust_ids: list, br_ids: list, emp_ids: list) -> list:
    docs = []

    # Build customer distribution (some get 0 accounts)
    pool = cust_ids.copy()
    random.shuffle(pool)
    assignments = []
    for cid in pool:
        count = wc([0, 1, 2, 3], [20, 45, 25, 10])
        assignments.extend([cid] * count)
    if len(assignments) < n:
        assignments.extend(random.choices(pool, k=n - len(assignments)))
    assignments = assignments[:n]
    random.shuffle(assignments)

    interest = {
        "savings":           lambda: round(random.uniform(3.0, 7.0), 2),
        "current":           lambda: 0.0,
        "salary":            lambda: round(random.uniform(2.5, 4.5), 2),
        "fixed_deposit":     lambda: round(random.uniform(6.5, 8.5), 2),
        "recurring_deposit": lambda: round(random.uniform(6.0, 8.0), 2),
    }
    min_bal = {
        "savings":           lambda: random.choice([0, 1000, 5000, 10000]),
        "current":           lambda: random.choice([5000, 10000, 25000]),
        "salary":            lambda: 0,
        "fixed_deposit":     lambda: 10000,
        "recurring_deposit": lambda: 500,
    }

    for i, cust_id in enumerate(assignments, start=1):
        acct_type  = wc(ACCT_TYPES, [45, 25, 15, 10, 5])
        status     = wc(ACCT_STATUSES, [75, 10, 8, 7])
        open_dt    = rand_date(datetime(2015,1,1), datetime(2025,1,1))
        m_bal      = min_bal[acct_type]()
        balance    = round(random.uniform(0, 300000), 2) \
                     if status == "closed" else round(random.uniform(m_bal, 2000000), 2)
        branch     = random.choice(br_ids)
        acct_id    = f"ACC{i:06d}"
        account_map[acct_id] = {"customer_id": cust_id, "branch_id": branch}
        doc = {
            "account_id":          acct_id,
            "customer_id":         cust_id,
            "account_number":      f"ACCTNO{i:010d}",
            "account_type":        acct_type,
            "branch_id":           branch,
            "ifsc_code":           f"FNTK{branch[2:]}0",
            "currency":            "INR",
            "balance":             balance,
            "available_balance":   round(balance * random.uniform(0.9, 1.0), 2),
            "opening_date":        open_dt,
            "status":              status,
            "interest_rate":       interest[acct_type](),
            "minimum_balance":     m_bal,
            "overdraft_limit":     random.choice([0, 5000, 10000, 25000])
                                   if acct_type == "current" else 0,
            "nominee_name":        fake.name(),
            "joint_holder":        fake.name() if random.random() < 0.10 else None,
            "account_manager_id":  random.choice(emp_ids),
            "last_transaction_date": rand_date(open_dt, datetime(2026, 9, 1)),
            "created_at":          open_dt,
            "updated_at":          rand_date(open_dt, datetime(2026, 9, 1)),
        }
        docs.append(doc)
    return docs


# ── 6.6  TRANSACTIONS  ──────────────────────────────────────────────────────
# v2: RTGS amount enforced >= 200000; customer_id derived from account_map.
def generate_transactions(n: int, acct_ids: list, merch_ids: list) -> list:
    docs = []

    cat_amt = {
        "groceries":    (100,    5000),
        "salary":       (20000, 300000),
        "rent":         (10000,  80000),
        "utilities":    (500,   10000),
        "transfer":     (1000,  500000),
        "shopping":     (200,   50000),
        "dining":       (150,    5000),
        "fuel":         (500,    5000),
        "investment":   (5000,  500000),
        "healthcare":   (500,   50000),
        "education":    (5000,  200000),
        "travel":       (1000,  100000),
        "entertainment":(200,    8000),
    }
    mode_amt = {
        "UPI":    (10,     100000),
        "NEFT":   (1000,   500000),
        "RTGS":   (200000, 5000000),   # v2: hard floor at 200000
        "IMPS":   (100,    200000),
        "cash":   (100,    50000),
        "cheque": (1000,   500000),
        "card":   (100,    100000),
    }
    # Categories where transaction type is always debit or credit
    always_credit = {"salary"}
    always_debit  = {"rent", "utilities", "shopping", "dining", "fuel",
                     "groceries", "entertainment", "fuel"}

    for i in range(1, n + 1):
        acct_id  = random.choice(acct_ids)
        # customer_id derived from account — enforces denormalisation rule
        cust_id  = account_map[acct_id]["customer_id"]
        mode     = wc(TXN_MODES, [35, 20, 5, 15, 10, 5, 10])
        category = random.choice(TXN_CATEGORIES)

        # Derive transaction type from category
        if category in always_credit:
            txn_type = "credit"
        elif category in always_debit:
            txn_type = "debit"
        else:
            txn_type = wc(TXN_TYPES, [60, 40])

        # Amount: RTGS always >= 200000 (v2 enforcement)
        if mode == "RTGS":
            amount = round(random.uniform(200000, 5000000), 2)
        else:
            lo_c, hi_c = cat_amt[category]
            lo_m, hi_m = mode_amt[mode]
            lo = max(lo_c, lo_m)
            hi = max(hi_c, hi_m, lo + 1)
            amount = round(random.uniform(lo, hi), 2)

        txn_date   = rand_date(datetime(2023, 1, 1), datetime(2026, 9, 1))
        status     = wc(TXN_STATUSES, [88, 5, 4, 3])
        is_flagged = random.random() < 0.02
        merchant   = random.choice(merch_ids) if random.random() < 0.65 else None
        txn_id     = f"TXN{i:09d}"

        doc = {
            "transaction_id":    txn_id,
            "account_id":        acct_id,
            "customer_id":       cust_id,   # derived — never independent
            "transaction_type":  txn_type,
            "amount":            amount,
            "currency":          "INR",
            "transaction_date":  txn_date,
            "transaction_mode":  mode,
            "merchant_id":       merchant,
            "description":       f"{category.title()} via {mode}",
            "balance_after":     round(random.uniform(0, 2000000), 2),
            "status":            status,
            "reference_number":  f"REF{random.randint(100000000,999999999)}",
            "counterparty_account": f"ACCTNO{random.randint(1,99999):010d}",
            "counterparty_name": fake.name(),
            "channel":           random.choice(TXN_CHANNELS),
            "location":          f"{fake.city()}, {random.choice(INDIAN_STATES)}",
            "ip_address":        fake.ipv4_private(),
            "device_id":         f"DEV{random.randint(100000,999999)}",
            "is_flagged":        is_flagged,
            "category":          category,
            "created_at":        txn_date,
        }
        docs.append(doc)
        txn_map[txn_id] = {"account_id": acct_id, "customer_id": cust_id}
        if is_flagged:
            flagged_txn_ids.append(txn_id)

    return docs


# ── 6.7  CARDS  ─────────────────────────────────────────────────────────────
# v2: customer_id is always derived from account_map[account_id]["customer_id"]
def generate_cards(n: int, cust_ids: list, acct_ids: list) -> list:
    docs = []

    # Build customer -> accounts lookup
    cust_accts: dict = {}
    for aid, info in account_map.items():
        cust_accts.setdefault(info["customer_id"], []).append(aid)

    # Distribution: some customers get 0, 1, or 2 cards
    pool = cust_ids.copy()
    random.shuffle(pool)
    assignments = []
    for cid in pool:
        cnt = wc([0, 1, 2], [25, 55, 20])
        assignments.extend([cid] * cnt)
    if len(assignments) < n:
        assignments.extend(random.choices(pool, k=n - len(assignments)))
    assignments = assignments[:n]
    random.shuffle(assignments)

    for i, cust_id in enumerate(assignments, start=1):
        # Pick an account belonging to this customer
        owned = cust_accts.get(cust_id, [])
        if owned:
            acct_id = random.choice(owned)
        else:
            # Customer has no account — pick any account and use ITS customer
            acct_id = random.choice(acct_ids)

        # v2: always derive customer_id from the account, never from assignment
        derived_cust_id = account_map[acct_id]["customer_id"]

        card_type  = wc(CARD_TYPES, [50, 50])
        issue_dt   = rand_date(datetime(2019, 1, 1), datetime(2025, 6, 1))
        expiry_dt  = issue_dt + timedelta(days=365 * random.randint(3, 5))
        status     = wc(CARD_STATUSES, [80, 12, 8])
        if expiry_dt < datetime.now():
            status = "expired"   # expired cards must have expired status

        credit_limit     = round(random.uniform(50000, 1000000), 2) if card_type == "credit" else 0.0
        available_credit = round(credit_limit * random.uniform(0.1, 1.0), 2) if card_type == "credit" else 0.0

        doc = {
            "card_id":            f"CARD{i:06d}",
            "customer_id":        derived_cust_id,   # v2: derived, not from assignment
            "account_id":         acct_id,
            "card_number_masked": masked_card(),
            "card_type":          card_type,
            "card_network":       wc(CARD_NETWORKS, [40, 35, 25]),
            "issue_date":         issue_dt,
            "expiry_date":        expiry_dt,
            "credit_limit":       credit_limit,
            "available_credit":   available_credit,
            "status":             status,
            "is_contactless":     random.random() < 0.80,
            "pin_set":            random.random() < 0.95,
            "billing_cycle_day":  random.randint(1, 28),
            "last_used_date":     rand_date(issue_dt, datetime(2026, 9, 1)),
            "reward_points":      random.randint(0, 50000),
            "created_at":         issue_dt,
        }
        docs.append(doc)
    return docs


# ── 6.8  LOANS  ─────────────────────────────────────────────────────────────
# v2: loan consistency rules enforced in code, not just documented.
def generate_loans(n: int, cust_ids: list, br_ids: list, emp_ids: list) -> list:
    docs = []
    pool = cust_ids.copy()
    random.shuffle(pool)
    assignments = []
    for cid in pool:
        cnt = wc([0, 1, 2], [40, 45, 15])
        assignments.extend([cid] * cnt)
    if len(assignments) < n:
        assignments.extend(random.choices(pool, k=n - len(assignments)))
    assignments = assignments[:n]
    random.shuffle(assignments)

    principal_range = {
        "home":      (1000000, 10000000),
        "personal":  (50000,   1000000),
        "auto":      (200000,  2000000),
        "education": (100000,  2000000),
        "gold":      (20000,    500000),
        "business":  (500000, 10000000),
    }
    rate_range = {
        "home":      (7.0,  9.5),
        "personal":  (10.5, 18.0),
        "auto":      (8.0,  12.0),
        "education": (7.5,  12.0),
        "gold":      (8.0,  14.0),
        "business":  (10.0, 18.0),
    }

    NOW = datetime.now()

    for i, cust_id in enumerate(assignments, start=1):
        loan_type  = random.choice(LOAN_TYPES)
        lo_p, hi_p = principal_range[loan_type]
        principal  = round(random.uniform(lo_p, hi_p), 2)
        rate       = round(random.uniform(*rate_range[loan_type]), 2)
        tenure     = random.choice([12, 24, 36, 48, 60, 84, 120, 180, 240])
        r          = rate / 12 / 100
        if r > 0:
            emi = round(principal * r * math.pow(1+r, tenure) / (math.pow(1+r, tenure)-1), 2)
        else:
            emi = round(principal / tenure, 2)

        status     = wc(LOAN_STATUSES, [55, 35, 10])
        start_date = rand_date(datetime(2018, 1, 1), datetime(2025, 6, 1))

        # v2: enforce null-field rules per status ──────────────────────────
        if status == "closed":
            outstanding  = 0.0
            next_due     = None   # rule: closed -> next_due_date = null

        elif status == "defaulted":
            outstanding  = round(principal * random.uniform(0.3, 0.90), 2)
            # rule: defaulted -> next_due_date is in the past
            next_due     = rand_date(datetime(2020, 1, 1), NOW - timedelta(days=1))

        else:  # active
            months_elapsed = max(1, (NOW - start_date).days // 30)
            paid_fraction  = min(months_elapsed / tenure, 0.95)
            outstanding    = round(principal * (1 - paid_fraction * 0.7), 2)
            # rule: active -> next_due_date in the future
            next_due       = rand_date(NOW + timedelta(days=1), NOW + timedelta(days=60))
        # ──────────────────────────────────────────────────────────────────

        doc = {
            "loan_id":                  f"LOAN{i:06d}",
            "customer_id":              cust_id,
            "loan_type":                loan_type,
            "principal_amount":         principal,
            "interest_rate":            rate,
            "tenure_months":            tenure,
            "emi_amount":               emi,
            "disbursement_date":        start_date,
            "status":                   status,
            "outstanding_amount":       outstanding,
            "next_due_date":            next_due,
            "collateral_type":          COLLATERAL_MAP.get(loan_type, "none"),
            "co_applicant":             fake.name() if random.random() < 0.25 else None,
            "sanctioning_branch_id":    random.choice(br_ids),
            "loan_officer_id":          random.choice(emp_ids),
            "credit_score_at_approval": random.randint(550, 900),
            "purpose":                  f"{loan_type.title()} loan",
            "prepayment_flag":          random.random() < 0.15,
            "created_at":               start_date,
        }
        docs.append(doc)
    return docs


# ── 6.9  KYC DOCUMENTS  ─────────────────────────────────────────────────────
# v2: verification_status != verified -> verified_by = null, verification_date = null
def generate_kyc_docs(n: int, cust_ids: list, emp_ids: list) -> list:
    docs = []
    for i, cust_id in enumerate(random.choices(cust_ids, k=n), start=1):
        doc_type  = random.choice(KYC_DOC_TYPES)
        v_status  = wc(KYC_STATUSES, [70, 20, 10])
        issue_dt  = rand_date(datetime(2010, 1, 1), datetime(2024, 1, 1))
        expiry_dt = issue_dt + timedelta(days=365 * random.randint(5, 10))

        # v2: enforce null-field rules ─────────────────────────────────────
        if v_status == "verified":
            verified_by   = random.choice(emp_ids)
            ver_date      = rand_date(issue_dt, datetime(2026, 1, 1))
        else:
            verified_by   = None   # rule: only null when not verified
            ver_date      = None   # rule: only null when not verified
        # ──────────────────────────────────────────────────────────────────

        doc = {
            "kyc_id":                 f"KYC{i:06d}",
            "customer_id":            cust_id,
            "document_type":          doc_type,
            "document_number_masked": masked_doc(doc_type),
            "issue_date":             issue_dt,
            "expiry_date":            expiry_dt,
            "verification_status":    v_status,
            "verified_by":            verified_by,
            "verification_date":      ver_date,
            "document_url":           f"https://docs.fintechbank.in/kyc/KYC{i:06d}.pdf",
            "created_at":             issue_dt,
        }
        docs.append(doc)
    return docs


# ── 6.10  SUPPORT TICKETS  ──────────────────────────────────────────────────
# v2: non-(resolved|closed) status -> resolved_date, resolution_notes,
#     satisfaction_rating all null.
def generate_support_tickets(n: int, cust_ids: list, emp_ids: list) -> list:
    docs = []
    for i in range(1, n + 1):
        cust_id  = random.choice(cust_ids)
        status   = wc(TICKET_STATUSES, [20, 25, 30, 25])
        priority = wc(TICKET_PRIORITIES, [30, 40, 20, 10])
        category = random.choice(TICKET_CATEGORIES)
        created  = rand_date(datetime(2024, 1, 1), datetime(2026, 9, 1))

        # v2: enforce null-field rules per status ──────────────────────────
        if status in TICKET_RESOLVED:
            resolved_date    = rand_date(created, datetime(2026, 9, 1))
            resolution_notes = fake.sentence()
            satisfaction     = random.randint(1, 5)
        else:
            resolved_date    = None   # rule
            resolution_notes = None   # rule
            satisfaction     = None   # rule
        # ──────────────────────────────────────────────────────────────────

        doc = {
            "ticket_id":          f"TKT{i:06d}",
            "customer_id":        cust_id,
            "category":           category,
            "subject":            f"{category.replace('_',' ').title()} Issue",
            "description":        fake.sentence(nb_words=12),
            "priority":           priority,
            "status":             status,
            "assigned_agent_id":  random.choice(emp_ids),
            "created_date":       created,
            "resolved_date":      resolved_date,
            "resolution_notes":   resolution_notes,
            "channel":            random.choice(TICKET_CHANNELS),
            "satisfaction_rating":satisfaction,
            "created_at":         created,
        }
        docs.append(doc)
    return docs


# ── 6.11  FRAUD ALERTS  ─────────────────────────────────────────────────────
# v2: customer_id derived from txn_map -> account_map chain (never independent)
def generate_fraud_alerts(n: int, emp_ids: list) -> list:
    docs = []
    # Use flagged transactions first; top up with random ones
    pool = flagged_txn_ids.copy()
    all_txn_ids = list(txn_map.keys())
    if len(pool) < n:
        pool.extend(random.choices(all_txn_ids, k=n - len(pool)))
    sample = random.choices(pool, k=n)

    for i, txn_id in enumerate(sample, start=1):
        info     = txn_map.get(txn_id, {})
        # v2: derive customer_id from transaction chain — never independently
        cust_id  = info.get("customer_id", customer_ids[0])
        a_status = wc(ALERT_STATUSES, [25, 20, 40, 15])

        # reviewed_by only for investigating/resolved statuses
        if a_status in ("resolved", "investigating"):
            reviewed_by  = random.choice(emp_ids)
            review_notes = fake.sentence()
        else:
            reviewed_by  = None
            review_notes = None

        doc = {
            "alert_id":       f"ALT{i:06d}",
            "transaction_id": txn_id,
            "customer_id":    cust_id,   # derived
            "alert_type":     random.choice(ALERT_TYPES),
            "risk_score":     round(random.uniform(0, 100), 2),
            "status":         a_status,
            "detected_at":    rand_date(datetime(2024, 1, 1), datetime(2026, 9, 1)),
            "reviewed_by":    reviewed_by,
            "review_notes":   review_notes,
            "action_taken":   wc(ALERT_ACTIONS, [40, 20, 25, 15]),
            "created_at":     rand_date(datetime(2024, 1, 1), datetime(2026, 9, 1)),
        }
        docs.append(doc)
    return docs


# ── 6.12  INVESTMENTS  ──────────────────────────────────────────────────────
# v2: investment_type=stocks -> maturity_date=null; all others require one.
def generate_investments(n: int, cust_ids: list) -> list:
    docs = []
    for i, cust_id in enumerate(random.choices(cust_ids, k=n), start=1):
        inv_type   = random.choice(INVEST_TYPES)
        status     = wc(INVEST_STATUSES, [55, 25, 20])
        purchase   = rand_date(datetime(2019, 1, 1), datetime(2025, 1, 1))
        amount     = round(random.uniform(5000, 2000000), 2)
        ret_pct    = round(random.uniform(-15.0, 45.0), 2)
        cur_val    = round(amount * (1 + ret_pct / 100), 2)

        # v2: stocks have no maturity date; all other types must have one
        if inv_type == "stocks":
            maturity = None
        else:
            maturity = purchase + timedelta(days=365 * random.randint(1, 10))

        doc = {
            "investment_id":     f"INV{i:06d}",
            "customer_id":       cust_id,
            "investment_type":   inv_type,
            "amount_invested":   amount,
            "current_value":     cur_val,
            "purchase_date":     purchase,
            "maturity_date":     maturity,   # null iff stocks
            "status":            status,
            "returns_percentage":ret_pct,
            "risk_level":        wc(INVEST_RISK_LEVELS, [35, 40, 25]),
            "fund_manager":      fake.name(),
            "created_at":        purchase,
        }
        docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# 7. INDEX CREATION
# ---------------------------------------------------------------------------
def create_indexes():
    print("\n-- Creating indexes -----------------------------------------------")
    specs = {
        "branches":        [("branch_id",         True)],
        "employees":       [("employee_id",        True),
                            ("branch_id",          False)],
        "merchants":       [("merchant_id",        True)],
        "customers":       [("customer_id",        True),
                            ("status",             False),
                            ("risk_category",      False)],
        "accounts":        [("account_id",         True),
                            ("customer_id",        False),
                            ("branch_id",          False),
                            ("status",             False)],
        "transactions":    [("transaction_id",     True),
                            ("account_id",         False),
                            ("customer_id",        False),
                            ("transaction_date",   False),
                            ("transaction_mode",   False),
                            ("status",             False),
                            ("is_flagged",         False)],
        "cards":           [("card_id",            True),
                            ("customer_id",        False),
                            ("account_id",         False)],
        "loans":           [("loan_id",            True),
                            ("customer_id",        False),
                            ("sanctioning_branch_id", False),
                            ("status",             False)],
        "kyc_documents":   [("kyc_id",             True),
                            ("customer_id",        False)],
        "support_tickets": [("ticket_id",          True),
                            ("customer_id",        False),
                            ("status",             False)],
        "fraud_alerts":    [("alert_id",           True),
                            ("transaction_id",     False),
                            ("customer_id",        False)],
        "investments":     [("investment_id",      True),
                            ("customer_id",        False)],
    }
    for coll_name, idx_list in specs.items():
        coll = db[coll_name]
        for field, unique in idx_list:
            coll.create_index([(field, ASCENDING)],
                              unique=unique, background=True)
            tag = "unique" if unique else "regular"
            print(f"  ok  {coll_name}.{field}  ({tag})")


# ---------------------------------------------------------------------------
# 8. MAIN
# ---------------------------------------------------------------------------
def main():
    global branch_ids, employee_ids, merchant_ids, customer_ids, account_ids

    print("=" * 65)
    print("  Fintech Agent DB -- Dataset Generator  (v2)")
    print(f"  URI: {MONGODB_URI}   DB: {DB_NAME}")
    print("=" * 65)

    if CONFIG["DROP_EXISTING"]:
        print("\n[Step 1] Dropping existing collections...")
        for c in ["branches","employees","merchants","customers","accounts",
                   "transactions","cards","loans","kyc_documents",
                   "support_tickets","fraud_alerts","investments"]:
            db[c].drop()
        print("  ok  All collections dropped.")

    # ── BRANCHES (no manager yet) ─────────────────────────────────────────
    print(f"\n[Step 2] Generating {CONFIG['NUM_BRANCHES']} branches...")
    branch_docs = generate_branches(CONFIG["NUM_BRANCHES"])
    branch_ids  = [d["branch_id"] for d in branch_docs]

    # ── EMPLOYEES (guarantees 1 manager per branch) ───────────────────────
    print(f"\n[Step 3] Generating {CONFIG['NUM_EMPLOYEES']} employees...")
    emp_docs    = generate_employees(CONFIG["NUM_EMPLOYEES"], branch_ids)
    employee_ids = [d["employee_id"] for d in emp_docs]

    # Back-fill branch.manager_id with an employee FROM THAT BRANCH (v2)
    for bdoc in branch_docs:
        bid  = bdoc["branch_id"]
        mgrs = branch_mgr_map.get(bid, [])
        if mgrs:
            bdoc["manager_id"] = random.choice(mgrs)
        else:
            # Fallback: any employee at this branch
            emps = branch_emp_map.get(bid, employee_ids[:1])
            bdoc["manager_id"] = random.choice(emps)

    batch_insert(db.branches, branch_docs)
    print(f"  ok  {len(branch_ids)} branches inserted (manager_id populated from same-branch employees).")

    batch_insert(db.employees, emp_docs)
    print(f"  ok  {len(employee_ids)} employees inserted.")

    # ── MERCHANTS ─────────────────────────────────────────────────────────
    print(f"\n[Step 4] Generating {CONFIG['NUM_MERCHANTS']} merchants...")
    merch_docs  = generate_merchants(CONFIG["NUM_MERCHANTS"])
    batch_insert(db.merchants, merch_docs)
    merchant_ids = [d["merchant_id"] for d in merch_docs]
    print(f"  ok  {len(merchant_ids)} merchants inserted.")

    # ── CUSTOMERS ─────────────────────────────────────────────────────────
    print(f"\n[Step 5] Generating {CONFIG['NUM_CUSTOMERS']} customers...")
    cust_docs   = generate_customers(CONFIG["NUM_CUSTOMERS"], employee_ids)
    batch_insert(db.customers, cust_docs)
    customer_ids = [d["customer_id"] for d in cust_docs]
    print(f"  ok  {len(customer_ids)} customers inserted.")

    # ── ACCOUNTS ─────────────────────────────────────────────────────────
    print(f"\n[Step 6] Generating {CONFIG['NUM_ACCOUNTS']} accounts...")
    acct_docs   = generate_accounts(CONFIG["NUM_ACCOUNTS"], customer_ids,
                                     branch_ids, employee_ids)
    batch_insert(db.accounts, acct_docs)
    account_ids = [d["account_id"] for d in acct_docs]
    print(f"  ok  {len(account_ids)} accounts inserted.")

    # ── TRANSACTIONS ─────────────────────────────────────────────────────
    print(f"\n[Step 7] Generating {CONFIG['NUM_TRANSACTIONS']} transactions...")
    txn_docs = generate_transactions(CONFIG["NUM_TRANSACTIONS"],
                                      account_ids, merchant_ids)
    batch_insert(db.transactions, txn_docs)
    print(f"  ok  {len(txn_docs)} transactions inserted "
          f"({len(flagged_txn_ids)} flagged).")

    # ── CARDS ────────────────────────────────────────────────────────────
    print(f"\n[Step 8] Generating {CONFIG['NUM_CARDS']} cards...")
    card_docs = generate_cards(CONFIG["NUM_CARDS"], customer_ids, account_ids)
    batch_insert(db.cards, card_docs)
    print(f"  ok  {len(card_docs)} cards inserted.")

    # ── LOANS ────────────────────────────────────────────────────────────
    print(f"\n[Step 9] Generating {CONFIG['NUM_LOANS']} loans...")
    loan_docs = generate_loans(CONFIG["NUM_LOANS"], customer_ids,
                                branch_ids, employee_ids)
    batch_insert(db.loans, loan_docs)
    print(f"  ok  {len(loan_docs)} loans inserted.")

    # ── KYC ──────────────────────────────────────────────────────────────
    print(f"\n[Step 10] Generating {CONFIG['NUM_KYC_DOCS']} KYC documents...")
    kyc_docs = generate_kyc_docs(CONFIG["NUM_KYC_DOCS"], customer_ids, employee_ids)
    batch_insert(db.kyc_documents, kyc_docs)
    print(f"  ok  {len(kyc_docs)} KYC documents inserted.")

    # ── TICKETS ──────────────────────────────────────────────────────────
    print(f"\n[Step 11] Generating {CONFIG['NUM_TICKETS']} support tickets...")
    ticket_docs = generate_support_tickets(CONFIG["NUM_TICKETS"],
                                            customer_ids, employee_ids)
    batch_insert(db.support_tickets, ticket_docs)
    print(f"  ok  {len(ticket_docs)} support tickets inserted.")

    # ── FRAUD ALERTS ─────────────────────────────────────────────────────
    print(f"\n[Step 12] Generating {CONFIG['NUM_FRAUD_ALERTS']} fraud alerts...")
    fraud_docs = generate_fraud_alerts(CONFIG["NUM_FRAUD_ALERTS"], employee_ids)
    batch_insert(db.fraud_alerts, fraud_docs)
    print(f"  ok  {len(fraud_docs)} fraud alerts inserted.")

    # ── INVESTMENTS ──────────────────────────────────────────────────────
    print(f"\n[Step 13] Generating {CONFIG['NUM_INVESTMENTS']} investments...")
    inv_docs = generate_investments(CONFIG["NUM_INVESTMENTS"], customer_ids)
    batch_insert(db.investments, inv_docs)
    print(f"  ok  {len(inv_docs)} investments inserted.")

    # ── INDEXES ──────────────────────────────────────────────────────────
    create_indexes()

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  GENERATION SUMMARY")
    print("=" * 65)
    colls = ["branches","employees","merchants","customers","accounts",
             "transactions","cards","loans","kyc_documents",
             "support_tickets","fraud_alerts","investments"]
    for c in colls:
        cnt = db[c].count_documents({})
        print(f"  {c:<24} {cnt:>8,} documents")
    print("=" * 65)
    print("  Dataset generation complete. v2 integrity rules applied.")
    client.close()


if __name__ == "__main__":
    main()
