"""Observable financial-policy cases, with deterministic monthly return fixtures."""
import unittest
from copy import deepcopy
import json

import numpy as np
import pandas as pd

from test_holy_grail_progress import independent_history


def positions(count=15):
    return [{"id": f"p{i}", "series": f"asset_{i}", "value_usd": 100.,
             "kind": "direct", "weak_proxy": False, "category": "Stocks",
             "risk_record": {"source": "synthetic dated evidence", "effective_from": "2020-01-01",
                             "reviewed_at": "2026-10-22", "stress_class": "equity",
                             "issuer_weights": {f"issuer{i}": 1.}, "counterparty_complete": True,
                             "counterparty_groups": {}, "liquidation_days": 2,
                             "fx_monetary": False}}
            for i in range(count)]


def calculate(rows, history, **kwargs):
    from analytics.diversification_quality import calculate_quality
    return calculate_quality(rows, history, as_of_date="2026-09-30",
                             total_assets=sum(r["value_usd"] for r in rows), **kwargs)


class RiskEquivalentTests(unittest.TestCase):
    def test_independent_fifteen_and_twenty_are_preserved(self):
        for n in (15,20):
            with self.subTest(n=n):
                result=calculate(positions(n),independent_history(n))
                self.assertAlmostEqual(result["effective_streams"],n)
                self.assertEqual(result["modeled_exposure_count"],n)
                self.assertEqual(len(result["checks"]),10)
                json.dumps(result,allow_nan=False)

    def test_positive_and_negative_correlations_have_different_meanings(self):
        base=independent_history(15)
        c=np.full((15,15),.5); np.fill_diagonal(c,1)
        history=pd.DataFrame(base.values@np.linalg.cholesky(c).T,index=base.index,columns=base.columns)
        result=calculate(positions(15),history)
        self.assertAlmostEqual(result["effective_streams"],1.875)
        base=independent_history(2)
        base["asset_1"]=-.9*base["asset_0"]+np.sqrt(1-.9**2)*base["asset_1"]
        result=calculate(positions(2),base)
        self.assertAlmostEqual(result["effective_streams"],20)
        self.assertIn("hedge_driven_count",result["constraints"])
        check=next(c for c in result["checks"] if c["id"]=="breadth")
        self.assertEqual(check["state"],"fail")

    def test_account_splits_cannot_inflate_count(self):
        row=positions(1)[0]
        split=[dict(deepcopy(row),id=str(i),value_usd=1) for i in range(100)]
        self.assertAlmostEqual(calculate(split,independent_history(1))["effective_streams"],1)

    def test_missing_future_and_short_histories_remain_honest(self):
        h=independent_history(2)
        baseline=calculate(positions(2),h)
        future=pd.DataFrame(100,index=[pd.Timestamp("2026-10-31")],columns=h.columns)
        self.assertEqual(calculate(positions(2),pd.concat([h,future]))["effective_streams"],baseline["effective_streams"])
        self.assertIsNone(calculate(positions(2),h.tail(24))["effective_streams"])
        short=calculate(positions(2),h.tail(36))
        self.assertIsNotNone(short["effective_streams"])
        self.assertEqual(next(c for c in short["checks"] if c["id"]=="breadth")["state"],"unknown")

    def test_perfect_hedge_and_nonfinite_inputs_are_unavailable(self):
        h=independent_history(2); h["asset_1"]=-h["asset_0"]
        self.assertIsNone(calculate(positions(2),h)["effective_streams"])
        rows=positions(2); rows[0]["value_usd"]=float('nan')
        result=calculate(rows,h)
        self.assertEqual(result["status"],"unavailable")
        json.dumps(result,allow_nan=False)

