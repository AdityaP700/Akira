"""Unit tests for money parsing and formatting."""

import pytest

from app.domain.money import MAX_PAISE, MoneyError, format_paise, parse_rupees


def test_parse_rupees_valid_inputs() -> None:
    assert parse_rupees("1200") == 120000
    assert parse_rupees("1200.5") == 120050
    assert parse_rupees("1200.50") == 120050
    assert parse_rupees(1200) == 120000
    assert parse_rupees("0.01") == 1
    assert parse_rupees("0.1") == 10
    assert parse_rupees("1000000.00") == MAX_PAISE
    assert parse_rupees(1000000) == MAX_PAISE


@pytest.mark.parametrize(
    "invalid_val, expected_err",
    [
        (1200.5, "Floats are not permitted"),
        (0.01, "Floats are not permitted"),
        (True, "Booleans are not valid"),
        (False, "Booleans are not valid"),
        ("0", "positive and greater than zero"),
        ("0.00", "positive and greater than zero"),
        (0, "positive and greater than zero"),
        ("-10", "positive and greater than zero"),
        ("-0.01", "positive and greater than zero"),
        (-100, "positive and greater than zero"),
        ("12.345", "more than 2 decimal places"),
        ("0.001", "more than 2 decimal places"),
        ("abc", "Invalid monetary value"),
        ("", "cannot be empty"),
        ("   ", "cannot be empty"),
        ("12.a", "Invalid monetary value"),
        ("12..34", "Malformed monetary value"),
        ("Infinity", "Invalid non-finite monetary value"),
        ("NaN", "Invalid non-finite monetary value"),
        ("1000000.01", "exceeds maximum allowed limit"),
        (1000001, "exceeds maximum allowed limit"),
        (None, "Expected str or int"),
        ([], "Expected str or int"),
    ],
)
def test_parse_rupees_invalid_inputs(invalid_val: object, expected_err: str) -> None:
    with pytest.raises(MoneyError, match=expected_err):
        parse_rupees(invalid_val)  # type: ignore[arg-type]


def test_format_paise_valid() -> None:
    assert format_paise(40050) == "400.50"
    assert format_paise(0) == "0.00"
    assert format_paise(5) == "0.05"
    assert format_paise(100) == "1.00"
    assert format_paise(1) == "0.01"
    assert format_paise(MAX_PAISE) == "1000000.00"
    assert format_paise(-40000) == "-400.00"
    assert format_paise(-5) == "-0.05"


@pytest.mark.parametrize("invalid_val", [400.5, "400", True, False, None, []])
def test_format_paise_invalid(invalid_val: object) -> None:
    with pytest.raises(MoneyError):
        format_paise(invalid_val)  # type: ignore[arg-type]
