"""Azure AI Foundry source adapter: the public Azure Retail Prices API.

Pricing for Foundry models is published (unauthenticated) at prices.azure.com
under `serviceName = 'Foundry Models'`. Meter names there are cryptic and
inconsistent (e.g. 'gpt 4.1 nano cached Inp glbl Tokens', '5.4 opt Dz 1M
Tokens'), so normalization is best-effort and lower fidelity than LiteLLM.

The normalizer is a set of pure functions (unit-testable, no I/O): only per-token
meters (`1K`/`1M`) are kept, Batch/fine-tune/media/hosting meters are dropped, the
input/output/cache meters of one model are merged into a single canonical entry,
and the global-zone price is preferred over regional/data-zone variants.
"""

import json
import re
import urllib.request
import urllib.parse

from pylon.core.tools import log

from .base import CanonicalEntry

SOURCE_ID = "azure_foundry"

_BASE_URL = "https://prices.azure.com/api/retail/prices"
_API_VERSION = "2023-01-01-preview"
_FILTER = "serviceName eq 'Foundry Models' and priceType eq 'Consumption'"
_FETCH_TIMEOUT = 30
_MAX_PAGES = 50

# retailPrice is quoted per this many tokens; divide to get per-token USD.
_UNIT_DIVISOR = {"1K": 1000.0, "1M": 1_000_000.0}

# Meter markers (lowercased word tokens) that mark a variant we don't import as a
# base chat price: batch jobs, fine-tuning, hosting, and media/audio/image meters.
_SKIP_MARKERS = {
    "batch", "ft", "grdr", "hosting", "training", "train",
    "rt", "aud", "audio", "img", "image", "trscb", "trans", "realtime",
    "tts", "whisper", "session", "calls", "megapixel", "unit",
}

# Direction / zone / noise tokens stripped when deriving the model key.
_INPUT_MARKERS = {"inp", "input", "inpt", "in"}
_OUTPUT_MARKERS = {"outp", "output", "outpt", "opt", "out"}
_CACHE_MARKERS = {"cchd", "cached", "cch", "cd"}
_WRITE_MARKERS = {"wr", "write"}
_ZONE_MARKERS = {
    "glbl", "gl", "global", "regnl", "rgnl", "regional", "reg",
    "dz", "dzn", "dzone", "datazone", "data", "zone", "gzone",
}
_NOISE_MARKERS = {"tokens", "token", "pp", "l", "the"}

_STRIP_MARKERS = (
    _INPUT_MARKERS | _OUTPUT_MARKERS | _CACHE_MARKERS
    | _WRITE_MARKERS | _ZONE_MARKERS | _NOISE_MARKERS
)

# Zone preference: prefer a global meter's price over regional / data-zone.
_ZONE_GLOBAL = 3
_ZONE_REGIONAL = 2
_ZONE_DATA = 1
_ZONE_UNKNOWN = 0

_PROVIDER_BY_PRODUCT = (
    ("cohere", "cohere"),
    ("grok", "xai"),
    ("llama", "meta"),
    ("phi", "microsoft"),
    ("kimi", "moonshot"),
    ("qwen", "alibaba"),
    ("mistral", "mistral"),
    ("deepseek", "deepseek"),
    ("flux", "blackforestlabs"),
    ("bfl", "blackforestlabs"),
    ("openai", "azure"),
    ("gpt", "azure"),
)


def _tokens(text: str) -> list:
    return [t for t in re.split(r"[\s\-_/]+", (text or "").lower()) if t]


def _provider_for(product_name: str) -> str:
    pl = (product_name or "").lower()
    for needle, provider in _PROVIDER_BY_PRODUCT:
        if needle in pl:
            return provider
    return "azure"


def _zone_rank(tokens: list) -> int:
    ts = set(tokens)
    if ts & {"glbl", "gl", "global", "gzone"}:
        return _ZONE_GLOBAL
    if ts & {"regnl", "rgnl", "regional", "reg"}:
        return _ZONE_REGIONAL
    if ts & {"dz", "dzn", "dzone", "datazone", "zone"}:
        return _ZONE_DATA
    return _ZONE_UNKNOWN


