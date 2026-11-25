# FinTech Agent — 55-Question Live Benchmark Execution Summary
**Date:** 2026-11-16 16:25:57 UTC  
**Target Dataset:** `fintech-agent/data/test_questions.json` (55 Questions across 5 Complexity Levels)  
**Database:** Authenticated MongoDB (`fintech_agent_db`, 19,120 records, Read-Only Sandboxed)  
**LLM Fallback Chain:** Gemini 3.8 Flash -> Groq GPT-OSS 120B -> Local Ollama  

---

## 1. Aggregate Execution Metrics

- **Total Questions Attempted:** **55 / 55**
- **Successful Database Executions:** **6** (10.9%)
- **Clarifications Requested by Agent:** **1** (1.8%)
- **Policy-Rejected / Unsupported Shielded:** **0** (0.0%)
- **Provider Failures / Timeouts:** **2** (3.6%)
- **Other / Unhandled Exceptions:** **46**
- **Overall Pipeline Completion Rate:** **96.4%**
- **Average Duration:** **3.21s** | **Median Duration:** **0.51s**
- **Provider Utilization:** {"groq": 9, "none": 46}
- **Ground Truth Correctness:** **NOT VERIFIED** (test_questions.json contains no expected output records)

---

## 2. Complete Question-by-Question Results Table

