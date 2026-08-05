"""Helpers for the `base_snapshot` column — the last imported values, used to
reset a custom price back to the imported default.
"""

_SNAPSHOT_FIELDS = (
    "provider",
    "mode",
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "cache_creation_input_token_cost",
    "max_input_tokens",
    "max_output_tokens",
)


def snapshot_from_entry(entry) -> dict:
    return {f: getattr(entry, f) for f in _SNAPSHOT_FIELDS}


def snapshot_from_row(row) -> dict:
    snap = {}
    for f in _SNAPSHOT_FIELDS:
        val = getattr(row, f)
        if f.endswith("_token") or f.endswith("_cost"):
            snap[f] = float(val) if val is not None else None
        else:
            snap[f] = val
    return snap
