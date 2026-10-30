# GUARDRAILS.md

These override every other instruction. Changing one needs the human's explicit approval, recorded in `CHANGELOG.md`.

## A. Agent behaviour

| ID | Rule |
|---|---|
| AG1 | One phase at a time. Do not implement features from later phases "while you are there". |
| AG2 | Ask before any action listed in AGENTS.md §8. When unsure, ask. |
| AG3 | Never invent library APIs, Decentro APIs, regulations or benchmark numbers. If unsure, write `UNKNOWN — VERIFY` and ask. |
| AG4 | Never weaken a test to make it pass. Fix the code or explain why the test is wrong and ask. |
| AG5 | Never disable lint, type checks or CI steps to get green. |
| AG6 | Commit after every completed change. **Never push**, never force-push, never rewrite history, never amend commits you did not create in this session. |
| AG7 | Keep the repo runnable after every commit. If interrupted, write the exact next step in `CHANGELOG.md`. |
| AG8 | Sub-agents get disjoint file scopes, never commit, never touch `.env`. |
| AG9 | Report honestly: what was done, not done, failed, and why. |

## B. Secrets and `.env`

| ID | Rule |
|---|---|
| S1 | **Ask the human before creating, reading, editing, copying or printing `.env`**, every time. The human fills values. |
| S2 | Never print, log, echo, paste into chat, or commit a secret. Refer to secrets by variable name only. |
| S3 | `.env.example` lists every variable name with an empty value and a one-line comment. |
| S4 | Settings are read through `app/core/config.py`; no `os.getenv` scattered in code. |
| S5 | Keys carry an id (`AUDIT_KEY_ID`, `WEBHOOK_KEY_ID`, `PII_KEY_ID`) so they can rotate. |
| S6 | Generated keys for local dev are created by the human with a documented command (`python -c "import secrets; print(secrets.token_hex(32))"`); the agent prints the command, not a key. |

Variables (filled progressively): `DATABASE_URL`, `APP_ENV` (dev|test|prod), `AUDIT_HMAC_KEY`, `AUDIT_KEY_ID`, `WEBHOOK_HMAC_KEY`, `WEBHOOK_KEY_ID`, `PII_ENC_KEY`, `PII_BLIND_INDEX_KEY`, `PII_KEY_ID`.

## C. Git: what may change, what may not

| Path | Agent access | Notes |
|---|---|---|
| `docs/assignment/**` | **Read-only** | The brief. Never modify. |
| `AGENTS.md`, `GUARDRAILS.md` | **Read-only** | Human edits only. |
| `docs/design/**` | Read; edit only with approval | Source of design decisions. |
| `alembic/versions/*` already committed | **Read-only** | Never edit an applied migration; add a new one. |
| `CHANGELOG.md`, `REVIEW_NOTES.md` | **Append-only** | Add entries at the top; never delete or rewrite old ones. |
| `.github/workflows/**` | Edit in its phase; later changes need approval | Never remove steps. |
| `app/**`, `tests/**`, `scripts/**`, `docs/API.md`, `docs/SCHEMA.md`, `docs/SECURITY.md`, `README.md` | Read/write | Normal work. |
| `.env`, `*.db`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `htmlcov/`, `*.log`, `.coverage` | **Never commit** | Must be in `.gitignore`. |

**Heavy files:** do not commit files larger than 5 MB, binaries, database dumps, videos or screenshots of more than a few hundred KB. Demo videos go to an external link referenced in README. If a large file is truly needed, ask; Git LFS is used only with approval. Postman collections and small PNG diagrams (< 300 KB) are fine.

## D. Money and correctness

| ID | Rule |
|---|---|
| M1 | Money is integer paise inside the app. No `float` anywhere in money paths (a test greps for it). |
| M2 | Input amounts: string or number with at most 2 decimals, > 0, ≤ a configured max (₹10,00,000). Otherwise 422. |
| M3 | Every expense stores its shares; Σ shares = amount, checked before commit. |
| M4 | Equal-split remainder: leftover paise go one each to participants in ascending internal user id. Deterministic and documented. |
| M5 | For every group, Σ net balances = 0 (tested). |
| M6 | Ledger, shares and provider events are append-only: no UPDATE/DELETE in code; corrections are reversing entries. |
| M7 | One transaction per use case; group row locked first; no external call inside a transaction. |
| M8 | POST endpoints that create money records accept `Idempotency-Key`; same key + same body → original response; same key + different body → 422 `IDEMPOTENCY_KEY_REUSED`. |

## E. Security and privacy

| ID | Rule |
|---|---|
| P1 | Every group-scoped route checks the caller is a member (from phase A1). Non-members get 404, not 403. |
| P2 | Request models use `extra="forbid"`; separate input and output schemas; clients can never set ids, status or timestamps. |
| P3 | Errors use one format and never include stack traces, SQL, or whether another user/group exists. |
| P4 | Never log tokens, keys, signatures, full VPAs or phone numbers. Mask before logging. |
| P5 | Webhooks verified with HMAC over the raw body + timestamp window ±300 s + `hmac.compare_digest` + unique event id. |
| P6 | PII (VPA) encrypted at application level; responses show masked values only. Amounts stay plaintext (documented tradeoff). |
| P7 | Parameterised queries only; no SQL built with f-strings or `%`. |
| P8 | The app's DB role has no UPDATE/DELETE on append-only tables (from phase A5). |
| P9 | `/docs` and mock-provider routes are disabled when `APP_ENV=prod`. |
| P10 | Do not claim legal or regulatory compliance anywhere. Say "designed for data minimisation". |

## F. Scope

Build only what the current phase prompt lists. New feature ideas go to `CHANGELOG.md` under "Proposed" and are built only if the human approves and the feature passes this gate:
1. It improves a graded area (DB design, logic, backend, code quality, enhancement) or a security property.
2. It ships with tests in about an hour.
3. It leaves existing tests and the schema intact (or adds an additive migration).
4. It can be justified in two sentences.
