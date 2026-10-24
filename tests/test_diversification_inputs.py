"""The canonical portfolio payload remains the only source for both analytics blocks."""
import json
import unittest
from copy import deepcopy
from decimal import Decimal

from test_holy_grail_data import snapshot_fixture
from test_holy_grail_progress import independent_history
from analytics.holy_grail_data import enrich_combined_data


class QualityInputTests(unittest.TestCase):
    def enrich(self,data,config=None):
        return enrich_combined_data(data,as_of_date='2026-09-30',config=config or {},allow_network=False,
                                    monthly_returns=independent_history().rename(columns=lambda s:'yf:'+s))

    def test_enrichment_adds_both_blocks_without_changing_financial_values(self):
        original=snapshot_fixture();untouched=deepcopy(original)
        saved=self.enrich(original)
        self.assertIn('DIVERSIFICATION_DATA',saved)
        self.assertIn('HOLY_GRAIL_DATA',saved)
        self.assertEqual(original,untouched)
        self.assertEqual({k:v for k,v in saved.items() if k not in {'HOLY_GRAIL_DATA','DIVERSIFICATION_DATA'}},original)
        self.assertAlmostEqual(saved['DIVERSIFICATION_DATA']['effective_streams'],15)

    def test_stablecoin_cash_is_decomposed_and_does_not_inflate_total(self):
        data=snapshot_fixture();data['CASH_DATA']={'Total':Decimal('100'),'Cash_Equivalents':{'USD1':Decimal('60')}}
        data['TOTAL_ASSETS']+=100
        record={'source':'synthetic stablecoin source','effective_from':'2020-01-01','reviewed_at':'2026-10-22',
                'stress_class':'stablecoin_cash','counterparty_complete':True,'counterparty_groups':{'issuer':1},
                'corporate_issuer_applicable':False,'liquidation_days':0,'fx_monetary':False}
        saved=self.enrich(data,{'diversification':{'exposures':{'cash_equivalent:USD1':record}}})
        q=saved['DIVERSIFICATION_DATA']
        self.assertNotEqual(q['status'],'unavailable')
        self.assertEqual(q['reserve_share_pct'],0)
        self.assertEqual(saved['CASH_DATA'],data['CASH_DATA'])
        self.assertAlmostEqual(q['cash_share_pct'],6.25)

    def test_overallocated_cash_components_cannot_create_an_assessment(self):
        data=snapshot_fixture();data['CASH_DATA']={'Total':10,'Cash_Equivalents':{'USD1':20}};data['TOTAL_ASSETS']+=10
        saved=self.enrich(data)
        self.assertEqual(saved['DIVERSIFICATION_DATA']['status'],'unavailable')
        self.assertNotEqual(saved['HOLY_GRAIL_DATA']['status'],'unavailable')

    def test_quality_fingerprint_survives_decimal_roundtrip_and_rejects_changed_metadata(self):
        from analytics.diversification_inputs import quality_inputs_fingerprint
        data=snapshot_fixture();data['CASH_DATA']={'Total':Decimal('10'),'Cash_Equivalents':{}};data['TOTAL_ASSETS']+=10
        saved=self.enrich(data)
        for default in (str,float):
            copy=json.loads(json.dumps(saved,default=default))
            self.assertEqual(quality_inputs_fingerprint(copy),saved['DIVERSIFICATION_DATA']['holdings_fingerprint'])
        data['DATA_METADATA']['last_updated']='2026-10-01'
        self.assertNotEqual(quality_inputs_fingerprint(data),saved['DIVERSIFICATION_DATA']['holdings_fingerprint'])
