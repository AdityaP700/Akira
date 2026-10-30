# API Documentation — Akira Expense Sharing Service

This document provides the OpenAPI-compliant REST API documentation for the Akira Expense Sharing Service.

## 1. Overview & Conventions

- **Base URL:** `http://localhost:8000`
- **Content Type:** `application/json`
- **Monetary amounts:** Formatted as 2-decimal rupee strings (e.g. `"400.00"`). Internal storage is strictly integer paise.
- **Identifiers:** External public resources use opaque IDs with prefix (`usr_`, `grp_`, `exp_`, `stl_`).
- **Request Models:** Enforce `extra="forbid"`. Unrecognized query parameters or JSON fields return `422 Unprocessable Content`.

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

| Method | Path | Request Body | Status | Description |
|---|---|---|---|---|
| `GET` | `/health` | None | 200 / 503 | Database connectivity health check |
| `POST` | `/users` | `{"name": "Mohit"}` | 201 | Register a new user |
| `GET` | `/users` | None (Query: `limit`, `cursor`) | 200 | Keyset paginated user list |
| `POST` | `/groups` | `{"name": "Goa Trip"}` | 201 | Create a new expense group |
| `POST` | `/groups/{group_id}/members` | `{"user_id": "usr_..."}` | 201 | Add a user to a group |
| `GET` | `/groups/{group_id}/members` | None | 200 | List all members in a group |
| `POST` | `/groups/{group_id}/expenses` | `{"paid_by", "amount", "description", "split_type", ...}` | 201 | Atomic expense creation with shares & ledger |
| `POST` | `/expenses` | `{"group_id", "paid_by", "amount", ...}` | 201 | Brief-compatible alias for expense creation |
| `GET` | `/groups/{group_id}/expenses` | None (Query: `limit`, `cursor`) | 200 | Keyset paginated group expenses list |
| `GET` | `/groups/{group_id}/balances` | None | 200 | Derived pairwise and net balances |
| `GET` | `/balances` | None | 200 | Derived balances across all groups |
| `GET` | `/groups/{group_id}/settle-up` | None | 200 | Greedy debt simplification suggestions |
| `POST` | `/groups/{group_id}/settlements` | `{"from_user", "to_user", "amount", "method"}` | 201 | Record repayment with ledger entry |
| `GET` | `/groups/{group_id}/settlements` | None (Query: `limit`, `cursor`) | 200 | Keyset paginated settlements list |

---

## 3. Endpoint Details & Examples

### 3.1 Health Check

```bash
curl -X GET "http://localhost:8000/health" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "status": "ok",
  "db": "ok"
}
```

---

### 3.2 Create User

```bash
curl -X POST "http://localhost:8000/users" \
  -H "Content-Type: application/json" \
  -d '{"name": "Mohit"}'
```

**Response (201 Created):**
```json
{
  "id": "usr_944e8bc1a43d92fb90a218f029",
  "name": "Mohit",
  "created_at": "2026-10-30T10:00:00Z"
}
```

---

### 3.3 List Users (Keyset Paginated)

```bash
curl -X GET "http://localhost:8000/users?limit=20" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "usr_944e8bc1a43d92fb90a218f029",
      "name": "Mohit",
      "created_at": "2026-10-30T10:00:00Z"
    }
  ],
  "next_cursor": "MjAyNi0xMC0zMFQxMDowMDowMHw0Mg=="
}
```

---

### 3.4 Create Group

```bash
curl -X POST "http://localhost:8000/groups" \
  -H "Content-Type: application/json" \
  -d '{"name": "Goa Trip"}'
```

**Response (201 Created):**
```json
{
  "id": "grp_5b8ef1092a48721c40ab21cd83",
  "name": "Goa Trip",
  "created_at": "2026-10-30T10:05:00Z"
}
```

---

### 3.5 Add Member to Group

```bash
curl -X POST "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/members" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "usr_944e8bc1a43d92fb90a218f029"}'
```

**Response (201 Created):**
```json
{
  "group_id": "grp_5b8ef1092a48721c40ab21cd83",
  "user_id": "usr_944e8bc1a43d92fb90a218f029",
  "name": "Mohit",
  "joined_at": "2026-10-30T10:06:00Z"
}
```

---

### 3.6 List Group Members

```bash
curl -X GET "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/members" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
[
  {
    "group_id": "grp_5b8ef1092a48721c40ab21cd83",
    "user_id": "usr_944e8bc1a43d92fb90a218f029",
    "name": "Mohit",
    "joined_at": "2026-10-30T10:06:00Z"
  }
]
```

---

### 3.7 Record Expense in Group

Record an expense with equal or exact shares, append-only ledger entry, and idempotency protection.