def _direction(tokens: list):
    """Return 'input' | 'output' | 'cache_read' | 'cache_creation' | None."""
    ts = set(tokens)
    is_cache = bool(ts & _CACHE_MARKERS)
    is_input = bool(ts & _INPUT_MARKERS)
    is_output = bool(ts & _OUTPUT_MARKERS)
    if is_cache and is_input:
        return "cache_creation" if ts & _WRITE_MARKERS else "cache_read"
    if is_input:
        return "input"
    if is_output:
        return "output"
    return None


def _model_key(tokens: list) -> str:
    kept = [t for t in tokens if t not in _STRIP_MARKERS]
    return " ".join(kept).strip()


def _per_token(retail_price, unit_of_measure):
    divisor = _UNIT_DIVISOR.get(unit_of_measure)
    if divisor is None or retail_price is None:
        return None
    try:
        return float(retail_price) / divisor
    except (TypeError, ValueError):
        return None


_DIRECTION_FIELD = {
    "input": "input_cost_per_token",
    "output": "output_cost_per_token",
    "cache_read": "cache_read_input_token_cost",
    "cache_creation": "cache_creation_input_token_cost",
}


def normalize_items(items: list) -> list:
    """Map raw Azure retail-price items into merged canonical entries."""
    groups = {}
    for item in items:
        unit = item.get("unitOfMeasure")
        if unit not in _UNIT_DIVISOR:
            continue
        meter = item.get("meterName") or ""
        sku = item.get("skuName") or meter
        tokens = _tokens(sku)
        if set(tokens) & _SKIP_MARKERS:
            continue
        direction = _direction(tokens)
        if direction is None:
            continue
        price = _per_token(item.get("retailPrice"), unit)
        if price is None:
            continue

        key = _model_key(tokens)
        if not key:
            continue
        provider = _provider_for(item.get("productName"))

        group = groups.get(key)
        if group is None:
            group = {
                "model_name": key,
                "provider": provider,
                "prices": {},          # field -> (zone_rank, value)
                "meters": [],
            }
            groups[key] = group
        rank = _zone_rank(tokens)
        field = _DIRECTION_FIELD[direction]
        prev = group["prices"].get(field)
        if prev is None or rank > prev[0]:
            group["prices"][field] = (rank, price)
        group["meters"].append(meter)

    return [_entry_from_group(g) for g in groups.values()]


def _entry_from_group(group: dict) -> CanonicalEntry:
    prices = {field: val for field, (_, val) in group["prices"].items()}
    return CanonicalEntry(
        model_name=group["model_name"],
        provider=group["provider"],
        mode="chat",
        input_cost_per_token=prices.get("input_cost_per_token"),
        output_cost_per_token=prices.get("output_cost_per_token"),
        cache_read_input_token_cost=prices.get("cache_read_input_token_cost"),
        cache_creation_input_token_cost=prices.get("cache_creation_input_token_cost"),
        aliases=[],
        extra={"meters": group["meters"]},
        source=SOURCE_ID,
        source_ref=group["meters"][0] if group["meters"] else None,
    )


def _fetch_items() -> list:
    url = "{base}?api-version={ver}&$filter={flt}".format(
        base=_BASE_URL,
        ver=_API_VERSION,
        flt=urllib.parse.quote(_FILTER),
    )
    items = []
    pages = 0
    while url and pages < _MAX_PAGES:
        req = urllib.request.Request(url, headers={"User-Agent": "elitea-costs"})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
        items.extend(payload.get("Items", []))
        url = payload.get("NextPageLink")
        pages += 1
    return items


class AzureFoundrySource:
    id = SOURCE_ID

    def fetch(self) -> list:
        items = _fetch_items()
        entries = normalize_items(items)
        log.info("costs.azure_foundry: %d meters -> %d entries", len(items), len(entries))
        return entries
