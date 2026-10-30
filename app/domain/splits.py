"""Expense split strategies.

Guardrails:
- M4: Equal split remainder: one paise each to participants in ascending user id order.
- M5: Exact split: participants must sum to total amount;
  missing/extra participant or sum mismatch -> error.
"""

from typing import Protocol


class SplitError(ValueError):
    """Raised when an expense split computation or validation fails."""

    pass


class SplitStrategy(Protocol):
    """Protocol for expense splitting algorithms."""

    def compute(
        self,
        amount_paise: int,
        participants: list[int],
        spec: dict[int, int] | None = None,
    ) -> dict[int, int]:
        """Compute the paise owed by each participant.

        Returns:
            Dictionary mapping user_id to owed amount in paise.
        """
        ...


class EqualSplit:
    """Splits an expense equally among participants.

    Remainder paise (from integer division) are allocated 1 paise each to participants
    in ascending order of their user_id.
    """

    def compute(
        self,
        amount_paise: int,
        participants: list[int],
        spec: dict[int, int] | None = None,
    ) -> dict[int, int]:
        if not participants:
            raise SplitError("Participants list cannot be empty")

        if amount_paise <= 0:
            raise SplitError("Amount must be strictly positive")

        sorted_ids = sorted(participants)
        if len(set(sorted_ids)) != len(participants):
            raise SplitError("Duplicate participant in split")

        base_share, remainder = divmod(amount_paise, len(sorted_ids))
        return {
            uid: base_share + (1 if index < remainder else 0)
            for index, uid in enumerate(sorted_ids)
        }


class ExactSplit:
    """Splits an expense by exact specified amounts.

    Every participant must appear in spec with their exact share in paise.
    The sum of all shares must exactly equal amount_paise.
    """

    def compute(
        self,
        amount_paise: int,
        participants: list[int],
        spec: dict[int, int] | None = None,
    ) -> dict[int, int]:
        if not participants:
            raise SplitError("Participants list cannot be empty")

        if amount_paise <= 0:
            raise SplitError("Amount must be strictly positive")

        if spec is None:
            raise SplitError("SPLITS_MISMATCH: exact split requires spec")

        participant_set = set(participants)
        if len(participant_set) != len(participants):
            raise SplitError("Duplicate participant in split")

        if set(spec.keys()) != participant_set:
            raise SplitError("SPLITS_MISMATCH: participants do not match spec keys")

        for uid, share in spec.items():
            if not isinstance(share, int) or isinstance(share, bool) or share < 0:
                raise SplitError(
                    f"SPLITS_MISMATCH: share for user {uid} must be a non-negative integer"
                )

        if sum(spec.values()) != amount_paise:
            total_shares = sum(spec.values())
            raise SplitError(
                f"SPLITS_MISMATCH: sum of shares ({total_shares}) "
                f"does not equal total amount ({amount_paise})"
            )

        return {uid: spec[uid] for uid in participants}


_REGISTRY: dict[str, SplitStrategy] = {
    "EQUAL": EqualSplit(),
    "EXACT": ExactSplit(),
}


def register_strategy(name: str, strategy: SplitStrategy) -> None:
    """Register a new split strategy."""
    _REGISTRY[name.upper()] = strategy


def get_strategy(name: str) -> SplitStrategy:
    """Retrieve a split strategy by name."""
    strategy = _REGISTRY.get(name.upper())
    if strategy is None:
        raise SplitError(f"Unknown split strategy: '{name}'")
    return strategy
