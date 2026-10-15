from decimal import Decimal

import pytest

from loanlab import LoanError, emi, max_principal_for_emi, monthly_rate, total_interest, total_payable


@pytest.mark.parametrize(
    "principal, rate, months, expected",
    [
        (100000, 12, 12, "8884.88"),
        (100000, 10, 12, "8791.59"),
        (500000, "8.5", 240, "4339.12"),
    ],
)
def test_emi_known_values(principal, rate, months, expected):
    assert emi(principal, rate, months) == Decimal(expected)


def test_zero_rate_emi_is_straight_division():
    assert emi(120000, 0, 12) == Decimal("10000.00")


def test_monthly_rate_converts_percent_to_monthly_fraction():
    assert monthly_rate(12) == Decimal("0.01")


def test_total_interest_for_one_year_loan():
    assert total_payable(100000, 12, 12) == Decimal("106618.56")
    assert total_interest(100000, 12, 12) == Decimal("6618.56")


def test_max_principal_is_inverse_of_emi():
    principal = max_principal_for_emi(Decimal("8884.88"), 12, 12)
    assert emi(principal, 12, 12) <= Decimal("8884.88")
    assert principal == Decimal("100000.01")


@pytest.mark.parametrize(
    "principal, rate, months",
    [
        (0, 12, 12),
        (100000, -1, 12),
        (100000, 12, 0),
        (100000, 12, 481),
    ],
)
def test_emi_rejects_invalid_input(principal, rate, months):
    with pytest.raises(LoanError):
        emi(principal, rate, months)
