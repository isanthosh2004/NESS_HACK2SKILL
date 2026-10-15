"""Interest helpers: simple interest, compounding and day-count accrual."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext

from .money import (
    HUNDRED,
    LoanError,
    Number,
    require_non_negative,
    require_whole_number,
    round_money,
    to_decimal,
)

DAY_COUNT_BASES = (360, 365)


def days_between(start: date, end: date) -> int:
    """Actual number of days from ``start`` to ``end`` (end exclusive)."""
    if not isinstance(start, date) or not isinstance(end, date):
        raise LoanError("start and end must be dates")
    if end < start:
        raise LoanError("end date is before start date")
    return (end - start).days


def simple_interest(principal: Number, annual_rate_pct: Number, days: int, day_count: int = 365) -> Decimal:
    """Simple interest for ``days`` days on an actual/``day_count`` basis."""
    p = require_non_negative("principal", principal)
    rate = require_non_negative("annual_rate_pct", annual_rate_pct)
    require_whole_number("days", days)
    if day_count not in DAY_COUNT_BASES:
        raise LoanError(f"day_count must be one of {DAY_COUNT_BASES}")
    return round_money(p * rate * Decimal(days) / (HUNDRED * Decimal(day_count)))


def accrued_interest(balance: Number, annual_rate_pct: Number, start: date, end: date) -> Decimal:
    """Interest accrued on a constant balance between two dates (actual/365)."""
    return simple_interest(balance, annual_rate_pct, days_between(start, end))


def compound_amount(principal: Number, annual_rate_pct: Number, years: int, periods_per_year: int = 12) -> Decimal:
    """Maturity value with periodic compounding: P * (1 + i/m)^(m*t)."""
    p = require_non_negative("principal", principal)
    rate = require_non_negative("annual_rate_pct", annual_rate_pct)
    require_whole_number("years", years)
    require_whole_number("periods_per_year", periods_per_year, minimum=1)
    with localcontext() as ctx:
        ctx.prec = 34
        factor = (Decimal(1) + rate / (HUNDRED * periods_per_year)) ** (years * periods_per_year)
        return round_money(p * factor)


def compound_interest(principal: Number, annual_rate_pct: Number, years: int, periods_per_year: int = 12) -> Decimal:
    return round_money(compound_amount(principal, annual_rate_pct, years, periods_per_year) - to_decimal(principal))


def effective_annual_rate(nominal_rate_pct: Number, periods_per_year: int = 12) -> Decimal:
    """Effective annual rate in percent, to four decimals (12% monthly -> 12.6825)."""
    rate = require_non_negative("nominal_rate_pct", nominal_rate_pct)
    require_whole_number("periods_per_year", periods_per_year, minimum=1)
    with localcontext() as ctx:
        ctx.prec = 34
        ear = ((Decimal(1) + rate / (HUNDRED * periods_per_year)) ** periods_per_year - 1) * HUNDRED
    return ear.quantize(Decimal("0.0001"))
