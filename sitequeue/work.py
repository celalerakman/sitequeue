"""Deterministic job handlers. Retry-safe work has no external side effects."""
from .certificate import certify
from .staging import stage_boq
from .queue import artifact_result


def execute(payload):
    if not isinstance(payload, dict):
        raise ValueError('Job payload must be an object')
    kind = payload.get('kind', 'fingerprint')
    data = payload.get('data', payload)
    if kind == 'certificate':
        return {'kind': kind, 'certificate': certify(**data)}
    if kind == 'erp-stage':
        return {'kind': kind, 'staging': stage_boq(**data)}
    if kind == 'fingerprint':
        return {'kind': kind, **artifact_result(data)}
    raise ValueError('Unsupported job kind: ' + str(kind))
