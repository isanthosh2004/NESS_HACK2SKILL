"""HIDDEN tests — never copied into the Fixer's working directory.

Used after a fix to check it generalises (e.g. no special-casing of the
visible test's inputs).
"""

from decimal import Decimal

import pytest

from loanlab import LateFeePolicy, LoanError, late_fee, prepayment_penalty, processing_fee


def test_custom_grace_period_is_inclusive():
    policy = LateFeePolicy(grace_days=10)
    assert late_fee(20000, 10, policy) == Decimal("0.00")
    assert late_fee(20000, 11, policy) == Decimal("400.00")


def test_zero_grace_period_charges_from_day_one():
    policy = LateFeePolicy(grace_days=0)
    assert late_fee(20000, 0, policy) == Decimal("0.00")
    assert late_fee(20000, 1, policy) == Decimal("400.00")


@pytest.mark.parametrize("days_late", [1, 2, 3, 4])
def test_no_fee_inside_default_grace_period(days_late):
    assert late_fee(15000, days_late) == Decimal("0.00")


def test_zero_overdue_never_charged():
    assert late_fee(0, 90) == Decimal("0.00")


def test_fee_exactly_at_max_boundary():
    # 2% of 50,000 is exactly the 1,000 cap.
    assert late_fee(50000, 7) == Decimal("1000.00")


def test_late_fee_rejects_fractional_days():
    with pytest.raises(LoanError):
        late_fee(10000, 6.5)


def test_processing_fee_maximum():
    assert processing_fee(5000000).total == Decimal("11800.00")


def test_prepayment_penalty_zero_amount():
    assert prepayment_penalty(0, 2) == Decimal("0.00")


def test_prepayment_penalty_rejects_unknown_rate_type():
    with pytest.raises(LoanError):
        prepayment_penalty(100000, 2, "variable")
