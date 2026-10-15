"""HIDDEN tests for EMI, interest, schedule and eligibility."""

from datetime import date
from decimal import Decimal

import pytest

from loanlab import (
    LoanError,
    amortization_schedule,
    check_eligibility,
    compound_interest,
    effective_annual_rate,
    emi,
    floor_to,
    max_eligible_loan,
    outstanding_after,
    simple_interest,
)


def test_emi_accepts_string_amounts_with_separators():
    assert emi("1,00,000", "12", 12) == Decimal("8884.88")


def test_emi_rejects_float_tenure():
    with pytest.raises(LoanError):
        emi(100000, 12, 12.0)


def test_emi_rejects_absurd_rate():
    with pytest.raises(LoanError):
        emi(100000, 61, 12)


def test_long_tenure_schedule_closes_at_zero():
    schedule = amortization_schedule(2500000, "8.75", 240)
    assert len(schedule) == 240
    assert schedule[-1].closing_balance == Decimal("0.00")
    assert all(row.principal > 0 for row in schedule)


def test_zero_rate_schedule_has_no_interest():
    schedule = amortization_schedule(12000, 0, 12)
    assert sum(row.interest for row in schedule) == Decimal("0")


def test_outstanding_after_zero_and_all_payments():
    assert outstanding_after(100000, 12, 12, 0) == Decimal("100000.00")
    assert outstanding_after(100000, 12, 12, 12) == Decimal("0.00")


def test_outstanding_after_rejects_too_many_payments():
    with pytest.raises(LoanError):
        outstanding_after(100000, 12, 12, 13)


def test_simple_interest_360_day_basis():
    assert simple_interest(50000, "7.5", 90, day_count=360) == Decimal("937.50")


def test_simple_interest_rejects_unknown_basis():
    with pytest.raises(LoanError):
        simple_interest(50000, 7, 30, day_count=366)


def test_quarterly_compound_interest():
    assert compound_interest(10000, 8, 5, 4) == Decimal("4859.47")


def test_effective_rate_quarterly():
    assert effective_annual_rate(12, 4) == Decimal("12.5509")


def test_leap_year_february_accrual():
    from loanlab import accrued_interest

    assert accrued_interest(365000, 10, date(2028, 2, 1), date(2028, 3, 1)) == Decimal("2900.00")


def test_foir_exactly_at_limit_is_eligible():
    assert check_eligibility(100000, 30000, 20000, 700).eligible


def test_foir_just_over_limit_is_not_eligible():
    assert not check_eligibility(100000, 30000, 20010, 700).eligible


def test_max_eligible_loan_zero_when_no_headroom():
    assert max_eligible_loan(40000, 25000, 10, 60) == Decimal("0.00")


def test_floor_to_rejects_non_positive_step():
    with pytest.raises(LoanError):
        floor_to(1234, 0)
