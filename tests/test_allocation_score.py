"""Observable anchors for the capital-weighted diversification score."""
import importlib.util
import unittest
import numpy as np
import pandas as pd


class AllocationScoreTests(unittest.TestCase):
    def test_one_sector_has_zero_but_one_broad_market_has_at_most_25(self):
        self.assertIsNotNone(importlib.util.find_spec('analytics.allocation_score'),
                             'The approved capital-weighted indicator is missing')
        from analytics.allocation_score import score_components
        narrow = score_components({'equity_us': 1.0}, {}, {'equity_us': {'IT': 1}}, 155)
        broad = score_components({'equity_us': 1.0}, {},
                                 {'equity_us': {str(i): 1/11 for i in range(11)}}, 155)
        self.assertEqual(narrow['score'], 0)
        self.assertAlmostEqual(broad['score'], 25)

    def test_90_10_is_concentrated_and_correlations_cannot_improve_score(self):
        from analytics.allocation_score import score_components, MAX_CALIBRATION
        weights = {'equity_us': .9, 'treasury_short': .1}
        sectors = {'equity_us': {str(i): 1/11 for i in range(11)}}
        scores = [score_components(weights, {('equity_us','treasury_short'): r}, sectors,
                                   MAX_CALIBRATION-1e-6)['score'] for r in [-1, 0, .4, 1]]
        self.assertLess(max(scores), 50)
        self.assertEqual(scores[0], scores[1])
        self.assertEqual(sorted(scores, reverse=True), scores)

    def test_missing_sectors_and_correlations_never_manufacture_diversity(self):
        from analytics.allocation_score import score_components
        unknown = score_components({'equity_us': 1}, {}, {'equity_us': {'Financials': .5}},155)
        self.assertEqual(unknown['score'], 0)
        self.assertEqual(score_components({'a': .5, 'b': .5},{},{},155)['score'], 0)

    def test_pairs_keep_their_own_calendar_window(self):
        from analytics.allocation_score import pair_correlations
        rng=np.random.default_rng(42)
        frame=pd.DataFrame(rng.normal(size=(60,3)),index=pd.date_range('2021-10-31',periods=60,freq='ME'),columns=['a','b','tiny'])
        frame.loc[frame.index[:24],'tiny']=np.nan
        pairs=pair_correlations(frame, ['a','b','tiny'], '2026-09-30')
        old=next(p for p in pairs if (p['left'],p['right'])==('a','b'))
        self.assertEqual(old['observations'],60)
        self.assertAlmostEqual(old['correlation'],frame.a.corr(frame.b))
        self.assertEqual(next(p for p in pairs if p['right']=='tiny')['observations'],36)

    def test_display_floor_handles_float_noise_but_does_not_round_up(self):
        from analytics.allocation_score import display_score
        self.assertEqual(display_score(49.999999999),50)
        self.assertEqual(display_score(49.99),49)
        self.assertEqual(display_score(99.6),99)

    def test_reference_calibration_is_frozen_and_reproducible(self):
        from analytics.allocation_score import freeze_calibration, validate_calibration
        rng=np.random.default_rng(72)
        samples=rng.normal(size=(60,3));samples-=samples.mean(axis=0)
        orthogonal=np.linalg.qr(samples)[0]
        frame=pd.DataFrame(orthogonal,index=pd.date_range('2021-10-31',periods=60,freq='ME'),columns=['a','b','c'])
        ref=dict(a=1/3,b=1/3,c=1/3)
        cal=freeze_calibration(frame,ref,{},profiles={})
        self.assertTrue(validate_calibration(cal))
        self.assertAlmostEqual(cal['reference_score'],100)
        cal['coefficient']+=1
        self.assertFalse(validate_calibration(cal))