class PolicyTests(unittest.TestCase):
    def check(self, result, name):
        return next(c for c in result['checks'] if c['id']==name)

    def test_ten_checks_define_exact_score_range(self):
        from analytics.diversification_quality import summarize_checks, CHECK_IDS
        states=['pass']*4+['fail']*3+['unknown']*3
        result=summarize_checks([dict(id=k,state=v) for k,v in zip(CHECK_IDS,states)])
        self.assertEqual((result['score_min'],result['score_max'],result['score']),(40,70,None))

    def test_known_risk_concentration_is_not_hidden_by_reserves(self):
        rows=positions(1)
        cash=dict(id='reserve',series=None,value_usd=900,is_cash=True,
                  risk_record=dict(source='synthetic custody evidence',effective_from='2020-01-01',
                                   reviewed_at='2026-10-22',stress_class='usd_cash',currency='USD',
                                   counterparty_complete=True,counterparty_groups={},liquidation_days=0,fx_monetary=False))
        result=calculate(rows+[cash],independent_history(1))
        self.assertEqual(self.check(result,'family_concentration')['state'],'fail')
        self.assertIn('family_concentration',result['critical_failures'])
        self.assertAlmostEqual(result['reserve_share_pct'],90)
        self.assertAlmostEqual(result['effective_streams'],1)

    def test_duration_and_credit_spreads_have_correct_units_and_signs(self):
        row=positions(1)[0]
        row['risk_record'].update(stress_class='corporate_credit',rate_duration=5,spread_duration=4)
        result=calculate([row],independent_history(1))
        self.assertAlmostEqual(result['scenarios']['recession']['loss_min_pct'],14)
        self.assertAlmostEqual(result['scenarios']['inflation']['loss_min_pct'],23)
        del row['risk_record']['rate_duration']
        self.assertEqual(self.check(calculate([row],independent_history(1)),'recession')['state'],'unknown')

    def test_unknown_exposure_uses_loss_bounds_not_zero_or_renormalization(self):
        rows=positions(2);rows[0]['value_usd']=10;rows[1]['value_usd']=90;rows[1]['risk_record']={}
        result=calculate(rows,independent_history(2))
        self.assertAlmostEqual(result['scenarios']['recession']['loss_min_pct'],3)
        self.assertAlmostEqual(result['scenarios']['recession']['loss_max_pct'],93)
        self.assertEqual(self.check(result,'recession')['state'],'unknown')

    def test_shared_default_dependencies_are_aggregated_without_double_counting(self):
        rows=positions(2)
        for e in rows:
            e['risk_record'].update(stress_class='stablecoin_lending',counterparty_groups={'platform':1,'stablecoin':1})
        result=calculate(rows,independent_history(2))
        self.assertEqual(self.check(result,'counterparty')['value'],100)
        self.assertEqual(self.check(result,'counterparty')['state'],'fail')
        self.assertLessEqual(result['scenarios']['market_liquidity']['loss_max_pct'],100)

    def test_car_and_fx_haircuts_apply_once_and_stablecoins_are_not_reserves(self):
        row=positions(1)[0];row['risk_record'].update(stress_class='car_inventory',fx_monetary=True)
        self.assertEqual(self.check(calculate([row],independent_history(1)),'local_fx')['value'],30)
        row['is_cash']=True; row['series']=None
        row['risk_record'].update(stress_class='stablecoin_cash',currency='USD',counterparty_groups={'issuer':1})
        result=calculate([row],pd.DataFrame())
        self.assertNotEqual(result['status'],'not_applicable')
        self.assertEqual(result['reserve_share_pct'],0)
        self.assertEqual(self.check(result,'counterparty')['state'],'fail')

    def test_reserve_exemption_requires_identity_and_remaining_maturity(self):
        row=positions(1)[0]
        row['risk_record'].update(stress_class='treasury_reserve',currency='USD',maturity='2027-03-31')
        result=calculate([row],independent_history(1))
        self.assertEqual(result['status'],'not_applicable')
        self.assertEqual(result['effective_streams'],0)
        self.assertIsNone(result['score_min'])
        row['risk_record']['maturity']='2028-03-31'
        self.assertNotEqual(calculate([row],independent_history(1))['status'],'not_applicable')

    def test_weak_stale_and_future_evidence_never_create_passes(self):
        for mutation in ('weak','stale','future'):
            rows=positions()
            for row in rows:
                if mutation=='weak': row['weak_proxy']=True
                if mutation=='stale': row['valuation_stale']=True
                if mutation=='future': row['risk_record']['effective_from']='2026-10-01'
            result=calculate(rows,independent_history())
            for name in ('family_concentration','breadth','stability'):
                if mutation!='future' or name=='family_concentration':
                    self.assertEqual(self.check(result,name)['state'],'unknown')
            self.assertEqual(result['confidence'],'low')

    def test_invalid_policy_and_inconsistent_totals_are_json_safe_unavailable(self):
        row=positions(1)[0]
        result=calculate([row],independent_history(1),policy={'thresholds':{'recession':float('nan')}})
        self.assertEqual(result['status'],'unavailable')
        json.dumps(result,allow_nan=False)
        from analytics.diversification_quality import calculate_quality
        result=calculate_quality([row],independent_history(1),as_of_date='2026-09-30',total_assets=999)
        self.assertEqual(result['status'],'unavailable')

