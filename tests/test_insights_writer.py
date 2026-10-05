import json
import unittest

import gspread

from src.google_sheets.insights_cells import CellBlock, CellValue
from src.google_sheets.insights_tables import build_insight_tabs
from src.google_sheets.insights_writer import (
    MARKER_COLUMN,
    OWNERSHIP_MARKER,
    write_insight_tabs,
)
from tests.fixtures_insights import current_snapshot, previous_snapshot


class FakeCell:
    def __init__(self, value):
        self.value = value


class FakeWorksheet:
    def __init__(self, title, sheet_id, rows=100, cols=29):
        self.title = title
        self.id = sheet_id
        self.row_count = rows
        self.col_count = cols
        self.values = {}
        self.charts = []

    def cell(self, row, column):
        return FakeCell(self.values.get((row, column)))


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = []
        self.batch_updates = []
        self._next_sheet_id = 1
        self._next_chart_id = 100

    def worksheets(self):
        return list(self.sheets)

    def worksheet(self, title):
        for worksheet in self.sheets:
            if worksheet.title == title:
                return worksheet
        raise gspread.exceptions.WorksheetNotFound(title)

    def add_worksheet(self, title, rows, cols, index=None):
        worksheet = FakeWorksheet(title, self._next_sheet_id, rows, cols)
        self._next_sheet_id += 1
        if index is None:
            self.sheets.append(worksheet)
        else:
            self.sheets.insert(index, worksheet)
        return worksheet

    def fetch_sheet_metadata(self, params=None):
        return {
            "sheets": [
                {
                    "properties": {"sheetId": sheet.id, "title": sheet.title},
                    "charts": [
                        {"chartId": chart["id"], "spec": {"title": chart["title"]}}
                        for chart in sheet.charts
                    ],
                    "rowGroups": [],
                }
                for sheet in self.sheets
            ]
        }

    def batch_update(self, body):
        self.batch_updates.append(body)
        by_id = {sheet.id: sheet for sheet in self.sheets}
        for request in body["requests"]:
            if "updateCells" in request:
                update = request["updateCells"]
                sheet_range = update.get("range")
                if sheet_range:
                    sheet = by_id[sheet_range["sheetId"]]
                    for row in range(
                        sheet_range.get("startRowIndex", 0) + 1,
                        sheet_range.get("endRowIndex", sheet.row_count) + 1,
                    ):
                        for column in range(
                            sheet_range.get("startColumnIndex", 0) + 1,
                            sheet_range.get("endColumnIndex", sheet.col_count) + 1,
                        ):
                            sheet.values.pop((row, column), None)
                else:
                    start = update["start"]
                    sheet = by_id[start["sheetId"]]
                    for row_offset, row_data in enumerate(update.get("rows", [])):
                        for column_offset, cell_data in enumerate(row_data.get("values", [])):
                            value = cell_data.get("userEnteredValue", {})
                            if "stringValue" in value:
                                rendered = value["stringValue"]
                            elif "numberValue" in value:
                                rendered = value["numberValue"]
                            elif "boolValue" in value:
                                rendered = value["boolValue"]
                            else:
                                rendered = None
                            sheet.values[
                                (
                                    start.get("rowIndex", 0) + row_offset + 1,
                                    start.get("columnIndex", 0) + column_offset + 1,
                                )
                            ] = rendered
            elif "deleteEmbeddedObject" in request:
                chart_id = request["deleteEmbeddedObject"]["objectId"]
                for sheet in self.sheets:
                    sheet.charts = [chart for chart in sheet.charts if chart["id"] != chart_id]
            elif "addChart" in request:
                chart = request["addChart"]["chart"]
                self._next_chart_id += 1
                anchor_id = chart["position"]["overlayPosition"]["anchorCell"]["sheetId"]
                by_id[anchor_id].charts.append(
                    {"id": self._next_chart_id, "title": chart["spec"]["title"]}
                )


