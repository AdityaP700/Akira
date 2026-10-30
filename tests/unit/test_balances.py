"""Unit tests for net balances and pairwise debts."""

import random

from app.domain.balances import (
    ExpenseRecord,
    SettlementRecord,
    ShareRecord,
    net_balances,
    pairwise_debts,
)
from app.domain.splits import EqualSplit


def test_brief_example_mohit_rahul_ankit() -> None:
    # Mohit (1) pays 1200 (120000 paise) among Mohit (1), Rahul (2), Ankit (3)
    exp = ExpenseRecord(id=1, paid_by=1, amount_paise=120000)
    shares = [
        ShareRecord(expense_id=1, user_id=1, owed_paise=40000),
        ShareRecord(expense_id=1, user_id=2, owed_paise=40000),
        ShareRecord(expense_id=1, user_id=3, owed_paise=40000),
    ]

    net = net_balances([exp], shares, [])
    assert net == {1: 80000, 2: -40000, 3: -40000}
    assert sum(net.values()) == 0

    debts = pairwise_debts([exp], shares, [])
    # Rahul (2) owes Mohit (1) 40000, Ankit (3) owes Mohit (1) 40000
    assert debts == {(2, 1): 40000, (3, 1): 40000}

    # Now Rahul settles 40000 with Mohit (CONFIRMED)
    settlement = SettlementRecord(from_user=2, to_user=1, amount_paise=40000, status="CONFIRMED")

    net_after_settle = net_balances([exp], shares, [settlement])
    assert net_after_settle == {1: 40000, 2: 0, 3: -40000}
    assert sum(net_after_settle.values()) == 0

    debts_after_settle = pairwise_debts([exp], shares, [settlement])
    # Pair (2, 1) is removed; only Ankit owes Mohit remains
    assert debts_after_settle == {(3, 1): 40000}


def test_settlements_pending_or_failed_ignored() -> None:
    exp = ExpenseRecord(id=1, paid_by=1, amount_paise=10000)
    shares = [
        ShareRecord(expense_id=1, user_id=1, owed_paise=5000),
        ShareRecord(expense_id=1, user_id=2, owed_paise=5000),
    ]

    pending_stl = SettlementRecord(from_user=2, to_user=1, amount_paise=5000, status="PENDING")
    failed_stl = SettlementRecord(from_user=2, to_user=1, amount_paise=5000, status="FAILED")

    net = net_balances([exp], shares, [pending_stl, failed_stl])
    assert net == {1: 5000, 2: -5000}

    debts = pairwise_debts([exp], shares, [pending_stl, failed_stl])
    assert debts == {(2, 1): 5000}


def test_property_200_random_expenses_sum_to_zero() -> None:
    rng = random.Random(42)  # noqa: S311
    users = list(range(1, 11))  # 10 users
    equal_split = EqualSplit()

    all_expenses: list[ExpenseRecord] = []
    all_shares: list[ShareRecord] = []

    for exp_id in range(1, 201):
        payer = rng.choice(users)
        amount_paise = rng.randint(100, 500_000)  # ₹1 to ₹5000
        # Random subset of participants (at least 2)
        k = rng.randint(2, len(users))
        participants = rng.sample(users, k)

        computed_shares = equal_split.compute(amount_paise, participants)
        # Invariant: sum of shares == amount_paise
        assert sum(computed_shares.values()) == amount_paise

        all_expenses.append(ExpenseRecord(id=exp_id, paid_by=payer, amount_paise=amount_paise))
        for uid, share_amt in computed_shares.items():
            all_shares.append(ShareRecord(expense_id=exp_id, user_id=uid, owed_paise=share_amt))

    # Invariant: sum of net balances == 0
    net = net_balances(all_expenses, all_shares, [])
    assert sum(net.values()) == 0


def test_dict_inputs_and_reverse_pair_debts() -> None:
    # Use dicts instead of dataclasses to test dict accessor
    # User 2 pays 10000 for User 1 and User 2 -> User 1 owes User 2
    # In pair (1, 2) with 1 < 2: debt[(1, 2)] is 5000, so net_uv > 0
    # Next, User 1 pays 20000 for User 1 and User 2 -> User 2 owes User 1 10000
    # Overall User 2 owes User 1 5000: so for pair (1, 2), debt[(2, 1)] = 10000, debt[(1, 2)] = 5000
    # net_uv = 5000 - 10000 = -5000 < 0 -> result[(2, 1)] = 5000!
    expenses = [
        {"id": 1, "paid_by": 1, "amount_paise": 20000},
        {"id": 2, "paid_by": 2, "amount_paise": 10000},
    ]
    shares = [
        {"expense_id": 1, "user_id": 1, "owed_paise": 10000},
        {"expense_id": 1, "user_id": 2, "owed_paise": 10000},
        {"expense_id": 2, "user_id": 1, "owed_paise": 5000},
        {"expense_id": 2, "user_id": 2, "owed_paise": 5000},
    ]
    settlements = [{"from_user": 2, "to_user": 1, "amount_paise": 1000, "status": "CONFIRMED"}]

    net = net_balances(expenses, shares, settlements)
    assert net == {1: 4000, 2: -4000}
    assert sum(net.values()) == 0

    debts = pairwise_debts(expenses, shares, settlements)
    # User 2 owes User 1: 5000 - 1000 = 4000
    assert debts == {(2, 1): 4000}


def test_user_lower_id_owes_higher_id() -> None:
    # User 2 pays 10000 for User 1
    exp = ExpenseRecord(id=1, paid_by=2, amount_paise=10000)
    shares = [ShareRecord(expense_id=1, user_id=1, owed_paise=10000)]
    debts = pairwise_debts([exp], shares, [])
    # User 1 (lower id) owes User 2 (higher id)
    assert debts == {(1, 2): 10000}
