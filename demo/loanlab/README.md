# loanlab

A small, dependency-free Python library for loan maths: EMI, amortization
schedules, interest accrual, late/processing/prepayment fees and borrower
eligibility (FOIR + credit-score bands).

```bash
pip install pytest
python -m pytest          # runs tests/ in a couple of seconds
```

```python
from loanlab import emi, late_fee
emi(100000, 12, 12)      # Decimal('8884.88')
late_fee(10000, 6)       # Decimal('200.00')
```

All amounts are `Decimal`, rounded half-up to two places.

Changes to `main` go through pull requests only.
