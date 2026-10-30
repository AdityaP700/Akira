"""Unit tests for split strategies."""

import pytest

from app.domain.splits import (
    EqualSplit,
    ExactSplit,
    SplitError,
    get_strategy,
    register_strategy,
)


def test_equal_split_clean_division() -> None:
    strategy = EqualSplit()
    result = strategy.compute(120000, [1, 2, 3])
    assert result == {1: 40000, 2: 40000, 3: 40000}
    assert sum(result.values()) == 120000


def test_equal_split_with_remainder_ascending_order() -> None:
    # ₹1000 / 3 = 100000 paise / 3 = 33333 rem 1 -> user 1 gets 33334
    strategy = EqualSplit()
    result = strategy.compute(100000, [3, 1, 2])
    assert result == {1: 33334, 2: 33333, 3: 33333}
    assert sum(result.values()) == 100000


def test_equal_split_tiny_amount() -> None:
    # 1 paise among 3 -> user 1 gets 1, others get 0
    strategy = EqualSplit()
    result = strategy.compute(1, [1, 2, 3])
    assert result == {1: 1, 2: 0, 3: 0}
    assert sum(result.values()) == 1


def test_equal_split_single_participant() -> None:
    strategy = EqualSplit()
    result = strategy.compute(50000, [42])
    assert result == {42: 50000}


def test_equal_split_invalid_cases() -> None:
    strategy = EqualSplit()
    with pytest.raises(SplitError, match="cannot be empty"):
        strategy.compute(1000, [])

    with pytest.raises(SplitError, match="strictly positive"):
        strategy.compute(0, [1, 2])

    with pytest.raises(SplitError, match="strictly positive"):
        strategy.compute(-100, [1, 2])

    with pytest.raises(SplitError, match="Duplicate participant"):
        strategy.compute(1000, [1, 2, 1])


def test_exact_split_valid() -> None:
    strategy = ExactSplit()
    spec = {1: 30000, 2: 70000}
    result = strategy.compute(100000, [1, 2], spec)
    assert result == {1: 30000, 2: 70000}
    assert sum(result.values()) == 100000


def test_exact_split_missing_participant() -> None:
    strategy = ExactSplit()
    spec = {1: 100000}
    with pytest.raises(SplitError, match="SPLITS_MISMATCH"):
        strategy.compute(100000, [1, 2], spec)


def test_exact_split_extra_participant() -> None:
    strategy = ExactSplit()
    spec = {1: 50000, 2: 50000, 3: 0}
    with pytest.raises(SplitError, match="SPLITS_MISMATCH"):
        strategy.compute(100000, [1, 2], spec)


def test_exact_split_sum_mismatch() -> None:
    strategy = ExactSplit()
    spec = {1: 40000, 2: 50000}  # sum is 90000 != 100000
    with pytest.raises(SplitError, match="SPLITS_MISMATCH"):
        strategy.compute(100000, [1, 2], spec)


def test_exact_split_negative_or_invalid_shares() -> None:
    strategy = ExactSplit()
    with pytest.raises(SplitError, match="SPLITS_MISMATCH"):
        strategy.compute(100000, [1, 2], {1: -10000, 2: 110000})

    with pytest.raises(SplitError, match="SPLITS_MISMATCH"):
        strategy.compute(100000, [1, 2], {1: 50000, 2: 50000.0})  # type: ignore[dict-item]


def test_exact_split_missing_spec() -> None:
    strategy = ExactSplit()
    with pytest.raises(SplitError, match="requires spec"):
        strategy.compute(100000, [1, 2], None)


def test_exact_split_empty_or_invalid_amount_or_duplicate() -> None:
    strategy = ExactSplit()
    with pytest.raises(SplitError, match="cannot be empty"):
        strategy.compute(100000, [], {1: 100000})

    with pytest.raises(SplitError, match="strictly positive"):
        strategy.compute(0, [1], {1: 0})

    with pytest.raises(SplitError, match="Duplicate participant"):
        strategy.compute(100000, [1, 1], {1: 100000})


def test_strategy_registry() -> None:
    assert isinstance(get_strategy("EQUAL"), EqualSplit)
    assert isinstance(get_strategy("equal"), EqualSplit)
    assert isinstance(get_strategy("EXACT"), ExactSplit)
    assert isinstance(get_strategy("exact"), ExactSplit)

    with pytest.raises(SplitError, match="Unknown split strategy"):
        get_strategy("PERCENTAGE")

    # Custom registration
    class DummySplit:
        def compute(
            self, amount_paise: int, participants: list[int], spec: dict[int, int] | None = None
        ) -> dict[int, int]:
            return {p: amount_paise for p in participants}

    register_strategy("DUMMY", DummySplit())
    assert isinstance(get_strategy("dummy"), DummySplit)
