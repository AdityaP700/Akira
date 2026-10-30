# DEMO.md — Akira 4-Minute Interactive Walkthrough

A complete, end-to-end scripted demonstration of the **Akira Expense Sharing Service** for the Decentro SDE Intern assignment review.

This demo can be executed against a running Akira instance (`http://localhost:8000` via `docker compose up` or `uvicorn app.main:app`). All steps use standard `curl` commands and show the exact expected JSON outputs.

---

## Prerequisites & Environment Setup

Start the server and apply migrations:
```bash
# Terminal 1: Start PostgreSQL and API service
make up
# Or locally:
alembic upgrade head
uvicorn app.main:app --port 8000
```

Set the base URL in your shell:
```bash
BASE_URL="http://localhost:8000"
```

---

## ⏱️ Timeline Overview (4 Minutes)

| Timestamp | Scenario / Action | What it Demonstrates |
|---|---|---|
| `0:00 - 0:30` | Health Check & User Creation | Clean bootstrap, bearer token issuance, hash-only token storage |
| `0:30 - 1:00` | Group Setup & Member Management | Creator auto-membership, duplicate rejection (409), member lists |
| `1:00 - 1:30` | PII Protection (Encrypted VPA) | AES-256-GCM encryption, blind indexing, response masking |
| `1:30 - 2:15` | Recording Expenses (EQUAL & SHARES) | Integer paise precision, snapshot shares, remainder distribution |
| `2:15 - 2:45` | Derived Balances & Settle-Up | Zero balance drift ($\sum \text{net} = 0$), greedy minimal cash flow |
| `2:45 - 3:15` | UPI Settlement & Signed Webhook | In-flight debt reservation, HMAC webhook, replay deduplication |
| `3:15 - 3:35` | Manual Cash Settlement (Claim & Confirm) | Two-sided approval state machine (`CLAIMED` $\to$ `CONFIRMED`) |
| `3:35 - 3:50` | Tamper-Evident Ledger Integrity | Cryptographic HMAC hash chain verification and tamper detection |
| `3:50 - 4:00` | Security & BOLA Prevention | OWASP API1 defense: non-member gets 404 `NOT_FOUND` |

---

## Step 1: Health Check (0:00)

Verify the service and active database connection:

```bash
curl -s -X GET "$BASE_URL/health"
```

**Expected Response (200 OK):**
```json
{
  "status": "ok",
  "db": "ok"
}
```

---

## Step 2: Register Users & Obtain Bearer Tokens (0:15)

Create the three Goa trip participants: **Mohit**, **Rahul**, and **Ankit**. Akira issues a secure bearer token (`est_...`) **only once** upon user creation. Only the SHA-256 hash is persisted in the database.

### 2.1 Create Mohit
```bash
curl -s -X POST "$BASE_URL/users" \
  -H "Content-Type: application/json" \
  -d '{"name": "Mohit"}'
```
**Expected Response (201 Created):**
```json
{
  "id": "usr_944e8bc1a43d92fb90a218f029",
  "name": "Mohit",
  "token": "est_3a7b9c1d5e7f9a2b4c6e8f0a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c",
  "created_at": "2026-10-31T01:00:00Z"
}
```
*(Store `MOHIT_ID` and `MOHIT_TOKEN` from your output)*

### 2.2 Create Rahul
```bash
curl -s -X POST "$BASE_URL/users" \
  -H "Content-Type: application/json" \
  -d '{"name": "Rahul"}'
```
*(Store `RAHUL_ID` and `RAHUL_TOKEN`)*

### 2.3 Create Ankit
```bash
curl -s -X POST "$BASE_URL/users" \
  -H "Content-Type: application/json" \
  -d '{"name": "Ankit"}'
```
*(Store `ANKIT_ID` and `ANKIT_TOKEN`)*

---

## Step 3: Group Setup & Duplicate Prevention (0:30)

### 3.1 Create Group "Goa Trip"
Mohit creates the group. The creator is automatically enrolled as the first member:
```bash
curl -s -X POST "$BASE_URL/groups" \
  -H "Authorization: Bearer $MOHIT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Goa Trip"}'
```
**Expected Response (201 Created):**
```json
{
  "id": "grp_5b8ef1092a48721c40ab21cd83",
  "name": "Goa Trip",
  "created_at": "2026-10-31T01:01:00Z"
}
```
*(Store `GROUP_ID`)*

