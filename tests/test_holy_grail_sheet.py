"""Scoped edits must not replace a sheet or hide unrelated data."""
import importlib.util
import unittest
import test_holy_grail_indicator as indicator_cases

class SheetTests(unittest.TestCase):
    def test_owned_collapsed_group_with_foreign_cells_refuses_unhiding(self):
        from analytics.holy_grail_sheet import plan_requests
        grid = [[{} for _ in range(4)] for _ in range(100)]
        grid[39][0] = {'userEnteredValue': {'stringValue': 'Диверсифікація - Details'}}
        grid[50][2] = {'userEnteredValue': {'stringValue': 'unrelated data'}}
        group = {'range': {'startIndex': 40, 'endIndex': 90}, 'depth': 1, 'collapsed': True}
        with self.assertRaisesRegex(ValueError, 'foreign cells'):
            plan_requests(indicator_cases.IndicatorTests().enrich(), 7, grid, [group], 40, 90)

    def test_many_pair_details_fit_and_remain_present(self):
        from analytics.holy_grail_sheet import plan_requests
        from unittest.mock import patch
        view = {'indicator': True, 'allocation': True, 'sheet_summary': [],
                'sheet_number': 58, 'as_of': '2026-09-30', 'coverage_text': '', 'status': '',
                'rows': [('Method', 'definition')] * 40 +
                        [('Історія пар', 'pair-%02d' % n) for n in range(66)]}
        grid = [[{} for _ in range(4)] for _ in range(200)]
        grid[131][0] = {'userEnteredValue': {'stringValue': 'Диверсифікація - Details'}}
        with patch('analytics.holy_grail_sheet.saved_diversification_view', return_value=view):
            requests, owned = plan_requests({}, 7, grid, [], 132, 181)
        self.assertLessEqual(owned['new_end'], 200)
        output = str(requests)
        for n in range(66):
            self.assertIn('pair-%02d' % n, output)

    def test_details_end_marker_conflict_refuses_write_before_touching_manual_rows(self):
        from analytics.holy_grail_sheet import deliver
        from unittest.mock import Mock, patch
        import tempfile
        grid=[[{} for _ in range(4)] for _ in range(200)]
        for row,text in [(39,'Диверсифікація - Details'),(45,'Holy Grail - End'),
                         (80,'UNRELATED USER DATA')]:
            grid[row][0]={'userEnteredValue':{'stringValue':text}}
        before={'grid':grid,'groups':[{'range':{'startIndex':40,'endIndex':100},'depth':1}],
                'row_metadata':[{} for _ in grid],'properties':{'title':'QA'}}
        book=Mock();book.id='qa'
        for apply in [False,True]:
            with self.subTest(apply=apply),tempfile.TemporaryDirectory() as directory,patch('analytics.holy_grail_sheet.read_state',return_value=before):
                with self.assertRaisesRegex(ValueError,'end marker'):
                    deliver(book,7,indicator_cases.IndicatorTests().enrich(),directory,apply=apply)
        book.batch_update.assert_not_called()

    def test_scoped_planner_has_no_destructive_sheet_requests(self):
        self.assertIsNotNone(importlib.util.find_spec('analytics.holy_grail_sheet'))
        from analytics.holy_grail_sheet import plan_requests
        saved=indicator_cases.IndicatorTests().enrich()
        grid=[[{} for _ in range(4)] for _ in range(70)]
        grid[39][0]={'userEnteredValue':{'stringValue':'Диверсифікація - Details'}}
        grid[40][2]={'userEnteredValue':{'stringValue':'UNRELATED'}}
        requests,owned=plan_requests(saved,7,grid,[],40,60)
        self.assertNotIn('deleteSheet',str(requests));self.assertNotIn('deleteDimension',str(requests))
        self.assertNotIn('addDimensionGroup',str(requests))
        for r in requests:
            if 'updateCells' in r:
                bounds=r['updateCells']['range']
                self.assertEqual(bounds['endColumnIndex'],2)
        self.assertEqual(owned['summary'],[9,14])

    def test_existing_summary_conflict_is_refused(self):
        from analytics.holy_grail_sheet import plan_requests
        grid=[[{} for _ in range(4)] for _ in range(100)]
        grid[9][0]={'userEnteredValue':{'stringValue':'MANUAL ACCOUNTING'}}
        with self.assertRaises(ValueError):
            plan_requests(indicator_cases.IndicatorTests().enrich(),7,grid,[],40,60)

    def test_safe_group_is_replaced_once_and_short_tail_cleared(self):
        from analytics.holy_grail_sheet import plan_requests
        grid=[[{} for _ in range(4)] for _ in range(100)]
        grid[39][0]={'userEnteredValue':{'stringValue':'Диверсифікація - Details'}}
        group={'range':{'startIndex':40,'endIndex':90},'depth':1}
        req,owned=plan_requests(indicator_cases.IndicatorTests().enrich(),7,grid,[group],40,90)
        self.assertEqual(sum('deleteDimensionGroup' in r for r in req),1)
        self.assertEqual(sum('addDimensionGroup' in r for r in req),1)
        clears=[r['updateCells'] for r in req if 'updateCells' in r and r['updateCells']['range']['endRowIndex']==90]
        self.assertTrue(clears)

    def test_foreign_group_prevents_collapsing(self):
        from analytics.holy_grail_sheet import plan_requests
        grid=[[{} for _ in range(4)] for _ in range(100)]
        foreign={'range':{'startIndex':30,'endIndex':55},'depth':1}
        req,owned=plan_requests(indicator_cases.IndicatorTests().enrich(),7,grid,[foreign],40,60)
        self.assertFalse(owned['collapsed'])
        self.assertNotIn('deleteDimensionGroup',str(req))
        self.assertNotIn('addDimensionGroup',str(req))

    def test_groupless_ownership_never_consumes_adjacent_manual_rows(self):
        from analytics.holy_grail_sheet import _details
        grid=[[{} for _ in range(4)] for _ in range(100)]
        grid[39][0]={'userEnteredValue':{'stringValue':'Диверсифікація - Details'}}
        for i in range(40,62):grid[i][0]={'userEnteredValue':{'stringValue':'MANUAL OR UNPROVEN'}}
        with self.assertRaises(ValueError): _details({'grid':grid,'groups':[]})

    def test_unavailable_indicator_can_replace_old_count(self):
        from analytics.holy_grail_sheet import plan_requests
        data=indicator_cases.IndicatorTests().enrich(history=__import__('pandas').DataFrame())
        grid=[[{} for _ in range(4)] for _ in range(100)]
        req,owned=plan_requests(data,7,grid,[],40,60)
        self.assertIn('Дані недоступні',str(req))

    def test_readback_rejects_collapsed_group_without_hidden_rows(self):
        from analytics.holy_grail_sheet import deliver,plan_requests
        from copy import deepcopy
        from unittest.mock import Mock,patch
        import tempfile
        data=indicator_cases.IndicatorTests().enrich()
        grid=[[{} for _ in range(4)] for _ in range(100)]
        grid[39][0]={'userEnteredValue':{'stringValue':'Диверсифікація - Details'}}
        before={'grid':grid,'groups':[],'row_metadata':[{} for _ in range(100)],'properties':{'title':'QA'}}
        req,owned=plan_requests(data,7,grid,[],40,40);after=deepcopy(before)
        for r in req:
            if 'updateCells' in r:
                u=r['updateCells'];offset=u['range']['startRowIndex']
                for i,row in enumerate(u['rows'],offset):
                    for j,c in enumerate(row['values']):after['grid'][i][j]['userEnteredValue']=c['userEnteredValue']
            if 'repeatCell' in r:
                u=r['repeatCell'];b=u['range']
                for i in range(b['startRowIndex'],b['endRowIndex']):
                    for j in range(b['startColumnIndex'],b['endColumnIndex']):after['grid'][i][j].setdefault('userEnteredFormat',{}).update(u['cell']['userEnteredFormat'])
        after['groups']=[{'range':{'startIndex':40,'endIndex':owned['new_end']},'depth':1,'collapsed':True}]
        book=Mock();book.id='qa'
        with tempfile.TemporaryDirectory() as directory,patch('analytics.holy_grail_sheet.read_state',side_effect=[before,before,after]):
            with self.assertRaises(RuntimeError):deliver(book,7,data,directory,apply=True)
