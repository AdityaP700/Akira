# B5 — Balances, settle-up suggestions, recorded settlements (the enhancement)

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md` (D), `docs/design/PROJECT_PLAN.md` §6, §7, §11, latest `CHANGELOG.md`. Run `git status`.

**Goal:** answer "who owes whom" exactly as the brief shows, then the enhancement: suggest the fewest transfers and record repayments.

**Endpoints**
- `GET /groups/{group_id}/balances` →
  ```json
  {"balances": {"Rahul": {"owes": {"Mohit": "400.00"}}, "Ankit": {"owes": {"Mohit": "400.00"}}},
   "pairs": [{"from": {"id":"usr_…","name":"Rahul"}, "to": {"id":"usr_…","name":"Mohit"}, "amount":"400.00"}],
   "net": [{"user": {"id","name"}, "net":"800.00"}]}
  ```
  `balances` keeps the brief's name-keyed shape; `pairs` and `net` use ids (names can collide — document it).
- `GET /balances` → `{"groups":[{"group":{"id","name"}, …same body…}]}` (brief-compatible).
- `GET /groups/{group_id}/settle-up` → `{"transfers":[{"from","to","amount"}], "count": n, "note":"suggestion only; greedy, may not be the minimum possible"}`.
- `POST /groups/{group_id}/settlements` → `{"from_user","to_user","amount","method":"CASH|OTHER"}` + `Idempotency-Key`. Baseline stores `status="CONFIRMED"`. One transaction: lock group → both users members → amount ≤ current debt from→to (else 422 `OVERPAYMENT`, documented choice) → insert → ledger entry `SETTLEMENT`.
- `GET /groups/{group_id}/settlements` (paginated).

Balances are computed on read from shares + confirmed settlements (single source of truth). Add the index-backed queries; no balance table in baseline.

**Tests**
- Brief example exact JSON for `balances`.
- Rahul pays Mohit 400 → Rahul disappears from `balances`.
- Overpayment → 422.
- Settle-up: applying the suggested transfers as settlements makes every net zero.
- 6 users with mixed expenses: transfers ≤ 5.
- Σ net = 0 after random expenses + settlements (API-level).

**Acceptance gate:** tests pass; README section "Product enhancement" written (why, problem, design, tradeoffs — copy structure from PROJECT_PLAN §11).

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(balances): balances, settle-up suggestions and recorded settlements`. Do not push.

**References**
- GfG minimum cash flow (greedy): https://www.geeksforgeeks.org/minimize-cash-flow-among-given-set-friends-borrowed-money/
- NP-hardness of minimal settlement: https://ar5iv.labs.arxiv.org/html/1402.6556
- ihatemoney (open-source, has settle suggestions): https://github.com/spiral-project/ihatemoney
- split-pro (BigInt money, derived balances): https://github.com/oss-apps/split-pro
