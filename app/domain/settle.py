"""Debt simplification algorithm (greedy minimum cash flow).

Finds a minimal or near-minimal set of transfers (at most n-1) that settles
all net balances in a group.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Transfer:
    from_user: int
    to_user: int
    amount_paise: int


def simplify(net: dict[int, int]) -> list[Transfer]:
    """Greedily simplify net balances into at most n - 1 transfers.

    Args:
        net: Dictionary mapping user_id to net balance in paise.
             Creditors have positive balances; debtors have negative balances.

    Returns:
        List of Transfer objects settling all balances.

    Raises:
        ValueError: If the sum of net balances is not strictly zero.
    """
    total = sum(net.values())
    if total != 0:
        raise ValueError(f"Net balances must sum to zero before simplification, got sum={total}")

    debtors: dict[int, int] = {uid: -bal for uid, bal in net.items() if bal < 0}
    creditors: dict[int, int] = {uid: bal for uid, bal in net.items() if bal > 0}

    transfers: list[Transfer] = []

    while debtors and creditors:
        # Pick largest debtor; tie-break by lowest user_id
        debtor_id = max(debtors.keys(), key=lambda uid: (debtors[uid], -uid))
        # Pick largest creditor; tie-break by lowest user_id
        creditor_id = max(creditors.keys(), key=lambda uid: (creditors[uid], -uid))

        transfer_amt = min(debtors[debtor_id], creditors[creditor_id])
        if transfer_amt > 0:
            transfers.append(
                Transfer(
                    from_user=debtor_id,
                    to_user=creditor_id,
                    amount_paise=transfer_amt,
                )
            )

        debtors[debtor_id] -= transfer_amt
        creditors[creditor_id] -= transfer_amt

        if debtors[debtor_id] == 0:
            del debtors[debtor_id]
        if creditors[creditor_id] == 0:
            del creditors[creditor_id]

    return transfers
