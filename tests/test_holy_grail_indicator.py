"""Observable saved indicator, independent of the legacy policy checklist."""
from copy import deepcopy
import unittest
from test_holy_grail_data import legacy_enrich as enrich_combined_data
from test_holy_grail_data import snapshot_fixture
from test_holy_grail_progress import independent_history

class IndicatorTests(unittest.TestCase):
    def enrich(self, data=None, history=None, config=None):
        return enrich_combined_data(data or snapshot_fixture(), as_of_date='2026-09-30',
            monthly_returns=history if history is not None else independent_history().rename(columns=lambda s:'yf:'+s),
            config=config or {}, allow_network=False)

    def test_independent_indicator_is_saved_without_qualifications(self):
        original=snapshot_fixture();saved=self.enrich(original)
        self.assertIn('indicator',saved['DIVERSIFICATION_DATA'])
        result=saved['DIVERSIFICATION_DATA']['indicator']
        self.assertAlmostEqual(result['effective_streams'],15)
        self.assertEqual(result['observation_count'],60)
        self.assertEqual(original,snapshot_fixture())

    def test_short_treasury_is_a_modeled_asset_distinct_from_long_treasury(self):
        import numpy as np
        data=snapshot_fixture()
        data['IB_DATA']={'Stocks':{'asset_0':100,'asset_1':100},
                         'Bonds':{'IBCIDSHORT':100,'TLT':100}}
        data['TOTAL_ASSETS']=400
        history=independent_history(4).rename(columns={
            'asset_0':'yf:asset_0','asset_1':'yf:asset_1',
            'asset_2':'yf:SHV','asset_3':'yf:TLT'})
        history['yf:SHV']*=.01
        config={'mappings':{'ib:IBCIDSHORT':{
            'symbol':'SHV','kind':'proxy','provider':'yfinance',
            'valid_from':'2026-09-30','valid_until':'2027-09-30'}}}
        result=self.enrich(data,history,config)['DIVERSIFICATION_DATA']['indicator']
        cov=history.cov().to_numpy();w=np.full(4,.25)
        expected=(w@np.sqrt(np.diag(cov)))**2/(w@cov@w)
        self.assertAlmostEqual(result['effective_streams'],expected)
        self.assertEqual(result['modeled_exposure_count'],4)
        self.assertEqual(result['coverage']['reserve'],0)
        self.assertEqual(result['coverage']['model'],25)
        self.assertEqual(result['coverage']['direct'],75)
        self.assertTrue(any('SHV' in m['description'] and '0-1' in m['description']
                            for m in result['models']))
        self.assertEqual(next(m for m in result['models'] if m['series']=='yf:SHV').get('share_pct'),25)

    def test_rounding_is_symmetric_through_enrichment(self):
        for delta in (-.99,.99,-1.01,1.01):
            data=snapshot_fixture();data['TOTAL_ASSETS']+=delta
            result=self.enrich(data)['DIVERSIFICATION_DATA']['indicator']
            self.assertEqual(result['effective_streams'] is not None,abs(delta)<1)

    def test_reserve_and_cash_are_not_extra_streams_and_expire(self):
        data=snapshot_fixture();data['IB_DATA']['Bonds']={'IBCIDTEST':300};data['TOTAL_ASSETS']+=400;data['CASH_DATA']['Total']=100
        record=dict(kind='us_treasury',currency='USD',source='user confirmed',as_of_date='2026-09-30',max_remaining_days=365)
        config={'indicator':{'reserves':{'ib:IBCIDTEST':record}}}
        result=self.enrich(data,config=config)['DIVERSIFICATION_DATA']['indicator']
        self.assertAlmostEqual(result['coverage']['reserve'],300/1900*100)
        self.assertAlmostEqual(result['coverage']['cash'],100/1900*100)
        self.assertAlmostEqual(result['effective_streams'],15)
        record['as_of_date']='2024-09-30'
        expired=self.enrich(data,config=config)['DIVERSIFICATION_DATA']['indicator']
        self.assertEqual(expired['coverage']['reserve'],0)
        self.assertIn('reserve_confirmation_expired_or_invalid',expired['warnings'])

    def test_proxy_comparison_uses_same_months_and_recent_gaps_are_visible(self):
        import pandas as pd
        data=snapshot_fixture();data['POSITION_DATA']['p2p']=[{'balance_usd':100}];data['TOTAL_ASSETS']+=100
        history=independent_history(16).rename(columns=lambda s:'yf:'+s).rename(columns={'yf:asset_15':'yf:HYG'})
        history.loc[history.index[-5],'yf:HYG']=float('nan')
        result=self.enrich(data,history)['DIVERSIFICATION_DATA']['indicator']
        expected=history.dropna().drop(columns='yf:HYG');cov=expected.cov().to_numpy()
        import numpy as np
        w=np.full(15,100/1600);n=(w@np.sqrt(np.diag(cov)))**2/(w@cov@w)
        self.assertAlmostEqual(result['direct_only_effective_streams'],n)
        self.assertEqual(result['observation_count'],59)
        self.assertIsNone(result['recent_effective_streams'])
        self.assertIn('incomplete_recent_window',result['warnings'])

    def test_frozen_saved_result_rejects_changed_holdings_and_models(self):
        from analytics.holy_grail_indicator import validate_saved_indicator
        saved=self.enrich();result=saved['DIVERSIFICATION_DATA']['indicator']
        self.assertTrue(validate_saved_indicator(result,saved,'2026-09-30'))
        changed=deepcopy(saved);changed['TOTAL_ASSETS']+=1
        self.assertFalse(validate_saved_indicator(result,changed,'2026-09-30'))
        changed=deepcopy(result);changed['configuration']['test']='changed'
        self.assertFalse(validate_saved_indicator(changed,saved,'2026-09-30'))

    def test_all_cash_is_not_applicable_and_malformed_config_is_isolated(self):
        data=snapshot_fixture();data['IB_DATA']={};data['CASH_DATA']['Total']=1500
        result=self.enrich(data)['DIVERSIFICATION_DATA']['indicator']
        self.assertEqual(result['status'],'not_applicable')
        self.assertIsNone(result['effective_streams'])
        broken=self.enrich(config={'indicator':[]})['DIVERSIFICATION_DATA']['indicator']
        self.assertEqual(broken['status'],'unavailable')

    def test_count_headline_ignores_legacy_policy_and_invalid_new_does_not_fallback(self):
        from analytics.diversification_view import saved_diversification_view
        saved=self.enrich();saved['DIVERSIFICATION_DATA']['checks']=[]
        view=saved_diversification_view(saved)
        self.assertEqual(view['headline'],'15,0')
        self.assertEqual(view['sheet_number'],15)
        self.assertNotIn('/100',str(view['rows']))
        saved['DIVERSIFICATION_DATA']['indicator']['effective_streams']=999
        self.assertEqual(saved_diversification_view(saved)['effective'],'-')

    def test_html_and_sheet_render_same_count_without_policy_and_protect_provenance(self):
        from test_holy_grail_outputs import HolyGrailOutputTests
        from test_holy_grail_outputs import sheet_table
        saved=self.enrich(config={'indicator':{'private_note':'DO-NOT-PUBLISH'}})
        document=HolyGrailOutputTests().html(saved)
        self.assertIn('<p class="hg-value">15,0</p>',document)
        self.assertNotIn('DO-NOT-PUBLISH',document)
        self.assertNotIn('Оцінка /100',document)
        self.assertEqual(sheet_table(saved)[9][1],15)

    def test_nonlinear_records_are_not_silently_treated_as_linear_positions(self):
        result=self.enrich(config={'diversification':{'exposures':{'category:Stocks':{'leveraged':True}}}})['DIVERSIFICATION_DATA']['indicator']
        self.assertEqual(result['status'],'unavailable')

    def test_twenty_independent_and_shared_proxy_aliases(self):
        import numpy as np
        import pandas as pd
        data=snapshot_fixture();data['IB_DATA']['Stocks']={f'asset_{i}':100 for i in range(20)};data['TOTAL_ASSETS']=2000
        history=independent_history(20).rename(columns=lambda s:'yf:'+s)
        self.assertAlmostEqual(self.enrich(data,history)['DIVERSIFICATION_DATA']['indicator']['effective_streams'],20)
        data['POSITION_DATA']['p2p']=[{'balance_usd':50},{'balance_usd':50}];data['TOTAL_ASSETS']+=100
        history['yf:HYG']=history['yf:asset_0']
        result=self.enrich(data,history)['DIVERSIFICATION_DATA']['indicator']
        self.assertEqual(result['modeled_exposure_count'],20)
        self.assertAlmostEqual(result['coverage']['model'],100/2100*100)

    def test_negative_correlation_hedge_and_no_future_observations(self):
        import numpy as np
        import pandas as pd
        data=snapshot_fixture();data['IB_DATA']['Stocks']={'asset_0':100,'asset_1':100};data['TOTAL_ASSETS']=200
        history=independent_history(2).rename(columns=lambda s:'yf:'+s)
        history['yf:asset_1']=-.9*history['yf:asset_0']+np.sqrt(1-.9**2)*history['yf:asset_1']
        q=self.enrich(data,history)['DIVERSIFICATION_DATA']['indicator']
        self.assertAlmostEqual(q['effective_streams'],20)
        self.assertIn('hedge_driven_count',q['warnings'])
        future=pd.DataFrame(999,index=pd.to_datetime(['2026-10-31']),columns=history.columns)
        self.assertAlmostEqual(self.enrich(data,pd.concat([history,future]))['DIVERSIFICATION_DATA']['indicator']['effective_streams'],20)
