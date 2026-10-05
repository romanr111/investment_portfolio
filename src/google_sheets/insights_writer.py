"""Write generated insight tabs without taking ownership of existing user tabs."""

from __future__ import annotations

import json
import math
from typing import Any

import gspread

from src.google_sheets.insights_cells import CellValue, render_blocks
from src.google_sheets.insights_tables import InsightTab


MARKER_COLUMN = 28  # Zero-based column AC. gspread cell coordinates are one-based.
OWNERSHIP_MARKER = "portfolio_insights_generated_v1"
CHART_TITLE_PREFIX = "Portfolio insights: "
MAX_DATA_COLUMNS = MARKER_COLUMN

_NUMBER_FORMATS = {
    "money": {
        "type": "CURRENCY",
        "pattern": '+"$"#,##0.00########;-"$"#,##0.00########;"$"0.00########',
    },
    "percent": {
        "type": "PERCENT",
        "pattern": "+0.00######%;-0.00######%;0.00######%",
    },
    "pp": {
        "type": "NUMBER",
        "pattern": '+0.00######" pp";-0.00######" pp";0.00######" pp"',
    },
    "number": {"type": "NUMBER", "pattern": "#,##0.00#####"},
    "date": {"type": "DATE", "pattern": "yyyy-mm-dd"},
}


def _api_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, (int, float)):
        if math.isfinite(value):
            return {"userEnteredValue": {"numberValue": value}}
        return {"userEnteredValue": {"stringValue": "Unavailable"}}
    if value is None:
        return {"userEnteredValue": {"stringValue": ""}}
    return {"userEnteredValue": {"stringValue": str(value)}}


def _existing_metadata(worksheet: Any) -> dict[str, Any]:
    if getattr(worksheet, "col_count", 0) < MARKER_COLUMN + 1:
        return {}
    raw = worksheet.cell(2, MARKER_COLUMN + 1).value
    if not raw:
        return {}
    try:
        metadata = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _is_owned(worksheet: Any) -> bool:
    if getattr(worksheet, "col_count", 0) < MARKER_COLUMN + 1:
        return False
    return worksheet.cell(1, MARKER_COLUMN + 1).value == OWNERSHIP_MARKER


def _worksheet_for_title(spreadsheet: Any, title: str, by_title: dict[str, Any]):
    candidates = [title, f"{title} (generated)"]
    candidates.extend(f"{title} (generated) {index}" for index in range(2, 100))
    preserved = []
    for candidate in candidates:
        worksheet = by_title.get(candidate)
        if worksheet is None:
            continue
        if _is_owned(worksheet):
            return worksheet, False, preserved
        preserved.append(candidate)

    for candidate in candidates:
        if candidate in by_title:
            continue
        worksheet = spreadsheet.add_worksheet(
            title=candidate, rows=100, cols=MARKER_COLUMN + 1
        )
        by_title[candidate] = worksheet
        return worksheet, True, preserved
    raise RuntimeError(f"Could not find a safe generated tab title for {title!r}")


def _typed_format_ranges(
    typed_cells: dict[tuple[int, int], CellValue]
) -> list[tuple[str, int, int, int, int]]:
    by_row: dict[int, dict[str, list[int]]] = {}
    for (row, column), cell in typed_cells.items():
        kind = "date" if cell.kind == "date" else cell.kind
        if kind not in _NUMBER_FORMATS:
            continue
        by_row.setdefault(row, {}).setdefault(kind, []).append(column)

    row_runs = []
    for row, kinds in by_row.items():
        for kind, columns in kinds.items():
            columns.sort()
            start = previous = columns[0]
            for column in columns[1:]:
                if column != previous + 1:
                    row_runs.append((kind, row, row + 1, start, previous + 1))
                    start = column
                previous = column
            row_runs.append((kind, row, row + 1, start, previous + 1))

    row_runs.sort(key=lambda item: (item[0], item[3], item[4], item[1]))
    merged = []
    for kind, start_row, end_row, start_column, end_column in row_runs:
        if (
            merged
            and merged[-1][0] == kind
            and merged[-1][2] == start_row
            and merged[-1][3] == start_column
            and merged[-1][4] == end_column
        ):
            previous = merged[-1]
            merged[-1] = (kind, previous[1], end_row, start_column, end_column)
        else:
            merged.append((kind, start_row, end_row, start_column, end_column))
    return merged


