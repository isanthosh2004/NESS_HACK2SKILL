from decimal import Decimal

import pytest

from loanlab import LoanError, LateFeePolicy, late_fee, prepayment_penalty, processing_fee


def test_no_fee_when_paid_on_time():
    assert late_fee(10000, 0) == Decimal("0.00")


def test_no_fee_on_last_day_of_grace_period():
    # Default grace period is 5 days and is inclusive.
    assert late_fee(10000, 5) == Decimal("0.00")


def test_fee_starts_the_day_after_grace_period():
    assert late_fee(10000, 6) == Decimal("200.00")


def test_minimum_fee_applies_to_small_overdue_amounts():
    assert late_fee(3000, 10) == Decimal("100.00")


def test_fee_is_capped_at_max_fee():
    assert late_fee(80000, 10) == Decimal("1000.00")


def test_fee_never_exceeds_overdue_amount():
    assert late_fee(50, 30) == Decimal("50.00")


def test_custom_policy_rate():
    policy = LateFeePolicy(rate_pct=Decimal("3"))
    assert late_fee(20000, 15, policy) == Decimal("600.00")


def test_policy_rejects_max_below_min():
    with pytest.raises(LoanError):
        LateFeePolicy(min_fee=Decimal("500"), max_fee=Decimal("100"))


def test_processing_fee_includes_gst():
    result = processing_fee(200000)
    assert (result.fee, result.gst, result.total) == (
        Decimal("2000.00"),
        Decimal("360.00"),
        Decimal("2360.00"),
    )


def test_processing_fee_minimum():
    assert processing_fee(20000).fee == Decimal("500.00")


@pytest.mark.parametrize(
    "months_elapsed, rate_type, expected",
    [
        (3, "fixed", "4000.00"),
        (6, "fixed", "2000.00"),
        (3, "floating", "0.00"),
    ],
)
def test_prepayment_penalty(months_elapsed, rate_type, expected):
    assert prepayment_penalty(100000, months_elapsed, rate_type) == Decimal(expected)
