# FinTech Agent — 55-Question Benchmark: Cumulative Progress Summary
**Date:** 2026-11-18 14:37:30 UTC  
**Total Processed:** **55 / 55 Questions** (100.0% complete)  
**Database:** Authenticated MongoDB (`fintech_agent_db`, 19,120 records, Read-Only Sandboxed)  
**Provider Chain:** Gemini 3.8 Flash ➔ Groq `openai/gpt-oss-120b` (Active) ➔ Local Ollama  

---

## 1. Aggregate Execution Metrics (Cumulative Q01 - Q55)

- **Questions Evaluated:** **55**
- **Successful Database Executions:** **31** (56.4%)
- **Clarifications Requested:** **1** (1.8%)
- **Out-of-Scope Shielded:** **6** (10.9%)
- **Policy/AST Rejections:** **17** (30.9%)
- **Errors / Timeouts:** **0** (0.0%)
- **Mean Latency:** `7748.9 ms` (`7.75 s`)
- **Median Latency (P50):** `5761.7 ms` (`5.76 s`)
- **P90 Latency:** `15446.04 ms` (`15.45 s`)
- **P95 Latency:** `16307.64 ms` (`16.31 s`)

---

## 2. Complete Question Results Table

| ID | Batch | Question Prompt | Intent | Target Col | Validator | Execution | Latency (ms) | Status |
|:---:|:---:|:---|:---:|:---:|:---:|:---:|---:|:---:|
| **Q01** | Batch 1 | Show all active customers. | `CLARIFICATION_REQUIRED` | `customers` | `SKIPPED` | `SKIPPED` | 4,850 | **CLARIFICATION** |
| **Q02** | Batch 1 | Find all branches located in Maharashtra. | `QUERY_ONLY` | `branches` | `VALID` | `SUCCESS_WITH_DATA` | 11,850 | **SUCCESS** |
| **Q03** | Batch 1 | List all customers whose KYC status is 'pending'. | `QUERY_ONLY` | `kyc_documents` | `VALID` | `SUCCESS_WITH_DATA` | 5,180 | **SUCCESS** |
| **Q04** | Batch 1 | Show all loans that are currently defaulted. | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS_WITH_DATA` | 4,020 | **SUCCESS** |
| **Q05** | Batch 1 | List all merchants in the 'dining' category. | `QUERY_ONLY` | `merchants` | `VALID` | `SUCCESS_WITH_DATA` | 5,450 | **SUCCESS** |
| **Q06** | Batch 1 | Show all credit cards that are currently blocked. | `QUERY_ONLY` | `cards` | `VALID` | `SUCCESS_WITH_DATA` | 7,730 | **SUCCESS** |
| **Q07** | Batch 1 | Find all support tickets with critical priority. | `OUT_OF_SCOPE` | `support_tickets` | `SKIPPED` | `SKIPPED` | 8,100 | **OUT_OF_SCOPE** |
| **Q08** | Batch 1 | List all fraud alerts that are still open. | `QUERY_ONLY` | `fraud_alerts` | `VALID` | `SUCCESS_WITH_DATA` | 14,540 | **SUCCESS** |
| **Q09** | Batch 1 | Show all investments with a negative return. | `QUERY_ONLY` | `investments` | `VALID` | `SUCCESS_WITH_DATA` | 14,150 | **SUCCESS** |
| **Q10** | Batch 1 | List all employees in the 'Fraud & Risk' department. | `OUT_OF_SCOPE` | `employees` | `SKIPPED` | `SKIPPED` | 13,040 | **OUT_OF_SCOPE** |
| **Q11** | Batch 2 | Which customers have an annual income above ₹10 lakh, sorted by income descending? | `QUERY_ONLY` | `customers` | `VALID` | `SUCCESS` | 5,610 | **SUCCESS** |
| **Q12** | Batch 2 | Find the top 10 accounts with the highest balance. | `QUERY_ONLY` | `accounts` | `VALID` | `SUCCESS` | 5,723 | **SUCCESS** |
| **Q13** | Batch 2 | How many transactions failed in 2024? | `QUERY_ONLY` | `transactions` | `VALID` | `SUCCESS` | 23,480 | **SUCCESS** |
| **Q14** | Batch 2 | List all high-risk customers who are currently blocked. | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 15,565 | **REJECTED_POLICY** |
| **Q15** | Batch 2 | Show all RTGS transactions above ₹10 lakh, sorted by amount descending. | `QUERY_ONLY` | `transactions` | `VALID` | `SUCCESS` | 15,499 | **SUCCESS** |
| **Q16** | Batch 2 | How many active home loans are there? | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS` | 15,446 | **SUCCESS** |
| **Q17** | Batch 2 | Which merchants have processed more than 10,000 transactions? | `QUERY_ONLY` | `merchants` | `VALID` | `SUCCESS` | 5,108 | **SUCCESS** |
| **Q18** | Batch 2 | List all dormant accounts opened before 2020. | `QUERY_ONLY` | `accounts` | `VALID` | `SUCCESS` | 18,059 | **SUCCESS** |
| **Q19** | Batch 2 | Find all support tickets raised via email that are still open or in progress. | `OUT_OF_SCOPE` | `-` | `SKIPPED` | `SKIPPED` | 6,067 | **OUT_OF_SCOPE** |
| **Q20** | Batch 2 | Which employees have a performance rating above 4.5? | `OUT_OF_SCOPE` | `-` | `SKIPPED` | `SKIPPED` | 5,126 | **OUT_OF_SCOPE** |
| **Q21** | Batch 3 | What is the average balance of savings accounts? | `QUERY_ONLY` | `accounts` | `VALID` | `SUCCESS` | 16,307 | **SUCCESS** |
| **Q22** | Batch 3 | What is the total transaction amount per month in 2025? | `QUERY_ONLY` | `transactions` | `INVALID` | `SKIPPED` | 7,172 | **REJECTED_POLICY** |
| **Q23** | Batch 3 | How many customers are there in each risk category? | `QUERY_ONLY` | `customers` | `VALID` | `SUCCESS` | 5,533 | **SUCCESS** |
| **Q24** | Batch 3 | What is the average loan interest rate by loan type? | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS` | 6,344 | **SUCCESS** |
| **Q25** | Batch 3 | Which transaction category has the highest total spend? | `QUERY_ONLY` | `transactions` | `VALID` | `SUCCESS` | 3,053 | **SUCCESS** |
| **Q26** | Batch 3 | What is the total outstanding loan amount per loan type? | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS` | 5,815 | **SUCCESS** |
| **Q27** | Batch 3 | How many transactions were made through each channel (UPI, NEFT, RTGS, etc.)? | `QUERY_ONLY` | `transactions` | `VALID` | `SUCCESS` | 2,716 | **SUCCESS** |
| **Q28** | Batch 3 | What is the maximum credit limit among all credit cards? | `QUERY_ONLY` | `cards` | `VALID` | `SUCCESS` | 5,761 | **SUCCESS** |
| **Q29** | Batch 3 | What is the average credit score of customers who have defaulted loans? | `QUERY_ONLY` | `loans` | `INVALID` | `SKIPPED` | 4,692 | **REJECTED_POLICY** |
| **Q30** | Batch 3 | How many support tickets are there per priority level? | `OUT_OF_SCOPE` | `-` | `SKIPPED` | `SKIPPED` | 665 | **OUT_OF_SCOPE** |
| **Q31** | Batch 4 | Which customers have active personal loans? Show their name and outstanding amount. | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS` | 6,309 | **SUCCESS** |
| **Q32** | Batch 4 | List all transactions made at dining merchants, along with the merchant name. | `QUERY_ONLY` | `transactions` | `VALID` | `SUCCESS` | 4,919 | **SUCCESS** |
| **Q33** | Batch 4 | Which branch has sanctioned the highest total loan amount? | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS` | 13,024 | **SUCCESS** |
| **Q34** | Batch 4 | Which customers have an open fraud alert? Show customer name, alert type, and risk score. | `QUERY_ONLY` | `fraud_alerts` | `VALID` | `SUCCESS` | 3,956 | **SUCCESS** |
| **Q35** | Batch 4 | Find customers who have more than 2 active accounts. | `QUERY_ONLY` | `accounts` | `VALID` | `SUCCESS` | 6,331 | **SUCCESS** |
| **Q36** | Batch 4 | Which customers have never taken any loan? | `QUERY_ONLY` | `customers` | `INVALID` | `SKIPPED` | 5,409 | **REJECTED_POLICY** |
| **Q37** | Batch 4 | Which accounts have had no transactions in the last 6 months? | `QUERY_ONLY` | `accounts` | `INVALID` | `SKIPPED` | 6,700 | **REJECTED_POLICY** |
| **Q38** | Batch 4 | What is the total transaction amount per customer for the year 2025? Show top 10 customers. | `QUERY_ONLY` | `transactions` | `VALID` | `SUCCESS` | 2,368 | **SUCCESS** |
| **Q39** | Batch 4 | List all fraud alerts along with the transaction amount and account number of the flagged transaction. | `QUERY_ONLY` | `fraud_alerts` | `INVALID` | `SKIPPED` | 2,952 | **REJECTED_POLICY** |
| **Q40** | Batch 4 | Which employees have managed the most support tickets? Show top 5. | `OUT_OF_SCOPE` | `-` | `SKIPPED` | `SKIPPED` | 2,251 | **OUT_OF_SCOPE** |
| **Q41** | Batch 5 | Which customers with active personal loans made more than 5 transactions in the last 3 months? | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 5,746 | **REJECTED_POLICY** |
| **Q42** | Batch 5 | Which branch has the highest average account balance? Show branch name, city, and average balance. | `QUERY_ONLY` | `accounts` | `VALID` | `SUCCESS` | 4,565 | **SUCCESS** |
| **Q43** | Batch 5 | For each merchant category, what is the total transaction volume and average transaction amount in 2024? | `QUERY_ONLY` | `transactions` | `VALID` | `SUCCESS` | 3,185 | **SUCCESS** |
| **Q44** | Batch 5 | Which customers have both a defaulted loan and an open fraud alert? | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 8,256 | **REJECTED_POLICY** |
| **Q45** | Batch 5 | What is the month-over-month transaction count for UPI payments in 2025? | `QUERY_ONLY` | `transactions` | `INVALID` | `SKIPPED` | 11,356 | **REJECTED_POLICY** |
| **Q46** | Batch 5 | Which customers have investments with returns above 20% and also have an active loan? | `QUERY_ONLY` | `customers` | `INVALID` | `SKIPPED` | 6,386 | **REJECTED_POLICY** |
| **Q47** | Batch 5 | For each loan officer, how many loans have they approved, and what is the total outstanding amount of their portfolio? | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS` | 8,988 | **SUCCESS** |
| **Q48** | Batch 5 | Find customers from Karnataka who have a credit score above 750 and have made at least one transaction above ₹1 lakh in the last year. | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 5,414 | **REJECTED_POLICY** |
| **Q49** | Batch 5 | Which customers have unresolved support tickets AND have had a failed transaction in the past 6 months? | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 12,794 | **REJECTED_POLICY** |
| **Q50** | Batch 5 | Show the complete loan + account + customer summary for all defaulted loan customers: customer name, loan amount, outstanding, account balance, account type. | `QUERY_ONLY` | `loans` | `INVALID` | `SKIPPED` | 5,402 | **REJECTED_POLICY** |
| **Q51** | Batch 6 | Which branches have more than 50 accounts opened in the last 2 years? | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 3,649 | **REJECTED_POLICY** |
| **Q52** | Batch 6 | What is the average number of transactions per customer for customers who have both a credit card and a savings account? | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 4,787 | **REJECTED_POLICY** |
| **Q53** | Batch 6 | For high-risk customers, what is the distribution of their loan statuses? | `QUERY_ONLY` | `loans` | `VALID` | `SUCCESS` | 7,762 | **SUCCESS** |
| **Q54** | Batch 6 | Which merchant has received the highest total payment amount through transactions? | `QUERY_ONLY` | `transactions` | `INVALID` | `SKIPPED` | 5,750 | **REJECTED_POLICY** |
| **Q55** | Batch 6 | Generate a full customer 360 view: for a given customer_id, show their accounts, total transactions, active loans, open tickets, and card count. | `QUERY_ONLY` | `-` | `INVALID` | `SKIPPED` | 15,259 | **REJECTED_POLICY** |

---
**Status:** COMPLETED (COMPLETED)