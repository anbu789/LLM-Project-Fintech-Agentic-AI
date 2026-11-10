"""
sanity_check.py
================
Runs the three sanity-check queries against fintech_agent_db.
"""

from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["fintech_agent_db"]

print("=" * 60)
print("  Running Step 4 Sanity Check Queries...")
print("=" * 60)

# Query 1: Are RTGS amounts always >= 200k?
# Expectation: None
q1 = db.transactions.find_one({"transaction_mode": "RTGS", "amount": {"$lt": 200000}})
print("\n[Query 1] RTGS with amount < 200,000:")
print(f"  Result : {q1}")
print(f"  Check  : {'PASS (None found)' if q1 is None else 'FAIL (Found invalid record)'}")

# Query 2: Do closed loans have outstanding = 0?
# Expectation: None
q2 = db.loans.find_one({"status": "closed", "outstanding_amount": {"$gt": 0}})
print("\n[Query 2] Closed loans with outstanding_amount > 0:")
print(f"  Result : {q2}")
print(f"  Check  : {'PASS (None found)' if q2 is None else 'FAIL (Found invalid record)'}")

# Query 3: Branch manager works at the same branch?
# Expectation: 0 results
pipeline = [
    {"$lookup": {"from": "employees", "localField": "manager_id", "foreignField": "employee_id", "as": "mgr"}},
    {"$unwind": "$mgr"},
    {"$match": {"$expr": {"$ne": ["$branch_id", "$mgr.branch_id"]}}}
]
q3 = list(db.branches.aggregate(pipeline))
print("\n[Query 3] Branches where manager works at a different branch:")
print(f"  Mismatched count : {len(q3)}")
print(f"  Check            : {'PASS (0 mismatched)' if len(q3) == 0 else 'FAIL (Found mismatches)'}")
print("\n" + "=" * 60)