### 3.2 Add Members
Mohit adds Rahul and Ankit to the group:
```bash
# Add Rahul
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/members" \
  -H "Authorization: Bearer $MOHIT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$RAHUL_ID\"}"

# Add Ankit
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/members" \
  -H "Authorization: Bearer $MOHIT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$ANKIT_ID\"}"
```

### 3.3 Verify Duplicate Membership Guard
Attempting to add Mohit again returns a clean conflict error:
```bash
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/members" \
  -H "Authorization: Bearer $MOHIT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$MOHIT_ID\"}"
```
**Expected Response (409 Conflict):**
```json
{
  "error": {
    "code": "ALREADY_MEMBER",
    "message": "User is already a member of this group",
    "request_id": "req_019012345678"
  }
}
```

---

## Step 4: PII Protection — Encrypted UPI VPA (1:00)

Mohit registers his UPI VPA for settlement payouts. The VPA is encrypted using **AES-256-GCM** with a random 96-bit nonce and public ID bound as Associated Authenticated Data (AAD). An HMAC-SHA256 blind index is stored for $O(1)$ uniqueness checks.

```bash
curl -s -X PUT "$BASE_URL/users/me/vpa" \
  -H "Authorization: Bearer $MOHIT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"vpa": "mohit.dec@okhdfcbank"}'
```
**Expected Response (200 OK — VPA Masked):**
```json
{
  "id": "usr_944e8bc1a43d92fb90a218f029",
  "name": "Mohit",
  "vpa_masked": "mo***@okhdfcbank"
}
```

---

## Step 5: Recording Expenses (1:30)

### 5.1 Expense 1: Dinner ₹1200 paid by Mohit (EQUAL Split)
Divided equally among Mohit, Rahul, and Ankit (₹400.00 each):
```bash
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/expenses" \
  -H "Authorization: Bearer $MOHIT_TOKEN" \
  -H "Idempotency-Key: exp_dinner_001" \
  -H "Content-Type: application/json" \
  -d "{
    \"paid_by\": \"$MOHIT_ID\",
    \"amount\": \"1200.00\",
    \"description\": \"Dinner at Fisherman's Wharf\",
    \"split_type\": \"EQUAL\"
  }"
```
**Expected Response (201 Created):**
```json
{
  "id": "exp_7f8a9b0c1d2e3f4a5b6c7d8e",
  "group_id": "grp_5b8ef1092a48721c40ab21cd83",
  "description": "Dinner at Fisherman's Wharf",
  "amount": "1200.00",
  "paid_by": {"id": "usr_944e8bc1a43d92fb90a218f029", "name": "Mohit"},
  "split_type": "EQUAL",
  "shares": [
    {"user": {"id": "usr_944e8bc1a43d92fb90a218f029", "name": "Mohit"}, "amount": "400.00"},
    {"user": {"id": "usr_...", "name": "Rahul"}, "amount": "400.00"},
    {"user": {"id": "usr_...", "name": "Ankit"}, "amount": "400.00"}
  ]
}
```

### 5.2 Expense 2: Cab ₹600 paid by Rahul (EQUAL Split)
Divided equally among all 3 (₹200.00 each):
```bash
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/expenses" \
  -H "Authorization: Bearer $RAHUL_TOKEN" \
  -H "Idempotency-Key: exp_cab_002" \
  -H "Content-Type: application/json" \
  -d "{
    \"paid_by\": \"$RAHUL_ID\",
    \"amount\": \"600.00\",
    \"description\": \"Airport Cab\",
    \"split_type\": \"EQUAL\"
  }"
```

### 5.3 Expense 3: Villa Grocery ₹3000 paid by Mohit (SHARES Split 2:1:1)
Mohit pays ₹3000. Shares: Mohit weight=2 (₹1500), Rahul weight=1 (₹750), Ankit weight=1 (₹750):
```bash
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/expenses" \
  -H "Authorization: Bearer $MOHIT_TOKEN" \
  -H "Idempotency-Key: exp_grocery_003" \
  -H "Content-Type: application/json" \
  -d "{
    \"paid_by\": \"$MOHIT_ID\",
    \"amount\": \"3000.00\",
    \"description\": \"Villa Grocery\",
    \"split_type\": \"SHARES\",
    \"shares\": [
      {\"user_id\": \"$MOHIT_ID\", \"weight\": 2},
      {\"user_id\": \"$RAHUL_ID\", \"weight\": 1},
      {\"user_id\": \"$ANKIT_ID\", \"weight\": 1}
    ]
  }"
```

