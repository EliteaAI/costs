""" Per-unit prices for paid SDK tools (`tool_pricing.<backend>.usd_per_<unit>`) """

COST_SOURCE = "estimated:costs-tool-config"


def tool_rate(config, backend, unit):
    pricing = ((config or {}).get("tool_pricing") or {}).get(backend) or {}
    rate = pricing.get(f"usd_per_{unit}")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
        return None
    return float(rate)


def compute_tool_cost(config, backend, units, unit):
    rate = tool_rate(config, backend, unit)
    if rate is None:
        return {"cost": None, "cost_source": None, "rate": None, "unit": unit}
    return {"cost": max(float(units or 0), 0.0) * rate, "cost_source": COST_SOURCE, "rate": rate, "unit": unit}
