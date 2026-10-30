# B0 — Bootstrap: repo, tooling, Docker, CI, health

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md`, `CHANGELOG.md` (latest), `REVIEW_NOTES.md`. Run `git status`.

**Goal:** an empty but production-shaped skeleton that runs in Docker, passes CI, and has the folder layout from AGENTS.md §4. No business logic.

**Before starting, ask me:**
1. Is this already a git repository? (Do not run `git init` without my yes.)
2. May you create `.env` from `.env.example`? (I will fill values myself.)

**Tasks**
1. Create the folder layout from AGENTS.md §4 with empty `__init__.py` files and placeholder modules.
2. `pyproject.toml`: project metadata; dependencies `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `alembic`, `psycopg[binary]`, `pydantic>=2`, `pydantic-settings`; dev deps `pytest`, `pytest-cov`, `httpx`, `ruff`, `mypy`. Pin to current stable versions you can verify on PyPI. Configure ruff (line length 100, rules E,F,I,B,UP,S) and mypy (strict for `app/domain`, `app/services`).
3. `app/core/config.py`: `Settings` with `DATABASE_URL`, `APP_ENV`. Reads env by name. Never logs values.
4. `app/core/db.py`: engine with `pool_pre_ping=True`, `pool_timeout=5`, statement timeout 5 s (via connect args); session factory.
5. `app/core/errors.py`: `AppError(code, message, status)` + handlers for `AppError`, `RequestValidationError` and unhandled exceptions → `{"error": {"code", "message", "request_id"}}`. Unhandled errors return 500 with a generic message; details go to logs only.
6. `app/core/logging.py`: JSON logs; middleware that sets `X-Request-ID` (accept a safe incoming value or generate one) and adds it to every log line and error response.
7. `app/api/routers/health.py`: `GET /health` → runs `SELECT 1` with a 2 s timeout; `200 {"status":"ok","db":"ok"}` or `503 {"status":"degraded","db":"down"}`.
8. `Dockerfile` (python:3.12-slim, non-root user, no dev deps in the final image) and `docker-compose.yml` (api + postgres:16 with healthcheck; api waits for DB health).
9. `Makefile` targets from AGENTS.md §5.
10. `.gitignore` with every path in GUARDRAILS.md §C "Never commit". `.env.example` with `DATABASE_URL=`, `APP_ENV=`.
11. `.github/workflows/ci.yml`: on push and PR → set up Python 3.12 → install → `ruff check` + `ruff format --check` → `mypy` → `pytest` with a `postgres:16` service container.
12. Tests: `tests/api/test_health.py` (ok path; DB-down path by pointing at a bad URL via dependency override).
13. Create `docs/assignment/` and ask me to place the brief PDF there.

**Acceptance gate:** `make up` serves `/health` → ok; `make lint` and `make test` pass locally; CI file is valid YAML.

**Finish:** CHANGELOG + REVIEW_NOTES entries; stage only these files; commit `chore: bootstrap service skeleton, docker, ci`. Do not push.

**References**
- FastAPI features: https://fastapi.tiangolo.com/features/
- SQLAlchemy 2.0 ORM quickstart: https://docs.sqlalchemy.org/en/20/orm/quickstart.html
- PostgreSQL docs (connection settings): https://www.postgresql.org/docs/current/runtime-config-client.html
- OWASP Error Handling cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html
- OWASP Logging cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
