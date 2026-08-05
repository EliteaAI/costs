"""Offline fallback / first-run seed: the bundled canonical dump.

`data/prices_seed.json` is a plain canonical dump (schema `elitea-costs-canonical/v1`),
not tied to any provider format. Used to seed an empty catalog and as the fallback
when the configured source is unreachable (air-gapped / no-internet deployments).
"""

import json
import os

from pylon.core.tools import log

from .base import CanonicalEntry

SOURCE_ID = "bundled"
_SEED_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "prices_seed.json")

_CANONICAL_FIELDS = {
    "model_name", "provider", "mode",
    "input_cost_per_token", "output_cost_per_token",
    "cache_read_input_token_cost", "cache_creation_input_token_cost",
    "max_input_tokens", "max_output_tokens",
    "aliases", "extra", "source", "source_ref",
}


def _entry_from_dict(d: dict) -> CanonicalEntry:
    kwargs = {k: v for k, v in d.items() if k in _CANONICAL_FIELDS}
    kwargs.setdefault("source", SOURCE_ID)
    return CanonicalEntry(**kwargs)


class BundledSource:
    id = SOURCE_ID

    def fetch(self) -> list:
        try:
            with open(_SEED_PATH, "r") as f:
                payload = json.load(f)
        except (OSError, ValueError) as e:
            log.error("costs.bundled: failed to load %s: %s", _SEED_PATH, e)
            return []
        entries = [_entry_from_dict(d) for d in payload.get("entries", [])]
        log.info("costs.bundled: loaded %d entries", len(entries))
        return entries
