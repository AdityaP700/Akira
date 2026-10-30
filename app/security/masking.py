"""PII, credential, and secret masking utilities for logs and error responses."""

import re

# Regex patterns for sensitive data
TOKEN_REGEX = re.compile(r"\best_[a-zA-Z0-9_\-]{8,}\b")
BEARER_REGEX = re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-.]+\b")
VPA_REGEX = re.compile(r"\b([a-zA-Z0-9.\-_]{2})[a-zA-Z0-9.\-_]*(@[a-zA-Z0-9.\-_]+)\b")
PHONE_REGEX = re.compile(r"(\+?91[\-\s]?)?([6-9]\d{2})\d{4}(\d{3})\b")
SIGNATURE_REGEX = re.compile(r"(?i)\bv1=[a-fA-F0-9]{16,}\b")


def mask_token(token: str) -> str:
    """Mask an API token (retaining prefix if present)."""
    if token.startswith("est_"):
        return "est_***"
    return "***"


def mask_vpa(vpa: str) -> str:
    """Mask a UPI Virtual Payment Address (e.g., mohit@okaxis -> mo***@okaxis)."""
    match = VPA_REGEX.match(vpa.strip())
    if match:
        prefix = match.group(1)
        domain = match.group(2)
        return f"{prefix}***{domain}"
    if "@" in vpa:
        parts = vpa.split("@", 1)
        prefix = parts[0][:2] if len(parts[0]) >= 2 else parts[0]
        return f"{prefix}***@{parts[1]}"
    return "***"


def mask_phone(phone: str) -> str:
    """Mask a 10-digit Indian mobile number (e.g., 9876543210 -> 987****210)."""
    return PHONE_REGEX.sub(r"\g<1>\g<2>****\g<3>", phone)


def mask_sensitive_text(text: str) -> str:
    """Mask all recognized tokens, Authorization headers, VPAs, and phone numbers in text."""
    if not text:
        return text

    # Mask Bearer tokens first
    text = BEARER_REGEX.sub("Bearer est_***", text)
    # Mask raw est_ tokens
    text = TOKEN_REGEX.sub("est_***", text)
    # Mask webhook signatures
    text = SIGNATURE_REGEX.sub("v1=***", text)
    # Mask UPI VPAs
    text = VPA_REGEX.sub(r"\g<1>***\g<2>", text)
    # Mask phone numbers
    text = PHONE_REGEX.sub(r"\g<1>\g<2>****\g<3>", text)

    return text
