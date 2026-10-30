# A6 — Reliability proofs, threat model, final submission (heavy)

Paste into Antigravity. **Heavy phase: sub-agents allowed** — one as an independent reviewer that has not seen the implementation conversation (reads the brief, code and docs, reports gaps), one for test additions. The main agent fixes and commits.

---

Read `AGENTS.md`, `GUARDRAILS.md`, all of `docs/`, latest `CHANGELOG.md` and `REVIEW_NOTES.md`. Run `git status`.

**Goal:** prove the claims in the README with tests, document the threat model, and produce the final submission.

**Tasks**
1. **Reliability proofs** (`tests/concurrency/`, `tests/api/`):
   - 20 parallel expense creations in one group → consecutive ledger seqs, valid hash chain, Σ net = 0.
   - Parallel settlements against one debt → never overpaid.
   - Idempotent replay under parallel identical requests → one row.
   - DB unavailable → `/health` 503 and writes 503 with no partial rows.
2. **`docs/SECURITY.md` threat model** (STRIDE-style table: spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege) for these assets: tokens, ledger, VPAs, webhook endpoint, database. Each row: threat → control → test or "explain only". Include:
   - **Network attacks:** TLS termination at a reverse proxy/load balancer with HSTS (explain); DB only on the private Docker network; no DB port published in prod compose profile.
   - **Phishing / stolen tokens:** tokens are revocable via rotation, prefixed for secret scanning, never logged; future: short-lived tokens + device binding.
   - **Malicious payloads / malware uploads:** no file uploads exist; JSON size and schema limits; unknown fields rejected.
   - **Forged or replayed provider callbacks:** HMAC, timestamp window, event-id dedupe.
   - **Insider with DB access:** HMAC chain detects edits; VPA encrypted; app role cannot UPDATE/DELETE history.
   - **Agent-initiated payments (future):** payment intents with fixed payee/amount/expiry, signed requests with nonce, limits requiring human approval.
3. **Independent review:** reviewer sub-agent produces "requirement → evidence" and "claim in README → test" tables; every unsupported claim is either backed by a test or removed.
4. **Final docs:** README (setup, architecture diagram, schema, assumptions, decisions, enhancement, security summary linking SECURITY.md, demo script, "With more time"), `docs/API.md`, `docs/SCHEMA.md` (all migrations reflected), Postman collection covering the full demo, `DEMO.md` with a 4-minute script: Goa Trip → balances → settle-up → UPI settlement + signed webhook → duplicate webhook ignored → cash claim/confirm → tamper + verify → BOLA attempt 404.
5. `make lint`, `make test` (report coverage), clean-clone `docker compose up`.
6. Ask me whether to tag `v2-advanced`.

**Acceptance gate:** every README claim maps to a test or is labelled "explain only"; CI green; reviewer table attached to REVIEW_NOTES.

**Finish:** CHANGELOG + REVIEW_NOTES; commit `docs: threat model, reliability proofs and final submission docs`. Do not push.

**References**
- OWASP API Security Top 10 2023: https://api-security.owasp.org/editions/2023/en/0x11-t10/
- Microsoft STRIDE threat modeling: https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats
- PostgreSQL SSL modes (verify-full): https://www.postgresql.org/docs/current/libpq-ssl.html
- OWASP Secrets Management cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
