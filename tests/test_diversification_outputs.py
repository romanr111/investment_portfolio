"""Shared saved views, not output-side risk calculations."""
import unittest
from html import escape
from copy import deepcopy
from unittest.mock import Mock, patch
from types import SimpleNamespace

import test_diversification_inputs as input_cases
import test_holy_grail_outputs as legacy_cases
from test_holy_grail_outputs import sheet_table


class QualityOutputTests(unittest.TestCase):
    def saved(self):
        from test_holy_grail_data import snapshot_fixture
        saved = input_cases.QualityInputTests().enrich(snapshot_fixture())
        saved["DIVERSIFICATION_DATA"].pop("indicator", None)
        return saved

    def test_both_outputs_show_same_quality_and_count_without_fetching(self):
        from analytics.diversification_view import saved_diversification_view
        data=self.saved();view=saved_diversification_view(data)
        with patch('analytics.holy_grail_data.collect_return_history',side_effect=AssertionError('No output fetching')):
            table=sheet_table(data)
            self.assertEqual(table[9][:2],['Диверсифікація /100',view['score_cell']])
            html=legacy_cases.HolyGrailOutputTests().html(data)
            self.assertIn(view['headline'],html)
            self.assertIn('15,00',html)
            self.assertIn('Еквівалент за ризиком',html)
            self.assertNotIn('Ціль досягнута',html)
            self.assertNotIn('<p class="hg-value">100,0%</p>',html)

    def test_rounded_source_total_keeps_the_saved_estimate_visible(self):
        from analytics.diversification_view import saved_diversification_view
        from test_holy_grail_data import snapshot_fixture
        for extra in (.01, .99):
            with self.subTest(extra=extra):
                data = snapshot_fixture()
                data['IB_DATA']['Stocks']['asset_0'] += extra
                saved = input_cases.QualityInputTests().enrich(data)
                saved['DIVERSIFICATION_DATA'].pop('indicator', None)
                quality = saved['DIVERSIFICATION_DATA']
                self.assertAlmostEqual(sum(quality['coverage'].values()), 100)
                view = saved_diversification_view(saved)
                self.assertNotEqual(view['effective'], '-')
                table = sheet_table(saved)
                self.assertIn(view['effective'], str(table[10][:2]))
                self.assertIn(escape(view['effective']), legacy_cases.HolyGrailOutputTests().html(saved))
                self.assertEqual(saved['TOTAL_ASSETS'], 1500)

    def test_invalid_new_result_does_not_fall_back_to_legacy(self):
        from analytics.diversification_view import saved_diversification_view
        data=self.saved();data['DIVERSIFICATION_DATA']['as_of_date']='2026-06-30'
        view=saved_diversification_view(data)
        self.assertEqual(view['effective'],'-')
        self.assertIsNone(view['score'])
        self.assertIn('не відповідає',view['status'])

    def test_legacy_snapshot_has_no_current_quality_score_or_old_percentage(self):
        from analytics.diversification_view import saved_diversification_view
        data=self.saved();del data['DIVERSIFICATION_DATA']
        view=saved_diversification_view(data)
        self.assertTrue(view['legacy'])
        self.assertIsNone(view['score'])
        self.assertIn('Попередній метод',view['status'])
        self.assertNotIn('%',view['headline'])

    def test_private_evidence_never_appears_in_outputs_and_rounding_is_honest(self):
        from analytics.diversification_view import saved_diversification_view
        data=self.saved();q=data['DIVERSIFICATION_DATA']
        q['source_provenance']={'PRIVATE-ACCOUNT':'12345'}
        q['scenarios']['recession']['private']='PRIVATE-ACCOUNT'
        q['effective_streams']=14.9996
        self.assertEqual(saved_diversification_view(data)['effective'],'<15')
        self.assertNotIn('PRIVATE-ACCOUNT',legacy_cases.HolyGrailOutputTests().html(data))

    def test_point_and_range_scores_are_not_percent_cells(self):
        from analytics.diversification_view import saved_diversification_view
        data=self.saved();q=data['DIVERSIFICATION_DATA']
        for i,check in enumerate(q['checks']): check['state']='pass' if i<7 else 'fail'
        q.update(score=70,score_min=70,score_max=70,check_counts={'pass':7,'fail':3,'unknown':0})
        self.assertEqual(saved_diversification_view(data)['score_cell'],70)
        from src.google_sheets.formatting import PortfolioFormatter
        sheet=SimpleNamespace(id=27,spreadsheet=Mock(),get=Mock(return_value=[[]]*99+[['Holy Grail - Details']]))
        sheet.spreadsheet.fetch_sheet_metadata.return_value={'sheets':[{'properties':{'sheetId':27},'rowGroups':[
            {'range':{'startIndex':100,'endIndex':130},'depth':1},
            {'range':{'startIndex':100,'endIndex':130},'depth':2},
            {'range':{'startIndex':10,'endIndex':20},'depth':1}]}]}
        PortfolioFormatter(sheet).format_holy_grail((100,120),quality=True)
        requests=sheet.spreadsheet.batch_update.call_args.args[0]['requests']
        fmt=requests[0]['repeatCell']['cell']['userEnteredFormat']['numberFormat']
        self.assertEqual(fmt,{'type':'NUMBER','pattern':'0"/100"'})
        deleted=[r['deleteDimensionGroup']['range'] for r in requests if 'deleteDimensionGroup' in r]
        self.assertEqual(len(deleted),2)
        self.assertTrue(all(r['startIndex']==100 for r in deleted))
        self.assertTrue(any('updateCells' in r for r in requests),'Stale owned diagnostic rows must be cleared')

