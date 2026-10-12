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


def priced(name, **kw):
    r = row()
    r.model_name = name
    for key, value in kw.items():
        setattr(r, key, value)
    return {'model_name': name, 'routing_price': prices.projection(r)}


def catalog(*names):
    return {name: priced(name) for name in names}


class TestAliasFallback(unittest.TestCase):
    CANON = {'gpt-5.6-luna-2026-07-09': 'openai/gpt-5-6-luna'}

    def test_old_signature_output_is_unchanged(self):
        source = catalog('global.example')
        legacy = prices.snapshot(['global.example', 'missing'], source)
        self.assertEqual(legacy, prices.snapshot(['global.example', 'missing'], source, None))
        self.assertEqual(set(legacy), {'entries', 'missing', 'match', 'unit', 'revision'})
        self.assertNotIn('match', legacy['entries'][0])
        self.assertEqual(legacy['missing'], ['missing'])

    def test_old_signature_ignores_aliases_even_when_present(self):
        source = catalog('global.openai.gpt-5.6-luna')
        result = prices.snapshot(['gpt-5.6-luna-2026-07-09'], source)
        self.assertEqual(result['missing'], ['gpt-5.6-luna-2026-07-09'])

    def test_exact_wins_over_alias(self):
        source = catalog('gpt-5.6-luna-2026-07-09', 'global.openai.gpt-5.6-luna')
        source['gpt-5.6-luna-2026-07-09']['routing_price']['output_cost_per_token'] = '0.5'
        result = prices.snapshot(list(self.CANON), source, self.CANON)
        entry = result['entries'][0]
        self.assertEqual(entry['match'], 'exact')
        self.assertNotIn('matched_name', entry)
        self.assertEqual(entry['output_cost_per_token'], '0.5')

    def test_canonical_family_fills_gap_and_is_labelled(self):
        source = catalog('global.openai.gpt-5.6-luna')
        result = prices.snapshot(list(self.CANON), source, self.CANON)
        self.assertEqual(result['missing'], [])
        entry = result['entries'][0]
        self.assertEqual(entry['model_name'], 'gpt-5.6-luna-2026-07-09')
        self.assertEqual(entry['match'], 'alias')
        self.assertEqual(entry['matched_name'], 'global.openai.gpt-5.6-luna')
        self.assertEqual(entry['input_cost_per_token'], '0.000004000000')
        self.assertEqual(result['match'], 'exact')  # top-level field kept for compatibility

    def test_alias_entry_does_not_alias_catalog_state(self):
        source = catalog('global.openai.gpt-5.6-luna')
        result = prices.snapshot(list(self.CANON), source, self.CANON)
        result['entries'][0]['extra'].clear()
        result['entries'][0]['model_name'] = 'changed'
        self.assertEqual(source['global.openai.gpt-5.6-luna']['routing_price']['model_name'], 'global.openai.gpt-5.6-luna')
        self.assertTrue(source['global.openai.gpt-5.6-luna']['routing_price']['extra'])

    def test_alias_index_by_requested_name(self):
        source = catalog('global.openai.gpt-5.6-luna')
        result = prices.snapshot(['customer-luna'], source, {'customer-luna': 'openai/gpt-5-6-luna'},
                                 alias_index={'customer-luna': 'global.openai.gpt-5.6-luna'})
        self.assertEqual(result['entries'][0]['matched_name'], 'global.openai.gpt-5.6-luna')

    def test_prefix_stripped_lookup_of_requested_name(self):
        source = catalog('gpt-5.4')
        result = prices.snapshot(['azure/gpt-5.4'], source, {'azure/gpt-5.4': 'openai/gpt-5-4'})
        self.assertEqual((result['entries'][0]['match'], result['entries'][0]['matched_name']), ('alias', 'gpt-5.4'))

    def test_alias_index_by_canonical_family(self):
        source = catalog('luna-internal')
        result = prices.snapshot(['customer-luna'], source, {'customer-luna': 'openai/gpt-5-6-luna'},
                                 alias_index={'GPT_5.6_Luna': 'luna-internal'})
        self.assertEqual(result['entries'][0]['matched_name'], 'luna-internal')

    def test_regional_exact_price_preserved_when_both_rows_exist(self):
        source = catalog('x-model', 'eu.x-model')
        source['eu.x-model']['routing_price']['output_cost_per_token'] = '0.00003'
        result = prices.snapshot(['eu.x-model', 'x-model'], source, {'eu.x-model': 'vendor/x-model'})
        by_name = {e['model_name']: e for e in result['entries']}
        self.assertEqual(by_name['eu.x-model']['output_cost_per_token'], '0.00003')
        self.assertEqual({e['match'] for e in result['entries']}, {'exact'})

    def test_regional_request_does_not_borrow_other_region_when_ambiguous(self):
        source = catalog('x-model', 'eu.x-model')
        result = prices.snapshot(['us-gateway-x'], source, {'us-gateway-x': 'vendor/x-model'})
        self.assertEqual(result['entries'], [])
        self.assertEqual(result['missing'], ['us-gateway-x'])

    def test_unknown_stays_missing(self):
        source = catalog('global.openai.gpt-5.6-luna')
        result = prices.snapshot(['mystery', 'no-canonical'], source, {'mystery': 'openai/does-not-exist'})
        self.assertEqual(result['entries'], [])
        self.assertEqual(result['missing'], ['mystery', 'no-canonical'])

    def test_name_without_canonical_gets_no_alias_even_if_others_do(self):
        source = catalog('global.openai.gpt-5.6-luna')
        result = prices.snapshot(['gpt-5.6-luna-2026-07-09', 'other'], source, self.CANON)
        self.assertEqual([e['model_name'] for e in result['entries']], ['gpt-5.6-luna-2026-07-09'])
        self.assertEqual(result['missing'], ['other'])

    def test_invalid_canonical_by_name_rejected(self):
        for bad in ['openai/x', ['a'], {'a': None}, {'a': 1}, {1: 'a'}, {'a': ''}, {'a': 'x' * 257},
                    {str(i): 'v/f' for i in range(65)}]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                prices.snapshot(['a'], {}, bad)

    def test_name_bounds_unchanged_with_canonical(self):
        for names in ['global.example', ['a', 'a'], [''], [None], [str(i) for i in range(65)]]:
            with self.assertRaises(ValueError):
                prices.snapshot(names, {}, {})
        prices.snapshot([str(i) for i in range(64)], {}, {})

    def test_revision_changes_when_alias_match_changes(self):
        source = catalog('global.openai.gpt-5.6-luna')
        first = prices.snapshot(list(self.CANON), source, self.CANON)['revision']
        source['global.openai.gpt-5.6-luna']['routing_price']['output_cost_per_token'] = '0.00003'
        self.assertNotEqual(prices.snapshot(list(self.CANON), source, self.CANON)['revision'], first)


class TestResolveName(unittest.TestCase):
    """Shared with cache.get_price: behaviour must stay exactly what get_price did."""

    def test_order_exact_lower_prefix_alias(self):
        by_name = {'m': 1, 'lower': 2, 'plain': 3, 'target': 4}
        alias = {'nick': 'target', 'dangling': 'gone'}
        resolve = lambda n: prices.resolve_name(n, by_name, alias)
        self.assertEqual(resolve('m'), 'm')
        self.assertEqual(resolve('LOWER'), 'lower')
        self.assertEqual(resolve('openai/plain'), 'plain')
        self.assertEqual(resolve('EU.plain'), 'plain')
        self.assertEqual(resolve('nick'), 'target')
        self.assertIsNone(resolve('dangling'))
        self.assertIsNone(resolve('absent'))


if __name__ == '__main__':
    unittest.main()
