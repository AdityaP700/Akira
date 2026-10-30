# DESIGN_DEEP_DIVE.md — why each choice, where it comes from, how it grows

Companion to `PROJECT_PLAN.md` and `SECURITY_AND_STACK.md`.

## 1. Language and framework

The brief says **"Preferred: Python"** and lists FastAPI, Flask, Django. The JD says Python and "e.g., Flask". Reviewers will read the code in their own stack, so leaving Python costs more than any framework gain.

| Option | Strength | Why not here |
|---|---|---|
| Go | Fast, strong concurrency, single binary | Outside the brief's preferred language; reviewers expect Python |
| Node.js | Async I/O, huge ecosystem | Outside the brief; JS `Number` is a float, so money needs `BigInt` discipline everywhere |
| Django + DRF | Admin, auth, ORM and migrations included | Heavy for a 10-endpoint API; ORM hides locking details we want to show |
| Flask | Matches the JD; small and explicit | Validation and OpenAPI need plugins (pydantic / flask-smorest) |
| **FastAPI** | Pydantic validation and OpenAPI docs from type hints; async when needed | Not named in the JD (logic is portable: services and repositories don't import FastAPI) |

**Decision:** FastAPI. **Acceptable alternative:** Flask + Pydantic + flask-smorest, if you'd rather mirror the JD; the design below does not change.

## 2. Where the design comes from

| Our design choice | Inspiration | What we copy |
|---|---|---|
| Append-only ledger, corrections as new entries, "nets to zero" checks | Stripe's Ledger: an immutable log of events, double-entry, clearing accounts that should net to zero | Immutability; Σ net = 0 per group as a data-quality check |
| Idempotency keys stored with request fingerprint and response | Stripe API idempotency; Brandur Leach's Postgres design (key scoped per user, params stored to detect reuse, response replayed, keys recycled after ~24h) | Same table shape and rules |
| Separate local transaction from external calls | Brandur's "atomic phases": commit local state before a foreign call; each foreign call in its own phase | Settlement: commit PENDING → call provider → separate transaction on callback |
| Signed webhooks with timestamp and event-id dedupe | Stripe and Razorpay webhook docs | Signature format, ±300 s window, dedupe |
| Status callback + polling fallback | Decentro docs: "Check Payment Status" as an alternative to the terminal status callback | `GET /settlements/{id}/status` |
| Threat list | OWASP API Security Top 10 (2023) | Control per risk |
| Crypto-shredding for erasure | Event-sourcing pattern: per-subject key, delete the key to make data unreadable | Advanced phase (see §4) |

## 3. Atomicity and consistency: how it is guaranteed

1. **One use case = one transaction.** The service layer opens `with session.begin():`. Repositories never commit. Either the expense, its shares, its ledger entry and its notifications all persist, or none do.
2. **One lock, always the same order.** Every write to a group first runs `SELECT … FROM groups WHERE id = :id FOR UPDATE`. Writes to one group are serialised (this also protects the hash chain's `prev_hash`); different groups run in parallel. Locking a single row in a fixed order means no deadlocks.
3. **Isolation level:** PostgreSQL default READ COMMITTED plus the explicit lock above. Alternative: SERIALIZABLE with automatic retry on error `40001`. We pick explicit locking because it is easier to reason about and to test.
4. **Invariants checked before commit:** Σ shares = expense amount; new ledger `seq = head_seq + 1`; settlement status moves forward only. Failure raises and rolls back.
5. **Database as the last line:** `CHECK`, foreign keys, `UNIQUE (idempotency_key)`, `UNIQUE (event_id)`, `PRIMARY KEY (group_id, seq)`. If application code has a bug, the database refuses the bad row.
6. **External calls never inside a transaction.** Create the settlement as PENDING and commit; then talk to the provider; the callback updates it in a new transaction. A crash in between leaves a PENDING row that the status-check fallback can resolve.
7. **Side effects through the database first.** Notifications are rows written in the same transaction (outbox-lite). A worker that pushes them out can be added later without changing write paths.

Tests that prove it: concurrent settlement test (two threads, one succeeds, balance correct); crash simulation (exception after shares insert → no expense row); replay test (same key → same response, one row).

## 4. Privacy upgrades that also scale

| Upgrade | What it does | Phase |
|---|---|---|
| **Opaque public IDs** (`usr_…`, `grp_…`, UUIDv7) in the API, bigint inside | Nobody can guess or enumerate other users or groups by counting ids; pairs with the membership check | Advanced (deviation from the brief's `"id": 1`, documented) |
| **PII in its own table** (`user_pii`: name, encrypted VPA) with stricter grants | Ledger and expenses reference only ids; a query on money tables reveals no personal data | Advanced |
| **Per-user data key (envelope encryption)** | Each user's PII encrypted with their own key; keys encrypted by a master key (KMS later) | Advanced (env master key now) |
| **Crypto-shredding for erasure** | Delete a user's data key → their PII is unreadable everywhere, while the immutable ledger keeps only ids and amounts | Explain (note: whether this alone meets erasure laws is debated) |
| **Key ids + rotation** on every key (audit HMAC, webhook HMAC, VPA encryption) | Rotate without downtime: write with the new key, read with old and new | Advanced |
| **Response minimisation** | Balances and history only for members; names only, never VPAs; masked VPA only to its owner | Baseline (masking) / Advanced (membership) |
| **Separate PII vault service** | Tokenisation service; app stores tokens only | Explain (scale step) |

## 5. Modularity: how features plug in

```text
app/
  api/          routers + request/response schemas (HTTP only)
  services/     use cases: create_expense, settle, verify_audit (transactions live here)
  domain/       pure logic, no I/O: split strategies, balances, simplify, settlement state machine
  repositories/ SQL access per aggregate
  adapters/     interfaces + implementations
                  payment_provider.py   PaymentProvider → MockProvider (later DecentroProvider)
                  keys.py               KeyProvider     → EnvKeyProvider (later KmsKeyProvider)
                  notifier.py           Notifier        → DbNotifier (later push/SMS worker)
  security/     auth tokens, membership guard, webhook signatures, rate limits, masking
  core/         config, logging, error handler, request id
```

| Future change | What changes | What stays untouched |
|---|---|---|
| New split type (percentage) | One `SplitStrategy` class + tests, registered by name | Services, schema, API shape |
| Real Decentro payments | One `PaymentProvider` implementation | Settlement state machine, webhook verification |
| KMS instead of env keys | One `KeyProvider` implementation | Encryption code, ledger code |
| Push / WhatsApp notifications | Worker that reads `notifications` rows | Every write path |
| Flask instead of FastAPI | `api/` layer only | services, domain, repositories |

Rule: `domain/` imports nothing from the web framework or the database; `services/` depend on adapter interfaces, not implementations.

## 6. Onboarding

**Developer onboarding**
- `docker compose up` → Postgres + API; migrations run on start; `/docs` open.
- `make seed` (Goa Trip), `make test`, `make lint`; `.env.example` lists names only.
- CI runs the same commands, so "works on my machine" = "works in CI".

**User onboarding (API)**
- `POST /users` returns the user and an API token **once** (only its hash is stored); `POST /users/me/token/rotate` replaces it.
- Only an existing member can add someone to a group; the added user gets a notification.
- Rate limit on user creation; error messages identical whether or not something exists (no enumeration).
- VPA is optional and validated for format; stored encrypted; shown masked.

## 7. Baseline, then advanced

| Phase | Contents | Submittable on its own? |
|---|---|---|
| **Baseline (v1)** | All brief features; `expense_shares`; integer paise with rounding rule; one transaction per write; idempotency keys; balances (spec format + net); settle-up suggestions; error format; tests incl. Σ = 0; Docker; CI | Yes, meets the full brief |
| **Advanced (v2)** | User tokens + membership guard; opaque public ids; settlement lifecycle (UPI link, signed mock webhook, status fallback, cash claim→confirm); HMAC ledger chain + verify; PII table + VPA encryption + blind index; rate limits; masked JSON logs; notifications; EXACT/SHARES splits; DB roles | Yes, each item lands with tests |
| **Explain only** | KMS, RLS, TLS verify-full, pgaudit, crypto-shredding, PII vault service, outbox worker, read replicas, partitioning, agent payment intents | README + interview |

## Sources

- Stripe Ledger: https://stripe.dev/blog/ledger-stripe-system-for-tracking-and-validating-money-movement
- Brandur Leach, Implementing Stripe-like idempotency keys in Postgres: https://brandur.org/idempotency-keys
- Stripe idempotency: https://docs.stripe.com/idempotency
- Stripe webhooks: https://docs.stripe.com/webhooks
- Razorpay webhook validation: https://razorpay.com/docs/webhooks/validate-test
- Decentro UPI collections docs: https://docs.decentro.tech/reference/payments_api-collections
- OWASP API Security Top 10 (2023): https://api-security.owasp.org/editions/2023/en/0x11-t10/
- Crypto-shredding (Verraes): https://verraes.net/2019/05/eventsourcing-patterns-throw-away-the-key/
- PostgreSQL explicit locking: https://postgresql.org/docs/14/explicit-locking.html
- FastAPI features: https://fastapi.tiangolo.com/features/