```bash
curl -X POST "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/expenses" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: req_expense_001" \
  -d '{
    "paid_by": "usr_944e8bc1a43d92fb90a218f029",
    "amount": "1200",
    "description": "Dinner at Fisherman'\''s Wharf",
    "split_type": "EQUAL"
  }'
```

**Response (201 Created):**
```json
{
  "id": "exp_a1b2c3d4e5f6789012345678",
  "group_id": "grp_5b8ef1092a48721c40ab21cd83",
  "description": "Dinner at Fisherman's Wharf",
  "amount": "1200.00",
  "paid_by": {
    "id": "usr_944e8bc1a43d92fb90a218f029",
    "name": "Mohit"
  },
  "split_type": "EQUAL",
  "created_at": "2026-10-30T10:10:00Z",
  "shares": [
    {
      "user_id": "usr_944e8bc1a43d92fb90a218f029",
      "name": "Mohit",
      "amount": "400.00"
    },
    {
      "user_id": "usr_200779ba9d546100c7ebe1862c",
      "name": "Alice",
      "amount": "400.00"
    },
    {
      "user_id": "usr_311880cb0e657211d8fcf2973d",
      "name": "Bob",
      "amount": "400.00"
    }
  ],
  "warning": null
}
```

---

### 3.8 Record Expense (Brief Alias)

Brief-compatible alias requiring `group_id` in request body.

```bash
curl -X POST "http://localhost:8000/expenses" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: req_alias_001" \
  -d '{
    "group_id": "grp_5b8ef1092a48721c40ab21cd83",
    "paid_by": "usr_944e8bc1a43d92fb90a218f029",
    "amount": "1000",
    "description": "Scuba gear rental",
    "split_type": "EXACT",
    "splits": [
      {"user_id": "usr_944e8bc1a43d92fb90a218f029", "amount": "400.00"},
      {"user_id": "usr_200779ba9d546100c7ebe1862c", "amount": "600.00"}
    ]
  }'
```

**Response (201 Created):**
```json
{
  "id": "exp_f7e6d5c4b3a2109876543210",
  "group_id": "grp_5b8ef1092a48721c40ab21cd83",
  "description": "Scuba gear rental",
  "amount": "1000.00",
  "paid_by": {
    "id": "usr_944e8bc1a43d92fb90a218f029",
    "name": "Mohit"
  },
  "split_type": "EXACT",
  "created_at": "2026-10-30T10:15:00Z",
  "shares": [
    {
      "user_id": "usr_944e8bc1a43d92fb90a218f029",
      "name": "Mohit",
      "amount": "400.00"
    },
    {
      "user_id": "usr_200779ba9d546100c7ebe1862c",
      "name": "Alice",
      "amount": "600.00"
    }
  ],
  "warning": null
}
```

---

### 3.9 List Group Expenses (Keyset Paginated)

```bash
curl -X GET "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/expenses?limit=20" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "exp_f7e6d5c4b3a2109876543210",
      "description": "Scuba gear rental",
      "amount": "1000.00",
      "paid_by": {
        "id": "usr_944e8bc1a43d92fb90a218f029",
        "name": "Mohit"
      },
      "split_type": "EXACT",
      "created_at": "2026-10-30T10:15:00Z"
    }
  ],
  "next_cursor": null
}
```

---

### 3.10 Get Group Balances

