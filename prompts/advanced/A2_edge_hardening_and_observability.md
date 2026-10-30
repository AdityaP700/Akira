# A2 — Edge hardening, abuse protection, observability (OWASP API3/API4/API6/API8/API9)

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md` (E), `docs/design/SECURITY_AND_STACK.md` §3, latest `CHANGELOG.md`. Run `git status`. **Ask me before adding `slowapi`.**

**Goal:** malicious or malformed traffic is rejected cheaply and visibly, and nothing sensitive leaks through errors or logs.

**Tasks**
1. **Input:** confirm every request model has `extra="forbid"`; reject non-JSON content types with 415; body size cap 64 KB → 413 (middleware, checks `Content-Length` and streamed size); JSON nesting is shallow by schema design.
2. **Rate limits (slowapi):** per token for authenticated routes (e.g. 60/min), per IP for `POST /users` (e.g. 5/min) and settlements (e.g. 10/min). 429 with `Retry-After`. Limits configurable in Settings. Note in README that in-memory limits are per process; production would use a shared store.
3. **Headers on every response:** `X-Content-Type-Options: nosniff`, `Cache-Control: no-store` (API responses carry financial data), `Strict-Transport-Security` (when `APP_ENV=prod`), `Content-Security-Policy: frame-ancestors 'none'`, `Referrer-Policy: no-referrer`. CORS disabled (no browser client yet).
4. **Inventory:** `/docs`, `/redoc`, `/openapi.json` disabled when `APP_ENV=prod`; mock-provider routes (A3) only in dev/test.
5. **Logging:** JSON logs with `request_id`, method, route template (not raw path with ids), status, latency ms, actor public id. Masking filter strips `Authorization`, tokens, signatures, and any VPA/phone pattern. One test captures logs and asserts no token or VPA appears.
6. **Errors:** confirm stack traces never reach responses (test: force an exception → generic 500 with request_id).
7. **Timeouts:** DB statement timeout and pool timeout produce 503 `SERVICE_UNAVAILABLE` (not hangs).

**Tests:** 413, 415, 429 with Retry-After, headers present, `/docs` off in prod mode, log masking, forced-exception response shape.

**Acceptance gate:** tests pass; `docs/SECURITY.md` started with the OWASP API Top 10 table (risk → control → test name).

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(security): input limits, rate limiting, security headers, masked logs`. Do not push.

**References**
- OWASP REST Security cheat sheet (headers, 413/415/429): https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- RFC 6585 (429 Too Many Requests, Retry-After): https://datatracker.ietf.org/doc/html/rfc6585
- OWASP Logging cheat sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- slowapi (note: README says API may change): https://github.com/laurentS/slowapi
