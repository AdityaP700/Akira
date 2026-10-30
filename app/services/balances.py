"""Service layer for Balances calculation and Settle-up suggestions."""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.domain.balances import net_balances, pairwise_debts
from app.domain.money import format_paise
from app.domain.settle import simplify
from app.repositories import groups as groups_repo
from app.repositories.models import Expense, ExpenseShare, Group, Settlement, User


def _calculate_group_balances(session: Session, group: Group) -> dict[str, Any]:
    """Internal calculation of group balances and pairwise debts."""
    expenses = list(session.scalars(select(Expense).where(Expense.group_id == group.id)).all())
    shares = list(
        session.scalars(
            select(ExpenseShare)
            .join(Expense, ExpenseShare.expense_id == Expense.id)
            .where(Expense.group_id == group.id)
        ).all()
    )
    settlements = list(
        session.scalars(select(Settlement).where(Settlement.group_id == group.id)).all()
    )

    members = groups_repo.get_members(session, group.id)
    all_user_ids = {m.user_id for m in members}
    for exp in expenses:
        all_user_ids.add(exp.paid_by)
    for sh in shares:
        all_user_ids.add(sh.user_id)
    for stl in settlements:
        all_user_ids.add(stl.from_user)
        all_user_ids.add(stl.to_user)

    users = list(session.scalars(select(User).where(User.id.in_(all_user_ids))).all())
    user_map = {u.id: u for u in users}

    net_map = net_balances(expenses, shares, settlements)
    for uid in all_user_ids:
        net_map.setdefault(uid, 0)

    debts_map = pairwise_debts(expenses, shares, settlements)

    # Format brief's name-keyed balances shape: {Rahul: {owes: {Mohit: "400.00"}}}
    name_balances: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: {"owes": {}})
    for (debtor_id, creditor_id), paise in debts_map.items():
        debtor_name = user_map[debtor_id].name
        creditor_name = user_map[creditor_id].name
        name_balances[debtor_name]["owes"][creditor_name] = format_paise(paise)

    pairs_out = [
        {
            "from": {"id": user_map[d].public_id, "name": user_map[d].name},
            "to": {"id": user_map[c].public_id, "name": user_map[c].name},
            "amount": format_paise(amt),
        }
        for (d, c), amt in sorted(
            debts_map.items(),
            key=lambda x: (user_map[x[0][0]].public_id, user_map[x[0][1]].public_id),
        )
    ]

    net_out = [
        {
            "user": {"id": user_map[uid].public_id, "name": user_map[uid].name},
            "net": format_paise(bal),
        }
        for uid, bal in sorted(net_map.items(), key=lambda x: user_map[x[0]].public_id)
    ]

    return {
        "balances": dict(name_balances),
        "pairs": pairs_out,
        "net": net_out,
    }


def get_group_balances(session: Session, group_public_id: str) -> dict[str, Any]:
    """Retrieve derived balances for a specific group."""
    with session.begin():
        group = groups_repo.get_by_public_id(session, group_public_id)
        if group is None:
            raise NotFoundError(f"Group '{group_public_id}' not found")
        return _calculate_group_balances(session, group)


def get_all_group_balances(session: Session) -> list[dict[str, Any]]:
    """Retrieve derived balances across all groups (brief-compatible)."""
    with session.begin():
        groups = list(session.scalars(select(Group).order_by(Group.id.asc())).all())
        results = []
        for g in groups:
            data = _calculate_group_balances(session, g)
            results.append(
                {
                    "group": {"id": g.public_id, "name": g.name},
                    "balances": data["balances"],
                    "pairs": data["pairs"],
                    "net": data["net"],
                }
            )
        return results


def get_settle_up_suggestions(session: Session, group_public_id: str) -> dict[str, Any]:
    """Greedy debt simplification to suggest minimum transfers."""
    with session.begin():
        group = groups_repo.get_by_public_id(session, group_public_id)
        if group is None:
            raise NotFoundError(f"Group '{group_public_id}' not found")

        expenses = list(session.scalars(select(Expense).where(Expense.group_id == group.id)).all())
        shares = list(
            session.scalars(
                select(ExpenseShare)
                .join(Expense, ExpenseShare.expense_id == Expense.id)
                .where(Expense.group_id == group.id)
            ).all()
        )
        settlements = list(
            session.scalars(select(Settlement).where(Settlement.group_id == group.id)).all()
        )

        members = groups_repo.get_members(session, group.id)
        all_user_ids = {m.user_id for m in members}
        for exp in expenses:
            all_user_ids.add(exp.paid_by)
        for sh in shares:
            all_user_ids.add(sh.user_id)
        for stl in settlements:
            all_user_ids.add(stl.from_user)
            all_user_ids.add(stl.to_user)

        users = list(session.scalars(select(User).where(User.id.in_(all_user_ids))).all())
        user_map = {u.id: u for u in users}

        net_map = net_balances(expenses, shares, settlements)
        for uid in all_user_ids:
            net_map.setdefault(uid, 0)

        transfers = simplify(net_map)

        transfers_out = [
            {
                "from": {"id": user_map[t.from_user].public_id, "name": user_map[t.from_user].name},
                "to": {"id": user_map[t.to_user].public_id, "name": user_map[t.to_user].name},
                "amount": format_paise(t.amount_paise),
            }
            for t in transfers
        ]

        return {
            "transfers": transfers_out,
            "count": len(transfers_out),
            "note": "suggestion only; greedy, may not be the minimum possible",
        }