Calculates derived pairwise debts (matching the brief's name-keyed dictionary) as well as ID-keyed pairs and user net balances.

```bash
curl -X GET "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/balances" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "balances": {
    "Rahul": {
      "owes": {
        "Mohit": "400.00"
      }
    },
    "Ankit": {
      "owes": {
        "Mohit": "400.00"
      }
    }
  },
  "pairs": [
    {
      "from": {"id": "usr_200779ba9d546100c7ebe1862c", "name": "Rahul"},
      "to": {"id": "usr_944e8bc1a43d92fb90a218f029", "name": "Mohit"},
      "amount": "400.00"
    },
    {
      "from": {"id": "usr_311880cb0e657211d8fcf2973d", "name": "Ankit"},
      "to": {"id": "usr_944e8bc1a43d92fb90a218f029", "name": "Mohit"},
      "amount": "400.00"
    }
  ],
  "net": [
    {
      "user": {"id": "usr_944e8bc1a43d92fb90a218f029", "name": "Mohit"},
      "net": "800.00"
    },
    {
      "user": {"id": "usr_200779ba9d546100c7ebe1862c", "name": "Rahul"},
      "net": "-400.00"
    },
    {
      "user": {"id": "usr_311880cb0e657211d8fcf2973d", "name": "Ankit"},
      "net": "-400.00"
    }
  ]
}
```

---

### 3.11 Get Balances Across All Groups (Brief Alias)

```bash
curl -X GET "http://localhost:8000/balances" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "groups": [
    {
      "group": {
        "id": "grp_5b8ef1092a48721c40ab21cd83",
        "name": "Goa Trip"
      },
      "balances": {
        "Rahul": {"owes": {"Mohit": "400.00"}},
        "Ankit": {"owes": {"Mohit": "400.00"}}
      },
      "pairs": [ ... ],
      "net": [ ... ]
    }
  ]
}
```

---

### 3.12 Settle-up Transfer Suggestions

Greedy minimum cash-flow simplification suggesting at most \( n - 1 \) transfers to zero all group balances.

```bash
curl -X GET "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/settle-up" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "transfers": [
    {
      "from": {"id": "usr_200779ba9d546100c7ebe1862c", "name": "Rahul"},
      "to": {"id": "usr_944e8bc1a43d92fb90a218f029", "name": "Mohit"},
      "amount": "400.00"
    },
    {
      "from": {"id": "usr_311880cb0e657211d8fcf2973d", "name": "Ankit"},
      "to": {"id": "usr_944e8bc1a43d92fb90a218f029", "name": "Mohit"},
      "amount": "400.00"
    }
  ],
  "count": 2,
  "note": "suggestion only; greedy, may not be the minimum possible"
}
```

---

### 3.13 Record Settlement Repayment

Atomically records a debt repayment between two group members. Validates non-overpayment against current net debt capacity, increments ledger, and updates derived balances.

```bash
curl -X POST "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/settlements" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: req_stl_001" \
  -d '{
    "from_user": "usr_200779ba9d546100c7ebe1862c",
    "to_user": "usr_944e8bc1a43d92fb90a218f029",
    "amount": "400.00",
    "method": "CASH"
  }'
```

**Response (201 Created):**
```json
{
  "id": "stl_01948beef2384a7190bda4918e",
  "group_id": "grp_5b8ef1092a48721c40ab21cd83",
  "from_user": {
    "id": "usr_200779ba9d546100c7ebe1862c",
    "name": "Rahul"
  },
  "to_user": {
    "id": "usr_944e8bc1a43d92fb90a218f029",
    "name": "Mohit"
  },
  "amount": "400.00",
  "status": "CONFIRMED",
  "method": "CASH",
  "created_at": "2026-10-30T10:30:00Z"
}
```

---

### 3.14 List Group Settlements (Keyset Paginated)

```bash
curl -X GET "http://localhost:8000/groups/grp_5b8ef1092a48721c40ab21cd83/settlements?limit=20" \
  -H "Accept: application/json"
```

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "stl_01948beef2384a7190bda4918e",
      "group_id": "grp_5b8ef1092a48721c40ab21cd83",
      "from_user": {
        "id": "usr_200779ba9d546100c7ebe1862c",
        "name": "Rahul"
      },
      "to_user": {
        "id": "usr_944e8bc1a43d92fb90a218f029",
        "name": "Mohit"
      },
      "amount": "400.00",
      "status": "CONFIRMED",
      "method": "CASH",
      "created_at": "2026-10-30T10:30:00Z"
    }
  ],
  "next_cursor": null
}
```

---

## 4. Error Codes Reference

All error responses return HTTP status codes aligned with RFC standards and an error envelope containing `code`, `message`, and `request_id`.

| HTTP Status | Error Code | Description / Trigger Conditions |
|---|---|---|
| `400 Bad Request` | `BAD_REQUEST` | Malformed request syntax or unparseable headers. |
| `404 Not Found` | `NOT_FOUND` | Specified user or group does not exist. |
| `409 Conflict` | `ALREADY_MEMBER` | User is already a member of the target group. |
| `422 Unprocessable` | `VALIDATION_ERROR` | Schema validation error (e.g. empty name, negative amount, float amount, > 2 decimals, unrecognized fields). |
| `422 Unprocessable` | `PAYER_NOT_MEMBER` | The `paid_by` user is not a member of the group. |
| `422 Unprocessable` | `PARTICIPANT_NOT_MEMBER` | One or more split participants are not members of the group. |
| `422 Unprocessable` | `SPLITS_MISMATCH` | Exact shares do not sum to total expense amount, or participants mismatch. |
| `422 Unprocessable` | `OVERPAYMENT` | Settlement repayment amount exceeds debtor's net debt capacity. |
| `422 Unprocessable` | `IDEMPOTENCY_KEY_REUSED` | An `Idempotency-Key` was re-submitted with a differing payload or path. |
| `500 Internal Error`| `INTERNAL_SERVER_ERROR` | Unhandled server error (trace logged with request ID). |
| `503 Unavailable` | `DATABASE_UNAVAILABLE` | Database health probe failed or connection timeout. |