---

## Step 6: Derived Balances & Settle-Up (2:15)

### 6.1 View Balances
Query derived group balances. Notice that net balances strictly sum to ₹0.00:
```bash
curl -s -X GET "$BASE_URL/groups/$GROUP_ID/balances" \
  -H "Authorization: Bearer $MOHIT_TOKEN"
```
**Expected Response (200 OK):**
```json
{
  "balances": {
    "Rahul": {"owes": {"Mohit": "750.00"}},
    "Ankit": {"owes": {"Mohit": "1150.00"}}
  },
  "pairs": [
    {"from": {"id": "usr_...", "name": "Rahul"}, "to": {"id": "usr_...", "name": "Mohit"}, "amount": "750.00"},
    {"from": {"id": "usr_...", "name": "Ankit"}, "to": {"id": "usr_...", "name": "Mohit"}, "amount": "1150.00"}
  ],
  "net": [
    {"user": {"id": "usr_...", "name": "Ankit"}, "net": "-1150.00"},
    {"user": {"id": "usr_...", "name": "Rahul"}, "net": "-750.00"},
    {"user": {"id": "usr_...", "name": "Mohit"}, "net": "1900.00"}
  ]
}
```

### 6.2 View Settle-Up Recommendations
Akira's greedy simplification computes the minimum number of transfers required:
```bash
curl -s -X GET "$BASE_URL/groups/$GROUP_ID/settle-up" \
  -H "Authorization: Bearer $MOHIT_TOKEN"
```
**Expected Response (200 OK):**
```json
{
  "suggestions": [
    {"from_user": {"id": "usr_...", "name": "Ankit"}, "to_user": {"id": "usr_...", "name": "Mohit"}, "amount": "1150.00"},
    {"from_user": {"id": "usr_...", "name": "Rahul"}, "to_user": {"id": "usr_...", "name": "Mohit"}, "amount": "750.00"}
  ],
  "note": "Greedy debt simplification: suggests at most n-1 payments to zero all net balances."
}
```

---

## Step 7: UPI Settlement & Signed Webhooks (2:45)

### 7.1 Initiate UPI Settlement
Ankit initiates a partial UPI repayment of ₹400.00 to Mohit. Akira decrypts Mohit's stored VPA only inside the payment provider call to construct the UPI deep link:
```bash
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/settlements" \
  -H "Authorization: Bearer $ANKIT_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"from_user\": \"$ANKIT_ID\",
    \"to_user\": \"$MOHIT_ID\",
    \"amount\": \"400.00\",
    \"method\": \"UPI\"
  }"
```
**Expected Response (201 Created):**
```json
{
  "id": "stl_1a2b3c4d5e6f7a8b9c0d1e2f",
  "status": "PENDING",
  "reference": "ref_8f9a0b1c2d3e4f5a",
  "amount": "400.00",
  "upi_link": "upi://pay?pa=mohit.dec@okhdfcbank&pn=Mohit&am=400.00&tr=ref_8f9a0b1c2d3e4f5a&cu=INR"
}
```
*(Store `SETTLEMENT_REF` and `SETTLEMENT_ID`)*

### 7.2 Simulate Signed Webhook Callback
Use the dev webhook simulator to trigger the signed HMAC provider callback:
```bash
curl -s -X POST "$BASE_URL/dev/mock-provider/pay/$SETTLEMENT_REF?outcome=success"
```
**Expected Response (200 OK):**
```json
{
  "status": "processed",
  "reference": "ref_8f9a0b1c2d3e4f5a",
  "outcome": "success"
}
```

### 7.3 Duplicate Webhook Replay Protection
Attempting to deliver the identical webhook again demonstrates replay protection:
```bash
curl -s -X POST "$BASE_URL/dev/mock-provider/pay/$SETTLEMENT_REF?outcome=success"
```
**Expected Response (200 OK — Idempotently Ignored):**
```json
{
  "status": "ignored",
  "reference": "ref_8f9a0b1c2d3e4f5a",
  "reason": "duplicate_event"
}
```

---

## Step 8: Manual Cash Settlement (Claim & Confirm) (3:15)

