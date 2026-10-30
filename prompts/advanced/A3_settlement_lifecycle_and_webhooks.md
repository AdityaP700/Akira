# A3 — Settlement payment lifecycle, signed webhooks, notifications (heavy)

Paste into Antigravity. **Heavy phase: you may use sub-agents** (e.g. one for the provider adapter + webhook verification, one for the state machine + tests, one for notifications), each with a disjoint file list; the main agent integrates and commits.

---

Read `AGENTS.md`, `GUARDRAILS.md` (D, E5), `docs/design/SECURITY_AND_STACK.md` §5, `docs/design/DESIGN_DEEP_DIVE.md` §2–3, latest `CHANGELOG.md`. Run `git status`. **Ask me before editing `.env.example` with new key names.**

**Goal:** a settlement is "paid" only when evidence says so. Mirrors how payment APIs work: create intent → provider callback → status-check fallback.

**State machine (`domain/settlement_state.py`)**
```text
UPI:    PENDING → SUCCESS | FAILED            (FAILED is terminal; retry = new settlement)
Manual: CLAIMED → CONFIRMED | REJECTED         (payer claims; receiver decides)
Direct: CONFIRMED                              (receiver records money received)
```
Only forward transitions. Balances count `SUCCESS` and `CONFIRMED` only.

**Rule for manual settlements:** an entry that worsens the creator's own position is trusted immediately (receiver recording "I received ₹400" → `CONFIRMED`). An entry that benefits the creator (payer saying "I paid") is a claim → `CLAIMED`, needs the receiver to confirm.

**Migration (additive):** `settlements` + `reference TEXT UNIQUE`, `created_by BIGINT FK`, `updated_at TIMESTAMPTZ`, `provider_intent JSONB NULL`; new table `provider_events(event_id TEXT PRIMARY KEY, reference TEXT NOT NULL, status TEXT NOT NULL, amount_paise BIGINT NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now())`. Existing baseline settlements keep `status='CONFIRMED'`.

**Adapter (`adapters/payment_provider.py`)**
- `PaymentProvider` protocol: `create_collect(reference, amount_paise, payee_vpa_token) -> ProviderIntent`, `get_status(reference) -> ProviderStatus`.
- `MockProvider`: stores intents in memory/table; `upi_link = "upi://pay?pa=<masked or demo VPA>&am=<rupees>&tr=<reference>&tn=Settlement"`.
- Settlement creation is two phases: (1) transaction: lock group, validate, insert `PENDING` with `reference = stl ref`, commit; (2) call provider outside the transaction; store intent info in a new short transaction.

**Webhook `POST /webhooks/mock-provider`**
- Header `X-Provider-Signature: kid=<id>,t=<unix>,v1=<hex>`; `v1 = HMAC_SHA256(key[kid], f"{t}.{raw_body}")`.
- Verify on the **raw body** before parsing; reject `|now − t| > 300 s`; `hmac.compare_digest`; unknown `kid` → 401.
- Body `{"event_id","reference","status":"SUCCESS|FAILED","amount","occurred_at"}`; amount must match the settlement.
- Insert into `provider_events(event_id PK, …)` first; duplicate → 200 no-op. Then apply transition in the same transaction (lock group). Out-of-order/late events that would move backwards → 200, logged, ignored.
- Dev-only helper `POST /dev/mock-provider/pay/{reference}?outcome=success|failed` that signs and sends the webhook, for demos.

**Fallback:** `POST /groups/{group_id}/settlements/{id}/refresh` → calls `provider.get_status` and applies the same transition logic (for missed callbacks).

**Manual flow endpoints:** `POST …/settlements/{id}/confirm`, `…/reject` (receiver only; others 404).

**Notifications (`notifications` table, additive migration):** written in the same transaction as the event: member added, expense created (to each participant with their share), settlement claimed (to receiver), settlement succeeded/failed/confirmed/rejected. `GET /users/me/notifications?unread=true`, `POST /users/me/notifications/{id}/read`. `Notifier` protocol + `DbNotifier`.

**Tests**
- Happy UPI path: PENDING → webhook SUCCESS → balance updated, notification created.
- Forged signature, wrong kid, stale timestamp, tampered body, amount mismatch → rejected, no state change.
- Duplicate webhook → one transition. SUCCESS then late FAILED → stays SUCCESS.
- Missed webhook → refresh resolves it.
- Payer claim doesn't change balance until receiver confirms; receiver reject → no change; non-receiver confirm → 404.
- Concurrency: two settlements for the same debt in parallel → total never exceeds the debt.

**Acceptance gate:** tests pass; `docs/SECURITY.md` webhook section; Postman has the full lifecycle; README demo steps updated.

**Finish:** CHANGELOG + REVIEW_NOTES (list sub-agents); commit `feat(settlements): payment lifecycle with signed webhooks, fallback and notifications`. Do not push.

**References**
- Stripe webhooks (signature over timestamp + raw body, tolerance, dedupe): https://docs.stripe.com/webhooks
- Razorpay webhook validation (raw body HMAC, event id dedupe, out-of-order events): https://razorpay.com/docs/webhooks/validate-test
- Decentro UPI collections (status callback + "Check Payment Status" fallback): https://docs.decentro.tech/reference/payments_api-collections
- Brandur Leach, atomic phases around foreign calls: https://brandur.org/idempotency-keys
