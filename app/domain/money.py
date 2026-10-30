"""Money parsing and formatting utilities.

Guardrails:
- M1: Every internal money value is int paise. Never float.
- M2: Parse at the edge using decimal.Decimal. Max ₹10,00,000 (100_000_000 paise).
  Reject negatives, zero, > 2 decimals, float input.
- M3: format_paise(p) -> "400.50".
"""

from decimal import Decimal, InvalidOperation
from typing import Final

MAX_PAISE: Final[int] = 100_000_000  # ₹10,00,000 in paise


class MoneyError(ValueError):
    """Raised when an invalid monetary amount is encountered."""

    pass


def parse_rupees(value: str | int) -> int:
    """Parse a rupee amount string or integer into integer paise.

    Accepts: "1200", "1200.5", "1200.50", 1200.
    Rejects: Python floats, negatives, zero, > 2 decimal places, non-numeric strings,
             values exceeding MAX_PAISE.
    """
    if isinstance(value, float):
        raise MoneyError(
            "Floats are not permitted; provide a string or int to prevent precision loss"
        )

    if isinstance(value, bool):
        raise MoneyError("Booleans are not valid monetary values")

    if not isinstance(value, (str, int)):
        raise MoneyError(f"Expected str or int, got {type(value).__name__}")

    if isinstance(value, str):
        val_str = value.strip()
        if not val_str:
            raise MoneyError("Monetary value cannot be empty")
        # Check decimal places before decimal parsing to reject trailing exponent/extra dots
        if "." in val_str:
            parts = val_str.split(".")
            if len(parts) != 2:
                raise MoneyError(f"Malformed monetary value: '{value}'")
            if len(parts[1]) > 2:
                raise MoneyError(f"Monetary value has more than 2 decimal places: '{value}'")
        try:
            d = Decimal(val_str)
        except InvalidOperation as exc:
            raise MoneyError(f"Invalid monetary value: '{value}'") from exc
    else:
        d = Decimal(value)

    if not d.is_finite():
        raise MoneyError(f"Invalid non-finite monetary value: '{value}'")

    if d <= 0:
        raise MoneyError("Amount must be strictly positive and greater than zero")

    paise = int(d * 100)
    if paise > MAX_PAISE:
        raise MoneyError(
            f"Amount {paise} paise exceeds maximum allowed limit of {MAX_PAISE} paise (₹10,00,000)"
        )

    return paise


def format_paise(paise: int) -> str:
    """Format integer paise into standard 2-decimal rupee string (e.g. 40050 -> '400.50')."""
    if not isinstance(paise, int) or isinstance(paise, bool):
        raise MoneyError(f"paise must be an int, got {type(paise).__name__}")

    sign = "-" if paise < 0 else ""
    abs_paise = abs(paise)
    rupees = abs_paise // 100
    cents = abs_paise % 100
    return f"{sign}{rupees}.{cents:02d}"
