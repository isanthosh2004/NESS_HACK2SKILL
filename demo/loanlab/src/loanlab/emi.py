"""Equated Monthly Instalment (EMI) calculations for reducing-balance loans.

    EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)

where P is the principal, r the monthly interest rate (annual % / 1200) and n
the tenure in months. A 0% loan is simply P / n.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

from .money import (
    CENT,
    ZERO,
    LoanError,
    Number,
    require_non_negative,
    require_positive,
    require_whole_number,
    round_money,
    to_decimal,
)

MAX_TENURE_MONTHS = 480  # 40 years
MAX_ANNUAL_RATE_PCT = Decimal("60")


def monthly_rate(annual_rate_pct: Number) -> Decimal:
    """Convert an annual percentage rate into a monthly fraction (12 -> 0.01)."""
    rate = require_non_negative("annual_rate_pct", annual_rate_pct)
    if rate > MAX_ANNUAL_RATE_PCT:
        raise LoanError(f"annual_rate_pct above {MAX_ANNUAL_RATE_PCT}% is not supported")
    return rate / Decimal(1200)


def _validate_tenure(tenure_months: int) -> int:
    require_whole_number("tenure_months", tenure_months, minimum=1)
    if tenure_months > MAX_TENURE_MONTHS:
        raise LoanError(f"tenure_months above {MAX_TENURE_MONTHS} is not supported")
    return tenure_months


def emi_exact(principal: Number, annual_rate_pct: Number, tenure_months: int) -> Decimal:
    """Unrounded EMI, used internally by the amortization schedule."""
    p = require_positive("principal", principal)
    n = _validate_tenure(tenure_months)
    r = monthly_rate(annual_rate_pct)
    if r == ZERO:
        return p / Decimal(n)
    with localcontext() as ctx:
        ctx.prec = 34
        growth = (Decimal(1) + r) ** n
        return p * r * growth / (growth - Decimal(1))


def emi(principal: Number, annual_rate_pct: Number, tenure_months: int) -> Decimal:
    """EMI rounded to two decimals.

    >>> emi(100000, 12, 12)
    Decimal('8884.88')
    """
    return round_money(emi_exact(principal, annual_rate_pct, tenure_months))


def total_payable(principal: Number, annual_rate_pct: Number, tenure_months: int) -> Decimal:
    """Sum of all EMIs at the rounded EMI amount (before last-instalment adjustment)."""
    return round_money(emi(principal, annual_rate_pct, tenure_months) * tenure_months)


def total_interest(principal: Number, annual_rate_pct: Number, tenure_months: int) -> Decimal:
    return round_money(
        total_payable(principal, annual_rate_pct, tenure_months) - to_decimal(principal)
    )


def max_principal_for_emi(target_emi: Number, annual_rate_pct: Number, tenure_months: int) -> Decimal:
    """Largest principal whose EMI does not exceed ``target_emi``.

    Rounded *down* to the paisa so the resulting EMI never overshoots the budget.
    """
    budget = require_positive("target_emi", target_emi)
    n = _validate_tenure(tenure_months)
    r = monthly_rate(annual_rate_pct)
    if r == ZERO:
        principal = budget * Decimal(n)
    else:
        with localcontext() as ctx:
            ctx.prec = 34
            growth = (Decimal(1) + r) ** n
            principal = budget * (growth - Decimal(1)) / (r * growth)
    return principal.quantize(CENT, rounding=ROUND_DOWN)
