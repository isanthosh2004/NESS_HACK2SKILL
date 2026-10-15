"""Fees charged around a loan: late-payment fees, processing fees, prepayment penalties.

Late-fee policy (see ``LateFeePolicy``):
  * No fee while the payment is within the grace period. The grace period is
    inclusive: with ``grace_days=5`` a payment made 5 days late is still free,
    the fee starts on day 6.
  * After that the fee is ``rate_pct`` of the overdue amount, but at least
    ``min_fee`` and at most ``max_fee``.
  * The fee can never exceed the overdue amount itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import (
    ZERO,
    LoanError,
    Number,
    percent_of,
    require_non_negative,
    require_positive,
    require_whole_number,
    round_money,
    to_decimal,
)


@dataclass(frozen=True)
class LateFeePolicy:
    grace_days: int = 5
    rate_pct: Decimal = Decimal("2")
    min_fee: Decimal = Decimal("100")
    max_fee: Decimal = Decimal("1000")

    def __post_init__(self) -> None:
        require_whole_number("grace_days", self.grace_days)
        require_non_negative("rate_pct", self.rate_pct)
        require_non_negative("min_fee", self.min_fee)
        if to_decimal(self.max_fee) < to_decimal(self.min_fee):
            raise LoanError("max_fee must be >= min_fee")


DEFAULT_LATE_FEE_POLICY = LateFeePolicy()


def late_fee(overdue_amount: Number, days_late: int, policy: LateFeePolicy = DEFAULT_LATE_FEE_POLICY) -> Decimal:
    """Late-payment fee for an instalment paid ``days_late`` days after its due date."""
    overdue = require_non_negative("overdue_amount", overdue_amount)
    require_whole_number("days_late", days_late)
    if overdue == ZERO:
        return round_money(ZERO)
    if days_late <= policy.grace_days:
        return round_money(ZERO)
    fee = max(to_decimal(policy.min_fee), percent_of(overdue, policy.rate_pct))
    fee = min(fee, to_decimal(policy.max_fee))
    fee = min(fee, overdue)
    return round_money(fee)


@dataclass(frozen=True)
class ProcessingFee:
    fee: Decimal
    gst: Decimal
    total: Decimal


def processing_fee(
    principal: Number,
    rate_pct: Number = "1",
    min_fee: Number = "500",
    max_fee: Number = "10000",
    gst_pct: Number = "18",
) -> ProcessingFee:
    """One-time processing fee (``rate_pct`` of principal, clamped) plus GST on the fee."""
    p = require_positive("principal", principal)
    low = require_non_negative("min_fee", min_fee)
    high = require_non_negative("max_fee", max_fee)
    if high < low:
        raise LoanError("max_fee must be >= min_fee")
    fee = round_money(min(max(percent_of(p, rate_pct), low), high))
    gst = round_money(percent_of(fee, require_non_negative("gst_pct", gst_pct)))
    return ProcessingFee(fee=fee, gst=gst, total=fee + gst)


FIXED = "fixed"
FLOATING = "floating"


def prepayment_penalty(
    prepaid_amount: Number,
    months_elapsed: int,
    rate_type: str = FIXED,
    lock_in_months: int = 6,
    lock_in_penalty_pct: Number = "4",
    standard_penalty_pct: Number = "2",
) -> Decimal:
    """Penalty for prepaying part of the principal.

    Floating-rate loans carry no prepayment penalty. Fixed-rate loans pay
    ``lock_in_penalty_pct`` while still inside the lock-in window
    (``months_elapsed < lock_in_months``) and ``standard_penalty_pct`` after it.
    """
    amount = require_non_negative("prepaid_amount", prepaid_amount)
    require_whole_number("months_elapsed", months_elapsed)
    require_whole_number("lock_in_months", lock_in_months)
    if rate_type not in (FIXED, FLOATING):
        raise LoanError(f"rate_type must be {FIXED!r} or {FLOATING!r}")
    if rate_type == FLOATING or amount == ZERO:
        return round_money(ZERO)
    pct = lock_in_penalty_pct if months_elapsed < lock_in_months else standard_penalty_pct
    return round_money(percent_of(amount, pct))
