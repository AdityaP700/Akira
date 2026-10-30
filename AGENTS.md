# AGENTS.md — Expense Sharing Service (Decentro SDE Intern)

Read this file at the start of every session, then `GUARDRAILS.md`, the latest entries of `CHANGELOG.md` and `REVIEW_NOTES.md`, the phase prompt you were given, and `git status`. Do not start coding until you have stated the phase goal, the files you will touch, and the acceptance gate.

## 1. What we are building

A backend service for groups to record shared expenses and settle balances. It meets the assignment brief (users, groups, members, expenses, history, balances, one product enhancement) and goes further on what a payments-infrastructure company cares about: **money correctness, atomicity, security, privacy and auditability**.

- Baseline (v1): the full brief done correctly and structured so advanced features plug in without rewrites.
- Advanced (v2): authentication and object-level authorisation, settlement payment lifecycle with signed webhooks, tamper-evident ledger, encrypted PII, abuse protection, observability.

Design references (read before the matching phase): `docs/design/PROJECT_PLAN.md`, `docs/design/SECURITY_AND_STACK.md`, `docs/design/DESIGN_DEEP_DIVE.md`. The assignment PDF lives in `docs/assignment/` and is read-only.

## 2. Stack (do not change without asking)

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Web | FastAPI + Uvicorn |
| DB | PostgreSQL 16 (tests may use a Postgres service container; SQLite is **not** used because it lacks `SELECT … FOR UPDATE`) |
| ORM / migrations | SQLAlchemy 2.0 (typed, `Mapped[]`) + Alembic |
| Validation | Pydantic v2 (`extra="forbid"` on every request model) |
| Crypto | stdlib `hmac`, `hashlib`, `secrets`; `cryptography` (AES-GCM) from phase A5 |
| Rate limiting | slowapi (phase A2) |
| Tests | pytest, httpx, pytest-cov |
| Quality | ruff (lint + format), mypy (strict on `domain/` and `services/`) |
| Runtime | Docker + docker compose |
| CI | GitHub Actions (lint → type check → tests with Postgres service) |

No Redis, queues, Celery, Kafka, microservices, OAuth/JWT libraries, frontend frameworks or new databases unless the human approves in writing.

## 3. Architecture

```text
Request → api/ (routers, schemas) → services/ (use cases, transactions)
                                      ├── domain/ (pure logic, no I/O)
                                      ├── repositories/ (SQL)
                                      └── adapters/ (interfaces: payment provider, keys, notifier)
```

Rules:
1. `domain/` imports nothing from FastAPI, SQLAlchemy or the network. Pure functions and dataclasses only.
2. `services/` own transactions: `with session.begin():` per use case. Repositories never commit.
3. Every write to a group first locks the group row: `SELECT … FROM groups WHERE id = :id FOR UPDATE`. One lock, always first, so no deadlocks.
4. External calls (payment provider) never happen inside a DB transaction.
5. Money is `int` paise everywhere inside the app. Convert at the API edge only (string `"400.00"` in, string out).
6. Services depend on adapter **interfaces** (`PaymentProvider`, `KeyProvider`, `Notifier`), injected via FastAPI dependencies.
7. API resources use opaque public ids (`usr_…`, `grp_…`, `exp_…`, `stl_…`); internal ids are bigint and never leave the service.

## 4. Codebase layout

