# A5 — PII protection, splits upgrade, least-privilege database (heavy)

Paste into Antigravity. **Heavy phase: sub-agents allowed** (crypto/key provider; DB roles + migrations; SHARES split + tests), disjoint files, main agent integrates. **Ask me before adding `cryptography` and before editing `.env.example`.**

---

Read `AGENTS.md`, `GUARDRAILS.md` (B, E6, E8), `docs/design/SECURITY_AND_STACK.md` §4 and §6, `docs/design/DESIGN_DEEP_DIVE.md` §4, latest `CHANGELOG.md`. Run `git status`.

**Goal:** a full database dump reveals no usable personal data or credentials, and the application itself cannot rewrite history.

**Tasks**
1. **PII table** (additive migration): `user_pii(user_id PK FK, vpa_ciphertext BYTEA, vpa_nonce BYTEA, vpa_key_id TEXT, vpa_blind_index TEXT UNIQUE)`.
2. **`adapters/keys.py`:** `KeyProvider` protocol (`encryption_key(kid)`, `blind_index_key(kid)`, `current_kid()`), `EnvKeyProvider`. Docstring notes KMS envelope encryption as the production replacement.
3. **Encryption:** AES-256-GCM via `cryptography`, random 96-bit nonce per value, associated data = user public id (binds ciphertext to its owner). Blind index = `HMAC_SHA256(blind_key, normalised_vpa)` for exact-match lookup.
4. **API:** `PUT /users/me/vpa {"vpa":"name@bank"}` (format-validated), responses show only masked `na***@bank`. Settlement UPI links use the decrypted VPA only inside the provider adapter call; never logged, never returned except masked.
5. **SHARES split strategy:** `{"split_type":"SHARES","shares":[{"user_id","weight":2}]}`; distribute by weight, remainder paise by ascending id; registered in the strategy registry (no service changes).
6. **DB roles** (migration + docker init script): `app_owner` runs migrations and owns tables; `app_rw` used by the API with `SELECT, INSERT` on `ledger_entries`, `expense_shares`, `provider_events`, `notifications` (plus `UPDATE` on `notifications.read_at` only), and `SELECT, INSERT, UPDATE` where needed elsewhere; **no `UPDATE`/`DELETE` on append-only tables**. `DATABASE_URL` for the app uses `app_rw`. Document why the app must not own tables.
7. **Docs:** `docs/SECURITY.md` "Data protection" section (what is encrypted, what is not and why — amounts stay plaintext to keep `SUM`, `CHECK` and balances; protected by grants + hash chain), and "Explain only": KMS envelope encryption, per-user data keys + crypto-shredding for erasure, RLS with `FORCE`, TLS `verify-full`, SCRAM, pgaudit.

**Tests**
- Raw DB read of `user_pii` contains no plaintext VPA; decrypt round-trip works; tampered ciphertext or wrong associated data fails.
- Blind index finds by exact VPA; different users can't share a VPA (409).
- With the `app_rw` connection, `UPDATE ledger_entries …` and `DELETE FROM expense_shares …` fail with permission denied.
- SHARES 1000 with weights 2:1:1 → 500/250/250; weights with remainder deterministic.

**Acceptance gate:** tests pass; README updated.

**Finish:** CHANGELOG + REVIEW_NOTES (list sub-agents); commit `feat(privacy): encrypted VPA with blind index, shares split, least-privilege DB role`. Do not push.

**References**
- OWASP Cryptographic Storage cheat sheet (AES-GCM, minimise stored data): https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- PostgreSQL encryption options (why disk encryption isn't enough): https://www.postgresql.org/docs/current/encryption-options.html
- PostgreSQL privileges: https://www.postgresql.org/docs/current/ddl-priv.html
- Blind index pattern: https://github.com/ankane/blind_index
- AWS KMS envelope encryption: https://docs.aws.amazon.com/kms/latest/developerguide/kms-cryptography.html
- Crypto-shredding: https://verraes.net/2019/05/eventsourcing-patterns-throw-away-the-key/
- `cryptography` AEAD (AESGCM): https://cryptography.io/en/latest/hazmat/primitives/aead/
