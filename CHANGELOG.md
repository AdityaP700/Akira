# CHANGELOG.md

Append-only. Newest entry at the top. One entry per commit-sized change, including failed attempts.

## Entry format

```markdown
## YYYY-MM-DD HH:MM — <phase id> — <short title>
**Status:** done | partial | failed | blocked
**What changed:** 1–3 bullets
**Why:** 1–2 bullets (link the guardrail or design doc section)
**Not done / failed (and why):** bullets, with how to reproduce a failure
**Tests:** `make test` → N passed, M failed; `make lint` → ok/failed
**Decisions:** assumptions confirmed by the human
**Proposed (not built):** ideas parked for approval
**Commit:** <hash> `<message>`
**Next:** the exact next step
```

---

## 2026-10-30 17:20 — B2 — Database schema, Alembic migrations, repositories
**Status:** done
**What changed:**
- Created Alembic configuration (`alembic.ini`, `alembic/env.py`) and initial migration `001_initial_schema.py` defining users, groups, group_members, expenses, expense_shares, settlements, ledger_entries, and idempotency_keys with strict integrity constraints.
- Implemented SQLAlchemy 2.0 ORM models in `app/repositories/models.py` and repository functions in `app/repositories/` (`users`, `groups`, `expenses`, `settlements`, `ledger`, `idempotency`).
- Implemented `lock_for_update` on groups, monotonic sequential append on ledger entries, and public ID generation in `app/core/ids.py`.
- Documented schema architecture, ER diagram, and design decisions in `docs/SCHEMA.md`.
**Why:**
- Database constraints serve as the final line of defense for financial correctness (PROJECT_PLAN.md §5, GUARDRAILS.md).
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 80 passed, 0 failed (97% total coverage); `make lint` → ok (ruff & mypy clean)
**Decisions:**
- Primary keys use `BIGINT` with SQLite `INTEGER` variant for local/test compatibility.
- `ON DELETE RESTRICT` used across all financial tables to prevent cascading deletion of history.
- `ledger.append` requires caller to hold group row-level lock.
**Proposed (not built):** None.
**Commit:** PENDING `feat(db): schema with shares, settlements, append-only ledger, idempotency`
**Next:** Phase B3 — Users & Groups API (`prompts/baseline/B3_users_groups_api.md`).

## 2026-10-30 17:00 — B1 — Pure domain logic: money, splits, balances, settle-up
**Status:** done
**What changed:**
- Implemented pure money handling in `app/domain/money.py` (strict Decimal parsing, max ₹10,00,000 / 100M paise, 2-decimal formatting, float rejection).
- Implemented split strategy protocols and registry in `app/domain/splits.py` (`EqualSplit` with deterministic ascending user id remainder allocation, `ExactSplit` with strict validation).
- Implemented balance calculations, netting, and greedy debt simplification in `app/domain/balances.py` and `app/domain/settle.py`, plus settlement state transitions in `app/domain/settlement_state.py`.
**Why:**
- Core business logic correctness (PROJECT_PLAN.md §7, GUARDRAILS.md Section D). No database or framework dependencies in `app/domain`.
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 68 passed, 0 failed (100% domain coverage, 96% overall); `make lint` → ok (ruff & mypy strict clean)
**Decisions:**
- Remainder paise in EqualSplit allocated to lowest user_id first (GUARDRAILS M4).
- Pairwise debts net bidirectional debts and drop zero balances.
- Greedy debt simplification produces at most n - 1 transfers with deterministic user ID tie-breaking.
**Proposed (not built):** None.
**Commit:** 98f798a `feat(domain): money, split strategies, balances and settle-up`
**Next:** Phase B2 — Schema and repositories (`prompts/baseline/B2_schema_and_repositories.md`).

## 2026-10-30 15:45 — B0 — Bootstrap service skeleton, Docker, CI, health
**Status:** done
**What changed:**
- Created full project layout per AGENTS.md §4 with placeholder modules, core configuration, and structured logging.
- Implemented `GET /health` checking database connectivity with a 2-second timeout, uniform error handler, and request ID middleware.
- Configured `pyproject.toml`, Dockerfile (multi-stage non-root), docker-compose.yml, Makefile, and GitHub Actions CI workflow with PostgreSQL service.
**Why:**
- Establish production-shaped baseline infrastructure before adding business logic (PROJECT_PLAN.md §4, GUARDRAILS.md).
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 9 passed, 0 failed (92% coverage); `make lint` → ok
**Decisions:**
- Used `Annotated[Session, Depends(get_db)]` for FastAPI route dependencies to satisfy ruff B008 and preserve type annotations.
- In-memory SQLite session override used for unit/API tests locally, while CI provides PostgreSQL 16 service container.
**Proposed (not built):** None.
**Commit:** 8b3eb77 `chore: bootstrap service skeleton, docker, ci`
**Next:** Phase B1 — Domain logic (money parsing, split strategies, balances, settle-up pure calculations).

## 2026-10-30 15:30 — PLAN — Kit created
**Status:** done
**What changed:** AGENTS.md, GUARDRAILS.md, phase prompts B0–B6 and A1–A6, design docs copied to `docs/design/`.
**Why:** baseline first (full brief, extensible), then advanced (security, privacy, lifecycle, audit).
**Decisions:** FastAPI + PostgreSQL 16; integer paise; shares table; opaque public ids from baseline; no UI; mock payment provider only.
**Commit:** 9da5d4e `chore: initial kit, project plan, and phase prompts`
**Next:** human copies the assignment PDF to `docs/assignment/`, then runs prompt B0.
