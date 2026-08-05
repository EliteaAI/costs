"""Catalog upsert — applies canonical entries to `centry.model_prices`.

The upsert rule is the heart of the design:
- row missing              -> INSERT (is_custom=false, source=<adapter id>)
- row exists, not custom    -> UPDATE effective price cols + extra + base_snapshot
- row exists, is_custom     -> UPDATE base_snapshot ONLY (effective prices untouched)
- custom rows are never deleted by an import.
"""

from pylon.core.tools import log

from .base_snapshot import snapshot_from_entry

_CUSTOM_SOURCE = "custom"
_PRICE_FIELDS = (
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "cache_creation_input_token_cost",
)
_META_FIELDS = ("provider", "mode", "max_input_tokens", "max_output_tokens")


def _apply_import_fields(row, entry, source_id):
    row.provider = entry.provider
    row.mode = entry.mode
    row.input_cost_per_token = entry.input_cost_per_token
    row.output_cost_per_token = entry.output_cost_per_token
    row.cache_read_input_token_cost = entry.cache_read_input_token_cost
    row.cache_creation_input_token_cost = entry.cache_creation_input_token_cost
    row.max_input_tokens = entry.max_input_tokens
    row.max_output_tokens = entry.max_output_tokens
    row.aliases = entry.aliases or []
    row.extra = entry.extra or {}
    row.source = entry.source or source_id
    row.source_ref = entry.source_ref


def upsert_entries(entries: list, source_id: str) -> dict:
    """Apply canonical entries. Returns counts {inserted, updated, preserved}."""
    from tools import db
    from ..models.model_price import ModelPrice

    inserted = updated = preserved = 0
    with db.with_project_schema_session(None) as session:
        existing = {r.model_name: r for r in session.query(ModelPrice).all()}
        for entry in entries:
            if not entry.model_name:
                continue
            row = existing.get(entry.model_name)
            snap = snapshot_from_entry(entry)
            if row is None:
                row = ModelPrice(model_name=entry.model_name, is_custom=False)
                _apply_import_fields(row, entry, source_id)
                row.base_snapshot = snap
                session.add(row)
                inserted += 1
            elif row.is_custom:
                # Never overwrite an admin override's effective prices.
                row.base_snapshot = snap
                preserved += 1
            else:
                _apply_import_fields(row, entry, source_id)
                row.base_snapshot = snap
                updated += 1
        session.commit()
    counts = {"inserted": inserted, "updated": updated, "preserved": preserved}
    log.info("costs.catalog: upsert from %r -> %s", source_id, counts)
    return counts


def set_custom_price(model_name: str, values: dict):
    """Create or overwrite a custom (admin) price for a model.

    Marks the row `is_custom=true`, writes the provided fields, and preserves an
    existing `base_snapshot` (or snapshots current imported values if absent).
    Returns the row's json, or None if creating without any price given.
    """
    from tools import db
    from .base_snapshot import snapshot_from_row
    from ..models.model_price import ModelPrice

    with db.with_project_schema_session(None) as session:
        row = session.query(ModelPrice).filter(ModelPrice.model_name == model_name).first()
        if row is None:
            row = ModelPrice(model_name=model_name, extra={})
            session.add(row)
            base = None
        else:
            base = row.base_snapshot or snapshot_from_row(row)
        _apply_custom_fields(row, values)
        row.is_custom = True
        row.source = _CUSTOM_SOURCE
        if base is not None:
            row.base_snapshot = base
        session.commit()
        result = row.to_json()
    return result


def reset_custom_price(model_name: str):
    """Reset a custom override back to imported defaults.

    Restores price/meta columns from `base_snapshot` and clears `is_custom`.
    If the row has no `base_snapshot` (custom-only, never imported), delete it.
    Returns a dict describing the action, or None if the row does not exist.
    """
    from tools import db
    from ..models.model_price import ModelPrice

    with db.with_project_schema_session(None) as session:
        row = session.query(ModelPrice).filter(ModelPrice.model_name == model_name).first()
        if row is None:
            return None
        snap = row.base_snapshot
        if not snap:
            session.delete(row)
            session.commit()
            return {"model_name": model_name, "action": "deleted"}
        for f in _PRICE_FIELDS + _META_FIELDS:
            if f in snap:
                setattr(row, f, snap[f])
        row.is_custom = False
        session.commit()
        result = row.to_json()
        result["action"] = "reset"
        return result


def _apply_custom_fields(row, values: dict):
    for f in _PRICE_FIELDS + _META_FIELDS:
        if f in values and values[f] is not None:
            setattr(row, f, values[f])
