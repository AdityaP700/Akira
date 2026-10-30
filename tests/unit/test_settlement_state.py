"""Unit tests for settlement state transitions."""

from app.domain.settlement_state import (
    STATUS_CLAIMED,
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STATUS_SUCCESS,
    can_transition,
)


def test_allowed_settlement_transitions() -> None:
    assert can_transition(STATUS_PENDING, STATUS_SUCCESS) is True
    assert can_transition(STATUS_PENDING, STATUS_FAILED) is True
    assert can_transition(STATUS_CLAIMED, STATUS_CONFIRMED) is True
    assert can_transition(STATUS_CLAIMED, STATUS_REJECTED) is True


def test_disallowed_settlement_transitions() -> None:
    assert can_transition(STATUS_PENDING, STATUS_CLAIMED) is False
    assert can_transition(STATUS_SUCCESS, STATUS_PENDING) is False
    assert can_transition(STATUS_CONFIRMED, STATUS_REJECTED) is False
    assert can_transition("UNKNOWN", STATUS_SUCCESS) is False
