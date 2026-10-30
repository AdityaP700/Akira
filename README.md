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
