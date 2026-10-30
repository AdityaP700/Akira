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
