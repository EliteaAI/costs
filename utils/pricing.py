"""Cost arithmetic — same math as the legacy `model_pricing.compute_llm_cost`,
but sourcing rates from the in-memory cache instead of the vendored JSON.
"""

from . import cache

_COST_SOURCE_TAG = "estimated:costs-catalog"


def compute_llm_cost(model_name, input_tokens, output_tokens,
                     cache_read_input_tokens=0,
                     cache_creation_input_tokens=0):
    """Estimate LLM cost in USD from token counts.

    Returns (cost_usd, cost_source_tag) or (None, None) if the model is unpriced.
    """
    if not model_name or (not input_tokens and not output_tokens):
        return None, None

    entry = cache.get_price(model_name)
    if not entry:
        return None, None

    input_price = entry.get("input_cost_per_token")
    output_price = entry.get("output_cost_per_token")
    if input_price is None and output_price is None:
        return None, None

    input_price = input_price or 0.0
    output_price = output_price or 0.0
    cache_read_price = entry.get("cache_read_input_token_cost")
    cache_create_price = entry.get("cache_creation_input_token_cost")
    if cache_read_price is None:
        cache_read_price = input_price
    if cache_create_price is None:
        cache_create_price = input_price

    cost = (
        (input_tokens or 0) * input_price
        + (output_tokens or 0) * output_price
        + (cache_read_input_tokens or 0) * cache_read_price
        + (cache_creation_input_tokens or 0) * cache_create_price
    )
    return cost, _COST_SOURCE_TAG
