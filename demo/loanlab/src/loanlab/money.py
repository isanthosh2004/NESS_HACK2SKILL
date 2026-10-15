"""Money helpers shared by every loanlab module.

All public functions in loanlab accept int, float, str or Decimal amounts and
return Decimal values rounded to the paisa/cent (two decimal places) using
ROUND_HALF_UP, which is how lenders round customer-facing amounts.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Union

Number = Union[int, float, str, Decimal]

CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


class LoanError(ValueError):
    """Raised for any invalid loan input (negative amount, bad tenure, ...)."""


def to_decimal(value: Number) -> Decimal:
    """Convert a user-supplied number to Decimal without float artefacts.

    Strings may contain thousands separators ("1,00,000" or "100,000").
    Booleans are rejected because ``True`` silently behaving like ``1`` hides bugs.
    """
    if isinstance(value, bool):
        raise LoanError("boolean is not a valid amount")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(repr(value))
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("_", "")
        if not cleaned:
            raise LoanError("empty string is not a valid amount")
        try:
            result = Decimal(cleaned)
        except InvalidOperation as exc:
            raise LoanError(f"not a number: {value!r}") from exc
    else:
        raise LoanError(f"unsupported amount type: {type(value).__name__}")
    if not result.is_finite():
        raise LoanError(f"amount must be finite, got {value!r}")
    return result


def round_money(value: Number) -> Decimal:
    """Round to two decimal places, half up (2.345 -> 2.35)."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def floor_to(value: Number, step: Number) -> Decimal:
    """Round *down* to a multiple of ``step`` (e.g. floor_to(123456, 1000) -> 123000)."""
    amount = to_decimal(value)
    unit = to_decimal(step)
    if unit <= ZERO:
        raise LoanError("step must be positive")
    return ((amount / unit).to_integral_value(rounding=ROUND_DOWN) * unit).quantize(CENT)


def percent_of(amount: Number, pct: Number) -> Decimal:
    """Unrounded ``pct`` percent of ``amount``."""
    return to_decimal(amount) * to_decimal(pct) / HUNDRED


def require_positive(name: str, value: Number) -> Decimal:
    amount = to_decimal(value)
    if amount <= ZERO:
        raise LoanError(f"{name} must be positive, got {amount}")
    return amount


def require_non_negative(name: str, value: Number) -> Decimal:
    amount = to_decimal(value)
    if amount < ZERO:
        raise LoanError(f"{name} must not be negative, got {amount}")
    return amount


def require_whole_number(name: str, value: int, minimum: int = 0) -> int:
    """Validate counts such as months or days (must be a real int, not a float)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoanError(f"{name} must be a whole number, got {value!r}")
    if value < minimum:
        raise LoanError(f"{name} must be >= {minimum}, got {value}")
    return value