def _append_format_request(
    requests: list[dict[str, Any]],
    sheet_id: int,
    start_row: int,
    end_row: int,
    start_column: int,
    end_column: int,
    user_format: dict[str, Any],
    fields: str,
) -> None:
    requests.append(
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_column,
                    "endColumnIndex": end_column,
                },
                "cell": {"userEnteredFormat": user_format},
                "fields": fields,
            }
        }
    )


def _chart_request(
    tab: InsightTab,
    chart: Any,
    block_ranges: dict[str, tuple[int, int, int, int]],
    sheet_id: int,
    chart_index: int,
    data_width: int,
) -> dict[str, Any]:
    if chart.chart_type not in {"LINE", "BAR"}:
        raise ValueError(f"Unsupported chart type: {chart.chart_type}")
    if chart.block_name not in block_ranges:
        raise ValueError(f"Chart {chart.title!r} names missing block {chart.block_name!r}")

    block_start, block_end, _, _ = block_ranges[chart.block_name]
    header_row = block_start + chart.header_offset
    domain = {
        "domain": {
            "sourceRange": {
                "sources": [
                    {
                        "sheetId": sheet_id,
                        "startRowIndex": header_row,
                        "endRowIndex": block_end,
                        "startColumnIndex": chart.domain_column,
                        "endColumnIndex": chart.domain_column + 1,
                    }
                ]
            }
        }
    }
    series = [
        {
            "series": {
                "sourceRange": {
                    "sources": [
                        {
                            "sheetId": sheet_id,
                            "startRowIndex": header_row,
                            "endRowIndex": block_end,
                            "startColumnIndex": column,
                            "endColumnIndex": column + 1,
                        }
                    ]
                }
            },
            "targetAxis": "LEFT_AXIS",
        }
        for column in chart.series_columns
    ]
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": f"{CHART_TITLE_PREFIX}{chart.title}",
                    "basicChart": {
                        "chartType": chart.chart_type,
                        "legendPosition": "BOTTOM_LEGEND",
                        "domains": [domain],
                        "series": series,
                        "headerCount": 1,
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": 1,
                            "columnIndex": data_width + 1 + chart_index * 8,
                        },
                        "widthPixels": 600,
                        "heightPixels": 360,
                    }
                },
            }
        }
    }


