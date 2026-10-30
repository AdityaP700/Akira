# B4 — Expenses: atomic, locked, idempotent

Paste into Antigravity.

---

Read `AGENTS.md` (§3 rules 2–5), `GUARDRAILS.md` (D), `docs/design/DESIGN_DEEP_DIVE.md` §3, latest `CHANGELOG.md`. Run `git status`.

**Goal:** the core write path, done the way payment systems do it.

**Endpoints**
- `POST /groups/{group_id}/expenses` (primary) and `POST /expenses` with `group_id` in body (brief-compatible alias; both call the same service).
  - Body: `{"paid_by":"usr_…","amount":"1200","description":"Dinner","split_type":"EQUAL"}` or `"split_type":"EXACT","splits":[{"user_id":"usr_…","amount":"500"},…]`.
  - Header: optional `Idempotency-Key` (1–64 chars, `[A-Za-z0-9_-]`).
  - 201 → expense with `shares: [{"user_id","name","amount"}]`.
- `GET /groups/{group_id}/expenses?limit=&cursor=` → newest first: `{"items":[{"id","description","amount","paid_by":{"id","name"},"split_type","created_at"}],"next_cursor"}`.

**Service `create_expense` (one transaction, in this order)**
1. If `Idempotency-Key` present: fingerprint = sha256(method + path + canonical JSON body). Existing key with same fingerprint → return stored response (same status/body). Different fingerprint → 422 `IDEMPOTENCY_KEY_REUSED`.
2. `with session.begin():`
   1. Lock the group row (`FOR UPDATE`). 404 if missing.
   2. Validate payer is a member (422 `PAYER_NOT_MEMBER`).
   3. Participants: EQUAL → members at this moment; EXACT → listed users, all must be members (422 `PARTICIPANT_NOT_MEMBER`).
   4. Compute shares with the domain strategy; assert Σ = amount.
   5. Insert expense, shares, ledger entry (`EXPENSE`, payload = amounts and ids only, no names).
   6. Save idempotency record with the response.
3. Return 201.

Edge rules (document in README "Assumptions"):
- Group whose only member is the payer → 201, shares = payer only, response includes `"warning":"NO_OTHER_PARTICIPANTS"`.
- Payer always gets a share row in EQUAL (cancels out in balances).

**Tests**
- Brief example via HTTP reproduces shares 400/400/400.
- 1000 / 3 → 333.34 / 333.33 / 333.33.
- EXACT mismatch → 422; EXACT with non-member → 422.
- amount 0, -5, "abc", "10.001", 10000001 → 422.
- Member added after an expense is absent from its shares and present in the next.
- Same Idempotency-Key + same body twice → identical 201 body, one expense row; same key + different body → 422.
- Crash simulation: monkeypatch the ledger append to raise → no expense or share rows remain.

**Acceptance gate:** all tests pass; `docs/API.md` updated.

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(expenses): atomic expense creation with shares, ledger and idempotency`. Do not push.

**References**
- Stripe idempotent requests: https://docs.stripe.com/idempotency
- Brandur Leach, idempotency keys in Postgres (fingerprint, stored response, atomic phases): https://brandur.org/idempotency-keys
- PostgreSQL row-level locks: https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS
- SQLAlchemy `with_for_update`: https://docs.sqlalchemy.org/en/20/core/selectable.html#sqlalchemy.sql.expression.Select.with_for_update
