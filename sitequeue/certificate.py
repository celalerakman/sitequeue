"""Explicit decimal arithmetic for cumulative construction payment certificates."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal('0.01')


def number(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Expected a finite non-negative number')
    return result


def money(value):
    return number(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Item:
    code: str
    contract_quantity: Decimal
    previous_quantity: Decimal
    claimed_quantity: Decimal
    measured_quantity: Decimal
    unit_rate: Decimal

    @classmethod
    def from_dict(cls, row):
        if not str(row['code']).strip():
            raise ValueError('Item code required')
        return cls(str(row['code']), *(number(row[key]) for key in (
            'contract_quantity', 'previous_quantity', 'claimed_quantity',
            'measured_quantity', 'unit_rate')))


def certify(rows, retention='0.05', tax='0.20', previous_net='0'):
    """Quantities are cumulative. Net due is cumulative less earlier net certificates.

    This demo applies tax AFTER retention; contract/jurisdiction rules may differ.
    Negative net due is retained as a credit, never silently clamped to zero.
    """
    retention, tax = number(retention), number(tax)
    if retention > 1 or tax > 1:
        raise ValueError('Rates must be between zero and one')
    lines, seen = [], set()
    for row in rows:
        item = Item.from_dict(row)
        if item.code in seen:
            raise ValueError('Duplicate item code: ' + item.code)
        seen.add(item.code)
        if item.previous_quantity > item.contract_quantity:
            raise ValueError('Previous quantity exceeds contract')
        approved = min(item.contract_quantity, item.claimed_quantity, item.measured_quantity)
        if approved < item.previous_quantity:
            raise ValueError('Cumulative quantity regression requires a separate correction')
        lines.append({
            'code': item.code, 'approved_quantity': str(approved),
            'period_quantity': str(approved - item.previous_quantity),
            'held_quantity': str(item.claimed_quantity - approved),
            'cumulative_gross': str(money(approved * item.unit_rate)),
            'period_gross': str(money((approved - item.previous_quantity) * item.unit_rate)),
        })
    gross = sum((Decimal(line['cumulative_gross']) for line in lines), Decimal(0))
    retained = money(gross * retention)
    taxable = gross - retained
    taxes = money(taxable * tax)
    return {'lines': lines, 'gross': str(money(gross)), 'retention': str(retained),
            'tax': str(taxes), 'cumulative_net': str(money(taxable + taxes)),
            'net_due': str((taxable + taxes - money(previous_net)).quantize(CENT))}


def earned_value(planned, earned, actual):
    planned, earned, actual = map(number, (planned, earned, actual))
    return {'cost_variance': str(earned - actual), 'schedule_variance': str(earned - planned),
            'cpi': str(earned / actual) if actual else None,
            'spi': str(earned / planned) if planned else None}


def cash_forecast(opening, periods):
    balance = number(opening)
    result = []
    for period in periods:
        balance += number(period['inflow']) - number(period['outflow'])
        result.append({'period': period['period'], 'closing': str(balance), 'shortfall': balance < 0})
    return result
