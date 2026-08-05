"""Internal read RPCs — for the future cutover of the legacy `model_pricing`
consumers (M5). Served entirely from the in-memory cache.
"""

from pylon.core.tools import web

from ..utils import cache, pricing


class RPC:
    @web.rpc("costs_get_model_price", "get_model_price")
    def get_model_price(self, model_name: str, **kwargs):
        return cache.get_price(model_name)

    @web.rpc("costs_get_all_prices", "get_all_prices")
    def get_all_prices(self, **kwargs) -> dict:
        return cache.all_prices()

    @web.rpc("costs_compute_llm_cost", "compute_llm_cost")
    def compute_llm_cost(self, model_name, input_tokens, output_tokens,
                         cache_read_input_tokens=0,
                         cache_creation_input_tokens=0, **kwargs):
        cost, tag = pricing.compute_llm_cost(
            model_name, input_tokens, output_tokens,
            cache_read_input_tokens, cache_creation_input_tokens,
        )
        return {"cost": cost, "cost_source": tag}
