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

## 2026-10-30 15:30 — PLAN — Kit created
**Status:** done
**What changed:** AGENTS.md, GUARDRAILS.md, phase prompts B0–B6 and A1–A6, design docs copied to `docs/design/`.
**Why:** baseline first (full brief, extensible), then advanced (security, privacy, lifecycle, audit).
**Decisions:** FastAPI + PostgreSQL 16; integer paise; shares table; opaque public ids from baseline; no UI; mock payment provider only.
**Next:** human copies the assignment PDF to `docs/assignment/`, then runs prompt B0.
