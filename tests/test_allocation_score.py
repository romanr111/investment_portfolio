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
    def saved(self, name='allocation'):
        from test_holy_grail_data import saved_legacy_fixture
        return saved_legacy_fixture(name)

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


    def test_expired_and_reassigned_profiles_are_uncovered(self):
        from analytics.allocation_inputs import profile_for
        _,config,_=allocation_fixture();p=dict(id='ib:SPY',category='Stocks')
        config['profiles']['ib:SPY']['valid_until']='2026-09-29'
        self.assertIsNone(profile_for(p,config,'2026-09-30'))
        del config['profiles']['ib:SPY']['valid_until']
        config['profiles']['ib:SPY']['source_identity']={'asset_id':'car-one'}
        self.assertIsNone(profile_for(p,config,'2026-09-30'))


    def test_full_replay_rejects_incorrect_business_sensitivity_even_with_valid_seal(self):
        from copy import deepcopy
        from analytics.allocation_inputs import validate_saved_allocation
        from analytics.holy_grail import fingerprint
        saved=self.saved('business')
        self.assertTrue(validate_saved_allocation(saved['DIVERSIFICATION_DATA']['allocation_score'],saved))
        for field in ['sensitivity_score','sensitivity_display_score']:
            with self.subTest(field=field):
                altered=deepcopy(saved)
                q=altered['DIVERSIFICATION_DATA']['allocation_score']
                q[field]=99
                q['result_fingerprint']=fingerprint({k:v for k,v in q.items() if k!='result_fingerprint'})
                self.assertFalse(validate_saved_allocation(q,altered,replay=True))

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
        from analytics.holy_grail import fingerprint
        saved=self.saved()
        q=saved['DIVERSIFICATION_DATA']['allocation_score']
        q['source_provenance']={'private': 'SECRET-CONFIRMATION'}
        q['result_fingerprint']=fingerprint({k:v for k,v in q.items() if k!='result_fingerprint'})
        html=HolyGrailOutputTests().html(saved)
        self.assertNotIn('SECRET-CONFIRMATION',html)

    def test_cash_only_liability_and_accounting_adjustment_are_outside_score_but_margin_blocks(self):
        from analytics.holy_grail_data import enrich_combined_data
        data,settings,history=allocation_fixture()
        data['CASH_DATA']['Breakdown']={'ib_cash':20,'debt':-1,'manual_reconciliation':-9}
        q=enrich_combined_data(data,config={'allocation':settings},monthly_returns=history,
                               allow_network=False)['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertIsNotNone(q['score'])
        self.assertIn('cash_liabilities_outside_scope',q['warnings'])
        data['CASH_DATA']['Breakdown']['ib_cash']=-1
        q=enrich_combined_data(data,config={'allocation':settings},monthly_returns=history,
                               allow_network=False)['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertIsNone(q['score'])
        self.assertIn('unsupported_borrowing',q['warnings'])


    def test_maturity_groups_use_distinct_representatives(self):
        import json
        from analytics.allocation_inputs import PROFILE_PATH,GROUPS
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
            self.assertIsNotNone(result['DIVERSIFICATION_DATA']['allocation_score_v2']['score'])

    def test_signed_quantities_and_nonlinear_risk_cannot_hide_behind_positive_values(self):
        from analytics.holy_grail_data import enrich_combined_data
        data,settings,history=allocation_fixture()
        data['POSITION_DATA']['crypto']=[{'asset':'BTC','quantity':-1,'value_usd':10}]
        data['TOTAL_ASSETS']+=10
        history['yf:BTC-USD']=history['yf:IAU']
        q=enrich_combined_data(data,config={'allocation':settings},monthly_returns=history,
                               allow_network=False)['DIVERSIFICATION_DATA']['allocation_score_v2']
        self.assertIsNone(q['score'])
        self.assertIn('unsupported_risk',q['warnings'])


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
        from test_holy_grail_data import saved_legacy_fixture
        data = saved_legacy_fixture('allocation')
        with patch('analytics.holy_grail_data.collect_return_history',return_value=(history,{},set())):
            saved=enrich_combined_data(data,config={'allocation':[]},allow_network=False)
        self.assertIsNotNone(saved['HOLY_GRAIL_DATA']['effective_streams'])
        self.assertEqual(saved['DIVERSIFICATION_DATA']['allocation_score_v2']['status'],'unavailable')

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
