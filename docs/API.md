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
