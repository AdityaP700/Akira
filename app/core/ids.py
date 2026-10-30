"""Public opaque identifier generation.

Generates identifiers with prefixes:
- usr_ (users)
- grp_ (groups)
- exp_ (expenses)
- stl_ (settlements)
- ntf_ (notifications)
- ref_ (settlement references)
"""

import secrets


def generate_id(prefix: str) -> str:
    """Generate an opaque public identifier formatted as '{prefix}_{26_char_hex}'."""
    # 13 bytes = 26 lowercase hexadecimal characters
    suffix = secrets.token_hex(13)
    return f"{prefix}_{suffix}"


def new_user_id() -> str:
    return generate_id("usr")


def new_group_id() -> str:
    return generate_id("grp")


def new_expense_id() -> str:
    return generate_id("exp")


def new_settlement_id() -> str:
    return generate_id("stl")


def new_notification_id() -> str:
    return generate_id("ntf")


def new_reference_id() -> str:
    return generate_id("ref")
