"""Idempotent seed script creating the Goa Trip dataset.

Users: Mohit, Rahul, Ankit
Group: Goa Trip
Expenses:
1. Dinner ₹1200 paid by Mohit (EQUAL split)
2. Cab ₹600 paid by Rahul (EQUAL split)

Calculates and prints the resulting balances and settle-up recommendations.
"""

import sys

from sqlalchemy import select

from app.api.schemas.expenses import ExpenseIn
from app.core.db import Base, SessionLocal, engine
from app.repositories import groups as groups_repo
from app.repositories import users as users_repo
from app.repositories.models import Expense, Group, User
from app.services import balances as balances_service
from app.services import expenses as expenses_service


def seed() -> None:
    print("=" * 60)
    print("Akira Expense Sharing - Seeding 'Goa Trip' Dataset")
    print("=" * 60)

    Base.metadata.create_all(engine)

    # 1. Idempotently create users: Mohit, Rahul, Ankit
    user_names = ["Mohit", "Rahul", "Ankit"]
    user_ids: dict[str, tuple[int, str]] = {}

    for name in user_names:
        with SessionLocal() as session:
            with session.begin():
                u = session.scalar(select(User).where(User.name == name))
                if u is None:
                    u = users_repo.create(session, name)
                    session.flush()
                    print(f"[+] Created User: {name} ({u.public_id})")
                else:
                    print(f"[*] Found Existing User: {name} ({u.public_id})")
                user_ids[name] = (u.id, u.public_id)

    # 2. Idempotently create group: "Goa Trip"
    with SessionLocal() as session:
        with session.begin():
            group = session.scalar(select(Group).where(Group.name == "Goa Trip"))
            if group is None:
                group = groups_repo.create(session, "Goa Trip")
                session.flush()
                print(f"[+] Created Group: Goa Trip ({group.public_id})")
            else:
                print(f"[*] Found Existing Group: Goa Trip ({group.public_id})")
            group_public_id = group.public_id
            group_id = group.id

    # 3. Add members if not already joined
    for name, (u_id, _) in user_ids.items():
        with SessionLocal() as session:
            with session.begin():
                if not groups_repo.is_member(session, group_id, u_id):
                    groups_repo.add_member(session, group_id, u_id)
                    print(f"[+] Added {name} to Goa Trip")
                else:
                    print(f"[*] {name} already member of Goa Trip")

    # 4. Idempotently add expenses
    with SessionLocal() as session:
        with session.begin():
            existing_expenses = list(
                session.scalars(select(Expense).where(Expense.group_id == group_id)).all()
            )
            existing_descs = {exp.description for exp in existing_expenses}

    # Expense 1: Dinner ₹1200 paid by Mohit (EQUAL)
    if "Dinner at Fisherman's Wharf" not in existing_descs:
        exp1_in = ExpenseIn(
            paid_by=user_ids["Mohit"][1],
            amount="1200",
            description="Dinner at Fisherman's Wharf",
            split_type="EQUAL",
        )
        with SessionLocal() as session:
            data1, _ = expenses_service.create_expense(
                session=session,
                group_public_id=group_public_id,
                payload=exp1_in,
                idempotency_key="seed_expense_dinner_001",
                http_method="POST",
                http_path=f"/groups/{group_public_id}/expenses",
                canonical_body="seed_dinner",
            )
        print(f"[+] Recorded Expense: Dinner Rs.1200 paid by Mohit ({data1['id']})")
    else:
        print("[*] Dinner expense already recorded")

    # Expense 2: Cab ₹600 paid by Rahul (EQUAL)
    if "Cab to Baga Beach" not in existing_descs:
        exp2_in = ExpenseIn(
            paid_by=user_ids["Rahul"][1],
            amount="600",
            description="Cab to Baga Beach",
            split_type="EQUAL",
        )
        with SessionLocal() as session:
            data2, _ = expenses_service.create_expense(
                session=session,
                group_public_id=group_public_id,
                payload=exp2_in,
                idempotency_key="seed_expense_cab_002",
                http_method="POST",
                http_path=f"/groups/{group_public_id}/expenses",
                canonical_body="seed_cab",
            )
        print(f"[+] Recorded Expense: Cab Rs.600 paid by Rahul ({data2['id']})")
    else:
        print("[*] Cab expense already recorded")

    # 5. Fetch derived balances
    with SessionLocal() as session:
        balances = balances_service.get_group_balances(session, group_public_id)

    print("\n" + "-" * 60)
    print("DERIVED BALANCES (Brief Format)")
    print("-" * 60)
    import json

    print(json.dumps(balances["balances"], indent=2))

    print("\n" + "-" * 60)
    print("NET BALANCES PER USER")
    print("-" * 60)
    for net_entry in balances["net"]:
        print(f"  {net_entry['user']['name']}: Rs. {net_entry['net']}")

    # 6. Settle-up suggestions
    with SessionLocal() as session:
        settle_up = balances_service.get_settle_up_suggestions(session, group_public_id)

    print("\n" + "-" * 60)
    print("SETTLE-UP SUGGESTIONS (Greedy Minimal Transfers)")
    print("-" * 60)
    for idx, t in enumerate(settle_up["transfers"], 1):
        print(f"  {idx}. {t['from']['name']} pays {t['to']['name']} Rs. {t['amount']}")

    print("\n[+] Seed completed successfully.\n")


def main() -> None:
    try:
        seed()
    except Exception as exc:
        print(f"Error during seeding: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
