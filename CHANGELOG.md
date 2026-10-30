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

## 2026-10-30 19:20 — A1 — Authentication and object-level authorisation (OWASP API1/API2/API5)
**Status:** done
**What changed:**
- Added Alembic migration `002_user_token_hash.py` introducing unique `token_hash` VARCHAR(64) on `users`.
- Implemented `app/security/auth.py` for token generation (`est_` prefix + 32-byte URL-safe entropy), constant-time verification with SHA-256 and `hmac.compare_digest`.
- Implemented `app/security/guards.py` (`require_member`, `require_member_and_lock`) enforcing OWASP API1 (BOLA) protections returning 404 `NOT_FOUND` to prevent group ID enumeration.
- Wired FastAPI `get_actor` dependency in `app/api/deps.py` extracting Bearer tokens, expunging actors and closing read transactions for clean use-case isolation.
- Protected all group endpoints and updated services: creator is auto-added as first member, only members can add members, `GET /users` scopes to shared-group users (OWASP API3 data minimisation), `GET /balances` scopes to actor's groups, and added `POST /users/me/token/rotate`.
- Added comprehensive test suite `tests/api/test_auth_and_bola.py` (16 tests verifying 401 unauthenticated, DB hash cannot authenticate, token rotation, creator auto-membership, only members add members, and parametrised BOLA suite across all 8 group routes).
- Updated `scripts/seed_goa_trip.py`, `postman/expense-sharing.postman_collection.json` (19 steps), and `docs/API.md` with Bearer auth headers, token variables, and `UNAUTHENTICATED` error code.
**Why:**
- Implement bank-grade authentication and object-level authorisation preventing OWASP Top 10 API vulnerabilities (API1 BOLA, API2 Broken Authentication, API3 Excessive Data Exposure, API5 Broken Object Property Level Authorisation) per PROJECT_PLAN.md §2-3, GUARDRAILS.md (B, E), and prompts/advanced/A1_auth_and_object_authorization.md.
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 119 passed, 0 failed (94% total coverage, 100% security/guards); `make lint` → ok (ruff & mypy strict clean)
**Decisions:**
- Non-members accessing group routes receive identical 404 `NOT_FOUND` ("Group '{id}' not found") rather than 403 Forbidden to prevent group existence enumeration.
- Dependency `get_actor` expunges actor and issues `session.rollback()` so that service methods can cleanly own their own `with session.begin():` transactions without nested transaction conflicts.
- `UserRegistrationOut` exposes computed fields for `id`, `name`, `created_at` at the root while returning `user` and `api_token` for seamless backwards compatibility.
**Proposed (not built):**
- None.
**Commit:** 981900d `feat(security): bearer tokens and membership authorisation`
**Next:** Phase A2 — Edge hardening, rate limiting, and structured observability (`prompts/advanced/A2_edge_hardening_and_observability.md`).

---

## 2026-10-30 18:20 — B6 — Baseline release: docs, seed, Postman, and requirement audit
**Status:** done
**What changed:**
- Created `scripts/seed_goa_trip.py`: idempotent seed script populating Mohit, Rahul, Ankit, group "Goa Trip", dinner ₹1200 (EQUAL) and cab ₹600 paid by Rahul; outputs brief-compatible balances and settle-up suggestion.
- Created `postman/expense-sharing.postman_collection.json`: 18-step sequential Postman collection demonstrating the full Goa trip lifecycle with collection variables (`mohit_id`, `rahul_id`, `ankit_id`, `group_id`).
- Rewrote `README.md` from `docs/design/README_DRAFT.md` reflecting actual codebase architecture, database models, REST endpoints, design trade-offs, and planned advanced phases.
- Completed `docs/API.md` with Section 4 Error Codes Reference table.
- Conducted exhaustive requirement audit using research subagent (`bb26ccca-9685-415c-824d-e04cb060ecff`) checking every brief requirement and `PROJECT_PLAN.md (§1-§8)` scope: 100% compliant across 10 audited domains.
**Why:**
- Baseline release milestone delivering a self-contained submission that meets all brief specifications before advanced extensions (PROJECT_PLAN.md §1-§8, prompts/baseline/B6_baseline_release.md).
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 103 passed, 0 failed (95% total coverage, 100% money/domain); `make lint` → ok (ruff & mypy strict clean)
**Decisions:**
- Seeding script uses `SessionLocal()` with explicit `with session.begin():` blocks for clean transaction boundaries across SQLite and PostgreSQL.
- Postman collection automatically extracts and propagates opaque IDs between sequential requests.
**Proposed (not built):**
- Git tag `baseline-v1` pending human approval.
**Commit:** 069a907 `docs: baseline release docs, seed and postman collection`
**Next:** Phase A1 — Authentication and group object-level authorization (`prompts/advanced/A1_auth_and_membership.md`).

