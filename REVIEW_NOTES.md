# REVIEW_NOTES.md

A handoff log for teammates and reviewers, like a pull-request description for every commit. Append-only, newest first. Write it so Person B can review the change without asking Person A anything.

## Entry format

```markdown
## <commit hash> — <phase id> — <title>
**Author:** <person or agent> · **Sub-agents used:** none | <name: scope → deliverable>
**Summary:** what the change does, in 2–3 sentences.
**Files changed:** list with one line each on why.
**Behaviour before → after:** what an API caller now sees differently.
**How to verify:**
1. command(s) to run
2. request(s) to send (curl or Postman item) and the expected response
**Risks / things to look at closely:** e.g. locking order, rounding, error codes.
**Expected follow-up:** next phase or open question.
**Reviewer checklist:**
- [ ] Tests cover the new paths, including failure paths
- [ ] No float in money paths; no secrets in diff
- [ ] Guardrails respected (list any exceptions approved)
- [ ] README / docs updated where behaviour changed
```

---

## 98f798a — B1 — Pure domain logic: money, splits, balances, settle-up
**Author:** Antigravity · **Sub-agents used:** none
**Summary:** Implemented pure business logic without I/O or framework dependencies in `app/domain/`. Includes integer paise parsing and formatting with float prevention, Equal and Exact split strategies with remainder tie-breaking, net balance and pairwise debt computation, and greedy debt simplification.
**Files changed:**
- `app/domain/money.py`: Strict decimal-based rupee parsing into integer paise and two-decimal paise formatting.
- `app/domain/splits.py`: SplitStrategy protocol, EqualSplit (ascending user id remainder), ExactSplit, and strategy registry.
- `app/domain/balances.py`: net_balances and pairwise_debts calculations supporting expense, share, and settlement records.
- `app/domain/settle.py`: Greedy cash flow simplification yielding at most n-1 transfers with deterministic tie-breaking.
- `app/domain/settlement_state.py`: Settlement status constants and state machine transition rules.
- `tests/unit/test_money.py`: Table-driven tests for parsing and formatting, validating rejection of floats, negatives, and invalid decimals.
- `tests/unit/test_splits.py`: Unit tests for EqualSplit and ExactSplit covering edge cases, rounding, and registry lookup.
- `tests/unit/test_balances.py`: Unit tests covering brief's Mohit-Rahul-Ankit scenario, settlement netting, and 200 random expenses property test.
- `tests/unit/test_settle.py`: Unit tests verifying circular debt collapse, tie breaking, and transfer bounds.
- `tests/unit/test_settlement_state.py`: Unit tests for valid and invalid settlement lifecycle transitions.
- `tests/unit/test_no_float.py`: Static inspection test ensuring `float(` is never called in domain or service code.
**Behaviour before → after:**
- Pure domain algorithms are now fully implemented and verified with 100% test coverage, ready for service and repository integration in Phase B2.
**How to verify:**
1. `pytest -q --cov=app` → 68 passed (100% domain coverage, 96% total).
2. `ruff check .`, `ruff format --check .`, and `mypy app/domain app/services` → all pass with 0 errors.
**Risks / things to look at closely:**
- Rounding remains strictly integer paise; sum of shares in EqualSplit and ExactSplit always strictly matches expense amount.
- Grep test enforces absence of float operations in `app/domain` and `app/services`.
**Expected follow-up:**
- Phase B2: Database schema, migrations, and repositories.
**Reviewer checklist:**
- [x] Tests cover the new paths, including failure paths
- [x] No float in money paths; no secrets in diff
- [x] Guardrails respected (list any exceptions approved)
- [x] README / docs updated where behaviour changed

## 8b3eb77 — B0 — Bootstrap service skeleton, Docker, CI, health
**Author:** Antigravity · **Sub-agents used:** none
**Summary:** Established the project directory layout, configuration with environment variable loading and secret masking, structured JSON logging with request tracing, global error handling envelope, and GET /health check. Added Dockerfile, Docker Compose setup, Makefile, and GitHub Actions CI workflow with PostgreSQL 16 container.
**Files changed:**
- `.gitignore`: Ignore virtualenvs, caches, logs, secrets, and SQLite files.
- `.env.example`: Template for environment variables (`DATABASE_URL`, `APP_ENV`).
- `pyproject.toml`: Project metadata, dependencies, ruff, mypy, and pytest configs.
- `app/main.py`: FastAPI application factory with RequestIDMiddleware and route registration.
- `app/core/config.py`: Settings model loading from environment with masked `__repr__`.
- `app/core/db.py`: Engine factory with connect args, timeouts, and session generator.
- `app/core/errors.py`: Global error handlers returning uniform `{"error": {"code", "message", "request_id"}}` structure.
- `app/core/logging.py`: Structured JSON log formatter and RequestIDMiddleware with `X-Request-ID`.
- `app/core/ids.py`: Helper for generating prefixed public IDs.
- `app/api/deps.py`: Database session and actor dependency stubs.
- `app/api/routers/health.py`: `GET /health` endpoint running `SELECT 1` with 2 s timeout.
- `app/api/routers/{users,groups,expenses,balances,settlements}.py`: Route placeholders.
- `app/services/*.py`: Service layer placeholders.
- `app/domain/*.py`: Domain logic placeholders.
- `app/repositories/*.py`: Repository layer placeholders.
- `app/adapters/*.py`: Adapter layer placeholders.
- `app/security/*.py`: Security module placeholders.
- `Dockerfile`: Multi-stage build with `python:3.12-slim` and non-root user.
- `docker-compose.yml`: API + PostgreSQL 16 services with health checks.
- `Makefile`: Targets for up, down, migrate, seed, test, and lint.
- `.github/workflows/ci.yml`: CI pipeline running lint, format check, type check, and pytest against PostgreSQL.
- `tests/api/test_health.py`: Tests for ok health, DB failure, request ID propagation, 404 envelope, validation error, and 500 error handling.
- `scripts/seed_goa_trip.py`: Seed script placeholder.
- `docs/assignment/.gitkeep`: Folder for assignment brief PDF.
- `docs/{API,SCHEMA,SECURITY}.md`: Architecture documentation placeholders.
- `README.md`: Project description and quickstart instructions.
**Behaviour before → after:**
- Initial empty repository now runs a FastAPI application with `GET /health`, uniform error responses, and request tracing.
**How to verify:**
1. Run `pytest -q --cov=app` to verify all 9 tests pass with 92% coverage.
2. Run `ruff check .`, `ruff format --check .`, and `mypy app/domain app/services` to verify static checks pass.
3. Test `GET /health` returns `200 {"status": "ok", "db": "ok"}` with `X-Request-ID`.
**Risks / things to look at closely:**
- Unhandled exceptions correctly return 500 without leaking stack traces or internal details.
- Database credentials in `Settings` are masked when printed or logged.
**Expected follow-up:**
- Phase B1: implement pure domain logic for money handling, split strategies, balances, and settle-up.
**Reviewer checklist:**
- [x] Tests cover the new paths, including failure paths
- [x] No float in money paths; no secrets in diff
- [x] Guardrails respected (list any exceptions approved)
- [x] README / docs updated where behaviour changed
