# A4 — Tamper-evident ledger (HMAC hash chain)

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md` (B5, D6), `docs/design/SECURITY_AND_STACK.md` §7, latest `CHANGELOG.md`. Run `git status`. **Ask me before adding key names to `.env.example`.**

**Goal:** any change to recorded money history made outside the application is detectable.

**Design**
- Additive migration: `ledger_entries` + `prev_hash TEXT`, `entry_hash TEXT`, `key_id TEXT`; `groups` + `ledger_head_hash TEXT`.
- `entry_hash = HMAC_SHA256(AUDIT_HMAC_KEY[key_id], prev_hash || "|" || canonical_json(entry))` where `canonical_json` = sorted keys, no spaces, UTF-8, amounts as integer paise, ids as internal ids, timestamp ISO-8601 UTC. Genesis `prev_hash` = 64 zeros.
- Computed inside the same transaction as the entry, while the group row is locked (`ledger.append` from B2), so two writers can never share a `prev_hash`.
- Backfill script for entries created before this phase (one-off, run by me; ask first).
- `GET /groups/{group_id}/audit/verify` (members only) → `{"valid": true, "entries": n, "head": "<hash>"}` or `{"valid": false, "broken_at": <seq>, "reason": "hash_mismatch|seq_gap"}`. Also cross-checks each entry's payload against the referenced expense/settlement row.
- Key rotation: `key_id` stored per entry; verification uses the matching key.

**Why HMAC and not plain SHA-256 (put in `docs/SECURITY.md`):** with plain hashes, anyone with DB write access can edit a row and recompute every later hash. With HMAC the key lives outside the database. Next steps documented: Ed25519 signatures (public verification), periodic external anchoring of the head hash, Merkle trees at very large scale.

**Tests**
- Chain of 50 random entries verifies.
- Direct SQL update of one amount → `broken_at` = that seq.
- Deleted row → `seq_gap`.
- Hash recomputed with the wrong key → mismatch.
- Concurrent appends → consecutive seqs, valid chain.

**Acceptance gate:** tests pass; README demo step "tamper and verify" added.

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(audit): HMAC hash-chained ledger with verification endpoint`. Do not push.

**References**
- Stripe Ledger (immutable money log, verification): https://stripe.dev/blog/ledger-stripe-system-for-tracking-and-validating-money-movement
- Python `hmac`: https://docs.python.org/3/library/hmac.html
- OWASP Logging cheat sheet (log integrity): https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