---

## 2026-10-30 18:00 — B5 — Balances, settle-up suggestions, and recorded settlements
**Status:** done
**What changed:**
- Implemented `get_group_balances`, `get_all_group_balances`, and `get_settle_up_suggestions` in `app/services/balances.py` using derived domain queries (`net_balances`, `pairwise_debts`, `simplify`) with zero stored balance drift.
- Implemented `record_settlement` and `list_settlements` in `app/services/settlements.py` with group row lock (`SELECT ... FOR UPDATE`), overpayment validation against net debt capacity, append-only `SETTLEMENT` ledger entry, and idempotency key persistence.
- Added API endpoints in `app/api/routers/balances.py` (`GET /groups/{id}/balances`, `GET /balances` alias, `GET /groups/{id}/settle-up`) and `app/api/routers/settlements.py` (`POST /groups/{id}/settlements`, `GET /groups/{id}/settlements`).
- Created Pydantic v2 schemas in `app/api/schemas/` (`balances.py`, `settlements.py`) supporting the exact brief name-keyed format and ID-based pairs.
- Added `OverpaymentError` in `app/core/errors.py` (422 `OVERPAYMENT`).
- Documented "Product enhancement" section in `README.md` (problem, why, design, trade-offs, payments-infrastructure alignment).
- Added comprehensive API tests in `tests/api/test_balances_settleup.py` covering exact brief JSON format, repayment, overpayment 422, settle-up zeroing all net balances, 6-user transfer count bound (<= 5), cross-group balances alias, and keyset pagination.
**Why:**
- Deliver core balance calculation and settle-up product enhancement meeting assignment brief and Decentro infrastructure standards (PROJECT_PLAN.md §6, §7, §11, GUARDRAILS.md D).
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 103 passed, 0 failed (95% total coverage, 100% money/domain); `make lint` → ok (ruff & mypy clean)
**Decisions:**
- Overpayment bounds check enforces `amount <= min(-debtor_net, creditor_net)`, allowing both direct settlements and simplified multi-hop transfers while preventing debtor/creditor balance sign flips.
- Brief's name-keyed balances shape is preserved under `balances` while collision-safe opaque public IDs are provided under `pairs` and `net`.
**Proposed (not built):** None.
**Commit:** 54db9a5 `feat(balances): balances, settle-up suggestions and recorded settlements`
**Next:** Phase B6 — Baseline release, seed script, requirement audit (`prompts/baseline/B6_baseline_release.md`).

---