class AdversarialEvidenceTests(unittest.TestCase):
    def test_aliases_of_two_histories_cannot_pass_fifteen_exposure_gate(self):
        base=independent_history(2)
        a=base.asset_0;b=-.9*a+np.sqrt(.19)*base.asset_1
        history=pd.DataFrame({f'asset_{i}':a if i<8 else b for i in range(15)},index=base.index)
        result=calculate(positions(15),history)
        self.assertEqual(result['modeled_exposure_count'],2)
        self.assertEqual(next(c for c in result['checks'] if c['id']=='breadth')['state'],'fail')

    def test_missing_or_impossible_review_evidence_is_not_accepted(self):
        for field,value in [('source',None),('source',42),('reviewed_at','2999-01-01')]:
            rows=positions(15)
            for row in rows: row['risk_record'][field]=value
            result=calculate(rows,independent_history())
            self.assertEqual(next(c for c in result['checks'] if c['id']=='issuer_concentration')['state'],'unknown')

class BoundaryRobustnessTests(unittest.TestCase):
    def test_stale_reserves_do_not_bypass_evidence_rules(self):
        row=positions(1)[0];row['valuation_stale']=True
        row['risk_record'].update(stress_class='treasury_reserve',currency='USD',maturity='2027-03-31')
        self.assertNotEqual(calculate([row],independent_history(1))['status'],'not_applicable')

    def test_unphysical_policy_shocks_are_rejected_before_nonfinite_results(self):
        overrides={'shocks':{'gold':(1e308,0,0,0)}}
        result=calculate(positions(1),independent_history(1),policy=overrides)
        self.assertEqual(result['status'],'unavailable')
        json.dumps(result,allow_nan=False)

class EvidenceIntegrationTests(unittest.TestCase):
    def check(self,result,name):
        return next(c for c in result['checks'] if c['id']==name)

    def test_dated_fund_lookthrough_aggregates_shared_issuer(self):
        rows=positions(2)
        for row in rows:
            row['risk_record']['issuer_weights']={'shared issuer':.3,'other issuer':.7}
        result=calculate(rows,independent_history(2))
        self.assertEqual(self.check(result,'issuer_concentration')['value'],70)
        rows[1]['risk_record']['effective_to']='2026-06-30'
        result=calculate(rows,independent_history(2))
        check=self.check(result,'issuer_concentration')
        self.assertEqual(check['value'],35)
        self.assertEqual(check['upper_bound'],85)
        self.assertEqual(check['state'],'fail')

    def test_government_real_duration_and_loss_floor(self):
        row=positions(1)[0]
        for kind,recession,inflation in [('nominal_government',-10,15),('inflation_linked',-5,7.5)]:
            row['risk_record'].update(stress_class=kind,rate_duration=5)
            result=calculate([row],independent_history(1))
            self.assertAlmostEqual(result['scenarios']['recession']['loss_min_pct'],recession)
            self.assertAlmostEqual(result['scenarios']['inflation']['loss_max_pct'],inflation)
        row['risk_record'].update(stress_class='nominal_government',rate_duration=100)
        self.assertEqual(calculate([row],independent_history(1))['scenarios']['inflation']['loss_max_pct'],100)

    def test_failed_recent_stability_and_unsupported_leverage(self):
        history=independent_history(15)
        for name in history.columns:
            history.loc[history.index[-36:],name]=history.loc[history.index[-36:],'asset_0']
        result=calculate(positions(),history)
        self.assertLess(result['stability']['ratio'],.75)
        self.assertEqual(self.check(result,'stability')['state'],'fail')
        rows=positions();rows[0]['unsupported_risk']=True
        result=calculate(rows,history)
        self.assertEqual(result['status'],'unavailable')
        self.assertIsNone(result['effective_streams'])
