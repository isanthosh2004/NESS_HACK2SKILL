"""loanlab — small, dependency-free loan maths library (EMI, interest, fees, eligibility)."""

from .eligibility import (
    EligibilityResult,
    check_eligibility,
    credit_band,
    foir,
    max_eligible_emi,
    max_eligible_loan,
)
from .emi import emi, emi_exact, max_principal_for_emi, monthly_rate, total_interest, total_payable
from .fees import (
    DEFAULT_LATE_FEE_POLICY,
    FIXED,
    FLOATING,
    LateFeePolicy,
    ProcessingFee,
    late_fee,
    prepayment_penalty,
    processing_fee,
)
from .interest import (
    accrued_interest,
    compound_amount,
    compound_interest,
    days_between,
    effective_annual_rate,
    simple_interest,
)
from .money import LoanError, floor_to, percent_of, round_money, to_decimal
from .schedule import Installment, amortization_schedule, outstanding_after, schedule_totals

__version__ = "1.0.0"

__all__ = [
    "DEFAULT_LATE_FEE_POLICY",
    "EligibilityResult",
    "FIXED",
    "FLOATING",
    "Installment",
    "LateFeePolicy",
    "LoanError",
    "ProcessingFee",
    "accrued_interest",
    "amortization_schedule",
    "check_eligibility",
    "compound_amount",
    "compound_interest",
    "credit_band",
    "days_between",
    "effective_annual_rate",
    "emi",
    "emi_exact",
    "floor_to",
    "foir",
    "late_fee",
    "max_eligible_emi",
    "max_eligible_loan",
    "max_principal_for_emi",
    "monthly_rate",
    "outstanding_after",
    "percent_of",
    "prepayment_penalty",
    "processing_fee",
    "round_money",
    "schedule_totals",
    "simple_interest",
    "to_decimal",
    "total_interest",
    "total_payable",
]
