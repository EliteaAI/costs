"""LiteLLM catalog normalization: image-generation models must keep their output price.

LiteLLM ships gpt-image-* output rates under `output_cost_per_image_token` instead of
`output_cost_per_token`; dropping it billed image output at $0 (~300x under-billing).
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]

pylon = types.ModuleType('pylon')
core = types.ModuleType('pylon.core')
tools = types.ModuleType('pylon.core.tools')
tools.log = types.SimpleNamespace(warnings=[], info=lambda *a: None)
tools.log.warning = lambda *a: tools.log.warnings.append(a)
sys.modules.setdefault('pylon', pylon)
sys.modules.setdefault('pylon.core', core)
sys.modules['pylon.core.tools'] = tools

pkg = types.ModuleType('costs_sources')
pkg.__path__ = [str(root / 'sources')]
sys.modules['costs_sources'] = pkg
for name in ('base', 'litellm'):
    spec = importlib.util.spec_from_file_location(f'costs_sources.{name}', root / 'sources' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
litellm = sys.modules['costs_sources.litellm']

# Shape copied from LiteLLM's model_prices_and_context_window.json
GPT_IMAGE_2 = {
    'litellm_provider': 'openai', 'mode': 'image_generation',
    'input_cost_per_token': 0.000005, 'input_cost_per_image_token': 0.000008,
    'output_cost_per_image_token': 0.00003, 'cache_read_input_token_cost': 0.00000125,
}


class TestNormalizeEntry(unittest.TestCase):
    def test_image_output_price_mapped_to_output_cost_per_token(self):
        entry = litellm.normalize_entry('gpt-image-2', GPT_IMAGE_2)
        self.assertEqual(entry.output_cost_per_token, 0.00003)
        self.assertEqual(entry.input_cost_per_token, 0.000005)

    def test_chat_output_price_wins_when_present(self):
        raw = dict(GPT_IMAGE_2, output_cost_per_token=0.00004)
        self.assertEqual(litellm.normalize_entry('x', raw).output_cost_per_token, 0.00004)

    def test_non_image_mode_does_not_borrow_image_key(self):
        raw = dict(GPT_IMAGE_2, mode='chat')
        self.assertIsNone(litellm.normalize_entry('x', raw).output_cost_per_token)

    def test_catalog_warns_on_image_rows_left_without_output_price(self):
        tools.log.warnings.clear()
        broken = {k: v for k, v in GPT_IMAGE_2.items() if k != 'output_cost_per_image_token'}
        entries = litellm.normalize_catalog({'gpt-image-2': GPT_IMAGE_2, 'broken-img': broken,
                                             'sample_spec': {}})
        self.assertEqual(len(entries), 2)
        self.assertEqual(len(tools.log.warnings), 1)
        self.assertIn('broken-img', tools.log.warnings[0][-1])
        self.assertNotIn('gpt-image-2', tools.log.warnings[0][-1])

    def test_bundled_seed_has_no_image_rows_missing_output_price(self):
        import json
        entries = json.loads((root / 'data' / 'prices_seed.json').read_text())['entries']
        missing = [e['model_name'] for e in entries if e.get('mode') == 'image_generation'
                   and e.get('output_cost_per_token') is None
                   and (e.get('extra') or {}).get('output_cost_per_image_token') is not None]
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
