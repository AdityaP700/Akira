# API Documentation — Akira Expense Sharing Service

This document provides the OpenAPI-compliant REST API documentation for the Akira Expense Sharing Service.

## 1. Overview & Conventions

- **Base URL:** `http://localhost:8000`
- **Content Type:** `application/json` (Non-JSON write payloads return `415 UNSUPPORTED_MEDIA_TYPE`).
- **Maximum Request Body Size:** 64 KB (requests exceeding this cap return `413 PAYLOAD_TOO_LARGE`).
- **Monetary Amounts:** Formatted as 2-decimal rupee strings (e.g. `"400.00"`). Internal storage and calculations are strictly integer paise.
- **Identifiers:** External public resources use opaque IDs with prefix (`usr_`, `grp_`, `exp_`, `stl_`, `ref_`, `ntf_`). Internal integer serial IDs never leave the service.
- **Request Models:** Enforce `extra="forbid"`. Unrecognized query parameters or JSON fields return `422 Unprocessable Content`.

### Authentication & Object-Level Authorisation (OWASP API1/API2/API5)

- **Authentication Scheme:** `Authorization: Bearer <api_token>`
- **Token Format:** Cryptographically strong 32-byte tokens prefixed with `est_` (e.g. `est_...`). Stored as SHA-256 hashes in the database; plaintext tokens are displayed only once upon generation.
- **Token Delivery:** Generated and returned on user registration (`POST /users`). Token rotation supported via `POST /users/me/token/rotate`.
- **Public Routes:** `POST /users` (registration) and `GET /health` (probes) are public. All other endpoints require a valid Bearer token.
- **BOLA Protection (Broken Object-Level Authorisation):**
  - Group-scoped endpoints strictly require caller membership.
  - Non-members receive an identical **404 `NOT_FOUND`** (`{"error": {"code": "NOT_FOUND", "message": "Group 'grp_...' not found"}}`), preventing group ID enumeration attacks.
- **Data Minimisation (OWASP API3):**
  - `GET /users` returns only users who share at least one group with the authenticated caller (plus the caller themselves).
  - `GET /balances` returns only groups where the caller is an active member.
- **Membership Flow:** Creating a group automatically enrolls the creator as its first member. Only existing members may add new members.

### Uniform Error Response Format

