# Akira: Splitting Expenses Without Losing Trust

A backend for groups who share expenses: who paid, who owes, and who should pay whom. Built with **FastAPI**, **PostgreSQL 16**, **SQLAlchemy 2.0** and **Alembic**.

**Why it is built this way.** Moving money is a high-risk operation. A wrong balance, a duplicate payment or a leaked UPI ID costs real money and real trust. So Akira is designed in two layers:

| Layer | What it covers | Goal |
|---|---|---|
| **1. Baseline** | Everything the brief asks for: users, groups, expenses, balances, settle-up | **Reliable:** the numbers are always exactly right, even under retries and parallel requests |
| **2. Security and privacy** | Authentication, access control, payment proof, encryption, tamper detection | **Secure:** only the right people can see or change money, and any change to history is caught |

Both layers are built to **scale** without breaking correctness: locks are per group, so different groups never wait on each other, and all data lives in PostgreSQL rather than in the app process. [Section 3](#3-how-it-is-built-baseline-then-security-and-privacy) shows what each layer contains.

| | |
|---|---|
| **Demo video** | [Watch the walkthrough](https://github.com/user-attachments/assets/4aaf246b-7e02-4f79-b101-af04b22fa543) |
| **Live API** | https://akira-expense-sharing.onrender.com |
| **Interactive docs (Swagger)** | https://akira-expense-sharing.onrender.com/docs |
| **Health check** | https://akira-expense-sharing.onrender.com/health |

> The live service runs on a free tier. If it has been idle, the first request takes about a minute. Payments use a **mock provider**; every response carries `X-Environment: demo-mock-payments`.

---

## Contents

1. [At a glance](#1-at-a-glance)
2. [The Goa trip example](#2-the-goa-trip-example)
3. [How it is built: baseline, then security and privacy](#3-how-it-is-built-baseline-then-security-and-privacy)
4. [Architecture](#4-architecture)
5. [API design](#5-api-design)
6. [Database design](#6-database-design)
7. [Correct: getting the arithmetic right](#7-correct-getting-the-arithmetic-right)
8. [Protected: the security model](#8-protected-the-security-model)
9. [Provable: detecting changes to history](#9-provable-detecting-changes-to-history)
10. [Design decisions and alternatives](#10-design-decisions-and-alternatives)
11. [Verified walkthrough](#11-verified-walkthrough)
12. [Run it locally](#12-run-it-locally)
13. [Tests](#13-tests)
14. [Deployment](#14-deployment)
15. [Known limits and next steps](#15-known-limits-and-next-steps)
16. [References](#references)

---

## 1. At a glance

- **Exact money.** Amounts are integer paise. ₹1,000 ÷ 3 = ₹333.34 + ₹333.33 + ₹333.33, never ₹999.99.
- **History that doesn't shift.** Each expense stores who shared it at that moment, so a late joiner never inherits old bills.
- **No duplicates, no overpayment.** Idempotency keys stop double taps; a row lock per group stops two payments racing each other.
- **Smart settle-up (product enhancement).** Turns many pairwise debts into the fewest payments.
- **Only members see a group.** Bearer tokens stored as hashes, and a membership check on every group route. Outsiders get `404`.
- **"I paid" isn't enough.** UPI settlements complete only on a signed provider callback; cash needs the receiver to confirm.
- **Private UPI IDs.** Encrypted with AES-256-GCM, shown masked (`mo***@okhdfcbank`).
- **Tamper-evident.** Every money event is HMAC hash-chained, and `audit/verify` reports any change. The app's database role cannot `UPDATE` or `DELETE` history.
- **Tested on real Postgres.** 193 tests, 93% coverage, including parallel-write tests on separate connections.

---

## 2. The Goa trip example

This example is used throughout the README, the tests and the demo.

Mohit pays ₹1,200 for dinner. Rahul pays ₹600 for a cab. Ankit pays nothing.

```text
Pairwise:  Rahul owes Mohit ₹200 · Ankit owes Mohit ₹400 · Ankit owes Rahul ₹200   (3 payments)
Net:       Mohit +₹600 · Rahul ₹0 · Ankit −₹600                                    (sums to ₹0)
Settle-up: Ankit pays Mohit ₹600                                                    (1 payment)
```

```mermaid
flowchart LR
    subgraph Before["Pairwise: 3 payments"]
        R1["Rahul"] -- "₹200" --> M1["Mohit"]
        A1["Ankit"] -- "₹400" --> M1
        A1 -- "₹200" --> R1
    end
    subgraph After["Settle-up: 1 payment"]
        A2["Ankit"] -- "₹600" --> M2["Mohit"]
    end
```

---

## 3. How it is built: baseline, then security and privacy

**The starting question.** In a money app, the hard part is not the arithmetic. It is whether people can trust the numbers. Before designing anything, I wrote down seven ways a shared ledger goes wrong. The baseline handles the first four; the security and privacy layer handles the rest.

| Case | What goes wrong | Handled by |
|---|---|---|
| The missing paisa | ₹1,000 ÷ 3 rounds to ₹999.99 | Baseline |
| The late joiner | A new member inherits a dinner he never ate | Baseline |
| The double tap | A retry records the cab twice | Baseline |
| The two phones | Two parallel payments both succeed against one debt | Baseline |
| The "I already paid" | Someone marks a debt paid without paying | Security and privacy |
| The leaked backup | A database dump exposes everyone's UPI ID | Security and privacy |
| The quiet edit | Someone with database access changes an amount | Security and privacy |

### Layer 1: Baseline (the brief, built to be reliable)

Built and tagged first, so the brief was never at risk.

| What it adds | Why |
|---|---|
| Users, groups, members, expenses, balances | Everything the brief asks for |
| Integer paise and deterministic rounding | Money never loses a paisa |
| Frozen shares per expense | History doesn't change when members join |
| Balances derived from history | No stored copy that can drift |
| A lock per group and idempotency keys | Parallel requests and retries can't corrupt or duplicate data |
| Settle-up suggestions (product enhancement) | The fewest payments to clear a group |

### Layer 2: Security and privacy (built on top)

Each step answers one attacker. Details in [section 8](#8-protected-the-security-model) and [section 9](#9-provable-detecting-changes-to-history).

| Step | What it adds | Stops |
|---|---|---|
| A1 | Bearer tokens (stored hashed) and a membership check on every group route | Outsiders reading or changing a group |
| A2 | Input limits, rate limits, security headers, masked logs | Junk traffic, floods, data leaking through logs |
| A3 | Settlement lifecycle with signed provider webhooks; cash needs the receiver to confirm | "I already paid" without paying |
| A4 | HMAC hash-chained ledger with `audit/verify` | Silent edits to history |
| A5 | Encrypted UPI IDs and a database role that can't update or delete history | Leaked backups, history rewrites through the app |
| A6 | Concurrency tests on real Postgres, threat model, demo | Claims that aren't proven |

Every step is logged in [`CHANGELOG.md`](CHANGELOG.md).

---

## 4. Architecture

The code is split into layers. Each layer has one job, and inner layers never import outer ones.

```mermaid
flowchart TD
    API["api<br/>HTTP routes and schemas"] --> SVC["services<br/>one use case, one transaction"]
    SEC["security<br/>tokens, membership, limits, encryption"] -.-> API
    SVC --> DOM["domain<br/>pure money logic"]
    SVC --> REPO["repositories<br/>SQL access"]
    SVC --> ADP["adapters<br/>payment provider, keys, notifier"]
```

```text
app/
├── api/           routers and request/response schemas
├── services/      use cases; each owns exactly one transaction
├── domain/        pure money logic: splits, balances, settle-up, settlement states
├── repositories/  SQL access; never commits on its own
├── adapters/      payment provider, key provider, notifier (swappable)
├── security/      tokens, membership guard, rate limits, encryption, signatures
└── core/          config, errors, logging, public ids, pagination
```

**Three rules hold it together:**

1. **`domain/` knows nothing about HTTP or databases.** Money, split and settle-up logic are plain Python functions. That is why they are tested without a database and have 100% coverage.
2. **A service owns the transaction.** Each write use case opens one transaction, takes the group lock, does its work and commits. Repositories never commit, so a half-finished write can't happen.
3. **Anything outside Akira sits behind an interface.** The payment provider, the key store and the notifier are protocols with one implementation each today.

**What modularity buys in practice:**

| If we need to… | We change… |
|---|---|
| Use a real UPI provider instead of the mock | One new class in `adapters/` |
| Keep keys in AWS KMS instead of environment variables | One new `KeyProvider` |
| Add a percentage split | One class and one registry line in `domain/splits.py` |
| Send notifications by email | One new `Notifier` |

The `SHARES` split (weights like 2:1:1) was added late in the project exactly this way, without touching existing split or balance code.

---

## 5. API design

Akira exposes 25 routes, grouped by resource. The brief's suggested routes are all supported; the extra routes come from authentication, the settlement lifecycle and auditing.

| Resource | Routes | Purpose |
|---|---|---|
| Health | `GET /health` | Liveness and database check |
| Users | `POST /users`, `GET /users`, `GET /users/me`, `PUT /users/me/vpa`, `POST /users/me/token/rotate` | Sign up (token shown once), profile, UPI ID, token rotation |
| Notifications | `GET /users/me/notifications`, `POST /users/me/notifications/{id}/read` | In-app activity feed |
| Groups | `POST /groups`, `POST /groups/{id}/members`, `GET /groups/{id}/members` | Create a group, add and list members |
| Expenses | `POST /groups/{id}/expenses`, `POST /expenses`, `GET /groups/{id}/expenses` | Record and list expenses (`EQUAL`, `EXACT`, `SHARES`) |
| Balances | `GET /groups/{id}/balances`, `GET /balances`, `GET /groups/{id}/settle-up` | Who owes whom, and the fewest payments to settle |
| Settlements | `POST /groups/{id}/settlements`, `GET /groups/{id}/settlements`, `POST …/{sid}/confirm`, `POST …/{sid}/reject`, `POST …/{sid}/refresh` | Pay back by UPI or cash, confirm cash, check provider status |
| Audit | `GET /groups/{id}/audit/verify` | Check the hash chain for tampering |
| Payment provider | `POST /webhooks/mock-provider`, `POST /dev/mock-provider/pay/{reference}` | Signed provider callback; demo-only payment simulator |

**Design principles:**

| Principle | What it means here | Why |
|---|---|---|
| Resources nest under the group | `/groups/{id}/expenses`, not `/expenses?group=…` | Every group route runs the same membership check |
| Opaque ids | `usr_…`, `grp_…`, `exp_…`, `stl_…` | Sequential ids can be counted and guessed |
| Money as strings | `"1200.00"` in and out | No client ever parses money as a float |
| One error shape | `{"error": {"code", "message", "request_id"}}` | Clients branch on `code`; `request_id` links to logs |
| Safe retries | `Idempotency-Key` header on writes | A network retry can't create a second expense |
| Keyset pagination | Opaque cursor on list routes | Stable pages even while new rows arrive |
| `404` for non-members | Not `403` | A `403` would confirm the group exists |

Full request and response examples: [`docs/API.md`](docs/API.md).

**Where the API differs from the brief, and why:**

| Brief | Akira | Why |
|---|---|---|
| Integer ids (`"id": 1`) | Opaque ids (`usr_…`, `grp_…`) | Sequential ids can be guessed and enumerated |
| No authentication | Bearer token on group routes | Otherwise anyone can read or change any group's debts |
| `GET /users` lists everyone | Only users who share a group with you | Avoids exposing a full user directory |
| Add member with `group_id` in body | `POST /groups/{id}/members` | Resource in the path; one less mismatch case |
| `POST /expenses` | Kept, plus `POST /groups/{id}/expenses` | Nested route makes the membership check uniform |
| Name-keyed balances | Name-keyed (as in the brief) plus id-keyed `net` | Names can collide; ids can't |

---

## 6. Database design

```mermaid
flowchart LR
    U["users"] --> GM["group_members"]
    G["groups"] --> GM
    G --> E["expenses"]
    U -- "paid_by" --> E
    E --> ES["expense_shares"]
    U --> ES
    G --> S["settlements"]
    G --> L["ledger_entries"]
    U --> P["user_pii"]
    S -.-> PE["provider_events"]
```

| Table | Holds | The app's role (`app_rw`) can |
|---|---|---|
| `users`, `user_pii` | Users, token hashes, encrypted UPI ids | read, insert, update |
| `groups`, `group_members` | Groups (the lock target) and membership | read, insert, update |
| `expenses` | Amounts in paise, split type | read, insert, update |
| `expense_shares` | Frozen per-person shares | **read, insert only** |
| `settlements` | Repayments and their status | read, insert, update |
| `ledger_entries` | Hash-chained audit log | **read, insert only** |
| `provider_events` | Webhook dedupe log | **read, insert only** |
| `idempotency_keys`, `notifications` | Replay cache, in-app notifications | read, insert, update |

**The decisions that matter most:**

- **`expense_shares` is the key addition to the brief's schema.** It records what each person owed at the moment of the expense. Without it, shares would be recomputed from the current member list, and a late joiner would change history. The same table makes `EXACT` and `SHARES` splits possible without schema changes.
- **There is no balances table.** Balances are computed from expenses, shares and completed settlements. A stored balance is a second copy of the truth, and copies drift.
- **Amounts are `BIGINT` paise with `CHECK (amount > 0)`.** The database rejects bad data even if application validation is skipped.
- **Foreign keys use `ON DELETE RESTRICT`.** A user with expenses can't be deleted and take their history with them.
- **The groups row is the lock.** Every write locks one row, so writes in one group queue up while different groups run in parallel.

Column-level detail: [`docs/SCHEMA.md`](docs/SCHEMA.md).

---

## 7. Correct: getting the arithmetic right

| Problem | How Akira solves it | Guarantee |
|---|---|---|
| Float errors | Integer paise everywhere; a test fails the build if a float appears in money code | No rounding drift |
| Uneven division | Leftover paise go one each to participants in a fixed order | Shares always add up to the amount |
| Late joiners | Shares frozen in `expense_shares` | Past expenses never change |
| Balance drift | Balances derived from history | Net balances always sum to zero |
| Two parallel writes | `SELECT … FROM groups WHERE id = :id FOR UPDATE` | One writer per group at a time |
| Network retries | `Idempotency-Key` with a stored response | A retry returns the same response, no duplicate |
| Overpayment | Pending payments reserve their amount against the debt | Two parallel payments can't both succeed |

**Product enhancement: settle-up.** `GET /groups/{id}/settle-up` repeatedly matches the person who owes the most with the person who is owed the most. That gives at most n − 1 payments.

- **Why this feature:** at the end of every trip someone asks "so who pays whom?" Pairwise debts in a group of six can mean 15 transfers.
- **Trade-off:** the truly minimal answer is NP-hard. Greedy is fast, deterministic, and good at the size of a friend group.
- **Design:** a pure function in `app/domain/settle.py`. It suggests; actual repayments go through `POST /groups/{id}/settlements`, which blocks overpayment.

---

## 8. Protected: the security model

Every protection is aimed at a specific attacker, and each one is backed by a live check or an automated test.

| If someone… | What stops it | Proof |
|---|---|---|
| Changes a group id in the URL | Membership check on every group route; outsiders get `404` (OWASP API1) | Walkthrough 10 |
| Calls the API without logging in | Bearer token required; stored as a SHA-256 hash, compared in constant time, rotatable | Walkthrough 1, 2 |
| Sends junk or oversized input | 64 KB cap (`413`), JSON only (`415`), unknown fields rejected (`422`), rate limits (`429` + `Retry-After`) | Walkthrough 5, automated suite |
| Spoofs `X-Forwarded-For` to dodge rate limits | Client IP read from the right, skipping `TRUSTED_PROXY_HOPS` | Automated suite |
| Double-taps "pay", or pays from two devices | Group row lock plus the pending reservation | 10 parallel settlements: 1 succeeds, 9 rejected |
| Fakes or replays a "payment received" callback | HMAC-SHA256 over timestamp and raw body, 300-second window, unique event id | Walkthrough 13, automated suite |
| Steals a database dump | Only token hashes stored; UPI IDs encrypted with AES-256-GCM | Walkthrough 11 |

**Settlements need proof, not a claim.** Only `SUCCESS` and `CONFIRMED` change balances.

```mermaid
flowchart LR
    subgraph UPI["UPI: the provider decides"]
        P["PENDING"] -- "signed webhook: paid" --> S["SUCCESS"]
        P -- "signed webhook: failed" --> F["FAILED"]
    end
    subgraph Cash["Cash: the receiver decides"]
        C["CLAIMED"] -- "receiver confirms" --> OK["CONFIRMED"]
        C -- "receiver rejects" --> X["REJECTED"]
    end
```

The provider is called outside the database transaction, so a slow provider never holds a lock. If a callback is missed, `…/refresh` asks the provider directly.

**Encrypted UPI IDs.** AES-256-GCM with a random nonce, and the user's public id bound in as associated data so a ciphertext copied into another row won't decrypt. Because each encryption is different, uniqueness is enforced with a **blind index**: a keyed HMAC of the normalised UPI ID. A plain hash would not work here, because UPI IDs are easy to guess and could be brute-forced.

Full OWASP API Top 10 mapping and STRIDE threat model: [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 9. Provable: detecting changes to history

Sections 7 and 8 protect against people coming through the API. This section covers people who don't: someone with database access, or a bug that writes where it shouldn't.

| Layer | How | What it does |
|---|---|---|
| Least-privilege role | The API connects as `app_rw`, with no `UPDATE` or `DELETE` on history tables | **Prevents** changes through the app, even under SQL injection |
| HMAC hash chain | `hash_n = HMAC(key, hash_{n-1} ‖ entry_n)`, written under the group lock | **Detects** any edited, inserted or deleted entry |
| Key separation | The HMAC key lives in the app's environment, not the database | A database-only attacker can't forge valid hashes |

`GET /groups/{id}/audit/verify` recomputes the chain and checks each entry against the row it describes:

```json
{"valid": true,  "entries_checked": 2}
{"valid": false, "broken_at": 1, "reason": "hash_mismatch"}
```

**Why HMAC and not plain SHA-256?** Anyone who can edit a row can also recompute a plain SHA-256 chain. HMAC needs a key the database doesn't hold. Digital signatures (Ed25519) would let an outside auditor verify with a public key; that becomes the better choice once a third party needs to check the books.

---

## 10. Design decisions and alternatives

| Decision | Alternative considered | Why this one |
|---|---|---|
| Integer paise | `FLOAT` or `DECIMAL` | Floats lose paise; integers are exact and fast |
| `expense_shares` snapshot | Recompute shares from current members | History must not change when membership does |
| Derived balances | A stored balances table | One source of truth, no drift |
| Pessimistic group lock | Optimistic locking with retries | Money writes in one group are rare enough to queue; retries add client complexity |
| Opaque random tokens checked in the database | JWT | A stolen JWT stays valid until expiry; a database token can be revoked instantly |
| `404` for non-members | `403` | `403` confirms the group exists |
| Signed webhooks | Polling the provider | Webhooks are instant and cheap; polling is kept only as the `refresh` fallback |
| HMAC hash chain | Plain SHA-256 chain, or a blockchain | SHA-256 can be recomputed by an attacker; a blockchain is far heavier than needed |
| AES-256-GCM | AES-CBC | GCM also detects tampering with the ciphertext |
| Greedy settle-up | Exact minimum transfers | Exact is NP-hard; greedy is fast and deterministic |
| In-process rate limiter | Redis | No extra service for a single process; Redis once there are replicas |

---

## 11. Verified walkthrough

Every scenario below was run against the live deployment. Run them yourself at [`/docs`](https://akira-expense-sharing.onrender.com/docs):

1. Create users with `POST /users`, one request per user. Save each user's `id` and `api_token`; the token is shown only once.
2. Click **Authorize** and paste a user's token (without the word "Bearer") to act as that user.
3. Use a **new `Idempotency-Key`** for every new write, unless the step says to repeat one.

| # | Scenario | Act as | Steps | Result | Screenshot |
|---|---|---|---|---|---|
| 1 | One-time token | None | `POST /users`, then `GET /users/me` | Token appears at signup only; `/users/me` has none | [<img src="assets/screenshots/test-1.jpg" width="95%" />](assets/screenshots/test-1.jpg) |
| 2 | Token required | None | Any authenticated route without a token | `401 UNAUTHENTICATED`, consistent error body, security headers present | [<img src="assets/screenshots/test-2.jpg" width="95%" />](assets/screenshots/test-2.jpg) |
| 3 | Group and members | Mohit | Create "Goa Trip", add Rahul and Ankit, add Rahul again | `201`, `201`, then `409 ALREADY_MEMBER` | [<img src="assets/screenshots/test3-1.jpg" width="48%" />](assets/screenshots/test3-1.jpg) [<img src="assets/screenshots/test3-2.jpg" width="48%" />](assets/screenshots/test3-2.jpg) |
| 4 | Idempotent expense | Mohit | Dinner ₹1200 `EQUAL` with key `dinner-1`; repeat; repeat with ₹1300 | Same expense id twice; then `422 IDEMPOTENCY_KEY_REUSED` | [<img src="assets/screenshots/test4.jpg" width="95%" />](assets/screenshots/test4.jpg) |
| 5 | Input validation | Mohit | Amount `"0"`, `"10.001"`, or an unknown field | `422` each time | [<img src="assets/screenshots/test5-1.jpg" width="31%" />](assets/screenshots/test5-1.jpg) [<img src="assets/screenshots/test5-2.jpg" width="31%" />](assets/screenshots/test5-2.jpg) [<img src="assets/screenshots/test5-3.jpg" width="31%" />](assets/screenshots/test5-3.jpg) |
| 6 | Paise rounding | Mohit | New group of 3, ₹1000 `EQUAL` | Shares 333.34 / 333.33 / 333.33 | [<img src="assets/screenshots/test6.jpg" width="95%" />](assets/screenshots/test6.jpg) |
| 7 | Any member can record | Rahul | Cab ₹600 in Goa Trip | `201` | [<img src="assets/screenshots/test7.jpg" width="95%" />](assets/screenshots/test7.jpg) |
| 8 | Balances | Mohit | `GET /groups/{id}/balances` | Pairwise debts as in the example; net sums to 0 | [<img src="assets/screenshots/test8.jpg" width="95%" />](assets/screenshots/test8.jpg) |
| 9 | Settle-up | Mohit | `GET /groups/{id}/settle-up` | One transfer: Ankit to Mohit ₹600 | [<img src="assets/screenshots/test9.jpg" width="95%" />](assets/screenshots/test9.jpg) |
| 10 | Outsider blocked | Zara (not a member) | Goa Trip balances | `404`, not `403`: the group's existence isn't revealed | [<img src="assets/screenshots/test10.jpg" width="95%" />](assets/screenshots/test10.jpg) |
| 11 | Encrypted UPI ID | Mohit, then Rahul | `PUT /users/me/vpa`; Rahul tries the same VPA | Masked `mo***@okhdfcbank`; Rahul gets `409` | [<img src="assets/screenshots/upi-lifecycle-test11.jpg" width="95%" />](assets/screenshots/upi-lifecycle-test11.jpg) |
| 12 | Overpayment blocked | Ankit | Settle ₹700 against a ₹600 debt | `422 OVERPAYMENT` | [<img src="assets/screenshots/upi-lifecycle-test12-1.jpg" width="48%" />](assets/screenshots/upi-lifecycle-test12-1.jpg) [<img src="assets/screenshots/test-12b.jpg" width="48%" />](assets/screenshots/test-12b.jpg) |
| 13 | UPI lifecycle | Ankit | Settle ₹600 by UPI to get `PENDING`; trigger `POST /dev/mock-provider/pay/{reference}` with `outcome=success`; trigger it again | `SUCCESS` once; the repeat changes nothing; balances clear | [<img src="assets/screenshots/upi-lifecycle-test-combined.jpg" width="31%" />](assets/screenshots/upi-lifecycle-test-combined.jpg) [<img src="assets/screenshots/test-ignored.jpg" width="31%" />](assets/screenshots/test-ignored.jpg) [<img src="assets/screenshots/test-ankit_ka_loan_khatam.jpg" width="31%" />](assets/screenshots/test-ankit_ka_loan_khatam.jpg) |
| 14 | Cash needs confirmation | Ankit, then Mohit | Cash settlement gives `CLAIMED`; check balances; Mohit confirms | Balance unchanged until `CONFIRMED` | [<img src="assets/screenshots/upi-lifecycle-test14.jpg" width="48%" />](assets/screenshots/upi-lifecycle-test14.jpg) [<img src="assets/screenshots/upi-lifecycle-test14-2.jpg" width="48%" />](assets/screenshots/upi-lifecycle-test14-2.jpg) |
| 15 | Notifications | Mohit | `GET /users/me/notifications` | Expense and settlement events, written in the same transaction | [<img src="assets/screenshots/test13-notification.jpg" width="95%" />](assets/screenshots/test13-notification.jpg) |
| 16 | Audit chain | Mohit | `GET /groups/{id}/audit/verify` | `valid: true` | [<img src="assets/screenshots/test-15-audit.jpg" width="95%" />](assets/screenshots/test-15-audit.jpg) |

Rate limiting, the database-role test and the tamper test are covered by the automated suite (see [Tests](#13-tests)).

---

## 12. Run it locally

```bash
git clone https://github.com/AdityaP700/Akira.git && cd Akira
cp .env.example .env          # fill LOCAL_DB_PASSWORD and the keys (comments explain each)
python -c "import secrets; print(secrets.token_hex(32))"   # generate a key; one per variable
docker compose up --build
```

The API runs on `http://localhost:8000`, with docs on `/docs`. Seed the Goa trip with `python scripts/seed_goa_trip.py`. A Postman collection is in `postman/expense-sharing.postman_collection.json`; set `base_url` to local or live.

---

## 13. Tests

193 tests run against **PostgreSQL 16**, never SQLite. SQLite ignores `SELECT … FOR UPDATE`, which would make the locking tests meaningless, so the test setup refuses to start without Postgres. Money logic has 100% coverage; overall coverage is 93%.

| Proven on Postgres | Result |
|---|---|
| 20 parallel expenses in one group | Ledger sequence 1 to 20, valid hash chain, net sums to 0 |
| 10 parallel settlements against one ₹50 debt | Exactly 1 succeeds, 9 get `422 OVERPAYMENT` |
| Parallel requests with one idempotency key | One record; every caller gets the same response |
| `UPDATE` / `DELETE` on history as `app_rw` | `permission denied` from PostgreSQL |
| Edited ledger row | `audit/verify` returns `valid: false` with the broken entry |
| Database down | `/health` and writes return `503`; no partial writes |

```bash
make test   # pytest with coverage against TEST_DATABASE_URL
make lint   # ruff + mypy
```

---

## 14. Deployment

- **App:** Docker web service on Render (`render.yaml`), Singapore region. `scripts/start.sh` runs migrations, then starts the API with one worker.
- **Database:** Neon PostgreSQL 16 over TLS, with two roles created by `scripts/init_db_roles.sql`. Passwords are passed as `psql` variables and never stored in the repo.
- **Secrets:** set only in the Render dashboard. Every key has an id so it can be rotated.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Runtime connection as `app_rw` |
| `MIGRATION_DATABASE_URL` | Migrations as `app_owner` |
| `APP_ENV` | `demo` (docs and mock payments) or `prod` |
| `WEBHOOK_HMAC_KEY`, `AUDIT_HMAC_KEY`, `PII_ENC_KEY`, `PII_BLIND_INDEX_KEY` | 32-byte hex keys |
| `WEBHOOK_KEY_ID`, `AUDIT_KEY_ID`, `PII_KEY_ID` | Key ids for rotation |
| `TRUSTED_PROXY_HOPS` | Proxy hops to skip when reading the client IP |

---

## 15. Known limits and next steps

**What Akira does not protect against:**

- **A compromised app server.** Keys live in environment variables, so whoever controls the host can read them.
- **Tampering nobody checks for.** `audit/verify` runs on request, not on a schedule.
- **Spending visibility in a leak.** Amounts are stored in plaintext so the database can enforce `CHECK` constraints and sum balances.
- **Multiple replicas.** Rate limits are per process; replicas would need a shared store.
- **Real money movement.** The payment provider is a mock, with real signing and state handling.

**What I would build next:**

- Double-entry postings, so the database itself enforces that money is conserved.
- Scheduled audit checks, with each day's chain head stored outside the system.
- KMS-managed, per-user encryption keys, so deleting a key makes that user's data unreadable.
- PostgreSQL Row-Level Security, so group isolation is also enforced by the database.

---

---

## References

The ideas behind the design, and where each one is used.

| Idea | Used in | Source |
|---|---|---|
| Idempotency keys | Safe retries on every write | [Stripe: Idempotent requests](https://docs.stripe.com/api/idempotent_requests) |
| Signed webhooks with timestamp (`t=…,v1=…`) | Payment callbacks | [Stripe: Webhook signatures](https://docs.stripe.com/webhooks#verify-events) |
| Object-level authorization, input and rate limits | Membership checks, edge limits | [OWASP API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) |
| `404` instead of `403` for private resources | Non-member access | GitHub's handling of private repositories |
| Debt simplification | Settle-up | Splitwise's "simplify debts" feature |
| Append-only ledger, corrections as new entries | `ledger_entries`, database roles | Standard accounting practice |
| Hash-chained, tamper-evident logs | Audit chain | [Certificate Transparency (RFC 6962)](https://datatracker.ietf.org/doc/html/rfc6962) |
| Blind indexes for encrypted fields | UPI ID uniqueness | [Paragon Initiative: CipherSweet](https://ciphersweet.paragonie.com/) |
| Ports and adapters | Code layout, swappable providers | Alistair Cockburn, hexagonal architecture |
| Double-entry ledgers for engineers | Next steps | [Modern Treasury: Accounting for Developers](https://www.moderntreasury.com/journal/accounting-for-developers-part-i) |
| UPI payment lifecycle | Settlement states | Payment infrastructure providers such as Decentro |

---

Change history: [`CHANGELOG.md`](CHANGELOG.md) · Reviewer notes: [`REVIEW_NOTES.md`](REVIEW_NOTES.md)