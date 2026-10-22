"""ERP-neutral cost-code staging, independent of commercial ERP products."""
from decimal import Decimal, InvalidOperation


def scaled_integer(value, scale):
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal') from exc
    if not number.is_finite() or number < 0:
        raise ValueError('Finite non-negative value required')
    scaled = number * scale
    if scaled != scaled.to_integral_value() or scaled > 9_000_000_000_000_000:
        raise ValueError('Unsupported precision or magnitude')
    return int(scaled)


def stage_boq(rows, project_id, code_mapping):
    """Validate all source rows before import. An error blocks the full batch."""
    staged, errors, seen = [], [], set()
    for index, row in enumerate(rows, 1):
        try:
            source = row['source_code'].strip()
            target = code_mapping.get(source)
            if not target:
                raise ValueError('Unmapped source code: ' + source)
            if target in seen:
                raise ValueError('Multiple source rows map to ' + target)
            if row['unit'] not in ('m', 'm2', 'm3', 'kg', 't', 'each', 'day'):
                raise ValueError('Unsupported unit')
            quantity = scaled_integer(row['quantity'], 1000)
            rate = scaled_integer(row['unit_rate'], 100)
            seen.add(target)
            staged.append((project_id, target, row['unit'], quantity, rate))
        except (KeyError, ValueError, AttributeError, TypeError) as exc:
            errors.append({'row': index, 'error': str(exc)})
    return {'ready': bool(staged) and not errors, 'rows': staged, 'errors': errors}


def load_boq(db, staged):
    if not staged['ready'] or staged['errors']:
        raise ValueError('Staging exceptions must be resolved before loading')
    with db:
        db.executemany('INSERT INTO boq VALUES (?,?,?,?,?)', staged['rows'])
    return len(staged['rows'])