All error responses return a standardized JSON envelope with the active request trace ID:

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Group 'grp_123' not found",
    "request_id": "req_019012345678"
  }
}
```

---

## 2. Endpoints Summary

| Method | Path | Auth Required | Request Body | Status | Description |
|---|---|---|---|---|---|
| `GET` | `/health` | No | None | 200 / 503 | Database connectivity health probe |
| `POST` | `/users` | No | `{"name": "Mohit"}` | 201 | Register a new user & receive API token |
| `GET` | `/users/me` | Bearer Token | None | 200 | Get caller profile including masked VPA |
| `PUT` | `/users/me/vpa` | Bearer Token | `{"vpa": "user@bank"}` | 200 | Set encrypted VPA with blind index |
| `POST` | `/users/me/token/rotate` | Bearer Token | None | 200 | Invalidate old token and issue new API token |
| `GET` | `/users` | Bearer Token | None (Query: `limit`, `cursor`) | 200 | Keyset paginated shared users list |
| `POST` | `/groups` | Bearer Token | `{"name": "Goa Trip"}` | 201 | Create a group (caller is auto-enrolled as member) |
| `POST` | `/groups/{group_id}/members` | Bearer Token (Member) | `{"user_id": "usr_..."}` | 201 | Add a user to a group |
| `GET` | `/groups/{group_id}/members` | Bearer Token (Member) | None | 200 | List all members in a group |
| `POST` | `/groups/{group_id}/expenses` | Bearer Token (Member) | `{"paid_by", "amount", "description", "split_type", ...}` | 201 | Atomic expense creation with shares & ledger |
| `POST` | `/expenses` | Bearer Token (Member) | `{"group_id", "paid_by", "amount", ...}` | 201 | Brief-compatible alias for expense creation |
| `GET` | `/groups/{group_id}/expenses` | Bearer Token (Member) | None (Query: `limit`, `cursor`) | 200 | Keyset paginated group expenses list |
| `GET` | `/groups/{group_id}/balances` | Bearer Token (Member) | None | 200 | Derived pairwise and net balances |
| `GET` | `/balances` | Bearer Token | None | 200 | Derived balances across caller's groups |
| `GET` | `/groups/{group_id}/settle-up` | Bearer Token (Member) | None | 200 | Greedy debt simplification suggestions |
| `POST` | `/groups/{group_id}/settlements` | Bearer Token (Member) | `{"from_user", "to_user", "amount", "method", ...}` | 201 | Initiate or record repayment |
| `GET` | `/groups/{group_id}/settlements` | Bearer Token (Member) | None (Query: `limit`, `cursor`) | 200 | Keyset paginated settlements list |
| `POST` | `/groups/{group_id}/settlements/{id}/confirm` | Bearer Token (Creditor) | None | 200 | Confirm claimed manual cash settlement |
| `POST` | `/groups/{group_id}/settlements/{id}/reject` | Bearer Token (Creditor) | None | 200 | Reject claimed manual cash settlement |
| `POST` | `/groups/{group_id}/settlements/{id}/refresh` | Bearer Token (Member) | None | 200 | Query provider payment status fallback |
| `POST` | `/webhooks/mock-provider` | Provider Signature | `{"event_id", "reference", "status", "amount"}` | 200 | Signed raw body webhook callback |
| `GET` | `/groups/{group_id}/audit/verify` | Bearer Token (Member) | None | 200 | Verify HMAC hash chain & ledger integrity |
| `GET` | `/users/me/notifications` | Bearer Token | None (Query: `unread`, `limit`, `cursor`) | 200 | Keyset paginated notifications feed |
| `POST` | `/users/me/notifications/{id}/read` | Bearer Token | None | 200 | Acknowledge and mark notification read |

---

## 3. Detailed Endpoint Specifications

### 3.1 Health Probe
`GET /health`
- **Response (200 OK):** `{"status": "ok", "db": "ok"}`
- **Response (503 Service Unavailable):** `{"status": "degraded", "db": "down"}`

### 3.2 User Registration
`POST /users`
- **Body:** `{"name": "Mohit"}`
- **Response (201 Created):**
  ```json
  {
    "user": {
      "id": "usr_944e8bc1a43d92fb90a218f029",
      "name": "Mohit",
      "created_at": "2026-10-30T10:00:00Z"
    },
    "api_token": "est_3qV9A_c1F...<shown once>"
  }
  ```

### 3.3 User Profile & Encrypted VPA
`GET /users/me`
- **Headers:** `Authorization: Bearer <token>`
- **Response (200 OK):**
  ```json
  {
    "id": "usr_944e8bc1a43d92fb90a218f029",
    "name": "Mohit",
    "created_at": "2026-10-30T10:00:00Z",
    "vpa_masked": "mo***@okhdfcbank"
  }
  ```

`PUT /users/me/vpa`
- **Headers:** `Authorization: Bearer <token>`
- **Body:** `{"vpa": "mohit@okhdfcbank"}`
- **Response (200 OK):** `{"vpa_masked": "mo***@okhdfcbank"}`
- **Error (409 Conflict):** `{"error": {"code": "VPA_ALREADY_IN_USE", "message": "This VPA is already linked to another account"}}`

### 3.4 Token Rotation
`POST /users/me/token/rotate`
- **Headers:** `Authorization: Bearer <token>`
- **Response (200 OK):** `{"api_token": "est_new_secret_token..."}`

### 3.5 Group Management
`POST /groups`
- **Body:** `{"name": "Goa Trip"}`
- **Response (201 Created):** `{"id": "grp_...", "name": "Goa Trip", "created_at": "..."}`

`POST /groups/{group_id}/members`
- **Body:** `{"user_id": "usr_..."}`
- **Response (201 Created):** `{"id": "usr_...", "name": "...", "created_at": "..."}`

`GET /groups/{group_id}/members`
- **Response (200 OK):** `[{"id": "usr_...", "name": "...", "created_at": "..."}]`

### 3.6 Create Expense (EQUAL, EXACT, SHARES)
`POST /groups/{group_id}/expenses`
- **Header:** `Idempotency-Key: <unique_key>` (optional)

**EQUAL Split Example:**
```json
{
  "paid_by": "usr_alice",
  "amount": "300.00",
  "description": "Lunch",
  "split_type": "EQUAL"
}
```

**EXACT Split Example:**
```json
{
  "paid_by": "usr_alice",
  "amount": "300.00",
  "description": "Scuba Diving",
  "split_type": "EXACT",
  "splits": [
    {"user_id": "usr_alice", "amount": "100.00"},
    {"user_id": "usr_bob", "amount": "200.00"}
  ]
}
```

**SHARES Split Example:**
```json
{
  "paid_by": "usr_alice",
  "amount": "100.00",
  "description": "Groceries",
  "split_type": "SHARES",
  "shares": [
    {"user_id": "usr_alice", "weight": 2},
    {"user_id": "usr_bob", "weight": 1},
    {"user_id": "usr_charlie", "weight": 1}
  ]
}
```

- **Response (201 Created):**
  ```json
  {
    "id": "exp_...",
    "group_id": "grp_...",
    "description": "Groceries",
    "amount": "100.00",
    "paid_by": {"id": "usr_alice", "name": "Alice"},
    "split_type": "SHARES",
    "shares": [
      {"user_id": "usr_alice", "name": "Alice", "amount": "50.00"},
      {"user_id": "usr_bob", "name": "Bob", "amount": "25.00"},
      {"user_id": "usr_charlie", "name": "Charlie", "amount": "25.00"}
    ],
    "created_at": "2026-10-30T10:00:00Z"
  }
  ```

### 3.7 Balances & Settle-Up Suggestions
`GET /groups/{group_id}/balances`
- **Response (200 OK):**
  ```json
  {
    "group_id": "grp_...",
    "group_name": "Goa Trip",
    "net_balances": [
      {"user": {"id": "usr_alice", "name": "Alice"}, "net_balance": "50.00"},
      {"user": {"id": "usr_bob", "name": "Bob"}, "net_balance": "-50.00"}
    ],
    "pairwise_debts": [
      {
        "debtor": {"id": "usr_bob", "name": "Bob"},
        "creditor": {"id": "usr_alice", "name": "Alice"},
        "amount": "50.00"
      }
    ]
  }
  ```

`GET /groups/{group_id}/settle-up`
- **Response (200 OK):**
  ```json
  {
    "group_id": "grp_...",
    "suggestions": [
      {
        "from_user": {"id": "usr_bob", "name": "Bob"},
        "to_user": {"id": "usr_alice", "name": "Alice"},
        "amount": "50.00"
      }
    ],
    "count": 1,
    "note": "suggestion only; greedy, may not be the minimum possible"
  }
  ```

### 3.8 Settlements Lifecycle
`POST /groups/{group_id}/settlements`
- **Header:** `Idempotency-Key: <unique_key>` (optional)
- **Body (UPI):**
  ```json
  {
    "from_user": "usr_bob",
    "to_user": "usr_alice",
    "amount": "50.00",
    "method": "UPI"
  }
  ```
- **Response (201 Created):**
  ```json
  {
    "id": "stl_...",
    "group_id": "grp_...",
    "from_user": {"id": "usr_bob", "name": "Bob"},
    "to_user": {"id": "usr_alice", "name": "Alice"},
    "amount": "50.00",
    "status": "PENDING",
    "method": "UPI",
    "reference": "ref_...",
    "upi_link": "upi://pay?pa=alice@okhdfcbank&am=50.00&tr=ref_...&tn=Settlement",
    "created_at": "2026-10-30T10:00:00Z"
  }
  ```

- **Body (CASH Claim):**
  ```json
  {
    "from_user": "usr_bob",
    "to_user": "usr_alice",
    "amount": "50.00",
    "method": "CASH"
  }
  ```
- **Response (201 Created):** status is `"CLAIMED"`.

`POST /groups/{group_id}/settlements/{id}/confirm`
- **Headers:** `Authorization: Bearer <creditor_token>`
- **Response (200 OK):** status updated to `"CONFIRMED"`, ledger entry appended.

`POST /groups/{group_id}/settlements/{id}/reject`
- **Headers:** `Authorization: Bearer <creditor_token>`
- **Response (200 OK):** status updated to `"REJECTED"`, debt capacity freed.

### 3.9 Signed Provider Webhook
`POST /webhooks/mock-provider`
- **Header:** `X-Provider-Signature: kid=<kid>,t=<unix_timestamp>,v1=<hmac_sha256_hex>`
- **Body:**
  ```json
  {
    "event_id": "evt_0190123",
    "reference": "ref_...",
    "status": "SUCCESS",
    "amount": "50.00"
  }
  ```
- **Response (200 OK):** `{"status": "processed"}` (or `{"status": "ignored"}` if already processed).

### 3.10 Tamper-Evident Ledger Verification
`GET /groups/{group_id}/audit/verify`
- **Headers:** `Authorization: Bearer <member_token>`
- **Response (200 OK - Valid):**
  ```json
  {
    "valid": true,
    "entries": 25,
    "head": "9f82d7a...<64-hex>",
    "broken_at": null,
    "reason": null
  }
  ```
- **Response (200 OK - Tampered):**
  ```json
  {
    "valid": false,
    "entries": 25,
    "head": "9f82d7a...",
    "broken_at": 14,
    "reason": "hash_mismatch"
  }
  ```

### 3.11 In-App Notifications Feed
`GET /users/me/notifications?unread=true&limit=20`
- **Response (200 OK):**
  ```json
  {
    "items": [
      {
        "id": "ntf_...",
        "event_type": "SETTLEMENT_CLAIMED",
        "title": "Settlement Claimed",
        "message": "Bob claimed paying ₹50.00 to you.",
        "data": {"settlement_id": "stl_...", "amount_paise": 5000},
        "read_at": null,
        "created_at": "..."
      }
    ],
    "next_cursor": null
  }
  ```

`POST /users/me/notifications/{id}/read`
- **Response (200 OK):** `{"id": "ntf_...", "read_at": "2026-10-30T10:05:00Z"}`

---

## 4. Error Codes Reference

All error responses return HTTP status codes aligned with RFC standards and an error envelope containing `code`, `message`, and `request_id`.

| HTTP Status | Error Code | Description / Trigger Conditions |
|---|---|---|
| `400 Bad Request` | `BAD_REQUEST` | Malformed request syntax or unparseable headers. |
| `401 Unauthorized` | `UNAUTHENTICATED` | Missing, malformed, or invalid Bearer API token. |
| `401 Unauthorized` | `INVALID_SIGNATURE` | Webhook callback signature verification failed. |
| `401 Unauthorized` | `STALE_TIMESTAMP` | Webhook timestamp drift exceeds allowable window ($\pm 300\text{ s}$). |
| `404 Not Found` | `NOT_FOUND` | Specified user or group does not exist (or caller is not a member, preventing group ID enumeration). |
| `409 Conflict` | `ALREADY_MEMBER` | User is already a member of the target group. |
| `409 Conflict` | `VPA_ALREADY_IN_USE` | The requested VPA is already linked to another user account. |
| `413 Payload Too Large` | `PAYLOAD_TOO_LARGE` | Request body exceeds the strict 64 KB cap. |
| `415 Unsupported Media` | `UNSUPPORTED_MEDIA_TYPE` | Non-JSON `Content-Type` on write requests. |
| `422 Unprocessable` | `VALIDATION_ERROR` | Schema validation error (e.g. empty name, negative amount, float amount, > 2 decimals, unrecognized fields). |
| `422 Unprocessable` | `PAYER_NOT_MEMBER` | The `paid_by` user is not a member of the group. |
| `422 Unprocessable` | `PARTICIPANT_NOT_MEMBER` | One or more split participants are not members of the group. |
| `422 Unprocessable` | `SPLITS_MISMATCH` | Exact shares do not sum to total expense amount, or participants mismatch. |
| `422 Unprocessable` | `OVERPAYMENT` | Settlement repayment amount exceeds debtor's allowable debt capacity. |
| `422 Unprocessable` | `INVALID_TRANSITION` | Forbidden settlement state machine transition (e.g. confirming already rejected claim). |
| `422 Unprocessable` | `IDEMPOTENCY_KEY_REUSED` | An `Idempotency-Key` was re-submitted with a differing payload or path. |
| `429 Too Many Requests` | `RATE_LIMITED` | Rate limit threshold exceeded. Response includes `Retry-After` header. |
| `500 Internal Error` | `INTERNAL_SERVER_ERROR` | Sanitized unhandled server error with trace request ID. |
| `503 Unavailable` | `DATABASE_UNAVAILABLE` | Database health probe failed or database connection timeout. |
