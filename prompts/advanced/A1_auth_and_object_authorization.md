# A1 — Authentication and object-level authorisation (OWASP API1/API2/API5)

Paste into Antigravity. Start only after B6 is committed.

---

Read `AGENTS.md`, `GUARDRAILS.md` (B, E), `docs/design/SECURITY_AND_STACK.md` §2–3, `docs/design/DESIGN_DEEP_DIVE.md` §6, latest `CHANGELOG.md`. Run `git status`.

**Goal:** every caller is identified, and no caller can read or change a group they don't belong to.

**Design**
- `POST /users` now returns `{"user": {...}, "api_token": "<shown once>"}`. Token = `secrets.token_urlsafe(32)`, prefixed `est_` for easy secret scanning. DB stores only `sha256(token)` in `users.token_hash` (additive migration, UNIQUE).
- `Authorization: Bearer <token>` on every route except `POST /users` and `GET /health`. Lookup by hash; compare with `hmac.compare_digest`.
- `POST /users/me/token/rotate` → new token, old hash replaced in one transaction.
- `get_actor()` (seam from B3) now returns the authenticated user or 401 `UNAUTHENTICATED`.
- `security/guards.py::require_member(group_id, actor)` used by every group route. Non-member → **404 `NOT_FOUND`** (does not reveal that the group exists).
- Creating a group makes the creator its first member. Only members can add members.
- `GET /users` returns only users who share a group with the actor (no global user directory).
- `GET /balances` returns only the actor's groups.
- Expense `paid_by` may be any member (organiser records for others); every participant is notified in A3.

**Tests**
- 401 without/with bad token; token from DB dump (the hash) does not authenticate.
- BOLA suite: user X (not in group G) gets 404 on every G route (members, expenses, balances, settle-up, settlements, add member).
- Rotation invalidates the old token.
- Error bodies identical for "group doesn't exist" and "not a member".

**Acceptance gate:** BOLA suite passes for every group-scoped route (parametrised over the route list so new routes can't be forgotten); docs and Postman updated with the auth header.

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(security): bearer tokens and membership authorisation`. Do not push.

**References**
- OWASP API Security Top 10 2023 (API1 BOLA, API2, API5): https://api-security.owasp.org/editions/2023/en/0x11-t10/
- OWASP Authentication cheat sheet (no enumeration): https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- Python `secrets`: https://docs.python.org/3/library/secrets.html
- Python `hmac.compare_digest`: https://docs.python.org/3/library/hmac.html