class InsightsWriterTests(unittest.TestCase):
    def test_writes_typed_values_and_one_hidden_marker_to_each_generated_tab(self):
        spreadsheet = FakeSpreadsheet()
        tabs = build_insight_tabs(
            current_snapshot(),
            previous_snapshot=previous_snapshot(),
            previous_date="2026-09-30",
            current_date="2026-10-04",
            history_snapshots=[
                {"as_of_date": "2026-09-30", "data": previous_snapshot()},
                {"as_of_date": "2026-10-04", "data": current_snapshot()},
            ],
        )

        result = write_insight_tabs(spreadsheet, tabs)

        self.assertEqual(result["created_tabs"], list(tabs))
        self.assertEqual([sheet.title for sheet in spreadsheet.sheets], list(tabs))
        for sheet in spreadsheet.sheets:
            marker_values = [
                value
                for (row, column), value in sheet.values.items()
                if value == OWNERSHIP_MARKER
            ]
            self.assertEqual(marker_values, [OWNERSHIP_MARKER])
            self.assertEqual(sheet.cell(1, MARKER_COLUMN + 1).value, OWNERSHIP_MARKER)

        overview = spreadsheet.worksheet("Overview")
        self.assertEqual(overview.cell(3, 1).value, "Tracked asset value")
        self.assertEqual(overview.cell(3, 2).value, 900.003)
        self.assertEqual(overview.cell(5, 2).value, "Unavailable")
        holdings = spreadsheet.worksheet("Holdings")
        self.assertEqual(holdings.cell(10, 1).value, "Asset")
        self.assertTrue(holdings.cell(11, 1).value)
        percent = next(
            value
            for (row, column), value in overview.values.items()
            if value == 0.0705
        )
        self.assertEqual(percent, 0.0705)
        requests = spreadsheet.batch_updates[0]["requests"]
        number_patterns = [
            request["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["pattern"]
            for request in requests
            if request.get("repeatCell", {})
            .get("cell", {})
            .get("userEnteredFormat", {})
            .get("numberFormat", {})
            .get("pattern")
        ]
        self.assertIn(
            '+"$"#,##0.00########;-"$"#,##0.00########;"$"0.00########',
            number_patterns,
        )
        self.assertIn("+0.00######%;-0.00######%;0.00######%", number_patterns)
        self.assertIn(
            '+0.00######" pp";-0.00######" pp";0.00######" pp"',
            number_patterns,
        )
        self.assertTrue(
            any(
                request.get("updateDimensionProperties", {})
                .get("properties", {})
                .get("hiddenByUser")
                for request in requests
            )
        )
        self.assertTrue(any("addDimensionGroup" in request for request in requests))
        self.assertFalse(any("deleteSheet" in request for request in requests))
        self.assertTrue(
            any(
                request.get("repeatCell", {})
                .get("cell", {})
                .get("userEnteredFormat", {})
                .get("numberFormat", {})
                .get("type")
                == "PERCENT"
                for request in requests
            )
        )

    def test_keeps_foreign_title_and_uses_generated_copy(self):
        spreadsheet = FakeSpreadsheet()
        foreign = spreadsheet.add_worksheet("Overview", rows=20, cols=10)
        foreign.values[(1, 1)] = "User content"
        tab = {"Overview": tabs_for_test("Overview")}

        result = write_insight_tabs(spreadsheet, tab)

        self.assertEqual(foreign.cell(1, 1).value, "User content")
        self.assertEqual(result["preserved_foreign_tabs"], ["Overview"])
        generated = spreadsheet.worksheet("Overview (generated)")
        self.assertEqual(
            generated.cell(1, MARKER_COLUMN + 1).value, OWNERSHIP_MARKER
        )

    def test_refresh_reuses_owned_tab_and_replaces_only_generator_charts(self):
        spreadsheet = FakeSpreadsheet()
        overview = spreadsheet.add_worksheet("Overview", rows=100, cols=29)
        overview.values[(1, MARKER_COLUMN + 1)] = OWNERSHIP_MARKER
        overview.values[(2, MARKER_COLUMN + 1)] = json.dumps(
            {"rows": 2, "cols": 2, "row_groups": []}
        )
        overview.charts.extend(
            [
                {"id": 11, "title": "Portfolio insights: old chart"},
                {"id": 12, "title": "My chart"},
            ]
        )
        foreign = spreadsheet.add_worksheet("Notes", rows=20, cols=29)
        foreign.values[(1, 1)] = "Keep"
        foreign.charts.append({"id": 13, "title": "Portfolio insights: user chart"})
        tabs = {"Overview": tabs_for_test("Overview", with_chart=True)}

        first = write_insight_tabs(spreadsheet, tabs)
        second = write_insight_tabs(spreadsheet, tabs)

        self.assertEqual(first["updated_tabs"], ["Overview"])
        self.assertEqual(second["updated_tabs"], ["Overview"])
        self.assertEqual(len(spreadsheet.sheets), 2)
        self.assertEqual(
            [chart["title"] for chart in overview.charts],
            ["My chart", "Portfolio insights: Test chart"],
        )
        self.assertEqual(foreign.cell(1, 1).value, "Keep")
        self.assertEqual(foreign.charts[0]["id"], 13)
        self.assertEqual(overview.cell(1, MARKER_COLUMN + 1).value, OWNERSHIP_MARKER)

    def test_reuses_owned_generated_copy_when_original_title_is_foreign(self):
        spreadsheet = FakeSpreadsheet()
        foreign = spreadsheet.add_worksheet("Overview", rows=20, cols=29)
        foreign.values[(1, 1)] = "User data"
        generated = spreadsheet.add_worksheet("Overview (generated)", rows=100, cols=29)
        generated.values[(1, MARKER_COLUMN + 1)] = OWNERSHIP_MARKER
        tabs = {"Overview": tabs_for_test("Overview")}

        result = write_insight_tabs(spreadsheet, tabs)

        self.assertEqual(result["created_tabs"], [])
        self.assertEqual(result["updated_tabs"], ["Overview (generated)"])
        self.assertEqual(len(spreadsheet.sheets), 2)
        self.assertEqual(foreign.cell(1, 1).value, "User data")


def tabs_for_test(title, with_chart=False):
    from src.google_sheets.insights_tables import ChartDefinition, InsightTab

    charts = (
        (ChartDefinition("Test chart", "data", "LINE", 0, (1,)),)
        if with_chart
        else ()
    )
    return InsightTab(
        title=title,
        blocks=(
            CellBlock(
                "data",
                (
                    ("Date", "Value"),
                    ("2026-10-04", CellValue(0.0705, "percent")),
                ),
            ),
        ),
        header_offsets={"data": 0},
        freeze_rows=1,
        charts=charts,
    )


if __name__ == "__main__":
    unittest.main()
