"""No database or Pylon required for immutable rate projection contracts."""
from decimal import Decimal
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

path = Path(__file__).resolve().parents[1]/'utils/routing_prices.py'
spec = importlib.util.spec_from_file_location('costs_routing_projection', path)
prices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prices)


def row():
    return SimpleNamespace(model_name='global.example', provider='provider', mode='chat',
        input_cost_per_token=Decimal('0.000004000000'), output_cost_per_token=Decimal('0.000020000000'),
        cache_read_input_token_cost=Decimal('0.000000400000'), cache_creation_input_token_cost=None,
        is_custom=False, source='catalog', source_ref='global.example',
        extra={'input_cost_per_token_above_272k_tokens': 0.000008, 'api_key': 'fixture-secret',
               'internal_notes': {'private': 'not part of rate contract'}})


class TestRoutingPrices(unittest.TestCase):
    def test_only_rate_evidence_is_projected(self):
        value = prices.projection(row())
        self.assertEqual(value['input_cost_per_token'], '0.000004000000')
        self.assertEqual(set(value['extra']), {'input_cost_per_token_above_272k_tokens'})

    def test_exact_names_keep_region_prices_distinct(self):
        source = {'global.example': {'routing_price': prices.projection(row())}}
        result = prices.snapshot(['global.example', 'eu.example'], source)
        self.assertEqual(result['missing'], ['eu.example'])
        self.assertEqual(len(result['entries']), 1)

    def test_returned_snapshot_cannot_mutate_catalog(self):
        source = {'global.example': {'routing_price': prices.projection(row())}}
        first = prices.snapshot(['global.example'], source)
        revision = first['revision']
        first['entries'][0]['extra'].clear()
        self.assertEqual(prices.snapshot(['global.example'], source)['revision'], revision)

    def test_revision_changes_with_effective_rate(self):
        source = {'global.example': {'routing_price': prices.projection(row())}}
        old = prices.snapshot(['global.example'], source)['revision']
        source['global.example']['routing_price']['output_cost_per_token'] = '0.00003'
        self.assertNotEqual(prices.snapshot(['global.example'], source)['revision'], old)

    def test_invalid_or_unbounded_requests_fail(self):
        for names in ['global.example', ['a', 'a'], [''], [None], [str(i) for i in range(65)]]:
            with self.assertRaises(ValueError):
                prices.snapshot(names, {})


if __name__ == '__main__':
    unittest.main()
