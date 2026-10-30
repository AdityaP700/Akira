"""Balance calculations and debt netting.

Invariants:
- Sum of net balances across all members in a group is strictly zero.
- Balances reflect expenses, shares, and settlements with status CONFIRMED or SUCCESS.
- Pairwise debts represent net debt between pairs (debtor, creditor).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.settlement_state import EFFECTIVE_SETTLEMENT_STATUSES


@dataclass(frozen=True)
class ExpenseRecord:
    id: int
    paid_by: int
    amount_paise: int


@dataclass(frozen=True)
class ShareRecord:
    expense_id: int
    user_id: int
    owed_paise: int


@dataclass(frozen=True)
class SettlementRecord:
    from_user: int
    to_user: int
    amount_paise: int
    status: str


def _get(obj: Any, key: str) -> Any:
    """Retrieve an attribute or dict item from a record."""
    if isinstance(obj, dict):
        return obj[key]
    return getattr(obj, key)


def net_balances(
    expenses: Sequence[Any],
    shares: Sequence[Any],
    settlements: Sequence[Any],
) -> dict[int, int]:
    """Compute the net balance for each user.

    Formula: paid - owed + settlements_sent - settlements_received.
    Only settlements with status in EFFECTIVE_SETTLEMENT_STATUSES ('CONFIRMED', 'SUCCESS') count.

    Returns:
        Mapping from user_id to net balance in paise
        (positive = is owed money, negative = owes money).
    """
    net: dict[int, int] = defaultdict(int)

    for exp in expenses:
        paid_by = _get(exp, "paid_by")
        amount = _get(exp, "amount_paise")
        net[paid_by] += amount

    for share in shares:
        user_id = _get(share, "user_id")
        owed = _get(share, "owed_paise")
        net[user_id] -= owed

    for stl in settlements:
        status = _get(stl, "status")
        if status in EFFECTIVE_SETTLEMENT_STATUSES:
            from_user = _get(stl, "from_user")
            to_user = _get(stl, "to_user")
            amount = _get(stl, "amount_paise")
            net[from_user] += amount
            net[to_user] -= amount

    return dict(net)


def pairwise_debts(
    expenses: Sequence[Any],
    shares: Sequence[Any],
    settlements: Sequence[Any],
) -> dict[tuple[int, int], int]:
    """Compute pairwise simplified debts (who owes whom).

    Returns:
        Mapping from (debtor_user_id, creditor_user_id) to amount_paise (> 0).
    """
    expense_payers: dict[int, int] = {_get(exp, "id"): _get(exp, "paid_by") for exp in expenses}

    # Directed debt: debt[(debtor, creditor)] = paise
    raw_debts: dict[tuple[int, int], int] = defaultdict(int)

    for share in shares:
        exp_id = _get(share, "expense_id")
        user_id = _get(share, "user_id")
        owed = _get(share, "owed_paise")
        payer = expense_payers.get(exp_id)
        if payer is not None and user_id != payer:
            raw_debts[(user_id, payer)] += owed

    for stl in settlements:
        status = _get(stl, "status")
        if status in EFFECTIVE_SETTLEMENT_STATUSES:
            from_user = _get(stl, "from_user")
            to_user = _get(stl, "to_user")
            amount = _get(stl, "amount_paise")
            raw_debts[(from_user, to_user)] -= amount

    # Collect all distinct pairs (unordered)
    pairs: set[tuple[int, int]] = set()
    for debtor, creditor in raw_debts.keys():
        if debtor != creditor:
            u, v = sorted((debtor, creditor))
            pairs.add((u, v))

    # Net each pair and drop zero balances
    result: dict[tuple[int, int], int] = {}
    for u, v in sorted(pairs):
        # u owes v minus v owes u
        net_uv = raw_debts[(u, v)] - raw_debts[(v, u)]
        if net_uv > 0:
            result[(u, v)] = net_uv
        elif net_uv < 0:
            result[(v, u)] = -net_uv

    return result
