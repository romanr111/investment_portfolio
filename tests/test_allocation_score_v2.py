"""Analytical controls for the v2 capital diversity methodology."""
import importlib.util
import unittest


class AllocationScoreV2Tests(unittest.TestCase):
    def test_six_equal_uncorrelated_groups_anchor_100(self):
        self.assertIsNotNone(importlib.util.find_spec('analytics.allocation_score_v2'),
                             'v2 methodology has not been implemented')
        from analytics.allocation_score_v2 import score_components_v2
        groups = {str(i): 1 / 6 for i in range(6)}
        pairs = {(a, b): 0 for a in groups for b in groups if a < b}
        self.assertAlmostEqual(score_components_v2(groups, pairs, {})['score'], 100)

    def test_global_equity_sectors_are_aggregated_before_breadth(self):
        from analytics.allocation_score_v2 import score_components_v2
        weights = {'equity_us': .5, 'equity_china': .5}
        same = {'equity_us': {'Financials': 1}, 'equity_china': {'Financials': 1}}
        split = {'equity_us': {'Financials': 1}, 'equity_china': {'Energy': 1}}
        pair = {('equity_us', 'equity_china'): 1}
        self.assertEqual(score_components_v2(weights, pair, same)['score'], 0)
        self.assertAlmostEqual(score_components_v2(weights, pair, split)['score'], 13.75)

    def test_correlation_monotonicity_and_conservative_missing(self):
        from analytics.allocation_score_v2 import score_components_v2
        weights = {'a': .5, 'b': .5}
        scores = [score_components_v2(weights, {('a', 'b'): r}, {})['score']
                  for r in [-1, 0, .5, 1]]
        self.assertEqual(scores[:2], [20, 20])
        self.assertGreater(scores[1], scores[2])
        self.assertGreater(scores[2], scores[3])
        self.assertEqual(score_components_v2(weights, {}, {})['score'], 0)

    def test_invalid_financial_values_are_rejected(self):
        from analytics.allocation_score_v2 import score_components_v2
        for weights, correlations, sectors in [
            ({'a': True}, {}, {}), ({'a': float('nan')}, {}, {}),
            ({'a': -.1, 'b': 1.1}, {}, {}), ({'a': .9}, {}, {}),
            ({'a': .5, 'b': .5}, {('a', 'b'): True}, {}),
            ({'equity_us': 1}, {}, {'equity_us': {'Energy': 1.1}}),
        ]:
            with self.subTest(weights=weights, correlations=correlations, sectors=sectors):
                with self.assertRaises(ValueError):
                    score_components_v2(weights, correlations, sectors)

    def test_display_and_classification_snap_only_integer_noise(self):
        from analytics.allocation_score_v2 import display_score, category
        self.assertEqual(display_score(49.999999999), 50)
        self.assertEqual(display_score(49.99), 49)
        self.assertEqual(category(49.99), 'concentrated')
        self.assertEqual(category(49.999999999), 'partly_diversified')
        self.assertEqual(category(80), 'well_diversified')


