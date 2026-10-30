"""Unit tests for SHARES split strategy and deterministic remainder distribution."""

import pytest

from app.domain.splits import SharesSplit, SplitError, get_strategy


def test_shares_split_proportions_exact_sum() -> None:
    strategy = SharesSplit()
    # 1000 with weights 2:1:1 -> 500, 250, 250
    participants = [1, 2, 3]
    spec = {1: 2, 2: 1, 3: 1}
    result = strategy.compute(1000, participants, spec=spec)
    assert result == {1: 500, 2: 250, 3: 250}
    assert sum(result.values()) == 1000


def test_shares_split_deterministic_remainder_allocation() -> None:
    strategy = SharesSplit()
    # 100 with equal weights 1:1:1 -> 33 each, remainder 1 paise to lowest user_id (10)
    participants = [30, 10, 20]
    spec = {10: 1, 20: 1, 30: 1}
    result = strategy.compute(100, participants, spec=spec)
    assert result[10] == 34
    assert result[20] == 33
    assert result[30] == 33
    assert sum(result.values()) == 100


def test_shares_split_multiple_remainder_paise() -> None:
    strategy = SharesSplit()
    # 100 with weights 1:1:1:1:1:1:1 (7 participants). 100 // 7 = 14 (14*7 = 98, remainder 2)
    # The two lowest user_ids (1, 2) get 15 each; users 3..7 get 14 each.
    participants = [7, 6, 5, 4, 3, 2, 1]
    spec = {i: 1 for i in range(1, 8)}
    result = strategy.compute(100, participants, spec=spec)
    assert result[1] == 15
    assert result[2] == 15
    assert result[3] == 14
    assert result[4] == 14
    assert result[5] == 14
    assert result[6] == 14
    assert result[7] == 14
    assert sum(result.values()) == 100


def test_shares_split_validation_errors() -> None:
    strategy = SharesSplit()

    with pytest.raises(SplitError, match="Participants list cannot be empty"):
        strategy.compute(100, [], spec={})

    with pytest.raises(SplitError, match="Amount must be strictly positive"):
        strategy.compute(0, [1, 2], spec={1: 1, 2: 1})

    with pytest.raises(SplitError, match="shares split requires spec"):
        strategy.compute(100, [1, 2], spec=None)

    with pytest.raises(SplitError, match="Duplicate participant"):
        strategy.compute(100, [1, 1], spec={1: 2})

    with pytest.raises(SplitError, match="participants do not match spec keys"):
        strategy.compute(100, [1, 2], spec={1: 1, 3: 1})

    with pytest.raises(SplitError, match="must be a strictly positive integer"):
        strategy.compute(100, [1, 2], spec={1: 0, 2: 1})

    with pytest.raises(SplitError, match="must be a strictly positive integer"):
        strategy.compute(100, [1, 2], spec={1: -5, 2: 1})


def test_shares_strategy_registry_lookup() -> None:
    strat = get_strategy("SHARES")
    assert isinstance(strat, SharesSplit)
