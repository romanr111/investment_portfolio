"""The current v2 Sheets pipeline reserves the agreed summary without collisions."""
import unittest

from test_holy_grail_data import saved_legacy_fixture
from src.google_sheets.insights_tables import build_portfolio_tab
from src.google_sheets.insights_cells import render_blocks


class AllocationInsightsTests(unittest.TestCase):
    def saved(self):
        data=saved_legacy_fixture('allocation')
        data['INDEX_PERFORMANCE']={str(i):dict(name='Benchmark '+str(i),rate_of_return_pct=i) for i in range(5)}
        return data

    def test_new_summary_keeps_all_benchmarks_and_has_no_overlapping_blocks(self):
        data=self.saved();tab=build_portfolio_tab(data)
        rows,typed,bounds=render_blocks(tab.blocks)
        self.assertIn('diversification_summary',bounds)
        start,end,col_start,col_end=bounds['diversification_summary']
        # Summary sits below Performance on the left side, one blank row apart.
        self.assertEqual(col_start,0)
        self.assertEqual(start,bounds['performance'][1]+2)
        first_row=rows[start]
        self.assertEqual(first_row[1],data['DIVERSIFICATION_DATA']['allocation_score']['display_score']/100)
        self.assertEqual(typed[(start,1)].kind,'allocation_score')
        self.assertTrue(all(any('Benchmark '+str(i) in row for row in rows) for i in range(5)))
        # Summary only (owner 2026-10-29): no Details group leaves the tab.
        self.assertNotIn('diversification_details',bounds)
        self.assertEqual([row[0] for row in rows if row[0]=='Диверсифікація - Details'],[])

    def test_actual_updater_reuses_score_format_without_details_group_on_repeat(self):
        from tests.fake_sheets import FakeSpreadsheet
        from src.google_sheets.insights_refresh import refresh_insights
        book=FakeSpreadsheet();data=self.saved()
        for _ in range(2):
            refresh_insights(book,data,config={})
        main=book.worksheet('30 Sep 2026')
        tab=build_portfolio_tab(data)
        _,_,bounds=render_blocks(tab.blocks)
        start,end,col_start,col_end=bounds['diversification_summary']
        self.assertEqual(main.values[(start+1,2)],data['DIVERSIFICATION_DATA']['allocation_score']['display_score']/100)
        self.assertEqual(main.formats[(start+1,2)]['numberFormat'],{'type':'PERCENT','pattern':'0%'})
        self.assertEqual(len(main.groups),0)