class AllocationV2IntegrationTests(unittest.TestCase):
    def test_v2_enrichment_does_not_depend_on_v1_calibration(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        settings['calibration'] = {'invalid': True}
        output = enrich_combined_data(data, config={'allocation': settings},
                                      monthly_returns=histories, allow_network=False)
        self.assertIn('allocation_score_v2', output['DIVERSIFICATION_DATA'])
        result = output['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertEqual(result['version'], 'capital_diversification_v2')
        self.assertIn(result['status'], {'modeled', 'provisional'})
        self.assertEqual(result['unit'], 'points')
        self.assertIsNotNone(result['score'])

    def test_scenarios_bound_missing_pairs_and_require_complete_recent_window(self):
        import numpy as np
        import pandas as pd
        from analytics.allocation_score_v2 import evaluate_scenarios
        dates = pd.date_range('2021-10-31', periods=60, freq='ME')
        rng = np.random.default_rng(77)
        history = pd.DataFrame({'a': rng.normal(size=60), 'b': rng.normal(size=60)}, index=dates)
        history.loc[dates[-1], 'b'] = np.nan
        scenarios = evaluate_scenarios({'a': .5, 'b': .5}, {}, history, '2026-09-30')
        self.assertEqual(scenarios['m60']['status'], 'provisional')
        self.assertEqual(scenarios['m60']['pairs'][0]['observations'], 59)
        self.assertEqual(scenarios['m36']['status'], 'unavailable')
        self.assertEqual(scenarios['m36']['reason'], 'incomplete_window')
        missing = evaluate_scenarios({'a': .5, 'unknown': .5}, {}, history, '2026-09-30')
        self.assertEqual(missing['m60']['status'], 'unavailable')
        self.assertGreater(missing['m60']['missing_pair_max_points'], 5)

    def test_zero_weight_does_not_require_a_return_history(self):
        import pandas as pd
        from analytics.allocation_score_v2 import evaluate_scenarios
        empty = pd.DataFrame(index=pd.date_range('2021-10-31', periods=60, freq='ME'))
        scenarios = evaluate_scenarios({'treasury_short': 1.0, 'unknown': 0.0}, {}, empty, '2026-09-30')
        self.assertEqual(scenarios['m36']['status'], 'modeled')
        self.assertEqual(scenarios['m36']['score'], 0)

    def test_future_return_observations_are_rejected(self):
        import pandas as pd
        from analytics.allocation_score_v2 import evaluate_scenarios
        history = pd.DataFrame({'a': [0.01]}, index=pd.to_datetime(['2026-10-31']))
        with self.assertRaises(ValueError):
            evaluate_scenarios({'a': 1.0}, {}, history, '2026-09-30')

    def test_history_observation_boundaries_and_business_scenarios(self):
        import numpy as np
        import pandas as pd
        from analytics.allocation_score_v2 import evaluate_scenarios
        dates = pd.date_range('2021-10-31', periods=60, freq='ME')
        rng = np.random.default_rng(3)
        for count in (35, 36, 59, 60):
            frame = pd.DataFrame({'a': rng.normal(size=60), 'b': rng.normal(size=60)}, index=dates)
            frame.loc[dates[:60-count], 'b'] = np.nan
            result = evaluate_scenarios({'a': .5, 'b': .5}, {}, frame, '2026-09-30')
            self.assertEqual(result['m60']['pairs'][0]['observations'], count)
            self.assertEqual(result['m60']['pairs'][0]['kind'], 'missing' if count < 36 else 'measured')
            self.assertEqual(result['m36']['status'], 'modeled' if count >= 36 else 'unavailable')
        frame = pd.DataFrame({'a': rng.normal(size=60)}, index=dates)
        result = evaluate_scenarios({'a': .5, 'car_business': .5}, {}, frame, '2026-09-30')
        self.assertEqual(set(result), {'m60_r025', 'm60_r075', 'm36_r025', 'm36_r075'})
        self.assertEqual(result['m60_r025']['pairs'][0]['correlation'], .25)
        self.assertEqual(result['m60_r075']['pairs'][0]['correlation'], .75)

    def test_present_invalid_v2_never_falls_back_to_v1(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        self.assertNotEqual(saved_diversification_view(saved)['headline'], 'Дані недоступні')
        saved['DIVERSIFICATION_DATA']['allocation_score_v2'] = None
        self.assertEqual(saved_diversification_view(saved)['headline'], 'Дані недоступні')

    def test_saved_replay_rejects_resealed_tampered_groups(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail import fingerprint
        from analytics.allocation_v2_inputs import validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertTrue(validate_saved_allocation_v2(q, saved, '2026-09-30'))
        q['groups'][0]['weight'] += .01
        q['result_fingerprint'] = fingerprint({k: v for k, v in q.items() if k != 'result_fingerprint'})
        self.assertFalse(validate_saved_allocation_v2(q, saved, '2026-09-30'))

    def test_cash_only_saved_record_replays_as_not_applicable(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.allocation_v2_inputs import validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        data['IB_DATA'] = {}
        data['CASH_DATA']['Total'] = 110
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertEqual(q['status'], 'not_applicable')
        self.assertIsNone(q['score'])
        self.assertTrue(validate_saved_allocation_v2(q, saved, '2026-09-30'))

    def test_historical_upgrade_preserves_existing_analytics_and_enrichment(self):
        from copy import deepcopy
        from pathlib import Path
        import json
        import tempfile
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data, enrich_snapshot_file
        data, settings, histories = allocation_fixture()
        from tests.test_holy_grail_data import saved_legacy_fixture
        old = saved_legacy_fixture('allocation')
        payload = {'as_of_date': '2026-09-30', 'data': old, 'holy_grail_enrichment': {'prior': True}}
        before = deepcopy(payload)
        settings['method_version'] = 'capital_diversification_v2'
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'source' / 'old.json'
            source.parent.mkdir()
            source.write_text(json.dumps(payload))
            output = root / 'derived' / 'new.json'
            result = enrich_snapshot_file(source, output, config={'allocation': settings},
                                          monthly_returns=histories, allow_network=False)
        self.assertEqual(result['holy_grail_enrichment'], before['holy_grail_enrichment'])
        self.assertEqual(result['data']['HOLY_GRAIL_DATA'], before['data']['HOLY_GRAIL_DATA'])
        q = result['data']['DIVERSIFICATION_DATA']
        self.assertIn('allocation_score_v2', q)
        self.assertEqual({k: v for k, v in q.items() if k != 'allocation_score_v2'}, before['data']['DIVERSIFICATION_DATA'])
        self.assertIn('allocation_score_v2_enrichment', result)

    def test_replay_rejects_cleared_leverage_guard_in_frozen_evidence(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import extract_exposures
        from analytics.allocation_inputs import allocation_settings
        from analytics.allocation_v2_inputs import calculate_allocation_score_v2, validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        all_settings = {'allocation': settings, 'diversification': {'exposures': {'ib:SPY': {'leveraged': True}}}}
        positions, cash, flags = extract_exposures(data, '2026-09-30', all_settings)
        config = allocation_settings(all_settings)
        config['extraction_settings'] = all_settings
        config['unsupported_ids'] = []
        forged = calculate_allocation_score_v2(data, positions, cash, histories, config, '2026-09-30', flags)
        self.assertFalse(validate_saved_allocation_v2(forged, data, '2026-09-30'))

    def test_unavailable_financial_result_retains_replayable_reason(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.allocation_v2_inputs import validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        data['TOTAL_ASSETS'] -= 1.01
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertEqual(q['status'], 'unavailable')
        self.assertIn('unreconciled_valuations', q['warnings'])
        self.assertTrue(validate_saved_allocation_v2(q, saved, '2026-09-30'))

    def test_invalid_v2_settings_never_produce_valid_score(self):
        import pandas as pd
        from analytics.holy_grail_data import enrich_combined_data
        data = {'TOTAL_ASSETS': 100., 'CASH_DATA': {'Total': 0., 'Breakdown': {}},
                'IB_DATA': {}, 'POSITION_DATA': {'p2p': [{'balance_usd': 100.}], 'as_of_date': '2026-09-30'},
                'DATA_METADATA': {'last_updated': '2026-09-30'}}
        settings = {'allocation': {'method_version': 'capital_diversification_v2', 'profiles': []}}
        saved = enrich_combined_data(data, config=settings, monthly_returns=pd.DataFrame(), allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertEqual(q['status'], 'unavailable')
        self.assertIsNone(q['score'])

    def test_infinite_return_cannot_become_a_missing_observation(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        histories.iloc[-1, 0] = float('inf')
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        self.assertEqual(saved['DIVERSIFICATION_DATA']['allocation_score_v2']['status'], 'unavailable')

    def test_saved_view_exposes_explicit_points_not_percent(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        result = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        view = saved_diversification_view(saved)
        self.assertEqual(view['number_kind'], 'allocation_points')
        self.assertEqual(view['sheet_number'], result['display_score'])
        self.assertEqual(view['headline'], f"{result['display_score']} зі 100")
        self.assertEqual(view['number_format'], {'type': 'NUMBER', 'pattern': '0" зі 100"'})

    def test_integrity_mode_rejects_resealed_bad_score_types(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail import fingerprint
        from analytics.allocation_v2_inputs import validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        q['score'] = True
        q['display_score'] = 999
        q['result_fingerprint'] = fingerprint({k: v for k, v in q.items() if k != 'result_fingerprint'})
        self.assertFalse(validate_saved_allocation_v2(q, saved, '2026-09-30', replay=False))

    def test_scoped_sheet_writer_uses_points_format_for_v2(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail_sheet import plan_requests
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        grid = [[{} for _ in range(4)] for _ in range(200)]
        requests, _ = plan_requests(saved, 7, grid, [], 40, 40)
        format_request = next(r['repeatCell'] for r in requests if 'repeatCell' in r and r['repeatCell']['fields'] == 'userEnteredFormat.numberFormat')
        self.assertEqual(format_request['cell']['userEnteredFormat']['numberFormat'], {'type': 'NUMBER', 'pattern': '0" зі 100"'})

    def test_regular_insights_writer_preserves_v2_points_on_repeat(self):
        from tests.test_allocation_score import allocation_fixture
        from tests.fake_sheets import FakeSpreadsheet
        from analytics.holy_grail_data import enrich_combined_data
        from src.google_sheets.insights_refresh import refresh_insights
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        book = FakeSpreadsheet()
        for _ in range(2):
            refresh_insights(book, saved, config={})
        main = book.worksheet('30 Sep 2026')
        self.assertEqual(main.values[(10, 2)], saved['DIVERSIFICATION_DATA']['allocation_score_v2']['display_score'])
        self.assertEqual(main.formats[(10, 2)]['numberFormat'], {'type': 'NUMBER', 'pattern': '0" зі 100"'})

    def test_legacy_formatter_accepts_explicit_points_kind(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from src.google_sheets.formatting import PortfolioFormatter
        sheet = SimpleNamespace(id=27, spreadsheet=Mock())
        PortfolioFormatter(sheet).format_holy_grail(None, number_kind='allocation_points')
        request = sheet.spreadsheet.batch_update.call_args.args[0]['requests'][0]
        self.assertEqual(request['repeatCell']['cell']['userEnteredFormat']['numberFormat'],
                         {'type': 'NUMBER', 'pattern': '0" зі 100"'})

    def test_factual_review_uses_frozen_cutoff(self):
        from analytics.diversification_quality import reviewed_record
        record = {'source': 'https://example.org', 'effective_from': '2020-01-01', 'reviewed_at': '2026-10-20'}
        self.assertEqual(reviewed_record({'risk_record': record}, '2026-09-30', review_cutoff='2026-10-19'), {})
        self.assertEqual(reviewed_record({'risk_record': record}, '2026-09-30', review_cutoff='2026-10-20'), record)

    def test_unreviewed_or_mismatched_risk_evidence_is_not_reported_as_fact(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        risk = {'source': 'https://example.org', 'effective_from': '2020-01-01',
                'reviewed_at': '2020-01-01', 'fx_monetary': True}
        config = {'allocation': settings, 'diversification': {'exposures': {'ib:SPY': risk}}}
        saved = enrich_combined_data(data, config=config, monthly_returns=histories, allow_network=False)
        facts = saved['DIVERSIFICATION_DATA']['allocation_score_v2']['risk_facts']
        self.assertIn('economic_fx', {row['id'] for row in facts})
        risk['reviewed_at'] = '2999-01-01'
        saved = enrich_combined_data(data, config=config, monthly_returns=histories, allow_network=False)
        facts = saved['DIVERSIFICATION_DATA']['allocation_score_v2']['risk_facts']
        self.assertNotIn('economic_fx', {row['id'] for row in facts})

    def test_public_view_includes_risk_percent_without_private_evidence(self):
        import json
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        config = {'allocation': settings, 'diversification': {'exposures': {'ib:SPY': {
            'source': 'PRIVATE_SOURCE', 'effective_from': '2020-01-01',
            'reviewed_at': '2020-01-01', 'fx_monetary': True}}}}
        saved = enrich_combined_data(data, config=config, monthly_returns=histories, allow_network=False)
        view = saved_diversification_view(saved)
        self.assertTrue(any('Валют' in text for text in view['risk_facts']))
        self.assertNotIn('PRIVATE_SOURCE', json.dumps(view, ensure_ascii=False))

    def test_previous_v2_attribution_sums_to_total(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        old = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        changed = dict(data, IB_DATA={'Stocks': {'SPY': 80}, 'Bonds': {'SHV': 20}})
        new = enrich_combined_data(changed, config={'allocation': settings}, monthly_returns=histories,
                                   allow_network=False, previous_combined_data=old)
        comparison = new['DIVERSIFICATION_DATA']['allocation_score_v2']['comparison']
        self.assertEqual(comparison['status'], 'available')
        self.assertAlmostEqual(comparison['market_relationship_change'] + comparison['positions_and_profiles_change'],
                               comparison['total_change'], places=8)

    def test_unavailable_attribution_retains_valid_current_score_and_replays(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.allocation_v2_inputs import validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        old = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        new_data = dict(data, IB_DATA={'Stocks': {'SPY': 100}, 'Bonds': {}})
        new_histories = histories.drop(columns=['yf:SHV'])
        new = enrich_combined_data(new_data, config={'allocation': settings}, monthly_returns=new_histories,
                                   allow_network=False, previous_combined_data=old)
        q = new['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertIsNotNone(q['score'])
        self.assertEqual(q['comparison']['reason'], 'missing_comparison_history')
        self.assertTrue(validate_saved_allocation_v2(q, new, '2026-09-30'))

    def test_replay_rejects_future_evidence_review_cutoff(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail import fingerprint
        from analytics.allocation_v2_inputs import calculate_allocation_score_v2, validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        config = q['configuration'].copy()
        config['evidence_review_cutoff'] = '2999-01-01'
        forged = calculate_allocation_score_v2(data, q['positions'], q['cash_value'], histories,
                                               config, q['as_of_date'], q['input_flags'], q['source_provenance'])
        forged['calculated_at'] = q['calculated_at']
        forged['result_fingerprint'] = fingerprint({k: v for k, v in forged.items() if k != 'result_fingerprint'})
        self.assertFalse(validate_saved_allocation_v2(forged, data, '2026-09-30'))

    def test_saved_history_is_bounded_to_sixty_completed_months(self):
        import numpy as np
        import pandas as pd
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        earlier = pd.DataFrame(0.01, index=pd.date_range('2016-10-31', periods=60, freq='ME'), columns=histories.columns)
        histories = pd.concat([earlier, histories])
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertLessEqual(max(map(len, q['histories'].values())), 60)

    def test_previous_snapshot_reader_handles_missing_and_malformed_files(self):
        import json
        import tempfile
        from pathlib import Path
        from src.data_source import _read_previous_combined_data
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'previous.json'
            self.assertIsNone(_read_previous_combined_data(path))
            path.write_text('{bad')
            self.assertIsNone(_read_previous_combined_data(path))
            path.write_text(json.dumps({'TOTAL_ASSETS': 12}))
            self.assertEqual(_read_previous_combined_data(path), {'TOTAL_ASSETS': 12})

    def test_cli_reports_v2_field_without_removing_legacy_output(self):
        import contextlib
        import io
        import json
        import sys
        from unittest.mock import patch
        from analytics.holy_grail_cli import main
        payload = {'HOLY_GRAIL_DATA': {'as_of_date': '2026-09-30', 'status': 'modeled',
                   'effective_streams': 1, 'estimated_progress_pct': 2, 'target_achieved': False},
                   'DIVERSIFICATION_DATA': {'allocation_score_v2': {'version': 'capital_diversification_v2'},
                                            'allocation_score': {'version': 'capital_diversification_v1'}}}
        output = io.StringIO()
        with patch.object(sys, 'argv', ['x', '--snapshot', 'a', '--output', 'b']), \
             patch('analytics.holy_grail_cli.enrich_snapshot_file', return_value=payload), \
             patch('analytics.holy_grail_cli.load_config', return_value={}), contextlib.redirect_stdout(output):
            main()
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed['allocation_score_v2']['version'], 'capital_diversification_v2')
        self.assertEqual(parsed['allocation_score']['version'], 'capital_diversification_v1')

    def test_replay_uses_frozen_representatives_not_current_mappings(self):
        from unittest.mock import patch
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.allocation_v2_inputs import validate_saved_allocation_v2
        from analytics.allocation_inputs import GROUPS
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        with patch.dict(GROUPS, {'equity_us': ('changed label', 'CHANGED')}):
            self.assertTrue(validate_saved_allocation_v2(q, saved, '2026-09-30'))

    def test_profile_theme_without_reviewed_evidence_is_not_confirmed(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        settings['profiles']['ib:SPY']['themes'] = ['ai']
        settings['profiles']['ib:SPY']['reviewed_at'] = '2999-01-01'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        facts = saved['DIVERSIFICATION_DATA']['allocation_score_v2']['risk_facts']
        self.assertNotIn('confirmed_ai_theme', {item['id'] for item in facts})

    def test_missing_risk_evidence_is_explicit_without_blocking_score(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        result = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertIsNotNone(result['score'])
        self.assertGreater(result['risk_unknown']['duration_pct_nav'], 0)
        view = saved_diversification_view(saved)
        self.assertTrue(any('duration' in text.lower() for _, text in view['rows']))

    def test_boolean_financial_position_is_rejected(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        data['IB_DATA']['Stocks']['SPY'] = True
        data['TOTAL_ASSETS'] = 21
        settings['method_version'] = 'capital_diversification_v2'
        q = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories,
                                 allow_network=False)['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertEqual(q['status'], 'unavailable')

    def test_resealed_prior_basis_with_forged_weights_is_rejected(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail import fingerprint
        from analytics.allocation_v2_inputs import _compare_basis, validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        old = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        changed = dict(data, IB_DATA={'Stocks': {'SPY': 80}, 'Bonds': {'SHV': 20}})
        new = enrich_combined_data(changed, config={'allocation': settings}, monthly_returns=histories,
                                   allow_network=False, previous_combined_data=old)
        q = new['DIVERSIFICATION_DATA']['allocation_score_v2']
        basis = q['comparison']['previous_basis']
        basis['weights']['equity_us'] -= .01
        basis['weights']['treasury_short'] += .01
        from analytics.allocation_v2_inputs import _group_history
        from analytics.allocation_score_v2 import evaluate_scenarios
        basis['score'] = evaluate_scenarios(basis['weights'], basis['sectors'],
                            _group_history(basis['histories'], basis['weights'], basis['method_definition']['group_definitions']),
                            basis['as_of_date'])['m60']['score']
        q['comparison'] = _compare_basis(q, basis)
        q['result_fingerprint'] = fingerprint({k: v for k, v in q.items() if k != 'result_fingerprint'})
        self.assertFalse(validate_saved_allocation_v2(q, new, '2026-09-30'))

    def test_legacy_v1_is_labeled_as_previous_method(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        from tests.test_holy_grail_data import saved_legacy_fixture
        saved = saved_legacy_fixture('allocation')
        view = saved_diversification_view(saved)
        self.assertIn('Попередня методика capital_diversification_v1', str(view))

    def test_reviewed_treasury_duration_and_maturity_are_disclosed(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        record = {'source': 'https://example.org', 'effective_from': '2020-01-01',
                  'reviewed_at': '2020-01-01', 'maturity': '2027-03-01', 'rate_duration': 0.4}
        saved = enrich_combined_data(data, config={'allocation': settings, 'diversification': {'exposures': {'ib:SHV': record}}},
                                     monthly_returns=histories, allow_network=False)
        view = saved_diversification_view(saved)
        self.assertTrue(any('0,4' in str(value) and '2027' in str(value) for _, value in view['rows']))

    def test_v2_enrichment_preserves_existing_v1_and_nested_fields(self):
        from copy import deepcopy
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        from tests.test_holy_grail_data import saved_legacy_fixture
        old = saved_legacy_fixture('allocation')
        old['DIVERSIFICATION_DATA']['custom_history'] = {'nested': ['preserve']}
        before = deepcopy(old['DIVERSIFICATION_DATA'])
        settings['method_version'] = 'capital_diversification_v2'
        new = enrich_combined_data(old, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        new_quality = new['DIVERSIFICATION_DATA']
        self.assertEqual(new_quality['allocation_score'], before['allocation_score'])
        self.assertEqual(new_quality['custom_history'], before['custom_history'])
        self.assertIn('allocation_score_v2', new_quality)

    def test_v2_details_show_sector_history_and_attribution_status(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        rows = saved_diversification_view(saved)['rows']
        names = [key for key, _ in rows]
        self.assertIn('Сектори: Акції США', names)
        self.assertIn('Історія пар', names)
        self.assertIn('Порівняння', names)
        self.assertIn('Модель', names)

    def test_private_group_override_cannot_change_pinned_method(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        settings['group_definitions'] = {'equity_us': {'label': 'US', 'representative': 'SHV'}}
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        self.assertEqual(saved['DIVERSIFICATION_DATA']['allocation_score_v2']['status'], 'unavailable')

    def test_missing_risk_details_do_not_replace_main_assessment(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        view = saved_diversification_view(saved)
        self.assertIn('Концентрований', view['status'])
        self.assertNotIn('Економічна валютна', view['status'])

    def test_previous_source_references_have_explicit_verification_status(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail import fingerprint
        from analytics.allocation_v2_inputs import validate_saved_allocation_v2
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        old = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        new = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories,
                                   allow_network=False, previous_combined_data=old)
        q = new['DIVERSIFICATION_DATA']['allocation_score_v2']
        basis = q['comparison']['previous_basis']
        self.assertEqual(basis['source_reference_verification'], 'unverified_without_original')
        basis['source_result_fingerprint'] = 'forged'
        q['result_fingerprint'] = fingerprint({k: v for k, v in q.items() if k != 'result_fingerprint'})
        self.assertFalse(validate_saved_allocation_v2(q, new, '2026-09-30'))

    def test_mixed_fund_matches_exact_look_through(self):
        from copy import deepcopy
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        direct = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        fund = deepcopy(data)
        fund['IB_DATA'] = {'Stocks': {'MIXED': 100}, 'Bonds': {}}
        settings['profiles']['ib:MIXED'] = {'as_of_date': '2026-09-30', 'source': 'https://example.org/mixed',
            'components': [{'group': 'equity_us', 'share': .9, 'sectors': {'Information Technology': .5, 'Financials': .5}},
                           {'group': 'treasury_short', 'share': .1}]}
        indirect = enrich_combined_data(fund, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        a = direct['DIVERSIFICATION_DATA']['allocation_score_v2']
        b = indirect['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertEqual(a['groups'], b['groups'])
        self.assertAlmostEqual(a['score'], b['score'], places=10)

    def test_malformed_previous_data_does_not_poison_current_score(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories,
                                      allow_network=False, previous_combined_data={'data': {'DIVERSIFICATION_DATA': None}})
        q = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertIsNotNone(q['score'])
        self.assertEqual(q['comparison']['status'], 'unavailable')

    def test_v2_enrichment_does_not_reuse_stale_quality_fields(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_inputs import quality_inputs_fingerprint
        data, settings, histories = allocation_fixture()
        old = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        old['IB_DATA']['Stocks']['SPY'] = 80
        old['TOTAL_ASSETS'] = 100
        settings['method_version'] = 'capital_diversification_v2'
        new = enrich_combined_data(old, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        self.assertEqual(new['DIVERSIFICATION_DATA']['allocation_score_v2']['holdings_fingerprint'], quality_inputs_fingerprint(new))

    def test_duplicate_split_and_small_perturbation_do_not_manufacture_breadth(self):
        from analytics.allocation_score_v2 import score_components_v2
        original = score_components_v2({'a': .5, 'b': .5}, {('a', 'b'): .3}, {})['score']
        split = score_components_v2({'a1': .25, 'a2': .25, 'b': .5},
                                    {('a1', 'a2'): 1, ('a1', 'b'): .3, ('a2', 'b'): .3}, {})['score']
        perturbed = score_components_v2({'a': .500001, 'b': .499999}, {('a', 'b'): .300001}, {})['score']
        self.assertAlmostEqual(original, split, places=10)
        self.assertLess(abs(perturbed-original), .001)

    def test_two_and_four_group_caps_include_equity_bonus(self):
        from analytics.allocation_score_v2 import SECTORS, score_components_v2
        sectors = {name: 1/11 for name in SECTORS}
        for n, cap in [(2, 40), (4, 70)]:
            weights = {'equity_us': 1/n, **{f'g{i}': 1/n for i in range(n-1)}}
            pairs = {(a, b): 0 for a in weights for b in weights if a < b}
            self.assertLessEqual(score_components_v2(weights, pairs, {'equity_us': sectors})['score'], cap)

    def test_scoped_sheet_writer_refuses_foreign_summary_formula_and_note(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail_sheet import plan_requests
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        grid = [[{} for _ in range(4)] for _ in range(200)]
        grid[10][1] = {'userEnteredValue': {'formulaValue': '=1+1'}, 'note': 'manual'}
        with self.assertRaisesRegex(ValueError, 'Summary'):
            plan_requests(saved, 7, grid, [], 40, 40)

    def test_unclaimed_summary_block_with_recognizable_row_is_not_owned(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail_sheet import plan_requests
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        grid = [[{} for _ in range(4)] for _ in range(200)]
        grid[10][0] = {'userEnteredValue': {'stringValue': 'Висновок'}}
        grid[10][1] = {'userEnteredValue': {'stringValue': 'manual'}}
        with self.assertRaisesRegex(ValueError, 'Summary'):
            plan_requests(saved, 7, grid, [], 40, 40)

    def test_scoped_sheet_writer_refuses_foreign_detail_formula(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail_sheet import plan_requests
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        grid = [[{} for _ in range(4)] for _ in range(200)]
        grid[41][1] = {'userEnteredValue': {'formulaValue': '=1+1'}}
        with self.assertRaisesRegex(ValueError, 'Details'):
            plan_requests(saved, 7, grid, [], 40, 50)

    def test_new_details_never_claims_foreign_group_at_insertion_point(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.holy_grail_sheet import plan_requests
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        grid = [[{} for _ in range(4)] for _ in range(200)]
        foreign = {'range': {'startIndex': 40, 'endIndex': 50}, 'depth': 1, 'collapsed': True}
        with self.assertRaisesRegex(ValueError, 'Details'):
            plan_requests(saved, 7, grid, [foreign], 40, 40)

    def test_failed_extraction_cannot_become_a_cash_only_result(self):
        import pandas as pd
        from analytics.holy_grail_data import enrich_combined_data
        data = {'TOTAL_ASSETS': True, 'CASH_DATA': {'Total': 0}, 'IB_DATA': {},
                'POSITION_DATA': {'as_of_date': '2026-09-30'}}
        settings = {'allocation': {'method_version': 'capital_diversification_v2'}}
        q = enrich_combined_data(data, config=settings, monthly_returns=pd.DataFrame(),
                                 allow_network=False)['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertEqual(q['status'], 'unavailable')

    def test_v2_details_disclose_method_and_market_representatives(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        from analytics.diversification_view import saved_diversification_view
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        saved = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories, allow_network=False)
        rows = saved_diversification_view(saved)['rows']
        self.assertTrue(any(label == 'Представник: Акції США' and value == 'SPY' for label, value in rows))
        self.assertTrue(any(label == 'Формула' and '100' in value for label, value in rows))

    def test_boolean_or_nonfinite_cash_breakdown_is_rejected(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        for invalid in (True, float('inf')):
            data, settings, histories = allocation_fixture()
            data['CASH_DATA']['Breakdown'] = {'brokerage': invalid}
            settings['method_version'] = 'capital_diversification_v2'
            q = enrich_combined_data(data, config={'allocation': settings}, monthly_returns=histories,
                                     allow_network=False)['DIVERSIFICATION_DATA']['allocation_score_v2']
            self.assertEqual(q['status'], 'unavailable')

    def test_malformed_liquidity_metadata_remains_unknown(self):
        from tests.test_allocation_score import allocation_fixture
        from analytics.holy_grail_data import enrich_combined_data
        data, settings, histories = allocation_fixture()
        settings['method_version'] = 'capital_diversification_v2'
        record = {'source': 'https://example.org', 'effective_from': '2020-01-01',
                  'reviewed_at': '2020-01-01', 'liquidation_days': 'unknown'}
        saved = enrich_combined_data(data, config={'allocation': settings, 'diversification': {'exposures': {'ib:SPY': record}}},
                                     monthly_returns=histories, allow_network=False)
        self.assertGreater(saved['DIVERSIFICATION_DATA']['allocation_score_v2']['risk_unknown']['liquidity_pct_nav'], 90/110*100-0.001)