## 2026-10-30 17:50 — B4 — Expenses: atomic, locked, idempotent
**Status:** done
**What changed:**
- Implemented `create_expense` and `list_expenses` in `app/services/expenses.py` with row-level group lock (`SELECT ... FOR UPDATE`), member validations, split strategy execution, append-only ledger entry recording, and idempotency key persistence.
- Implemented API endpoints in `app/api/routers/expenses.py`: `POST /groups/{group_id}/expenses`, `POST /expenses` (brief-compatible alias requiring `group_id` in body), and keyset-paginated `GET /groups/{group_id}/expenses`.
- Created Pydantic v2 schemas in `app/api/schemas/expenses.py` enforcing `extra="forbid"`, string trimming, rupee decimal validation, and structured responses.
- Added error types in `app/core/errors.py`: `PayerNotMemberError` (422 `PAYER_NOT_MEMBER`), `ParticipantNotMemberError` (422 `PARTICIPANT_NOT_MEMBER`), and `IdempotencyKeyReusedError` (422 `IDEMPOTENCY_KEY_REUSED`).
- Added comprehensive API tests in `tests/api/test_expenses.py` covering EQUAL split (400/400/400 and remainder tie-breaking 333.34/333.33/333.33), EXACT split success/mismatch/non-member, invalid amounts, member addition after expense, idempotency replay and conflict detection, single-payer warning, brief alias, crash rollback simulation, and keyset pagination.
- Updated `docs/API.md` with curl examples and response schemas for all expense endpoints.
**Why:**
- Core write path for recording shared expenses with banking-grade atomicity, auditability, and idempotency (PROJECT_PLAN.md §5-§6, DESIGN_DEEP_DIVE.md §3, GUARDRAILS.md D).
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 97 passed, 0 failed (96% total coverage, 100% money/domain); `make lint` → ok (ruff & mypy strict clean)
**Decisions:**
- Idempotency key fingerprint computed as SHA-256 of `METHOD:PATH:CANONICAL_JSON_BODY`.
- Replaying identical request with the same idempotency key returns stored 201 response without duplicate records; differing payload returns 422 `IDEMPOTENCY_KEY_REUSED`.
- Group whose only member is the payer succeeds with 201 and includes `"warning": "NO_OTHER_PARTICIPANTS"`.
- Ledger entry payload contains amounts and integer IDs only (no user names or PII).
**Proposed (not built):** None.
**Commit:** 058546f `feat(expenses): atomic expense creation with shares, ledger and idempotency`
**Next:** Phase B5 — Balances and settle-up API (`prompts/baseline/B5_balances_settleup.md`).

---

## 2026-10-30 17:35 — B3 — Users, groups, and members API
**Status:** done
**What changed:**
- Implemented Pydantic v2 schemas (`extra="forbid"`) for users and groups in `app/api/schemas/` (`users.py`, `groups.py`).
- Built keyset pagination with opaque base64 cursor (`created_at`, internal `id`) in `app/core/pagination.py`.
- Implemented use-case transactions in `app/services/` (`users.py`, `groups.py`) and FastAPI endpoints in `app/api/routers/` (`users.py`, `groups.py`).
- Added specialized application error types (`NotFoundError`, `ConflictError`, `ValidationError`) in `app/core/errors.py`.
- Auth seam stubbed with `get_actor` in `app/api/deps.py` returning `None` for baseline.
- Added API tests in `tests/api/test_users_groups.py` covering creation, validation (empty strings, whitespace-only, extra fields), 404s, 409 duplicate memberships, and multi-page keyset pagination.
- Added REST API documentation in `docs/API.md` with endpoints summary and curl examples.
**Why:**
- Deliver core REST resources meeting assignment brief and project plan (PROJECT_PLAN.md §6, GUARDRAILS.md E2, E3).
**Not done / failed (and why):**
- None.
**Tests:** `make test` → 87 passed, 0 failed (97% total coverage); `make lint` → ok (ruff & mypy clean)
**Decisions:**
- Keyset cursor encodes `(created_at, item_id)` in URL-safe base64.
- All request models strictly forbid extra fields and strip whitespace.
- StaticPool used for SQLite in-memory test fixtures to ensure session connection consistency across request threads.
**Proposed (not built):** None.
**Commit:** c08ff69 `feat(api): users, groups and membership endpoints`
**Next:** Phase B4 — Atomic, locked, idempotent expenses API (`prompts/baseline/B4_expenses_atomic_idempotent.md`).

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
**Commit:** 078ddfc `feat(db): schema with shares, settlements, append-only ledger, idempotency`
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