| ID | Level | Natural Language Prompt | Provider | Target Collection | Validation | DB Execution | Rows | Duration (s) | Status |
|:---:|:---:|:---|:---:|:---:|:---:|:---:|---:|---:|:---:|
| **Q01** | L1 | Show all active customers. | `groq` | `-` | `-` | `-` | 0 | 4.85s | **CLARIFICATION** |
| **Q02** | L1 | Find all branches located in Maharashtra. | `-` | `-` | `-` | `-` | 0 | 32.68s | **PROVIDER_FAILURE** |
| **Q03** | L1 | List all customers whose KYC status is 'pending'. | `-` | `-` | `-` | `-` | 0 | 40.99s | **PROVIDER_FAILURE** |
| **Q04** | L1 | Show all loans that are currently defaulted. | `groq` | `loans` | `VALID` | `SUCCESS` | 61 | 4.02s | **SUCCESS** |
| **Q05** | L1 | List all merchants in the 'dining' category. | `groq` | `merchants` | `VALID` | `SUCCESS` | 27 | 5.45s | **SUCCESS** |
| **Q06** | L1 | Show all credit cards that are currently blocked. | `groq` | `cards` | `VALID` | `SUCCESS` | 23 | 7.73s | **SUCCESS** |
| **Q07** | L1 | Find all support tickets with critical priority. | `groq` | `-` | `-` | `-` | 0 | 8.1s | **OUT_OF_SCOPE** |
| **Q08** | L1 | List all fraud alerts that are still open. | `groq` | `fraud_alerts` | `VALID` | `SUCCESS` | 77 | 14.54s | **SUCCESS** |
| **Q09** | L1 | Show all investments with a negative return. | `groq` | `investments` | `VALID` | `SUCCESS` | 210 | 14.15s | **SUCCESS** |
| **Q10** | L1 | List all employees in the 'Fraud & Risk' department. | `groq` | `-` | `-` | `-` | 0 | 13.04s | **OUT_OF_SCOPE** |
| **Q11** | L2 | Which customers have an annual income above ₹10 lakh, sorted by income descending? | `-` | `-` | `-` | `-` | 0 | 0.41s | **ERROR** |
| **Q12** | L2 | Find the top 10 accounts with the highest balance. | `-` | `-` | `-` | `-` | 0 | 0.44s | **ERROR** |
| **Q13** | L2 | How many transactions failed in 2024? | `-` | `-` | `-` | `-` | 0 | 0.47s | **ERROR** |
| **Q14** | L2 | List all high-risk customers who are currently blocked. | `-` | `-` | `-` | `-` | 0 | 0.54s | **ERROR** |
| **Q15** | L2 | Show all RTGS transactions above ₹10 lakh, sorted by amount descending. | `-` | `-` | `-` | `-` | 0 | 0.45s | **ERROR** |
| **Q16** | L2 | How many active home loans are there? | `groq` | `loans` | `VALID` | `SUCCESS` | 1 | 8.36s | **SUCCESS** |
| **Q17** | L2 | Which merchants have processed more than 10,000 transactions? | `-` | `-` | `-` | `-` | 0 | 0.7s | **ERROR** |
| **Q18** | L2 | List all dormant accounts opened before 2020. | `-` | `-` | `-` | `-` | 0 | 0.75s | **ERROR** |
| **Q19** | L2 | Find all support tickets raised via email that are still open or in progress. | `-` | `-` | `-` | `-` | 0 | 0.47s | **ERROR** |
| **Q20** | L2 | Which employees have a performance rating above 4.5? | `-` | `-` | `-` | `-` | 0 | 0.64s | **ERROR** |
| **Q21** | L3 | What is the average balance of savings accounts? | `-` | `-` | `-` | `-` | 0 | 0.51s | **ERROR** |
| **Q22** | L3 | What is the total transaction amount per month in 2025? | `-` | `-` | `-` | `-` | 0 | 0.49s | **ERROR** |
| **Q23** | L3 | How many customers are there in each risk category? | `-` | `-` | `-` | `-` | 0 | 0.51s | **ERROR** |
| **Q24** | L3 | What is the average loan interest rate by loan type? | `-` | `-` | `-` | `-` | 0 | 0.58s | **ERROR** |
| **Q25** | L3 | Which transaction category has the highest total spend? | `-` | `-` | `-` | `-` | 0 | 0.47s | **ERROR** |
| **Q26** | L3 | What is the total outstanding loan amount per loan type? | `-` | `-` | `-` | `-` | 0 | 0.43s | **ERROR** |
| **Q27** | L3 | How many transactions were made through each channel (UPI, NEFT, RTGS, etc.)? | `-` | `-` | `-` | `-` | 0 | 0.48s | **ERROR** |
| **Q28** | L3 | What is the maximum credit limit among all credit cards? | `-` | `-` | `-` | `-` | 0 | 0.56s | **ERROR** |
| **Q29** | L3 | What is the average credit score of customers who have defaulted loans? | `-` | `-` | `-` | `-` | 0 | 0.5s | **ERROR** |
| **Q30** | L3 | How many support tickets are there per priority level? | `-` | `-` | `-` | `-` | 0 | 0.4s | **ERROR** |
| **Q31** | L4 | Which customers have active personal loans? Show their name and outstanding amount. | `-` | `-` | `-` | `-` | 0 | 0.46s | **ERROR** |
| **Q32** | L4 | List all transactions made at dining merchants, along with the merchant name. | `-` | `-` | `-` | `-` | 0 | 0.5s | **ERROR** |
| **Q33** | L4 | Which branch has sanctioned the highest total loan amount? | `-` | `-` | `-` | `-` | 0 | 0.5s | **ERROR** |
| **Q34** | L4 | Which customers have an open fraud alert? Show customer name, alert type, and risk score. | `-` | `-` | `-` | `-` | 0 | 0.55s | **ERROR** |
| **Q35** | L4 | Find customers who have more than 2 active accounts. | `-` | `-` | `-` | `-` | 0 | 0.43s | **ERROR** |
| **Q36** | L4 | Which customers have never taken any loan? | `-` | `-` | `-` | `-` | 0 | 0.52s | **ERROR** |
| **Q37** | L4 | Which accounts have had no transactions in the last 6 months? | `-` | `-` | `-` | `-` | 0 | 0.49s | **ERROR** |
| **Q38** | L4 | What is the total transaction amount per customer for the year 2025? Show top 10 customers. | `-` | `-` | `-` | `-` | 0 | 0.49s | **ERROR** |
| **Q39** | L4 | List all fraud alerts along with the transaction amount and account number of the flagged transaction. | `-` | `-` | `-` | `-` | 0 | 0.72s | **ERROR** |
| **Q40** | L4 | Which employees have managed the most support tickets? Show top 5. | `-` | `-` | `-` | `-` | 0 | 0.48s | **ERROR** |
| **Q41** | L5 | Which customers with active personal loans made more than 5 transactions in the last 3 months? | `-` | `-` | `-` | `-` | 0 | 0.44s | **ERROR** |
| **Q42** | L5 | Which branch has the highest average account balance? Show branch name, city, and average balance. | `-` | `-` | `-` | `-` | 0 | 0.47s | **ERROR** |
| **Q43** | L5 | For each merchant category, what is the total transaction volume and average transaction amount in 2024? | `-` | `-` | `-` | `-` | 0 | 0.4s | **ERROR** |
| **Q44** | L5 | Which customers have both a defaulted loan and an open fraud alert? | `-` | `-` | `-` | `-` | 0 | 0.61s | **ERROR** |
| **Q45** | L5 | What is the month-over-month transaction count for UPI payments in 2025? | `-` | `-` | `-` | `-` | 0 | 0.49s | **ERROR** |
| **Q46** | L5 | Which customers have investments with returns above 20% and also have an active loan? | `-` | `-` | `-` | `-` | 0 | 0.56s | **ERROR** |
| **Q47** | L5 | For each loan officer, how many loans have they approved, and what is the total outstanding amount of their portfolio? | `-` | `-` | `-` | `-` | 0 | 0.51s | **ERROR** |
| **Q48** | L5 | Find customers from Karnataka who have a credit score above 750 and have made at least one transaction above ₹1 lakh in the last year. | `-` | `-` | `-` | `-` | 0 | 0.49s | **ERROR** |
| **Q49** | L5 | Which customers have unresolved support tickets AND have had a failed transaction in the past 6 months? | `-` | `-` | `-` | `-` | 0 | 0.48s | **ERROR** |
| **Q50** | L5 | Show the complete loan + account + customer summary for all defaulted loan customers: customer name, loan amount, outstanding, account balance, account type. | `-` | `-` | `-` | `-` | 0 | 0.66s | **ERROR** |
| **Q51** | L5 | Which branches have more than 50 accounts opened in the last 2 years? | `-` | `-` | `-` | `-` | 0 | 0.7s | **ERROR** |
| **Q52** | L5 | What is the average number of transactions per customer for customers who have both a credit card and a savings account? | `-` | `-` | `-` | `-` | 0 | 0.5s | **ERROR** |
| **Q53** | L5 | For high-risk customers, what is the distribution of their loan statuses? | `-` | `-` | `-` | `-` | 0 | 0.69s | **ERROR** |
| **Q54** | L5 | Which merchant has received the highest total payment amount through transactions? | `-` | `-` | `-` | `-` | 0 | 0.42s | **ERROR** |
| **Q55** | L5 | Generate a full customer 360 view: for a given customer_id, show their accounts, total transactions, active loans, open tickets, and card count. | `-` | `-` | `-` | `-` | 0 | 0.54s | **ERROR** |

---
*Generated by FinTech Agent Benchmark Runner | Antigravity AI*