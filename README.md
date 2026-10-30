# Akira — Expense Sharing Service

A robust, production-grade backend service for groups to record shared expenses, calculate net balances, and settle debts cleanly.

## Key Features
- **Deterministic Money Handling:** All currency stored as integer paise (no floating point arithmetic).
- **Group Locking & Single Transactions:** Prevents race conditions and double-spending.
- **Auditable & Tamper-Evident:** Hash-chained ledger and signed webhook lifecycles.
- **Secure by Default:** Constant-time verification, strict input schemas, encrypted PII with blind index.

## Quickstart

### Prerequisites
- Python 3.12+
- Docker & Docker Compose
- Make (optional)

### Running Locally
```bash
make up          # Start API and PostgreSQL in Docker
make migrate     # Apply database migrations
make seed        # Populate demo Goa trip dataset
make test        # Run test suite with pytest
make lint        # Run ruff check, format, and mypy
```

## Product Enhancement: Settle-up Suggestions & Recorded Settlements

### 1. Problem
Balances alone tell participants what they owe pairwise, not how to finish settling up efficiently. In a group trip with 6 people, pairwise debts can produce up to \( \frac{n(n-1)}{2} = 15 \) individual transfers. For example, if A owes B, and B owes C, requiring A to pay B and then B to pay C creates unnecessary payment friction, duplicate transaction costs, and delayed settlement.

### 2. Why
Greedy debt simplification collapses circular and multi-hop debts into at most \( n - 1 \) total transfers (e.g. at most 5 transfers for 6 people). It answers the real-world user question: *"What is the minimum number of payments needed to settle all balances?"*

### 3. Design
- **Pure Domain Simplification (`domain/settle.py`):** Implements a greedy minimum-cash-flow algorithm with deterministic tie-breaking (largest debtor and creditor matched first, tie-broken by lowest internal user ID). It operates purely on net balances (`paid - owed + settlements_sent - settlements_received`) and requires no I/O.
- **Read-Only Settle-Up Suggestions (`GET /groups/{group_id}/settle-up`):** Returns the suggested list of transfers with a clear advisory note.
- **Recorded Settlements (`POST /groups/{group_id}/settlements`):** Records actual repayments (CASH or OTHER) within an atomic transaction. Locks the group row (`FOR UPDATE`), validates membership, enforces non-overpayment bounds against current net debt capacity, and appends a `SETTLEMENT` entry to the immutable ledger.
- **Derived Balances:** Balances are computed on-the-fly from shares and confirmed settlements (single source of truth), ensuring zero balance drift.

### 4. Trade-offs
- **Greedy vs. Optimal NP-Hard Minimum:** Finding the strictly minimal number of transactions across arbitrary subset sums is NP-complete (equivalent to the subset-sum problem). The greedy heuristic produces at most \( n - 1 \) transfers in \( O(n \log n) \) time, which is optimal for practical group sizes and guarantees convergence.
- **Trust & Intermediary Matching:** Simplification can suggest a transfer between two individuals who did not directly transact (e.g., A paying C directly instead of B). For this reason, the endpoint provides suggestions while allowing users to settle directly or record custom repayments.
- **Append-Only Immutability:** Settlements cannot be modified or deleted. Corrections are recorded as reversing settlement entries, maintaining a tamper-evident audit trail.

### 5. Payments-Infrastructure Alignment
This mirrors real-world payments clearing and settlement architectures (such as Decentro's Ledgers and split-settlement rails): net balance calculation, idempotent money movement, and tamper-evident reconciliation.
