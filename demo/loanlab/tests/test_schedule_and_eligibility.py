from decimal import Decimal

import pytest

from loanlab import (
    LoanError,
    amortization_schedule,
    check_eligibility,
    credit_band,
    foir,
    max_eligible_emi,
    max_eligible_loan,
    outstanding_after,
    schedule_totals,
)


def test_schedule_first_row():
    first = amortization_schedule(100000, 12, 12)[0]
    assert first.interest == Decimal("1000.00")
    assert first.principal == Decimal("7884.88")
    assert first.closing_balance == Decimal("92115.12")


def test_schedule_closes_at_zero():
    schedule = amortization_schedule(100000, 12, 12)
    assert len(schedule) == 12
    assert schedule[-1].closing_balance == Decimal("0.00")


def test_schedule_totals_repay_principal_exactly():
    totals = schedule_totals(amortization_schedule(100000, 12, 12))
    assert totals["total_principal"] == Decimal("100000.00")
    assert totals["total_interest"] == Decimal("6618.53")


def test_outstanding_after_six_payments():
    assert outstanding_after(100000, 12, 12, 6) == Decimal("51492.09")


def test_foir_percentage():
    assert foir(100000, 20000, 15000) == Decimal("35.00")


def test_eligible_borrower():
    result = check_eligibility(100000, 20000, 15000, 720)
    assert result.eligible
    assert result.band == "good"


def test_ineligible_borrower_lists_every_reason():
    result = check_eligibility(50000, 20000, 10000, 640)
    assert not result.eligible
    assert len(result.reasons) == 2


@pytest.mark.parametrize("score, band", [(750, "excellent"), (749, "good"), (650, "fair"), (649, "poor")])
def test_credit_band_boundaries(score, band):
    assert credit_band(score) == band


def test_max_eligible_emi_never_negative():
    assert max_eligible_emi(40000, 25000) == Decimal("0.00")


def test_max_eligible_loan_rounds_down_to_thousand():
    assert max_eligible_loan(100000, 20000, 10, 60) == Decimal("1411000.00")


def test_credit_score_out_of_range():
    with pytest.raises(LoanError):
        credit_band(950)
