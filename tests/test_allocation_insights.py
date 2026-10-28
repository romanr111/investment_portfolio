"""The current v2 Sheets pipeline reserves the agreed summary without collisions."""
import unittest

from test_holy_grail_data import legacy_enrich as enrich_combined_data
from src.google_sheets.insights_tables import build_portfolio_tab
from src.google_sheets.insights_cells import render_blocks
from test_allocation_score import allocation_fixture


class AllocationInsightsTests(unittest.TestCase):
    def saved(self):
        data,config,history=allocation_fixture()
        data['INDEX_PERFORMANCE']={str(i):dict(name='Benchmark '+str(i),rate_of_return_pct=i) for i in range(5)}
        return enrich_combined_data(data,config={'allocation':config},monthly_returns=history,allow_network=False)

    def test_new_summary_keeps_all_benchmarks_and_has_no_overlapping_blocks(self):
        data=self.saved();tab=build_portfolio_tab(data)
        rows,typed,bounds=render_blocks(tab.blocks)
        self.assertIn('diversification_summary',bounds)
        self.assertEqual(bounds['diversification_summary'],(9,14,0,2))
        self.assertEqual(rows[9][1],data['DIVERSIFICATION_DATA']['allocation_score']['display_score']/100)
        self.assertEqual(typed[(9,1)].kind,'allocation_score')
        self.assertTrue(all(any('Benchmark '+str(i) in row for row in rows) for i in range(5)))
        details=bounds['diversification_details']
        self.assertGreater(details[0],max(b[1] for key,b in bounds.items() if key!='diversification_details'))
        self.assertEqual(rows[details[0]][0],'Диверсифікація - Details')
        self.assertEqual(rows[details[1]-1][0],'Holy Grail - End')

    def test_actual_updater_reuses_score_format_and_details_group_on_repeat(self):
        from tests.fake_sheets import FakeSpreadsheet
        from src.google_sheets.insights_refresh import refresh_insights
        book=FakeSpreadsheet();data=self.saved()
        for _ in range(2):
            refresh_insights(book,data,config={})
        main=book.worksheet('30 Sep 2026')
        self.assertEqual(main.values[(10,2)],data['DIVERSIFICATION_DATA']['allocation_score']['display_score']/100)
        self.assertEqual(main.formats[(10,2)]['numberFormat'],{'type':'PERCENT','pattern':'0%'})
        self.assertEqual(len(main.groups),1)