def _tab_requests(
    tab: InsightTab,
    worksheet: Any,
    old_metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], int, int]:
    grid, typed_cells, block_ranges = render_blocks(tab.blocks)
    if not grid:
        raise ValueError(f"Generated tab {tab.title!r} has no cells")
    row_count = len(grid)
    column_count = len(grid[0])
    if column_count > MAX_DATA_COLUMNS:
        raise ValueError(
            f"Generated tab {tab.title!r} has {column_count} columns; "
            f"the hidden ownership marker reserves column {MARKER_COLUMN + 1}"
        )

    sheet_id = worksheet.id
    old_rows = old_metadata.get("rows", row_count)
    old_columns = old_metadata.get("cols", column_count)
    if not isinstance(old_rows, int) or old_rows < 0:
        old_rows = row_count
    if not isinstance(old_columns, int) or old_columns < 0:
        old_columns = column_count
    clear_rows = max(old_rows, row_count)
    clear_columns = min(max(old_columns, column_count), MAX_DATA_COLUMNS)
    requests: list[dict[str, Any]] = []

    if old_metadata:
        requests.append(
            {
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": clear_rows,
                        "startColumnIndex": 0,
                        "endColumnIndex": clear_columns,
                    },
                    "fields": "userEnteredValue,userEnteredFormat",
                }
            }
        )

    rows = [{"values": [_api_value(value) for value in row]} for row in grid]
    requests.append(
        {
            "updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                "rows": rows,
                "fields": "userEnteredValue",
            }
        }
    )

    requested_rows = max(row_count + 5, getattr(worksheet, "row_count", 0))
    requested_columns = max(MARKER_COLUMN + 1, getattr(worksheet, "col_count", 0))
    if (
        requested_rows > getattr(worksheet, "row_count", 0)
        or requested_columns > getattr(worksheet, "col_count", 0)
    ):
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "rowCount": requested_rows,
                            "columnCount": requested_columns,
                        },
                    },
                    "fields": "gridProperties.rowCount,gridProperties.columnCount",
                }
            }
        )

    requests.append(
        {
            "updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": MARKER_COLUMN},
                "rows": [{"values": [_api_value(OWNERSHIP_MARKER)]}],
                "fields": "userEnteredValue",
            }
        }
    )
    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": MARKER_COLUMN,
                    "endIndex": MARKER_COLUMN + 1,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }
    )
    requests.append(
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": tab.freeze_rows,
                        "frozenColumnCount": tab.freeze_columns,
                    },
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
            }
        }
    )

    for block_name, (start, end, _, width) in block_ranges.items():
        _append_format_request(
            requests,
            sheet_id,
            start,
            min(start + 1, end),
            0,
            width,
            {
                "backgroundColor": {"red": 0.13, "green": 0.23, "blue": 0.37},
                "textFormat": {
                    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                    "bold": True,
                    "fontSize": 12,
                },
            },
            "userEnteredFormat(backgroundColor,textFormat)",
        )
        if block_name in tab.header_offsets:
            header_row = start + tab.header_offsets[block_name]
            _append_format_request(
                requests,
                sheet_id,
                header_row,
                header_row + 1,
                0,
                width,
                {
                    "backgroundColor": {"red": 0.85, "green": 0.89, "blue": 0.94},
                    "textFormat": {"bold": True},
                    "wrapStrategy": "WRAP",
                    "horizontalAlignment": "CENTER",
                },
                "userEnteredFormat(backgroundColor,textFormat,wrapStrategy,horizontalAlignment)",
            )

    for kind, start_row, end_row, start_column, end_column in _typed_format_ranges(
        typed_cells
    ):
        _append_format_request(
            requests,
            sheet_id,
            start_row,
            end_row,
            start_column,
            end_column,
            {
                "numberFormat": _NUMBER_FORMATS[kind],
                "horizontalAlignment": "RIGHT",
            },
            "userEnteredFormat.numberFormat,userEnteredFormat.horizontalAlignment",
        )

    _append_format_request(
        requests,
        sheet_id,
        0,
        row_count,
        0,
        1,
        {"wrapStrategy": "WRAP"},
        "userEnteredFormat.wrapStrategy",
    )
    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 240},
                "fields": "pixelSize",
            }
        }
    )
    if column_count > 1:
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": column_count,
                    },
                    "properties": {"pixelSize": 150},
                    "fields": "pixelSize",
                }
            }
        )

    if tab.filter_block_name and tab.filter_block_name in block_ranges:
        start, end, _, width = block_ranges[tab.filter_block_name]
        header_start = start + tab.header_offsets.get(tab.filter_block_name, 0)
        filter_end = min(
            end,
            start + tab.filter_end_offset
            if tab.filter_end_offset is not None
            else end,
        )
        if header_start < filter_end:
            requests.append(
                {
                    "setBasicFilter": {
                        "filter": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": header_start,
                                "endRowIndex": filter_end,
                                "startColumnIndex": 0,
                                "endColumnIndex": width,
                            }
                        }
                    }
                }
            )

    previous_groups = old_metadata.get("row_groups", [])
    if isinstance(previous_groups, list):
        for group in previous_groups:
            if not isinstance(group, dict):
                continue
            start = group.get("start")
            end = group.get("end")
            if isinstance(start, int) and isinstance(end, int) and start < end:
                requests.append(
                    {
                        "deleteDimensionGroup": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start,
                                "endIndex": end,
                            }
                        }
                    }
                )

    current_groups = []
    for block_name, relative_start, relative_end in tab.row_groups:
        if block_name not in block_ranges:
            continue
        block_start = block_ranges[block_name][0]
        start = block_start + relative_start
        end = block_start + relative_end
        if start >= end:
            continue
        group_range = {
            "sheetId": sheet_id,
            "dimension": "ROWS",
            "startIndex": start,
            "endIndex": end,
        }
        requests.append({"addDimensionGroup": {"range": group_range}})
        requests.append(
            {
                "updateDimensionGroup": {
                    "dimensionGroup": {
                        "range": group_range,
                        "depth": 1,
                        "collapsed": True,
                    },
                    "fields": "collapsed",
                }
            }
        )
        current_groups.append({"start": start, "end": end})

    metadata = {
        "rows": row_count,
        "cols": column_count,
        "row_groups": current_groups,
    }
    # The marker metadata is rewritten after construction so it records this refresh's geometry.
    requests.append(
        {
            "updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": 1, "columnIndex": MARKER_COLUMN},
                "rows": [{"values": [_api_value(json.dumps(metadata, sort_keys=True))]}],
                "fields": "userEnteredValue",
            }
        }
    )

    chart_count = 0
    for chart_index, chart in enumerate(tab.charts):
        requests.append(
            _chart_request(tab, chart, block_ranges, sheet_id, chart_index, column_count)
        )
        chart_count += 1

    return requests, metadata, row_count, chart_count


