"""Observable saved indicator, independent of the legacy policy checklist."""
from copy import deepcopy
import unittest
from test_holy_grail_data import saved_legacy_fixture

class IndicatorTests(unittest.TestCase):
    def enrich(self, history=None):
        data = saved_legacy_fixture()
        if history is not None and history.empty:
            data['DIVERSIFICATION_DATA']['indicator'] = saved_legacy_fixture('empty')
        return data


    def test_frozen_saved_result_rejects_changed_holdings_and_models(self):
        from analytics.holy_grail_indicator import validate_saved_indicator
        saved=self.enrich();result=saved['DIVERSIFICATION_DATA']['indicator']
        self.assertTrue(validate_saved_indicator(result,saved,'2026-09-30'))
        changed=deepcopy(saved);changed['TOTAL_ASSETS']+=1
        self.assertFalse(validate_saved_indicator(result,changed,'2026-09-30'))
        changed=deepcopy(result);changed['configuration']['test']='changed'
        self.assertFalse(validate_saved_indicator(changed,saved,'2026-09-30'))


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
        from analytics.holy_grail import fingerprint
        from test_holy_grail_outputs import HolyGrailOutputTests
        from test_holy_grail_outputs import sheet_table
        saved=self.enrich()
        indicator=saved['DIVERSIFICATION_DATA']['indicator']
        indicator['configuration']['private_note']='DO-NOT-PUBLISH'
        indicator['configuration_fingerprint']=fingerprint(indicator['configuration'])
        indicator['result_fingerprint']=fingerprint({k:v for k,v in indicator.items() if k!='result_fingerprint'})
        document=HolyGrailOutputTests().html(saved)
        self.assertIn('<p class="hg-value">15,0</p>',document)
        self.assertNotIn('DO-NOT-PUBLISH',document)
        self.assertNotIn('Оцінка /100',document)
        self.assertEqual(sheet_table(saved)[9][1],15)