def allocation_fixture():
    from analytics.allocation_score import freeze_calibration
    rng=np.random.default_rng(125)
    dates=pd.date_range('2021-10-31',periods=60,freq='ME')
    samples=rng.normal(size=(60,4));samples-=samples.mean(axis=0)
    groups=['equity_us','treasury_short','gold','car_business']
    frame=pd.DataFrame(np.linalg.qr(samples)[0][:,:3],index=dates,columns=groups[:3])
    sectors={'equity_us': {'Information Technology': .5,'Financials': .5}}
    ref=dict.fromkeys(groups,.25)
    cal=freeze_calibration(frame,ref,sectors,profiles={},business=['car_business'])
    data={'IB_DATA':{'Stocks':{'SPY':90},'Bonds':{'SHV':10}},'TOTAL_ASSETS':110,
          'CASH_DATA':{'Total':10},'POSITION_DATA':{'as_of_date':'2026-09-30'},
          'DATA_METADATA':{'last_updated':'2026-09-30'}}
    settings={'calibration':cal,'profiles':{'ib:SPY':{'as_of_date':'2026-09-30','source':'https://example.org/fund',
              'components':[{'group':'equity_us','share':1,'sectors':sectors['equity_us']}]},
              'ib:SHV':{'as_of_date':'2026-09-30','source':'https://example.org/fund',
              'components':[{'group':'treasury_short','share':1}]}}}
    histories=frame.rename(columns={'equity_us':'yf:SPY','treasury_short':'yf:SHV','gold':'yf:IAU'})
    return data,settings,histories


