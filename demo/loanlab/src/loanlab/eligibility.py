"""Borrower eligibility: FOIR checks, credit-score bands and maximum loan size.

FOIR (Fixed Obligation to Income Ratio) is the share of monthly income already
committed to EMIs, including the EMI of the loan being applied for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

from .emi import max_principal_for_emi
from .money import (
    HUNDRED,
    ZERO,
    LoanError,
    Number,
    floor_to,
    percent_of,
    require_non_negative,
    require_positive,
    require_whole_number,
    round_money,
)

MIN_CREDIT_SCORE = 300
MAX_CREDIT_SCORE = 900


def credit_band(score: int) -> str:
    """Map a 300-900 bureau score to a band."""
    require_whole_number("score", score)
    if not MIN_CREDIT_SCORE <= score <= MAX_CREDIT_SCORE:
        raise LoanError(f"score must be between {MIN_CREDIT_SCORE} and {MAX_CREDIT_SCORE}")
    if score >= 750:
        return "excellent"
    if score >= 700:
        return "good"
    if score >= 650:
        return "fair"
    return "poor"


def foir(monthly_income: Number, existing_emis: Number, proposed_emi: Number) -> Decimal:
    """FOIR in percent, two decimals."""
    income = require_positive("monthly_income", monthly_income)
    committed = require_non_negative("existing_emis", existing_emis) + require_non_negative("proposed_emi", proposed_emi)
    return round_money(committed * HUNDRED / income)


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    foir_pct: Decimal
    band: str
    reasons: List[str] = field(default_factory=list)


def check_eligibility(
    monthly_income: Number,
    existing_emis: Number,
    proposed_emi: Number,
    credit_score: int,
    max_foir_pct: Number = "50",
    min_credit_score: int = 650,
) -> EligibilityResult:
    """Approve when FOIR is at most ``max_foir_pct`` and the score is at least ``min_credit_score``."""
    ratio = foir(monthly_income, existing_emis, proposed_emi)
    band = credit_band(credit_score)
    reasons: List[str] = []
    if ratio > Decimal(str(max_foir_pct)):
        reasons.append(f"FOIR {ratio}% exceeds limit of {max_foir_pct}%")
    if credit_score < min_credit_score:
        reasons.append(f"credit score {credit_score} below minimum {min_credit_score}")
    return EligibilityResult(eligible=not reasons, foir_pct=ratio, band=band, reasons=reasons)


def max_eligible_emi(monthly_income: Number, existing_emis: Number, max_foir_pct: Number = "50") -> Decimal:
    """Largest new EMI that keeps FOIR within the limit (never negative)."""
    income = require_positive("monthly_income", monthly_income)
    existing = require_non_negative("existing_emis", existing_emis)
    headroom = percent_of(income, max_foir_pct) - existing
    return round_money(max(headroom, ZERO))


def max_eligible_loan(
    monthly_income: Number,
    existing_emis: Number,
    annual_rate_pct: Number,
    tenure_months: int,
    max_foir_pct: Number = "50",
) -> Decimal:
    """Largest principal (rounded down to the nearest 1,000) the borrower can service."""
    budget = max_eligible_emi(monthly_income, existing_emis, max_foir_pct)
    if budget == ZERO:
        return round_money(ZERO)
    return floor_to(max_principal_for_emi(budget, annual_rate_pct, tenure_months), 1000)
