"""Unit tests for debt simplification algorithm."""

from collections import defaultdict

import pytest

from app.domain.settle import Transfer, simplify


def test_simplify_empty_or_all_zero() -> None:
    assert simplify({}) == []
    assert simplify({1: 0, 2: 0, 3: 0}) == []


def test_simplify_invalid_sum_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Net balances must sum to zero"):
        simplify({1: 100, 2: -50})


def test_simplify_circular_debt_collapses() -> None:
    # A owes B 100, B owes C 100, C owes A 100
    # Net balances: A = 0, B = 0, C = 0
    net = {1: 0, 2: 0, 3: 0}
    transfers = simplify(net)
    assert transfers == []


def test_simplify_simple_pair() -> None:
    net = {1: 5000, 2: -5000}
    transfers = simplify(net)
    assert transfers == [Transfer(from_user=2, to_user=1, amount_paise=5000)]


def test_simplify_two_debtors_one_creditor() -> None:
    # Mohit (1) is owed 80000; Rahul (2) owes 40000; Ankit (3) owes 40000
    net = {1: 80000, 2: -40000, 3: -40000}
    transfers = simplify(net)

    assert len(transfers) <= 2
    # Verify applying transfers settles balances to zero
    applied = defaultdict(int, net)
    for t in transfers:
        applied[t.from_user] += t.amount_paise
        applied[t.to_user] -= t.amount_paise

    assert all(bal == 0 for bal in applied.values())


def test_simplify_complex_multiple_debtors_and_creditors() -> None:
    # 5 participants with diverse balances
    net = {
        1: 150000,  # creditor
        2: 50000,  # creditor
        3: -70000,  # debtor
        4: -80000,  # debtor
        5: -50000,  # debtor
    }
    assert sum(net.values()) == 0

    transfers = simplify(net)

    # Invariant 1: Count <= n - 1 (here n=5 participants with non-zero balances -> count <= 4)
    assert len(transfers) <= 4

    # Invariant 2: Applying transfers clears all balances
    applied = defaultdict(int, net)
    for t in transfers:
        applied[t.from_user] += t.amount_paise
        applied[t.to_user] -= t.amount_paise

    assert all(bal == 0 for bal in applied.values())


def test_simplify_deterministic_tie_breaking() -> None:
    # Two debtors with identical amounts: user 2 and user 4 owe 5000 each.
    # User 1 is owed 10000.
    net = {1: 10000, 2: -5000, 4: -5000}
    transfers = simplify(net)

    # Tie break should pick smaller user_id first: user 2, then user 4
    assert transfers[0].from_user == 2
    assert transfers[1].from_user == 4
