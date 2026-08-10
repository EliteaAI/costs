"""AWS Bedrock source adapter: the public AWS Price List Bulk API.

Bedrock pricing is published (unauthenticated) as a single JSON offer file per
region. Unlike Azure, the feed is clean: `attributes.inferenceType` names the
token direction directly and `attributes.feature` isolates on-demand inference
from Batch / Provisioned / Customization, so the normalizer maps rather than
guesses.

Only base on-demand token meters (`feature == 'On-demand Inference'`, region
us-east-1) are imported; Batch, Provisioned, latency-optimized, priority and flex
variants and all non-token meters (image/video/audio/per-hour) are dropped.

The pricing feed carries a display name ("Claude 3 Haiku"), not the canonical
Bedrock model id ("anthropic.claude-3-haiku-20240307-v1:0"), so a provider-
prefixed slug plus a few aliases are emitted for best-effort matching.
"""

import json
import re
import urllib.request

from pylon.core.tools import log

from .base import CanonicalEntry

SOURCE_ID = "bedrock"

_REGION = "us-east-1"
_URL = (
    "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock"
    "/current/{region}/index.json".format(region=_REGION)
)
_FETCH_TIMEOUT = 30

_FEATURE_ON_DEMAND = "On-demand Inference"

# pricePerUnit is quoted per this many tokens; divide to get per-token USD.
_UNIT_DIVISOR = {"1K tokens": 1000.0, "1M tokens": 1_000_000.0}

# Exact inferenceType -> canonical cost field. Anything not listed here
# (priority/flex/batch variants, image/video/audio meters) is skipped.
_DIRECTION_FIELD = {
    "Input tokens": "input_cost_per_token",
    "Output tokens": "output_cost_per_token",
    "Text Input Token": "input_cost_per_token",
    "Text output token": "output_cost_per_token",
    "Prompt cache read input tokens": "cache_read_input_token_cost",
    "Prompt cache write input tokens": "cache_creation_input_token_cost",
}

_PROVIDER_SLUG = {
    "anthropic": "anthropic",
    "meta": "meta",
    "mistral": "mistral",
    "mistral ai": "mistral",
    "amazon": "amazon",
    "cohere": "cohere",
    "ai21 labs": "ai21",
    "ai21": "ai21",
    "stability ai": "stability",
    "google": "google",
    "deepseek": "deepseek",
    "openai": "openai",
    "qwen": "qwen",
    "nvidia": "nvidia",
    "writer": "writer",
    "moonshot ai": "moonshot",
    "kimi ai": "moonshot",
    "minimax ai": "minimax",
    "z ai": "zai",
}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def _provider_slug(provider, model_display) -> str:
    if provider:
        key = provider.strip().lower()
        if key in _PROVIDER_SLUG:
            return _PROVIDER_SLUG[key]
        return _slug(provider).split("-")[0] or SOURCE_ID
    # Bedrock's own models (Nova, Titan) carry no provider attribute.
    md = (model_display or "").lower()
    if md.startswith("nova") or md.startswith("titan"):
        return "amazon"
    return SOURCE_ID


def _model_key(provider_slug: str, model_display: str) -> str:
    return "{p}.{m}".format(p=provider_slug, m=_slug(model_display))


def _aliases(provider_slug: str, model_display: str, usagetype: str) -> list:
    key = _model_key(provider_slug, model_display)
    candidates = [
        _slug(model_display),
        "bedrock/{key}".format(key=key),
        _slug(usagetype),
    ]
    seen = {key}
    aliases = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            aliases.append(c)
    return aliases


def _per_token(price_per_unit: dict, unit: str):
    divisor = _UNIT_DIVISOR.get(unit)
    usd = (price_per_unit or {}).get("USD")
    if divisor is None or usd is None:
        return None
    try:
        return float(usd) / divisor
    except (TypeError, ValueError):
        return None


def _first_price_dimension(term: dict):
    """First priceDimension across the first OnDemand offer of a SKU."""
    for offer in (term or {}).values():
        for dim in (offer.get("priceDimensions") or {}).values():
            return dim
    return None


def normalize_products(products: dict, on_demand_terms: dict) -> list:
    """Map raw AWS Price List products into merged canonical entries."""
    groups = {}
    for sku, product in (products or {}).items():
        attrs = product.get("attributes") or {}
        if attrs.get("feature") != _FEATURE_ON_DEMAND:
            continue
        field = _DIRECTION_FIELD.get(attrs.get("inferenceType"))
        if field is None:
            continue

        dim = _first_price_dimension(on_demand_terms.get(sku))
        if dim is None:
            continue
        unit = dim.get("unit")
        if unit not in _UNIT_DIVISOR:
            continue
        price = _per_token(dim.get("pricePerUnit"), unit)
        if price is None:
            continue

        model_display = attrs.get("model") or ""
        provider = _provider_slug(attrs.get("provider"), model_display)
        key = _model_key(provider, model_display)
        usagetype = attrs.get("usagetype") or ""

        group = groups.get(key)
        if group is None:
            group = {
                "model_name": key,
                "provider": provider,
                "model_display": model_display,
                "usagetype": usagetype,
                "prices": {},
            }
            groups[key] = group
        # First price wins per field (feed has one on-demand meter per direction).
        group["prices"].setdefault(field, price)

    return [_entry_from_group(g) for g in groups.values()]


def _entry_from_group(group: dict) -> CanonicalEntry:
    prices = group["prices"]
    return CanonicalEntry(
        model_name=group["model_name"],
        provider=group["provider"],
        mode="chat",
        input_cost_per_token=prices.get("input_cost_per_token"),
        output_cost_per_token=prices.get("output_cost_per_token"),
        cache_read_input_token_cost=prices.get("cache_read_input_token_cost"),
        cache_creation_input_token_cost=prices.get("cache_creation_input_token_cost"),
        aliases=_aliases(group["provider"], group["model_display"], group["usagetype"]),
        extra={"model": group["model_display"], "region": _REGION},
        source=SOURCE_ID,
        source_ref=group["usagetype"] or None,
    )


def _fetch_offer() -> dict:
    req = urllib.request.Request(_URL, headers={"User-Agent": "elitea-costs"})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


class BedrockSource:
    id = SOURCE_ID

    def fetch(self) -> list:
        offer = _fetch_offer()
        products = offer.get("products") or {}
        on_demand = (offer.get("terms") or {}).get("OnDemand") or {}
        entries = normalize_products(products, on_demand)
        log.info("costs.bedrock: %d products -> %d entries", len(products), len(entries))
        return entries
