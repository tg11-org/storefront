from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


TWOPLACES = Decimal('0.01')


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def amount_to_cents(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal('1')))


def cents_to_money(amount: int) -> Decimal:
    return money(Decimal(amount) / Decimal('100'))
