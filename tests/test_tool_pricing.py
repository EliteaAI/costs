"""Tool prices are pure config lookups: units × usd_per_<unit>, None when unpriced."""
import importlib.util
import json
from pathlib import Path
import unittest

import yaml

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('costs_tool_pricing', root/'utils/tool_pricing.py')
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)


class ToolPricingTest(unittest.TestCase):
    cfg = {"tool_pricing": {"tavily": {"usd_per_credit": 0.008}, "brave": {"usd_per_request": 0.005}}}

    def test_units_times_rate(self):
        out = tp.compute_tool_cost(self.cfg, "tavily", 3, "credit")
        self.assertAlmostEqual(out["cost"], 0.024)
        self.assertEqual(out["cost_source"], tp.COST_SOURCE)

    def test_unit_maps_to_usd_per_unit(self):
        self.assertAlmostEqual(tp.compute_tool_cost(self.cfg, "brave", 2, "request")["cost"], 0.01)
        self.assertIsNone(tp.compute_tool_cost(self.cfg, "brave", 2, "credit")["cost"])

    def test_missing_rate_is_unpriced(self):
        for cfg in ({}, None, {"tool_pricing": {"tavily": {"usd_per_credit": 0}}},
                    {"tool_pricing": {"tavily": {"usd_per_credit": "x"}}}):
            self.assertIsNone(tp.compute_tool_cost(cfg, "tavily", 1, "credit")["cost"])

    def test_live_edit_is_picked_up(self):
        cfg = {"tool_pricing": {"tavily": {"usd_per_credit": 0.008}}}
        tp.compute_tool_cost(cfg, "tavily", 1, "credit")
        cfg["tool_pricing"]["tavily"]["usd_per_credit"] = 0.01
        self.assertAlmostEqual(tp.compute_tool_cost(cfg, "tavily", 1, "credit")["cost"], 0.01)

    def test_zero_units_cost_zero(self):
        self.assertEqual(tp.compute_tool_cost(self.cfg, "tavily", 0, "credit")["cost"], 0.0)

    def test_units_can_never_lower_cost(self):
        for units in (-100, -0.0001, float("nan"), float("inf"), "5", True, None):
            with self.assertRaises(ValueError):
                tp.compute_tool_cost(self.cfg, "tavily", units, "credit")

    def test_schema_default_matches_config(self):
        schema = json.loads((root/'admin_schema.json').read_text())["properties"]
        cfg = yaml.safe_load((root/'config.yml').read_text())
        for prop in schema.values():
            node = cfg
            for part in prop["path"].split("."):
                node = node[part]
            self.assertEqual(node, prop["default"])


if __name__ == '__main__':
    unittest.main()