class AllocationIntegrationTests(unittest.TestCase):
    def saved(self, data=None, settings=None, history=None):
        from analytics.holy_grail_data import enrich_combined_data
        original,config,returns=allocation_fixture()
        return enrich_combined_data(data if data is not None else original,
            config={'allocation':settings if settings is not None else config},
            monthly_returns=history if history is not None else returns,allow_network=False)

    def test_enrichment_saves_new_score_without_changing_financial_fields(self):
        from analytics.holy_grail_data import enrich_combined_data
        from copy import deepcopy
        data,settings,history=allocation_fixture();before=deepcopy(data)
        saved=enrich_combined_data(data,config={'allocation':settings},monthly_returns=history,allow_network=False)
        self.assertIn('allocation_score',saved['DIVERSIFICATION_DATA'])
        result=saved['DIVERSIFICATION_DATA']['allocation_score']
        self.assertEqual(result['version'],'capital_diversification_v1')
        self.assertLess(result['score'],50)
        self.assertEqual(result['coverage']['cash_pct_nav'],10/110*100)
        self.assertEqual(data,before)
        self.assertEqual({k:saved[k] for k in before},before)

    def test_saved_result_replays_and_stale_or_corrupt_data_never_falls_back(self):
        from analytics.allocation_inputs import validate_saved_allocation
        from analytics.diversification_view import saved_diversification_view
        saved=self.saved();q=saved['DIVERSIFICATION_DATA']['allocation_score']
        self.assertTrue(validate_saved_allocation(q,saved,'2026-09-30'))
        view=saved_diversification_view(saved)
        self.assertTrue(view.get('allocation'))
        self.assertEqual(view['headline'],str(q['display_score'])+'%')
        q['score']=99
        self.assertEqual(saved_diversification_view(saved)['headline'],'Дані недоступні')

    def test_rounding_unknowns_and_cached_balances_have_explicit_statuses(self):
        for delta in [-.99,.99,-1.01,1.01]:
            data,_,_=allocation_fixture();data['TOTAL_ASSETS']+=delta
            q=self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']
            self.assertEqual(q['score'] is not None,abs(delta)<1)
        data,settings,_=allocation_fixture();data['DATA_QUALITY']={'crypto':{'freshness':'stale'}}
        q=self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertEqual(q['status'],'provisional')
        self.assertIsNotNone(q['score'])

    def test_unknown_position_stays_in_denominator_and_can_block_main_score(self):
        data,_,_=allocation_fixture();data['IB_DATA']['Stocks']['UNMAPPED']=.01;data['TOTAL_ASSETS']+=.01
        q=self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertIsNotNone(q['score']);self.assertGreater(q['coverage']['unknown_pct_invested'],0)
        data['IB_DATA']['Stocks']['UNMAPPED']=10;data['TOTAL_ASSETS']=120
        self.assertIsNone(self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']['score'])

    def test_all_cash_and_one_known_asset_need_no_fake_correlations(self):
        data,_,_=allocation_fixture();data['IB_DATA']={};data['CASH_DATA']['Total']=110
        q=self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertEqual(q['status'],'not_applicable');self.assertIsNone(q['score'])
        data['IB_DATA']={'Stocks':{'SPY':100}};data['CASH_DATA']['Total']=10
        q=self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertGreater(q['score'],0);self.assertLessEqual(q['score'],25)

    def test_split_accounts_and_identical_lookthrough_cannot_change_score(self):
        data,settings,history=allocation_fixture();base=self.saved()['DIVERSIFICATION_DATA']['allocation_score']['score']
        data['IB_DATA']['Stocks']={'SPY':45,'DUPLICATE':45}
        settings['profiles']['ib:DUPLICATE']=settings['profiles']['ib:SPY']
        self.assertEqual(self.saved(data,settings,history)['DIVERSIFICATION_DATA']['allocation_score']['score'],base)

    def test_expired_and_reassigned_profiles_are_uncovered(self):
        from analytics.allocation_inputs import profile_for
        _,config,_=allocation_fixture();p=dict(id='ib:SPY',category='Stocks')
        config['profiles']['ib:SPY']['valid_until']='2026-09-29'
        self.assertIsNone(profile_for(p,config,'2026-09-30'))
        del config['profiles']['ib:SPY']['valid_until']
        config['profiles']['ib:SPY']['source_identity']={'asset_id':'car-one'}
        self.assertIsNone(profile_for(p,config,'2026-09-30'))

    def test_business_sensitivity_uses_the_same_fixed_coefficient(self):
        data,settings,history=allocation_fixture()
        data['POSITION_DATA']['other_assets']=[dict(asset_id='car-one',carrying_value_usd=30)]
        data['TOTAL_ASSETS']+=30
        settings['profiles']['other_assets:0']=dict(as_of_date='2026-09-30',source='user confirmed model',
            source_identity={'asset_id':'car-one'},components=[dict(group='car_business',share=1)])
        q=self.saved(data,settings,history)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertIsNotNone(q['sensitivity_score'])
        self.assertLess(q['sensitivity_score'],q['score'])
        self.assertEqual(q['calibration_fingerprint'],settings['calibration']['fingerprint'])

    def test_html_sheet_and_scoped_writer_share_one_percent_not_the_old_count(self):
        from test_holy_grail_outputs import HolyGrailOutputTests
        from test_holy_grail_outputs import sheet_table
        from analytics.holy_grail_sheet import plan_requests
        saved=self.saved();q=saved['DIVERSIFICATION_DATA']['allocation_score']
        html=HolyGrailOutputTests().html(saved)
        self.assertIn('Диверсифікація інвестованої частини',html)
        self.assertIn('<p class="hg-value">'+str(q['display_score'])+'%</p>',html)
        self.assertNotIn('Еквівалента джерел ризику / орієнтир',html)
        table=sheet_table(saved)
        self.assertEqual(table[9][1],q['display_score']/100)
        grid=[[{} for _ in range(4)] for _ in range(200)]
        requests,_=plan_requests(saved,7,grid,[],40,100)
        cell=requests[0]['updateCells']['rows'][0]['values'][1]['userEnteredValue']['numberValue']
        self.assertEqual(cell,q['display_score']/100)
        formats=[r['repeatCell']['cell']['userEnteredFormat'].get('numberFormat') for r in requests if 'repeatCell' in r]
        self.assertIn({'type':'PERCENT','pattern':'0%'},formats)

    def test_private_sources_and_usd_values_are_not_published(self):
        from test_holy_grail_outputs import HolyGrailOutputTests
        data,settings,history=allocation_fixture()
        settings['profiles']['ib:SPY']['source']='https://private.example/SECRET-CONFIRMATION'
        saved=self.saved(data,settings,history)
        html=HolyGrailOutputTests().html(saved)
        self.assertNotIn('SECRET-CONFIRMATION',html)

    def test_cash_only_liability_and_accounting_adjustment_are_outside_score_but_margin_blocks(self):
        data,_,_=allocation_fixture()
        data['CASH_DATA']['Breakdown']={'ib_cash':20,'debt':-1,'manual_reconciliation':-9}
        q=self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertIsNotNone(q['score'])
        self.assertIn('cash_liabilities_outside_scope',q['warnings'])
        data['CASH_DATA']['Breakdown']['ib_cash']=-1
        self.assertIsNone(self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']['score'])

    def test_pair_uncertainty_gate_blocks_even_under_five_percent_unknown_capital(self):
        data,_,_=allocation_fixture();data['IB_DATA']['Stocks']['UNMAPPED']=2;data['TOTAL_ASSETS']+=2
        q=self.saved(data=data)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertLess(q['coverage']['unknown_pct_invested'],5)
        self.assertGreater(q['coverage']['missing_pair_max_points'],5)
        self.assertEqual(q['status'],'unavailable')

    def test_partial_and_lagged_pairs_preserve_real_dates_and_never_fill_returns(self):
        _,_,history=allocation_fixture();history.loc[history.index[-1],'yf:SHV']=np.nan
        q=self.saved(history=history)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertEqual(q['status'],'provisional')
        self.assertEqual(q['pairs'][0]['observations'],59)
        self.assertEqual(q['pairs'][0]['last_month'],'2026-08-31')
        self.assertIsNone(q['histories']['treasury_short']['2026-09-30T00:00:00.000'])

    def test_future_duplicate_and_non_month_end_histories_are_rejected_or_excluded(self):
        _,_,history=allocation_fixture()
        history.loc[pd.Timestamp('2026-10-31')]=10000
        q=self.saved(history=history)['DIVERSIFICATION_DATA']['allocation_score']
        self.assertEqual(q['pairs'][0]['observations'],60)
        history.index=list(history.index[:-1])+[pd.Timestamp('2026-10-15')]
        self.assertIsNone(self.saved(history=history)['DIVERSIFICATION_DATA']['allocation_score']['score'])

    def test_shipped_reference_and_maturity_groups_use_the_same_method(self):
        import json
        from analytics.allocation_inputs import MODEL_PATH,PROFILE_PATH,GROUPS
        from analytics.allocation_score import validate_calibration
        cal=json.loads(MODEL_PATH.read_text())
        self.assertTrue(validate_calibration(cal))
        self.assertEqual(cal['reference_score'],100)
        profiles=json.loads(PROFILE_PATH.read_text())
        self.assertNotEqual(profiles['ib:SHV']['components'][0]['group'],profiles['ib:TLT']['components'][0]['group'])
        self.assertEqual(GROUPS['credit_hy_usd'][1],'HYG')

    def test_derived_snapshot_adds_score_without_rewriting_existing_analytics(self):
        import json,tempfile
        from pathlib import Path
        from analytics.holy_grail_data import enrich_snapshot_file
        data,settings,history=allocation_fixture()
        data['HOLY_GRAIL_DATA']={'original':'preserve me'}
        data['DIVERSIFICATION_DATA']={'indicator':{'original':'preserve me too'}}
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'input.json';target=Path(directory)/'derived'/'output.json'
            source.write_text(json.dumps(dict(as_of_date='2026-09-30',data=data)))
            raw=source.read_bytes()
            with patch('analytics.holy_grail_data.collect_return_history',return_value=(history,{},set())):
                result=enrich_snapshot_file(source,target,config={'allocation':settings},allow_network=False)['data']
            self.assertEqual(source.read_bytes(),raw)
            self.assertEqual(result['HOLY_GRAIL_DATA'],data['HOLY_GRAIL_DATA'])
            self.assertEqual(result['DIVERSIFICATION_DATA']['indicator'],data['DIVERSIFICATION_DATA']['indicator'])
            self.assertIsNotNone(result['DIVERSIFICATION_DATA']['allocation_score']['score'])

    def test_signed_quantities_and_nonlinear_risk_cannot_hide_behind_positive_values(self):
        data,settings,history=allocation_fixture()
        data['POSITION_DATA']['crypto']=[{'asset':'BTC','quantity':-1,'value_usd':10}]
        data['TOTAL_ASSETS']+=10
        history['yf:BTC-USD']=history['yf:IAU']
        self.assertIsNone(self.saved(data,settings,history)['DIVERSIFICATION_DATA']['allocation_score']['score'])

    def test_sector_count_cannot_exceed_eleven_or_create_more_than_25_points(self):
        from analytics.allocation_score import score_components
        with self.assertRaises(ValueError):
            score_components({'equity_us':1},{},{'equity_us':{str(i):1/12 for i in range(12)}},155)

    def test_main_histories_are_collected_once_before_legacy_individual_tickers(self):
        import tempfile
        from analytics.holy_grail_data import collect_return_history
        calls=[]
        def fetch(symbol,start,end):
            calls.append(symbol)
            return dict(prices=pd.Series(np.arange(63)+100.,index=pd.date_range('2021-07-31',periods=63,freq='ME')),
                        currency='USD',frequency='daily')
        positions=[dict(series='yf:OLD',symbol='OLD',value_usd=100),
                   dict(series='yf:SPY',symbol='SPY',value_usd=0,collection_priority=0),
                   dict(series='yf:SPY',symbol='SPY',value_usd=50)]
        with tempfile.TemporaryDirectory() as directory:
            frame,_,_=collect_return_history(positions,as_of_date='2026-09-30',cache_dir=directory,fetch_market=fetch)
        self.assertEqual(calls,['SPY','OLD'])
        self.assertEqual(set(frame.columns),{'yf:SPY','yf:OLD'})

    def test_broken_new_configuration_does_not_destroy_usable_legacy_analytics(self):
        from unittest.mock import patch
        from analytics.holy_grail_data import enrich_combined_data
        data,_,history=allocation_fixture()
        with patch('analytics.holy_grail_data.collect_return_history',return_value=(history,{},set())):
            saved=enrich_combined_data(data,config={'allocation':[]},allow_network=False)
        self.assertIsNotNone(saved['HOLY_GRAIL_DATA']['effective_streams'])
        self.assertEqual(saved['DIVERSIFICATION_DATA']['allocation_score']['status'],'unavailable')

    def test_sheet_cli_rejects_envelope_date_mismatch_before_authentication(self):
        import contextlib,io,json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from analytics.holy_grail_sheet import main
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad_date.json'
            path.write_text(json.dumps(dict(as_of_date='2026-10-31',data=self.saved())))
            args=['sheet','--snapshot',str(path),'--spreadsheet-id','test','--sheet-id','1','--dry-run']
            with patch('sys.argv',args),patch('src.google_sheets.spreadsheet_structure.GoogleSheetsClient',side_effect=AssertionError('No auth on invalid input')),contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:main()
            self.assertEqual(error.exception.code,2)

    def test_historical_display_uses_its_saved_group_models_not_todays_registry(self):
        from unittest.mock import patch
        from analytics.diversification_view import saved_diversification_view
        data=self.saved();before=saved_diversification_view(data)
        with patch.dict('analytics.allocation_inputs.GROUPS',{'equity_us':('CHANGED LABEL','QQQ')}):
            after=saved_diversification_view(data)
        self.assertEqual(after['rows'],before['rows'])
        self.assertEqual(after['drivers'],before['drivers'])


if __name__ == '__main__':
    unittest.main()
