import uuid


def generate_id(prefix: str) -> str:
    """Generate an opaque public identifier formatted as '{prefix}_{uuid_hex}'."""
    raw = uuid.uuid4().hex
    return f"{prefix}_{raw}"
