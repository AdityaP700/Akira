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
