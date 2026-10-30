# B2 — Schema, migrations, repositories

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md` (C, D, E7), `docs/design/PROJECT_PLAN.md` §5, `docs/design/DESIGN_DEEP_DIVE.md` §3–4, latest `CHANGELOG.md`. Run `git status`.

**Goal:** the database is the last line of defence for correctness. Build a schema that is correct for the brief **and** already shaped for advanced phases (so those become additive migrations, not rewrites).

**Tables (first Alembic migration)**

```text
users(id BIGINT PK identity, public_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 100), created_at TIMESTAMPTZ NOT NULL DEFAULT now())
groups(id BIGINT PK, public_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL CHECK (...1..100), ledger_head_seq INT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ)
group_members(group_id FK, user_id FK, joined_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY (group_id, user_id))
expenses(id BIGINT PK, public_id TEXT UNIQUE, group_id FK NOT NULL, paid_by FK NOT NULL, amount_paise BIGINT NOT NULL CHECK (amount_paise > 0 AND amount_paise <= 100000000), description TEXT NOT NULL CHECK (...1..200), split_type TEXT NOT NULL CHECK (split_type IN ('EQUAL','EXACT','SHARES')), created_at TIMESTAMPTZ)
  INDEX (group_id, created_at DESC, id DESC)
expense_shares(expense_id FK ON DELETE RESTRICT, user_id FK, owed_paise BIGINT NOT NULL CHECK (owed_paise >= 0), PRIMARY KEY (expense_id, user_id))
  INDEX (user_id)
settlements(id BIGINT PK, public_id TEXT UNIQUE, group_id FK, from_user FK, to_user FK, amount_paise BIGINT CHECK (> 0), status TEXT NOT NULL DEFAULT 'CONFIRMED' CHECK (status IN ('PENDING','SUCCESS','FAILED','CLAIMED','CONFIRMED','REJECTED')), method TEXT NOT NULL DEFAULT 'OTHER' CHECK (method IN ('UPI','CASH','OTHER')), created_at, CHECK (from_user <> to_user))
  INDEX (group_id, created_at DESC)
ledger_entries(group_id FK, seq INT, entry_type TEXT CHECK (IN ('EXPENSE','SETTLEMENT','REVERSAL')), ref_id BIGINT NOT NULL, payload JSONB NOT NULL, created_at, PRIMARY KEY (group_id, seq))
idempotency_keys(key TEXT, scope TEXT, request_fingerprint TEXT NOT NULL, response_status INT, response_body JSONB, created_at, PRIMARY KEY (scope, key))
```

Notes:
- `status` and `method` exist now with baseline defaults so advanced phases only add behaviour.
- `ledger_entries` is append-only from day one; hash columns arrive in A4 via an additive migration.
- `ON DELETE RESTRICT` everywhere money is involved: history is never cascaded away.
- `public_id` format: prefix + 26-char random/UUIDv7-based string (`usr_`, `grp_`, `exp_`, `stl_`) generated in `core/ids.py`.

**Repositories** (`app/repositories/`): plain functions or small classes taking a `Session`; no commits; typed return values.
- `groups.lock_for_update(session, group_id)` → `SELECT … FOR UPDATE`.
- `ledger.append(session, group_id, entry_type, ref_id, payload)` → reads locked `ledger_head_seq`, inserts `seq+1`, updates head. Must be called only while the group row is locked.
- `idempotency.get(scope, key)`, `idempotency.save(...)`.

**Tests**
- Migration up/down runs on a fresh Postgres.
- DB rejects: `amount_paise = 0`, negative share, duplicate member, settlement from == to, unknown split_type (insert raw SQL in tests to prove the DB, not just the app, refuses).
- `ledger.append` produces consecutive `seq` values.

**Acceptance gate:** `make migrate` on a fresh DB succeeds; tests pass; `docs/SCHEMA.md` written with a table per entity, an ER diagram in Mermaid, and a "why" line per design choice (copy reasoning from PROJECT_PLAN §5).

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(db): schema with shares, settlements, append-only ledger, idempotency`. Do not push.

**References**
- PostgreSQL constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- PostgreSQL explicit locking (`FOR UPDATE`): https://www.postgresql.org/docs/current/explicit-locking.html
- Alembic tutorial: https://alembic.sqlalchemy.org/en/latest/tutorial.html
- Stripe Ledger (immutable, append-only money log): https://stripe.dev/blog/ledger-stripe-system-for-tracking-and-validating-money-movement