```text
app/
  main.py                 # app factory, middleware, router registration
  core/
    config.py             # Settings (pydantic-settings), reads env by NAME only
    db.py                 # engine, session factory
    errors.py             # AppError hierarchy + global handlers → {"error":{"code","message","request_id"}}
    logging.py            # JSON logs, request_id, masking filter
    ids.py                # public id encode/decode (prefix + UUIDv7 or random)
  api/
    deps.py               # get_session, get_actor (stub in baseline), providers
    routers/              # users.py, groups.py, expenses.py, balances.py, settlements.py, health.py
    schemas/              # request/response Pydantic models (separate In/Out)
  services/               # users.py, groups.py, expenses.py, balances.py, settlements.py, audit.py
  domain/
    money.py              # parse_rupees("400.50") -> 40050, format_paise(40050) -> "400.50"
    splits.py             # SplitStrategy protocol; Equal, Exact (baseline), Shares (advanced)
    balances.py           # net_balances, pairwise_debts
    settle.py             # simplify(net) -> transfers (greedy)
    settlement_state.py   # allowed transitions (advanced)
  repositories/           # users.py, groups.py, expenses.py, settlements.py, ledger.py, idempotency.py
  adapters/
    payment_provider.py   # PaymentProvider protocol + MockProvider (advanced)
    keys.py               # KeyProvider protocol + EnvKeyProvider (advanced)
    notifier.py           # Notifier protocol + DbNotifier (advanced)
  security/               # auth.py, guards.py, signatures.py, ratelimit.py, masking.py (advanced)
alembic/versions/
tests/
  unit/                   # domain tests (no DB)
  api/                    # endpoint tests (Postgres)
  concurrency/            # parallel writes (advanced)
scripts/seed_goa_trip.py
docs/
  assignment/             # brief PDF (read-only)
  design/                 # design docs (edit only with approval)
  API.md  SCHEMA.md  SECURITY.md
.github/workflows/ci.yml
docker-compose.yml  Dockerfile  Makefile  pyproject.toml  .env.example  .gitignore
AGENTS.md  GUARDRAILS.md  CHANGELOG.md  REVIEW_NOTES.md  README.md
```

## 5. Commands

```bash
make up          # docker compose up --build (API :8000, Postgres :5432)
make migrate     # alembic upgrade head
make seed        # python scripts/seed_goa_trip.py
make test        # pytest -q --cov=app
make lint        # ruff check . && ruff format --check . && mypy app/domain app/services
make down
```

If a command does not exist yet, create it in the Makefile in the phase that needs it.

## 6. Tools

- **Antigravity** runs these prompts. Work one phase prompt at a time.
- **Ponytail** (the human's code-writing tool): use it for writing code if it is configured in this workspace, following its own instructions. I do not know its exact interface; on first use, ask the human how it is invoked rather than guessing.
- **Sub-agents:** for heavy phases (marked "heavy" in the prompt) you may split work into sub-agents with **disjoint file scopes** (for example, one writes tests while another writes the implementation, or one audits security). Rules:
  - The main agent assigns each sub-agent an explicit file list and a deliverable.
  - Sub-agents never commit, never edit `.env`, never touch files outside their list.
  - The main agent reviews, integrates, runs the full test suite, then commits once.
  - Record which sub-agents ran and what each produced in `REVIEW_NOTES.md`.

## 7. Workflow per change

1. Read the files listed at the top of this document. Run `git status`; stop if there are uncommitted changes you did not make, and ask.
2. State: goal, files to touch, acceptance gate, anything needing approval.
3. Implement the smallest change that passes the gate.
4. Run `make lint` and `make test`. Do not mark anything done with failing checks.
5. `git diff --stat` and `git status`; stage only files for this change (`git add <paths>`, never `git add -A` blindly).
6. Append a `CHANGELOG.md` entry and a `REVIEW_NOTES.md` entry (formats inside those files).
7. Commit with a Conventional Commit message (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`). **Commit only. Never push.** Pushing is done by the human.
8. Print: what changed, why, how to verify, what is next.

## 8. Asking the human

Ask before: creating or editing `.env`; `git init`; adding any dependency, service, tool or file type not listed here; deleting files; changing a migration that already exists; changing anything in `docs/design/`, `docs/assignment/`, `AGENTS.md` or `GUARDRAILS.md`; tagging a release; any action outside the repository folder. When something in the brief is ambiguous, propose an assumption and ask before building on it; record the answer in `CHANGELOG.md` under "Decisions".
