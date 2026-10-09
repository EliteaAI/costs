"""In-memory price cache — the whole catalog held in a process-wide dict.

Reads are served from memory; the DB is only touched on `reload()` (called after
a CRUD write or a catalog refresh). Double-checked locking mirrors the engine
cache in `elitea_core/utils/application_tools.py`.

Lookup mirrors the legacy `model_pricing._lookup`: exact -> lowercase -> strip
common provider prefixes, then fall back to per-entry aliases. This matching is
generic; it is not a LiteLLM dependency.
"""

import threading

from pylon.core.tools import log
from .routing_prices import build_family_index, projection, resolve_name, snapshot

_lock = threading.Lock()
_by_name = None      # {model_name: price_dict}
_alias_index = None  # {alias: model_name}
_family_index = None  # {family_key: [model_name]} for alias-labelled routing fallback
_loaded = False


def _price_dict(row) -> dict:
    return {
        "model_name": row.model_name,
        "provider": row.provider,
        "mode": row.mode,
        "input_cost_per_token": _f(row.input_cost_per_token),
        "output_cost_per_token": _f(row.output_cost_per_token),
        "cache_read_input_token_cost": _f(row.cache_read_input_token_cost),
        "cache_creation_input_token_cost": _f(row.cache_creation_input_token_cost),
        "is_custom": row.is_custom,
        "routing_price": projection(row),
    }


def _build():
    from tools import db
    from ..models.model_price import ModelPrice

    by_name = {}
    alias_index = {}
    with db.with_project_schema_session(None) as session:
        for row in session.query(ModelPrice).all():
            pd = _price_dict(row)
            by_name[row.model_name] = pd
            for alias in (row.aliases or []):
                if alias:
                    alias_index[alias] = row.model_name
    log.info("costs.cache: loaded %d models", len(by_name))
    return by_name, alias_index, build_family_index(by_name, alias_index)


def _ensure_loaded():
    global _by_name, _alias_index, _family_index, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _by_name, _alias_index, _family_index = _build()
        _loaded = True


def reload():
    """Invalidate and rebuild the cache from the DB."""
    global _by_name, _alias_index, _family_index, _loaded
    with _lock:
        _by_name, _alias_index, _family_index = _build()
        _loaded = True


def get_price(model_name: str):
    """Return the effective price dict for a model, or None."""
    if not model_name:
        return None
    _ensure_loaded()
    key = resolve_name(model_name, _by_name, _alias_index)
    return _by_name[key] if key is not None else None


def all_prices() -> dict:
    _ensure_loaded()
    return dict(_by_name)


def routing_prices(model_names, canonical_by_name=None):
    """One immutable-by-copy snapshot; exact names preserve regional prices.

    Exact always wins. Only when the caller supplies `canonical_by_name` may a missing name be
    filled from an alias, and the entry is then labelled `match: 'alias'`."""
    _ensure_loaded()
    current, aliases, families = _by_name, _alias_index, _family_index
    return snapshot(model_names, current, canonical_by_name, aliases, families)


def count() -> int:
    _ensure_loaded()
    return len(_by_name)


def _f(value):
    return float(value) if value is not None else None