### 8.1 Debtor Claims Cash Repayment
Rahul pays Mohit ₹750.00 in cash and records a claim:
```bash
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/settlements" \
  -H "Authorization: Bearer $RAHUL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"from_user\": \"$RAHUL_ID\",
    \"to_user\": \"$MOHIT_ID\",
    \"amount\": \"750.00\",
    \"method\": \"CASH\"
  }"
```
**Expected Response (201 Created — Status CLAIMED):**
```json
{
  "id": "stl_cash_998877665544",
  "status": "CLAIMED",
  "amount": "750.00",
  "method": "CASH"
}
```
*(Store `CASH_STL_ID`)*

### 8.2 Creditor Confirms Receipt
Mohit verifies that he received the cash and confirms the settlement:
```bash
curl -s -X POST "$BASE_URL/groups/$GROUP_ID/settlements/$CASH_STL_ID/confirm" \
  -H "Authorization: Bearer $MOHIT_TOKEN"
```
**Expected Response (200 OK — Status CONFIRMED):**
```json
{
  "id": "stl_cash_998877665544",
  "status": "CONFIRMED"
}
```
*(Rahul's net balance is now fully settled to ₹0.00)*

---

## Step 9: Tamper-Evident Ledger Integrity Proof (3:35)

### 9.1 Verify Cryptographic Chain
Verify the group's HMAC hash chain:
```bash
curl -s -X GET "$BASE_URL/groups/$GROUP_ID/audit/verify" \
  -H "Authorization: Bearer $MOHIT_TOKEN"
```
**Expected Response (200 OK — Valid):**
```json
{
  "valid": true,
  "entries": 5,
  "head": "a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d5e7f9a2b4c6e8f0a1b3c5d7e9f1a3b5c7"
}
```

### 9.2 Simulate Database Tampering
An adversary with direct database access alters a ledger entry payload:
```bash
# Execute tamper via sqlite or psql
sqlite3 /tmp/akira_test.db "UPDATE ledger_entries SET payload = json('{\"amount_paise\": 999999}') WHERE group_id = 1 AND seq = 1;"
# Or in PostgreSQL:
# docker compose exec db psql -U app_owner -d akira -c "UPDATE ledger_entries SET payload = '{\"amount_paise\": 999999}' WHERE group_id = 1 AND seq = 1;"
```

### 9.3 Detect Tampering Immediately
Query `/audit/verify` again:
```bash
curl -s -X GET "$BASE_URL/groups/$GROUP_ID/audit/verify" \
  -H "Authorization: Bearer $MOHIT_TOKEN"
```
**Expected Response (200 OK — Tamper Detected!):**
```json
{
  "valid": false,
  "broken_at": 1,
  "reason": "hash_mismatch"
}
```

---

## Step 10: Broken Object-Level Authorization (BOLA) Defense (3:50)

### 10.1 Outsider Attempts Access
Create a 4th user **Eve** who is NOT a member of Goa Trip:
```bash
curl -s -X POST "$BASE_URL/users" \
  -H "Content-Type: application/json" \
  -d '{"name": "Eve"}'
```
*(Store `EVE_TOKEN`)*

Eve attempts to view Goa Trip's balances:
```bash
curl -s -X GET "$BASE_URL/groups/$GROUP_ID/balances" \
  -H "Authorization: Bearer $EVE_TOKEN"
```
**Expected Response (404 Not Found — OWASP API1):**
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Group 'grp_5b8ef1092a48721c40ab21cd83' not found",
    "request_id": "req_019012345678"
  }
}
```
> **Security Note:** Akira intentionally returns `404 Not Found` rather than `403 Forbidden` to prevent malicious attackers from enumerating valid group IDs.

---

## 4-Minute Demo Summary

In 4 minutes, you have demonstrated:
1. **User Token Auth & Secret Masking:** Secure bearer tokens, constant-time verification, no token logging.
2. **Group Locking & Duplicate Protection:** Creator auto-membership and 409 conflict checks.
3. **PII Protection:** AES-256-GCM encryption with AAD binding and HMAC-SHA256 blind indexing.
4. **Money Correctness:** Integer paise representation, EQUAL and SHARES split remainder distribution.
5. **Zero Balance Drift:** Derived dynamic balances strictly summing to zero, greedy $O(n \log n)$ settle-up suggestions.
6. **Payment Lifecycle:** In-flight debt capacity reservation, signed HMAC webhooks, and duplicate replay immunity.
7. **Two-Sided Cash Confirmation:** Manual claim $\to$ confirmation flow.
8. **Tamper-Evident Ledger:** HMAC-SHA256 hash chaining with immediate tamper detection.
9. **OWASP API1 (BOLA) Defense:** Non-member 404 suppression.
