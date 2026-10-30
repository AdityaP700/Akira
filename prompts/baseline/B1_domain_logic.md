# B1 — Domain logic: money, splits, balances, settle-up (pure, no I/O)

Paste into Antigravity.

---

Read `AGENTS.md`, `GUARDRAILS.md` (section D), `docs/design/PROJECT_PLAN.md` §3 and §7, latest `CHANGELOG.md`. Run `git status`.

**Goal:** all money logic as pure, fully tested functions in `app/domain/`. This is where 30% of the grade (logic) is won. No database, no FastAPI imports.

**Tasks**
1. `domain/money.py`
   - `parse_rupees(value: str | int) -> int` → paise. Accept `"1200"`, `"1200.5"`, `"1200.50"`, `1200`. Reject floats passed as Python `float`, negatives, zero, > 2 decimals, non-numeric, above `MAX_PAISE` (₹10,00,000 = 100_000_000 paise). Use `decimal.Decimal`, never `float`.
   - `format_paise(40050) -> "400.50"`.
2. `domain/splits.py`
   - `SplitStrategy` protocol: `compute(amount_paise: int, participants: list[int], spec: dict | None) -> dict[int, int]`.
   - `EqualSplit`: floor division; remainder paise one each to participants in ascending id (GUARDRAILS M4).
   - `ExactSplit`: spec `{user_id: paise}`; every participant must appear once; Σ must equal amount, else `SplitError("SPLITS_MISMATCH")`.
   - Registry `get_strategy(name)` so new strategies (SHARES in advanced) plug in without touching callers.
3. `domain/balances.py`
   - `net_balances(expenses, shares, settlements) -> dict[int, int]`: paid − owed + settlements sent − settlements received. Only settlements with status in `{"CONFIRMED","SUCCESS"}` count (baseline records them as `CONFIRMED`).
   - `pairwise_debts(...) -> dict[(debtor, creditor), int]`: for each share where user ≠ payer add to `debt[user][payer]`; apply settlements; net each pair; drop zeros. This reproduces the brief's "Rahul owes Mohit ₹400".
4. `domain/settle.py`
   - `simplify(net: dict[int,int]) -> list[Transfer(from, to, paise)]`: greedy, largest creditor vs largest debtor; deterministic tie-break by id; at most n−1 transfers.
5. Tests in `tests/unit/` (no DB):
   - parse/format table tests including every rejection case.
   - Equal: 120000 / 3 → 40000 ×3; 100000 / 3 → 33334, 33333, 33333; 1 / 3 → 1, 0, 0; single participant.
   - Exact: valid; missing participant; extra participant; sum mismatch.
   - Brief example: Mohit pays 1200 among 3 → pairwise `{(Rahul,Mohit):40000,(Ankit,Mohit):40000}`, net Mohit +80000.
   - Settlement Rahul→Mohit 40000 → pair removed.
   - Property-style test: 200 random expenses (seeded RNG) → Σ net = 0 and Σ shares = amount for every expense.
   - simplify: applying returned transfers to net yields all zeros; count ≤ n−1; circular debts collapse.
   - A test that greps `app/domain` and `app/services` for `float(` and fails if found.

**Acceptance gate:** `make test` passes; coverage of `app/domain` ≥ 95%; `mypy` strict clean on `app/domain`.

**Finish:** CHANGELOG + REVIEW_NOTES; commit `feat(domain): money, split strategies, balances and settle-up`. Do not push.

**References**
- Greedy minimum cash flow: https://www.geeksforgeeks.org/minimize-cash-flow-among-given-set-friends-borrowed-money/
- Minimum-transfer debt settlement is NP-hard (why greedy is a suggestion): https://ar5iv.labs.arxiv.org/html/1402.6556
- Splitwise data model (paid_share / owed_share), official SDK: https://pypi.org/project/splitwise/2.0.1/
- Python `decimal`: https://docs.python.org/3/library/decimal.html
