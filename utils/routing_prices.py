"""Allowlisted exact-model snapshots for routing; existing billing is unchanged."""
import copy
import hashlib
import json
import re

RATES = ('input_cost_per_token', 'output_cost_per_token',
         'cache_read_input_token_cost', 'cache_creation_input_token_cost')
TIER = re.compile(r'^(input_cost_per_token|output_cost_per_token|cache_read_input_token_cost|cache_creation_input_token_cost)_above_\d+k_tokens$')


def projection(row):
    """Expose rate evidence only; never forward arbitrary imported metadata."""
    return {
        'model_name': row.model_name, 'provider': row.provider, 'mode': row.mode,
        **{name: str(getattr(row, name)) if getattr(row, name) is not None else None for name in RATES},
        'is_custom': row.is_custom, 'source': row.source, 'source_ref': row.source_ref,
        'extra': {key: copy.deepcopy(value) for key, value in (row.extra or {}).items() if TIER.fullmatch(key)},
    }


def snapshot(model_names, by_name):
    if (not isinstance(model_names, list) or len(model_names) > 64
            or any(not isinstance(name, str) or not 1 <= len(name) <= 256 for name in model_names)
            or len(set(model_names)) != len(model_names)):
        raise ValueError('Supply at most 64 unique exact model names')
    entries = []
    missing = []
    for name in sorted(model_names):
        value = (by_name.get(name) or {}).get('routing_price')
        if value is None:
            missing.append(name)
        else:
            entries.append(copy.deepcopy(value))
    content = {'entries': entries, 'missing': missing, 'match': 'exact', 'unit': 'USD per token'}
    content['revision'] = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return content
