"""Default (optional) source adapter: LiteLLM's public pricing JSON.

LiteLLM is just one registered source among equals — disabling it must not
break the plugin. The normalizer `normalize_entry` is a pure function so the
same mapping is reused to generate the bundled seed offline.
"""

import json
import urllib.request

from pylon.core.tools import log

from .base import CanonicalEntry

SOURCE_ID = "litellm"
_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
_FETCH_TIMEOUT = 30


def normalize_entry(key: str, raw: dict) -> CanonicalEntry:
    """Map one LiteLLM `{model_key: {...}}` pair into a canonical entry."""
    return CanonicalEntry(
        model_name=key,
        provider=raw.get("litellm_provider"),
        mode=raw.get("mode"),
        input_cost_per_token=raw.get("input_cost_per_token"),
        output_cost_per_token=raw.get("output_cost_per_token"),
        cache_read_input_token_cost=raw.get("cache_read_input_token_cost"),
        cache_creation_input_token_cost=raw.get("cache_creation_input_token_cost"),
        max_input_tokens=_as_int(raw.get("max_input_tokens")),
        max_output_tokens=_as_int(raw.get("max_output_tokens")),
        aliases=[],
        extra=dict(raw),
        source=SOURCE_ID,
        source_ref=key,
    )


def normalize_catalog(catalog: dict) -> list:
    """Map a full LiteLLM catalog dict into canonical entries (drops sample_spec)."""
    entries = []
    for key, raw in catalog.items():
        if key == "sample_spec" or not isinstance(raw, dict):
            continue
        entries.append(normalize_entry(key, raw))
    return entries


class LiteLLMSource:
    id = SOURCE_ID

    def fetch(self) -> list:
        req = urllib.request.Request(_URL, headers={"User-Agent": "elitea-costs"})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:  # nosec B310
            catalog = json.loads(resp.read().decode("utf-8"))
        entries = normalize_catalog(catalog)
        log.info("costs.litellm: fetched %d entries", len(entries))
        return entries


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
