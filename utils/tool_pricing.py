""" Per-unit prices for paid SDK tools (`tool_pricing.<backend>.usd_per_<unit>`) """

import math

COST_SOURCE = "estimated:costs-tool-config"


def tool_rate(config, backend, unit):
    pricing = ((config or {}).get("tool_pricing") or {}).get(backend) or {}
    rate = pricing.get(f"usd_per_{unit}")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
        return None
    return float(rate)


def compute_tool_cost(config, backend, units, unit):
    if isinstance(units, bool) or not isinstance(units, (int, float)) or not math.isfinite(units) or units < 0:
        raise ValueError("units must be a finite number >= 0")
    rate = tool_rate(config, backend, unit)
    if rate is None:
        return {"cost": None, "cost_source": None, "rate": None, "unit": unit}
    return {"cost": float(units) * rate, "cost_source": COST_SOURCE, "rate": rate, "unit": unit}
