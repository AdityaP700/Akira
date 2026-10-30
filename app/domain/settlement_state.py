"""Settlement state machine and transition rules.

Allowed settlement states:
- PENDING: Settlement payment initiated via provider.
- SUCCESS: Provider webhook confirmed payment success.
- FAILED: Provider webhook indicated payment failure.
- CLAIMED: Payer claimed cash settlement.
- CONFIRMED: Recipient confirmed cash settlement.
- REJECTED: Recipient rejected cash settlement.

Effective settlement states that impact balances: CONFIRMED, SUCCESS.
"""

from typing import Final

STATUS_PENDING: Final[str] = "PENDING"
STATUS_SUCCESS: Final[str] = "SUCCESS"
STATUS_FAILED: Final[str] = "FAILED"
STATUS_CLAIMED: Final[str] = "CLAIMED"
STATUS_CONFIRMED: Final[str] = "CONFIRMED"
STATUS_REJECTED: Final[str] = "REJECTED"

ALL_SETTLEMENT_STATUSES: Final[frozenset[str]] = frozenset(
    {
        STATUS_PENDING,
        STATUS_SUCCESS,
        STATUS_FAILED,
        STATUS_CLAIMED,
        STATUS_CONFIRMED,
        STATUS_REJECTED,
    }
)

EFFECTIVE_SETTLEMENT_STATUSES: Final[frozenset[str]] = frozenset(
    {
        STATUS_CONFIRMED,
        STATUS_SUCCESS,
    }
)

ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    STATUS_PENDING: frozenset({STATUS_SUCCESS, STATUS_FAILED}),
    STATUS_CLAIMED: frozenset({STATUS_CONFIRMED, STATUS_REJECTED}),
    STATUS_SUCCESS: frozenset(),
    STATUS_FAILED: frozenset(),
    STATUS_CONFIRMED: frozenset(),
    STATUS_REJECTED: frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    """Return True if transition from current to target status is valid."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())
