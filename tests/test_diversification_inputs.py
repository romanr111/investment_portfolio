"""The canonical portfolio payload remains the only source for both analytics blocks."""
import json
import unittest
from decimal import Decimal

from test_holy_grail_data import snapshot_fixture


class QualityInputTests(unittest.TestCase):
    def test_borrowing_cannot_be_hidden_by_positive_cash_elsewhere(self):
        from analytics.holy_grail_data import enrich_combined_data
        for source in ('broker', 'breakdown'):
            with self.subTest(source=source):
                data = snapshot_fixture()
                data['TOTAL_ASSETS'] += 100
                data['CASH_DATA'] = {'Total': 100, 'Breakdown': {'cash': 200}}
                if source == 'broker':
                    data['IB_DATA']['Net_cash'] = -100
                else:
                    data['CASH_DATA']['Breakdown']['ib_cash'] = -100
                saved = enrich_combined_data(data, config={'allocation': {}}, allow_network=False)
                result = saved['DIVERSIFICATION_DATA']['allocation_score_v2']
                self.assertEqual(result['status'], 'unavailable')
                self.assertIn('unsupported_borrowing', result['input_flags'])
                self.assertIsNone(result['score'])
                self.assertEqual(saved['CASH_DATA'], data['CASH_DATA'])

    def test_reordered_rows_cannot_inherit_another_positions_reviewed_evidence(self):
        for group, amount, identities in (
            ('p2p', 'balance_usd', [{'account': 'A'}, {'account': 'B'}]),
            ('crypto_lending', 'principal_usd', [{'account': 'A', 'asset': 'USDT'}, {'account': 'B', 'asset': 'USDT'}]),
            ('other_assets', 'carrying_value_usd', [{'asset_id': 'A'}, {'asset_id': 'B'}]),
        ):
            with self.subTest(group=group):
                data = snapshot_fixture()
                data['IB_DATA']['Stocks'] = {}
                data['TOTAL_ASSETS'] = 100
                data['POSITION_DATA'][group] = [dict(identity, **{amount: value}) for identity, value in zip(identities, (10, 90))]
                records = {}
                for index, identity in enumerate(identities):
                    records[f'{group}:{index}'] = dict(
                        source='synthetic dated source', effective_from='2020-01-01', reviewed_at='2026-10-22',
                        source_identity=identity, stress_class='p2p', corporate_issuer_applicable=False,
                        counterparty_complete=True, counterparty_groups={}, fx_monetary=False,
                        liquidation_days=0 if index == 0 else 365)
                config = {'diversification': {'exposures': records},
                          'mappings': {key: dict(source_identity=record['source_identity'], symbol=f'SOURCE_{index}')
                                       for index, (key, record) in enumerate(records.items())},
                          'qualifications': {key: dict(source_identity=record['source_identity'], status='reviewed')
                                             for key, record in records.items()}}
                from analytics.holy_grail_data import bound_exposure_record
                self.assertEqual(bound_exposure_record(records, f'{group}:0', None, identities[0]), records[f'{group}:0'])
                data['POSITION_DATA'][group].reverse()
                self.assertEqual(bound_exposure_record(records, f'{group}:0', None, identities[1]), {})
                from analytics.holy_grail_data import extract_exposures
                rows, _, _ = extract_exposures(data, '2026-09-30', config)
                self.assertTrue(all(row['weak_proxy'] for row in rows))
                self.assertTrue(all(row['qualification']['status'] == 'draft' for row in rows))
                self.assertFalse(any(row['symbol'].startswith('SOURCE_') for row in rows))

    def test_quality_fingerprint_survives_decimal_roundtrip_and_rejects_changed_metadata(self):
        from analytics.diversification_inputs import quality_inputs_fingerprint
        data=snapshot_fixture();data['CASH_DATA']={'Total':Decimal('10'),'Cash_Equivalents':{}};data['TOTAL_ASSETS']+=10
        expected=quality_inputs_fingerprint(data)
        for default in (str,float):
            copy=json.loads(json.dumps(data,default=default))
            self.assertEqual(quality_inputs_fingerprint(copy),expected)
        data['DATA_METADATA']['last_updated']='2026-10-01'
        self.assertNotEqual(quality_inputs_fingerprint(data),expected)
