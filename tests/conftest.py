"""Global pytest fixtures and configuration."""

from collections.abc import Generator

import pytest

from app.security.ratelimit import limiter


@pytest.fixture(autouse=True)
def manage_rate_limiting() -> Generator[None, None, None]:
    """Disable rate limiting by default across test fixtures so setup
    requests do not exhaust limits.

    Tests that specifically verify rate limiting will re-enable limiter.enabled explicitly.
    """
    prev_enabled = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = prev_enabled
