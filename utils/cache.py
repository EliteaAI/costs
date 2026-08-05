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

# Provider prefixes stripped when the exact model_name isn't found. Region
# prefixes (us./eu./apac./ca.) are the Bedrock inference-profile convention.
_STRIP_PREFIXES = (
    "openai/", "azure/", "anthropic/", "bedrock/", "vertex_ai/", "gemini/",
    "us.", "eu.", "apac.", "ca.",
)

_lock = threading.Lock()
_by_name = None      # {model_name: price_dict}
_alias_index = None  # {alias: model_name}
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
    return by_name, alias_index


def _ensure_loaded():
    global _by_name, _alias_index, _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _by_name, _alias_index = _build()
        _loaded = True


def reload():
    """Invalidate and rebuild the cache from the DB."""
    global _by_name, _alias_index, _loaded
    with _lock:
        _by_name, _alias_index = _build()
        _loaded = True


def get_price(model_name: str):
    """Return the effective price dict for a model, or None."""
    if not model_name:
        return None
    _ensure_loaded()
    if model_name in _by_name:
        return _by_name[model_name]
    lowered = model_name.lower()
    if lowered in _by_name:
        return _by_name[lowered]
    for prefix in _STRIP_PREFIXES:
        if model_name.startswith(prefix):
            stripped = model_name[len(prefix):]
            if stripped in _by_name:
                return _by_name[stripped]
        if lowered.startswith(prefix):
            stripped = lowered[len(prefix):]
            if stripped in _by_name:
                return _by_name[stripped]
    resolved = _alias_index.get(model_name) or _alias_index.get(lowered)
    if resolved:
        return _by_name.get(resolved)
    return None


def all_prices() -> dict:
    _ensure_loaded()
    return dict(_by_name)


def count() -> int:
    _ensure_loaded()
    return len(_by_name)


def _f(value):
    return float(value) if value is not None else None
