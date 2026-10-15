from datetime import date
from decimal import Decimal

import pytest

from loanlab import (
    LoanError,
    accrued_interest,
    compound_amount,
    days_between,
    effective_annual_rate,
    round_money,
    simple_interest,
    to_decimal,
)


def test_simple_interest_full_year():
    assert simple_interest(100000, 10, 365) == Decimal("10000.00")


def test_simple_interest_partial_year():
    assert simple_interest(50000, "7.5", 90) == Decimal("924.66")


def test_accrued_interest_between_dates():
    assert accrued_interest(250000, 9, date(2026, 1, 1), date(2026, 3, 1)) == Decimal("3636.99")


def test_days_between_rejects_reversed_dates():
    with pytest.raises(LoanError):
        days_between(date(2026, 3, 1), date(2026, 1, 1))


def test_compound_amount_monthly():
    assert compound_amount(100000, 12, 1) == Decimal("112682.50")


def test_effective_annual_rate_monthly_compounding():
    assert effective_annual_rate(12) == Decimal("12.6825")


@pytest.mark.parametrize(
    "raw, expected",
    [("2.345", "2.35"), ("2.344", "2.34"), ("1,00,000", "100000.00")],
)
def test_round_money(raw, expected):
    assert round_money(raw) == Decimal(expected)


@pytest.mark.parametrize("bad", ["abc", True, float("nan")])
def test_to_decimal_rejects_garbage(bad):
    with pytest.raises(LoanError):
        to_decimal(bad)