class OutputAdversarialTests(unittest.TestCase):
    def test_malformed_optional_saved_fields_fail_closed_without_legacy_fallback(self):
        from analytics.diversification_view import saved_diversification_view
        for field,value in [('constraints',None),('scenarios',None),('cash_share_pct','bad'),('cash_share_pct',float('nan'))]:
            data=QualityOutputTests().saved();data['DIVERSIFICATION_DATA'][field]=value
            view=saved_diversification_view(data)
            self.assertEqual(view['effective'],'-')
            self.assertFalse(view['legacy'])

    def test_prior_owned_groups_are_captured_before_rewrite_and_old_tail_is_unhidden(self):
        from src.google_sheets.formatting import PortfolioFormatter
        spreadsheet=Mock()
        spreadsheet.fetch_sheet_metadata.return_value={'sheets':[{'properties':{'sheetId':27},'rowGroups':[
            {'range':{'startIndex':100,'endIndex':130},'depth':1}]}]}
        sheet=SimpleNamespace(id=27,spreadsheet=spreadsheet,get=Mock(return_value=[[]]*99+[['Holy Grail - Details']]))
        formatter=PortfolioFormatter(sheet)
        formatter.capture_holy_grail_groups()
        sheet.get.return_value=[]  # the old header has now been replaced by holdings
        formatter.format_holy_grail((120,150),quality=True)
        requests=spreadsheet.batch_update.call_args.args[0]['requests']
        self.assertTrue(any(r.get('deleteDimensionGroup',{}).get('range',{}).get('startIndex')==100 for r in requests))
        restore=[r['updateDimensionProperties'] for r in requests if r.get('updateDimensionProperties',{}).get('properties',{}).get('hiddenByUser') is False]
        self.assertTrue(any(r['range']['startIndex']==100 and r['range']['endIndex']==130 for r in restore))

    def test_limits_and_key_failures_are_visible_next_to_headline(self):
        from analytics.diversification_view import saved_diversification_view
        data=QualityOutputTests().saved();q=data['DIVERSIFICATION_DATA']
        q['constraints']=['stale_valuations','hedge_driven_count']
        q['checks'][0]['state']='fail'
        q['checks'][-1].update(state='unknown',reasons=['insufficient_evidence'])
        from analytics.diversification_quality import summarize_checks
        q.update(summarize_checks(q['checks']))
        view=saved_diversification_view(data)
        self.assertIn('Концентрація',view['sheet_status'])
        self.assertIn('застарілі',view['principal_constraint'])
        self.assertIn('Хеджування',view['headline_warning'])
        html=legacy_cases.HolyGrailOutputTests().html(data)
        headline_area=html.split('<table class="hg-table">')[0].split('<section id="holy-grail">')[-1]
        self.assertIn(view['principal_constraint'],headline_area)
        self.assertIn('Хеджування',headline_area)
        self.assertTrue(any('недостатньо' in str(row).lower() for row in view['rows']))
