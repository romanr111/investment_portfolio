"""Small stateful Sheets fake shared by generator integration tests."""

from copy import deepcopy
from types import SimpleNamespace
import gspread
from gspread.utils import a1_range_to_grid_range


class FakeWorksheet:
    def __init__(self, title, sheet_id, rows=200, cols=29):
        self.title, self.id = title, sheet_id
        self.row_count, self.col_count = rows, cols
        self.values, self.formats, self.charts = {}, {}, []
        self.groups, self.hidden_columns, self.properties = set(), set(), {}
        self.hidden_rows = set()
        self.basic_filter = None
        self.spreadsheet = None
        self.annotations = {}

    def cell(self, row, column):
        return SimpleNamespace(value=self.values.get((row, column)))

    def get(self, range_name, **kwargs):
        r = a1_range_to_grid_range(range_name)
        end_row = min(r.get("endRowIndex", self.row_count), self.row_count)
        end_col = min(r.get("endColumnIndex", self.col_count), self.col_count)
        return [
            [
                self.values.get((row + 1, col + 1), "")
                for col in range(r.get("startColumnIndex", 0), end_col)
            ]
            for row in range(r.get("startRowIndex", 0), end_row)
        ]


class FakeSpreadsheet:
    def __init__(self):
        self.sheets, self.batch_updates = [], []

    def worksheets(self):
        return list(self.sheets)

    def worksheet(self, title):
        for sheet in self.sheets:
            if sheet.title == title:
                return sheet
        raise gspread.exceptions.WorksheetNotFound(title)

    def add_worksheet(self, title, rows=200, cols=29, index=None):
        sheet = FakeWorksheet(
            title, max([s.id for s in self.sheets] + [0]) + 1, rows, cols
        )
        self.sheets.append(sheet)
        sheet.spreadsheet = self
        return sheet

    def fetch_sheet_metadata(self, params=None):
        return {
            "sheets": [
                {
                    "properties": {"sheetId": s.id, "title": s.title},
                    "charts": deepcopy(s.charts),
                    "rowGroups": [],
                    "data": (
                        [
                            {
                                "startRow": 0,
                                "startColumn": 0,
                                "rowData": [
                                    {
                                        "values": [
                                            s.annotations.get((row, column), {})
                                            for column in range(s.col_count)
                                        ]
                                    }
                                    for row in range(
                                        max([r for r, c in s.annotations] + [-1]) + 1
                                    )
                                ],
                            }
                        ]
                        if params and params.get("includeGridData")
                        else []
                    ),
                }
                for s in self.sheets
            ]
        }

    def batch_update(self, body):
        self.batch_updates.append(deepcopy(body))
        replies = []
        for request in body["requests"]:
            by_id = {s.id: s for s in self.sheets}
            key, value = next(iter(request.items()))
            if key == "addSheet":
                p = value["properties"]
                self.sheets.append(
                    FakeWorksheet(
                        p["title"],
                        p["sheetId"],
                        p["gridProperties"]["rowCount"],
                        p["gridProperties"]["columnCount"],
                    )
                )
                self.sheets[-1].spreadsheet = self
                self.sheets.insert(
                    p.get("index", len(self.sheets) - 1), self.sheets.pop()
                )
            elif key == "updateSheetProperties":
                p = value["properties"]
                s = by_id[p["sheetId"]]
                s.properties.update(p.get("gridProperties", {}))
                s.row_count = s.properties.get("rowCount", s.row_count)
                s.col_count = s.properties.get("columnCount", s.col_count)
            elif key == "updateCells":
                start = value.get("start")
                if start is not None:
                    s = by_id[start["sheetId"]]
                    for y, row in enumerate(value.get("rows", [])):
                        for x, cell in enumerate(row.get("values", [])):
                            coord = (
                                start.get("rowIndex", 0) + y + 1,
                                start.get("columnIndex", 0) + x + 1,
                            )
                            self._check(s, coord)
                            s.values[coord] = next(
                                iter(cell.get("userEnteredValue", {}).values()), ""
                            )
                else:
                    r = value["range"]
                    s = by_id[r["sheetId"]]
                    for y in range(r.get("startRowIndex", 0), r["endRowIndex"]):
                        for x in range(
                            r.get("startColumnIndex", 0), r["endColumnIndex"]
                        ):
                            self._check(s, (y + 1, x + 1))
                            if "userEnteredValue" in value["fields"]:
                                s.values.pop((y + 1, x + 1), None)
                            if "userEnteredFormat" in value["fields"]:
                                s.formats.pop((y + 1, x + 1), None)
            elif key == "repeatCell":
                r = value["range"]
                s = by_id[r["sheetId"]]
                for y in range(r.get("startRowIndex", 0), r["endRowIndex"]):
                    for x in range(r.get("startColumnIndex", 0), r["endColumnIndex"]):
                        self._check(s, (y + 1, x + 1))
                        s.formats.setdefault((y + 1, x + 1), {}).update(
                            value["cell"].get("userEnteredFormat", {})
                        )
            elif key == "setBasicFilter":
                by_id[value["filter"]["range"]["sheetId"]].basic_filter = value[
                    "filter"
                ]
            elif key in ("addDimensionGroup", "deleteDimensionGroup"):
                r = value["range"]
                s = by_id[r["sheetId"]]
                group = (r["startIndex"], r["endIndex"])
                if key == "addDimensionGroup":
                    s.groups.add(group)
                else:
                    s.groups.remove(group)
            elif key == "updateDimensionGroup":
                group = value["dimensionGroup"]
                r = group["range"]
                if group.get("collapsed"):
                    by_id[r["sheetId"]].hidden_rows.update(
                        range(r["startIndex"], r["endIndex"])
                    )
            elif key == "autoResizeDimensions":
                pass
            elif key == "updateDimensionProperties":
                r = value["range"]
                s = by_id[r["sheetId"]]
                if "hiddenByUser" in value["properties"]:
                    hidden = (
                        s.hidden_rows if r["dimension"] == "ROWS" else s.hidden_columns
                    )
                    if value["properties"]["hiddenByUser"]:
                        hidden.update(range(r["startIndex"], r["endIndex"]))
                    else:
                        hidden.difference_update(range(r["startIndex"], r["endIndex"]))
            elif key == "addChart":
                chart = deepcopy(value["chart"])
                sheet_id = chart["position"]["overlayPosition"]["anchorCell"]["sheetId"]
                by_id[sheet_id].charts.append(chart)
            elif key == "updateChartSpec":
                chart = next(
                    c
                    for s in self.sheets
                    for c in s.charts
                    if c["chartId"] == value["chartId"]
                )
                chart["spec"] = deepcopy(value["spec"])
            else:
                raise AssertionError("Unsupported Sheets request: " + key)
            replies.append({})
        return {"replies": replies}

    @staticmethod
    def _check(sheet, coord):
        if not (1 <= coord[0] <= sheet.row_count and 1 <= coord[1] <= sheet.col_count):
            raise AssertionError("Write outside allocated sheet grid")
