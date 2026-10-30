# B6 — Baseline release: docs, seed, Postman, review

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md`, `docs/design/README_DRAFT.md`, the assignment brief in `docs/assignment/`, latest `CHANGELOG.md`. Run `git status`.

**Goal:** a submission that fully meets the brief on its own, before any advanced work.

**Tasks**
1. `scripts/seed_goa_trip.py`: idempotent seed creating Mohit, Rahul, Ankit, group "Goa Trip", dinner ₹1200 (EQUAL) and cab ₹600 paid by Rahul; prints the resulting balances and settle-up.
2. `README.md` from `docs/design/README_DRAFT.md`, updated to what actually exists: setup (Docker and local), architecture, DB design, assumptions, design decisions, enhancement, testing, "With more time". Remove anything not built yet or mark it "planned (advanced)".
3. `docs/API.md` complete: every endpoint, request/response example, error codes table.
4. `postman/expense-sharing.postman_collection.json`: the Goa Trip flow in order, using collection variables for ids.
5. **Requirement audit (heavy — you may use sub-agents):** one sub-agent reads the brief and checks every requirement against the code and tests, producing a table requirement → file/test → status. The main agent fixes gaps. Record the table in REVIEW_NOTES.
6. Run `make lint`, `make test` (report coverage), `docker compose up` from a clean clone.
7. Ask me whether to create a local git tag `baseline-v1`.

**Acceptance gate:** every brief requirement marked met with a test or document link; fresh clone runs in two commands; CI green.

**Finish:** CHANGELOG + REVIEW_NOTES; commit `docs: baseline release docs, seed and postman collection`. Do not push.
