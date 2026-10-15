"""Amortization schedules for reducing-balance EMI loans."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from .emi import emi, monthly_rate
from .money import ZERO, LoanError, Number, require_positive, require_whole_number, round_money


@dataclass(frozen=True)
class Installment:
    number: int
    opening_balance: Decimal
    payment: Decimal
    interest: Decimal
    principal: Decimal
    closing_balance: Decimal


def amortization_schedule(principal: Number, annual_rate_pct: Number, tenure_months: int) -> List[Installment]:
    """Month-by-month schedule.

    Every month's interest is rounded to the paisa. The final instalment is
    adjusted so the closing balance lands exactly on zero, which means the last
    payment can differ from the regular EMI by a few paise.
    """
    balance = round_money(require_positive("principal", principal))
    payment = emi(balance, annual_rate_pct, tenure_months)
    rate = monthly_rate(annual_rate_pct)
    rows: List[Installment] = []
    for number in range(1, tenure_months + 1):
        interest = round_money(balance * rate)
        if number == tenure_months:
            principal_part = balance
            this_payment = round_money(balance + interest)
        else:
            principal_part = round_money(payment - interest)
            this_payment = payment
        closing = round_money(balance - principal_part)
        rows.append(
            Installment(
                number=number,
                opening_balance=balance,
                payment=this_payment,
                interest=interest,
                principal=principal_part,
                closing_balance=closing,
            )
        )
        balance = closing
    return rows


def outstanding_after(principal: Number, annual_rate_pct: Number, tenure_months: int, payments_made: int) -> Decimal:
    """Principal still owed after ``payments_made`` regular instalments."""
    require_whole_number("payments_made", payments_made)
    if payments_made > tenure_months:
        raise LoanError("payments_made cannot exceed tenure_months")
    if payments_made == 0:
        return round_money(principal)
    schedule = amortization_schedule(principal, annual_rate_pct, tenure_months)
    return schedule[payments_made - 1].closing_balance


def schedule_totals(schedule: List[Installment]) -> dict:
    """Totals across a schedule: amount paid, interest paid, principal repaid."""
    if not schedule:
        raise LoanError("schedule is empty")
    total_paid = sum((row.payment for row in schedule), ZERO)
    total_interest = sum((row.interest for row in schedule), ZERO)
    total_principal = sum((row.principal for row in schedule), ZERO)
    return {
        "total_paid": round_money(total_paid),
        "total_interest": round_money(total_interest),
        "total_principal": round_money(total_principal),
        "instalments": len(schedule),
    }