def write_insight_tabs(spreadsheet: Any, tabs: dict[str, InsightTab]) -> dict[str, Any]:
    """Refresh generated tabs and preserve any unowned worksheet with a matching title."""
    worksheets = spreadsheet.worksheets()
    by_title = {worksheet.title: worksheet for worksheet in worksheets}
    created_tabs = []
    updated_tabs = []
    preserved_foreign_tabs = []
    sheet_work = []

    for title, tab in tabs.items():
        worksheet, created, preserved = _worksheet_for_title(spreadsheet, title, by_title)
        preserved_foreign_tabs.extend(preserved)
        if created:
            created_tabs.append(worksheet.title)
        else:
            updated_tabs.append(worksheet.title)
        sheet_work.append((tab, worksheet, created, _existing_metadata(worksheet)))

    metadata = spreadsheet.fetch_sheet_metadata(
        params={
            "includeGridData": False,
            "fields": "sheets(properties(sheetId,title),charts(chartId,spec(title)))",
        }
    )
    owned_sheet_ids = {worksheet.id for _, worksheet, _, _ in sheet_work}
    generated_charts = []
    for sheet in metadata.get("sheets", []):
        sheet_id = sheet.get("properties", {}).get("sheetId")
        if sheet_id not in owned_sheet_ids:
            continue
        for chart in sheet.get("charts", []):
            title = chart.get("spec", {}).get("title", "")
            if title.startswith(CHART_TITLE_PREFIX):
                generated_charts.append(chart.get("chartId"))

    requests: list[dict[str, Any]] = []
    for chart_id in generated_charts:
        if chart_id is not None:
            requests.append({"deleteEmbeddedObject": {"objectId": chart_id}})

    total_charts = 0
    for tab, worksheet, _, old_metadata in sheet_work:
        tab_requests, _, _, chart_count = _tab_requests(tab, worksheet, old_metadata)
        requests.extend(tab_requests)
        total_charts += chart_count

    spreadsheet.batch_update({"requests": requests})
    return {
        "created_tabs": created_tabs,
        "updated_tabs": updated_tabs,
        "preserved_foreign_tabs": list(dict.fromkeys(preserved_foreign_tabs)),
        "charts_written": total_charts,
        "requests_sent": len(requests),
    }
