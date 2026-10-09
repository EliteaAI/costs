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


# Provider prefixes stripped when the exact model_name isn't found. Region
# prefixes (us./eu./apac./ca.) are the Bedrock inference-profile convention.
STRIP_PREFIXES = (
    "openai/", "azure/", "anthropic/", "bedrock/", "vertex_ai/", "gemini/",
    "us.", "eu.", "apac.", "ca.",
)
# Wider set used only to compare a canonical family against catalog names.
_FAMILY_PREFIX = re.compile(
    r'^(?:(?:openai|azure|anthropic|bedrock|vertex_ai|gemini|google)/'
    r'|(?:global|us|eu|apac|ca|au|jp|openai|anthropic|amazon|meta|google)\.)')


def resolve_name(name, by_name, alias_index):
    """Catalog key for `name`: exact -> lowercase -> provider prefix stripped -> alias."""
    if name in by_name:
        return name
    lowered = name.lower()
    if lowered in by_name:
        return lowered
    for prefix in STRIP_PREFIXES:
        if name.startswith(prefix) and name[len(prefix):] in by_name:
            return name[len(prefix):]
        if lowered.startswith(prefix) and lowered[len(prefix):] in by_name:
            return lowered[len(prefix):]
    resolved = alias_index.get(name) or alias_index.get(lowered)
    return resolved if resolved in by_name else None


def family_key(name):
    """Comparable form of a model name: lowercase, provider/region prefixes dropped, `.`/`_` -> `-`."""
    name = name.lower()
    while True:
        stripped = _FAMILY_PREFIX.sub('', name, count=1)
        if stripped == name:
            return name.replace('.', '-').replace('_', '-')
        name = stripped


def build_family_index(by_name, alias_index):
    """{family_key: sorted catalog names}; aliases index the row they point at."""
    index = {}
    for key, target in [(name, name) for name in by_name] + list(alias_index.items()):
        if target in by_name:
            index.setdefault(family_key(key), set()).add(target)
    return {family: sorted(names) for family, names in index.items()}


def _check_canonical(canonical_by_name):
    if canonical_by_name is None:
        return
    if (not isinstance(canonical_by_name, dict) or len(canonical_by_name) > 64
            or any(not isinstance(key, str) or not isinstance(value, str) or not 1 <= len(key) <= 256
                   or not 1 <= len(value) <= 256 for key, value in canonical_by_name.items())):
        raise ValueError('canonical_by_name must map at most 64 model names to canonical identities')


def _alias_fallback(name, canonical, by_name, alias_index, family_index):
    """Catalog key for a missing exact name, or None. An ambiguous family never guesses."""
    hit = resolve_name(name, by_name, alias_index)
    if hit is not None:
        return hit
    family = family_key(canonical.rsplit('/', 1)[-1])
    candidates = family_index.get(family, ()) if family else ()
    return candidates[0] if len(candidates) == 1 else None


def snapshot(model_names, by_name, canonical_by_name=None, alias_index=None, family_index=None):
    """Exact-name snapshot. Exact always wins; with `canonical_by_name` a missing name may be filled
    from an alias and is then labelled `match: 'alias'` with the catalog row it came from."""
    if (not isinstance(model_names, list) or len(model_names) > 64
            or any(not isinstance(name, str) or not 1 <= len(name) <= 256 for name in model_names)
            or len(set(model_names)) != len(model_names)):
        raise ValueError('Supply at most 64 unique exact model names')
    _check_canonical(canonical_by_name)
    alias_index = alias_index or {}
    entries = []
    missing = []
    for name in sorted(model_names):
        value = (by_name.get(name) or {}).get('routing_price')
        if value is not None:
            value = copy.deepcopy(value)
            if canonical_by_name is not None:
                value['match'] = 'exact'
        elif canonical_by_name is not None and name in canonical_by_name:
            if family_index is None:
                family_index = build_family_index(by_name, alias_index)
            matched = _alias_fallback(name, canonical_by_name[name], by_name, alias_index, family_index)
            value = (by_name.get(matched) or {}).get('routing_price') if matched else None
            if value is not None:
                value = copy.deepcopy(value)
                value.update({'model_name': name, 'match': 'alias', 'matched_name': matched})
        if value is None:
            missing.append(name)
        else:
            entries.append(value)
    content = {'entries': entries, 'missing': missing, 'match': 'exact', 'unit': 'USD per token'}
    content['revision'] = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return content
