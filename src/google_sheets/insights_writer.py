"""Preflight and write one portfolio snapshot plus its shared timeline."""

from __future__ import annotations

import json
import math
import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import gspread

from src.google_sheets.insights_cells import CellBlock, CellValue, render_blocks
from src.google_sheets.insights_tables import InsightTab

MARKER_COLUMN = 28  # Zero-based column AC. gspread cell coordinates are one-based.
OWNERSHIP_MARKER = "portfolio_snapshot_generated_v2"
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
    "amount": {"type": "CURRENCY", "pattern": '"$"#,##0;-"$"#,##0;"$"0'},
    "amount_fraction": {"type": "CURRENCY", "pattern": '"$"#,##0.00;-"$"#,##0.00;"$"0'},
    "amount_tiny": {
        "type": "CURRENCY",
        "pattern": '"$"#,##0.##########;-"$"#,##0.##########;"$"0',
    },
    "weight": {"type": "PERCENT", "pattern": "0%;-0%;0%"},
    "weight_fraction": {"type": "PERCENT", "pattern": "0.00%;-0.00%;0%"},
    "weight_tiny": {"type": "PERCENT", "pattern": "0.########%;-0.########%;0%"},
}
for _kind in ("money", "percent", "pp"):
    _NUMBER_FORMATS[_kind + "_tiny"] = dict(_NUMBER_FORMATS[_kind])
_NUMBER_FORMATS["money"]["pattern"] = '+"$"#,##0.00;-"$"#,##0.00;"$"0.00'
_NUMBER_FORMATS["percent"]["pattern"] = "+0.00%;-0.00%;0.00%"
_NUMBER_FORMATS["pp"]["pattern"] = '+0.00" pp";-0.00" pp";0.00" pp"'
_NUMBER_FORMATS["native_amount"] = {
    "type": "NUMBER",
    "pattern": "+#,##0.00;-#,##0.00;0.00",
}
_NUMBER_FORMATS["native_amount_tiny"] = {
    "type": "NUMBER",
    "pattern": "+#,##0.00########;-#,##0.00########;0.00",
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


def _typed_format_ranges(
    typed_cells: dict[tuple[int, int], CellValue],
) -> list[tuple[str, int, int, int, int]]:
    by_row: dict[int, dict[str, list[int]]] = {}
    for (row, column), cell in typed_cells.items():
        kind = "date" if cell.kind == "date" else cell.kind
        if kind in {
            "money",
            "percent",
            "pp",
            "native_amount",
            "number",
            "amount",
            "weight",
        } and (
            isinstance(cell.value, bool)
            or not isinstance(cell.value, (int, float, Decimal))
            or not math.isfinite(cell.value)
        ):
            continue
        threshold = 0.00005 if kind in {"percent", "weight"} else 0.005
        if (
            kind in {"money", "percent", "pp", "native_amount", "amount", "weight"}
            and 0 < abs(cell.value) < threshold
        ):
            kind += "_tiny"
        if kind in {"amount", "weight"}:
            units = float(cell.value) * (100 if kind == "weight" else 1)
            if not round(units, 2).is_integer():
                kind += "_fraction"
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


def _gradient_signature(rule: Any) -> Any:
    """Identify a saved generator rule despite Sheets RGB readback rounding."""
    try:
        ranges = tuple(
            sorted(
                tuple(
                    r.get(key, 0)
                    for key in (
                        "sheetId",
                        "startRowIndex",
                        "endRowIndex",
                        "startColumnIndex",
                        "endColumnIndex",
                    )
                )
                for r in rule["ranges"]
            )
        )
        points = []
        for name in ("minpoint", "midpoint", "maxpoint"):
            point = rule["gradientRule"][name]
            color = point.get("color") or point.get("colorStyle", {}).get(
                "rgbColor", {}
            )
            points.append(
                (
                    point["type"],
                    float(point["value"]),
                    tuple(
                        round(color.get(channel, 0), 5)
                        for channel in ("red", "green", "blue")
                    ),
                )
            )
        return ranges, tuple(points)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _tab_requests(
    tab: InsightTab,
    worksheet: Any,
    old_metadata: dict[str, Any],
    timeline_id: int,
    conditional_formats: list[dict[str, Any]],
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
    requests: list[dict[str, Any]] = []
    requested_rows = max(row_count + 5, getattr(worksheet, "row_count", 0))
    requested_columns = max(MARKER_COLUMN + 1, getattr(worksheet, "col_count", 0))
    if requested_rows > getattr(
        worksheet, "row_count", 0
    ) or requested_columns > getattr(worksheet, "col_count", 0):
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

    for start_row, end_row, start_column, end_column in old_metadata.get("ranges", []):
        requests.append(
            {
                "updateCells": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row,
                        "endRowIndex": end_row,
                        "startColumnIndex": start_column,
                        "endColumnIndex": end_column,
                    },
                    "fields": "userEnteredValue,userEnteredFormat",
                }
            }
        )

    rows = [{"values": [_api_value(value) for value in row]} for row in grid]
    for (row, column), cell in typed_cells.items():
        if cell.kind == "formula":
            rows[row]["values"][column] = {
                "userEnteredValue": {"formulaValue": cell.value}
            }
        elif cell.kind == "link":
            label, target = cell.value
            target_id = timeline_id if target == "timeline" else sheet_id
            target_row = 1 if target == "timeline" else block_ranges[target][0] + 1
            label = label.replace('"', '""')
            formula = f'=HYPERLINK("#gid={target_id}&range=A{target_row}","{label}")'
            rows[row]["values"][column] = {
                "userEnteredValue": {"formulaValue": formula}
            }
    requests.append(
        {
            "updateCells": {
                "start": {"sheetId": sheet_id, "rowIndex": 0, "columnIndex": 0},
                "rows": rows,
                "fields": "userEnteredValue",
            }
        }
    )

    requests.append(
        {
            "updateCells": {
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": 0,
                    "columnIndex": MARKER_COLUMN,
                },
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

    for block_name, (start, end, first_column, width) in block_ranges.items():
        _append_format_request(
            requests,
            sheet_id,
            start,
            min(start + 1, end),
            first_column,
            width,
            {
                "backgroundColor": {"red": 0.96, "green": 0.96, "blue": 0.96},
                "textFormat": {
                    "foregroundColor": {"red": 0.12, "green": 0.12, "blue": 0.12},
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
                first_column,
                width,
                {
                    "backgroundColor": {"red": 0.94, "green": 0.94, "blue": 0.94},
                    "textFormat": {"bold": True},
                    "wrapStrategy": "WRAP",
                    "horizontalAlignment": "CENTER",
                },
                "userEnteredFormat(backgroundColor,textFormat,wrapStrategy,horizontalAlignment)",
            )

    for block_name, offset in tab.emphasis_rows:
        start, _, first_column, last_column = block_ranges[block_name]
        _append_format_request(
            requests,
            sheet_id,
            start + offset,
            start + offset + 1,
            first_column,
            last_column,
            {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.97, "green": 0.97, "blue": 0.97},
            },
            "userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor",
        )

    gradient_ranges = []
    for block_name, column_offset in tab.pnl_columns:
        start, end, first_column, _ = block_ranges[block_name]
        data_start = start + tab.header_offsets.get(block_name, 0) + 1
        if data_start >= end:
            continue
        gradient_ranges.append(
            {
                "sheetId": sheet_id,
                "startRowIndex": data_start,
                "endRowIndex": end,
                "startColumnIndex": first_column + column_offset,
                "endColumnIndex": first_column + column_offset + 1,
            }
        )
    gradient = (
        {
            "ranges": gradient_ranges,
            "gradientRule": {
                "minpoint": {
                    "type": "NUMBER",
                    "value": "-0.3",
                    "color": {"red": 245 / 255, "green": 69 / 255, "blue": 69 / 255},
                },
                "midpoint": {
                    "type": "NUMBER",
                    "value": "0",
                    "color": {"red": 1, "green": 1, "blue": 1},
                },
                "maxpoint": {
                    "type": "NUMBER",
                    "value": "0.5",
                    "color": {"red": 46 / 255, "green": 204 / 255, "blue": 113 / 255},
                },
            },
        }
        if gradient_ranges
        else None
    )
    old_signature = _gradient_signature(old_metadata.get("pnl_gradient"))
    if old_signature is not None:
        for index in range(len(conditional_formats) - 1, -1, -1):
            if _gradient_signature(conditional_formats[index]) == old_signature:
                requests.append(
                    {
                        "deleteConditionalFormatRule": {
                            "sheetId": sheet_id,
                            "index": index,
                        }
                    }
                )
    if gradient:
        requests.append({"addConditionalFormatRule": {"rule": gradient, "index": 0}})

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
        column_count,
        {
            "wrapStrategy": "WRAP",
            "verticalAlignment": "MIDDLE",
            "textFormat": {"fontFamily": "Arial", "fontSize": 10},
        },
        "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment,userEnteredFormat.textFormat.fontFamily,userEnteredFormat.textFormat.fontSize",
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
            start + tab.filter_end_offset if tab.filter_end_offset is not None else end,
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
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start,
                                "endIndex": end,
                            },
                            "properties": {"hiddenByUser": False},
                            "fields": "hiddenByUser",
                        }
                    }
                )
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
        "role": "main",
        "ranges": [[0, row_count, 0, column_count]],
        "pnl_gradient": gradient,
    }
    # The marker metadata is rewritten after construction so it records this refresh's geometry.
    requests.append(
        {
            "updateCells": {
                "start": {
                    "sheetId": sheet_id,
                    "rowIndex": 1,
                    "columnIndex": MARKER_COLUMN,
                },
                "rows": [
                    {"values": [_api_value(json.dumps(metadata, sort_keys=True))]}
                ],
                "fields": "userEnteredValue",
            }
        }
    )

    chart_count = 0
    widths = tab.column_widths or (240, 135, 130, 140, 130, 150, 110, 200)
    for column, width in enumerate(widths[:column_count]):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": column,
                        "endIndex": column + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )
    requests.append(
        {
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": row_count,
                }
            }
        }
    )
    return requests, metadata, row_count, chart_count


class SheetConflictError(ValueError):
    """A write would claim or overwrite content outside reviewed generated ranges."""


def _range(sheet_id, bounds):
    r0, r1, c0, c1 = bounds
    return dict(
        sheetId=sheet_id,
        startRowIndex=r0,
        endRowIndex=r1,
        startColumnIndex=c0,
        endColumnIndex=c1,
    )


def _read(worksheet, rows, columns=29):
    from gspread.utils import rowcol_to_a1

    if worksheet is None:
        return {}
    rows, columns = min(rows, worksheet.row_count), min(columns, worksheet.col_count)
    if rows <= 0 or columns <= 0:
        return {}
    values = worksheet.get(
        f"A1:{rowcol_to_a1(rows, columns)}", value_render_option="FORMULA"
    )
    return {
        (r, c): value
        for r, row in enumerate(values)
        for c, value in enumerate(row)
        if value not in ("", None)
    }


def _inside(row, column, ranges):
    return any(r0 <= row < r1 and c0 <= column < c1 for r0, r1, c0, c1 in ranges)


def _annotations(worksheet, ranges):
    """Read bounded non-value content that a values-only preflight cannot see."""
    from gspread.utils import absolute_range_name, rowcol_to_a1

    rows = min(max([r[1] for r in ranges] + [2]), worksheet.row_count)
    columns = min(MARKER_COLUMN + 1, worksheet.col_count)
    area = absolute_range_name(worksheet.title, f"A1:{rowcol_to_a1(rows, columns)}")
    metadata = worksheet.spreadsheet.fetch_sheet_metadata(
        params={
            "includeGridData": True,
            "ranges": [area],
            "fields": "sheets(properties(sheetId),data(startRow,startColumn,rowData(values(note,dataValidation))))",
        }
    )
    result = {}
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") != worksheet.id:
            continue
        for block in sheet.get("data", []):
            for row, cells in enumerate(
                block.get("rowData", []), block.get("startRow", 0)
            ):
                for column, cell in enumerate(
                    cells.get("values", []), block.get("startColumn", 0)
                ):
                    if cell.get("note") or cell.get("dataValidation"):
                        result[(row, column)] = cell
    return result


def _validated_ranges(ranges):
    if not isinstance(ranges, (list, tuple)):
        raise SheetConflictError("Invalid ownership ranges")
    result = []
    for bounds in ranges:
        if (
            not isinstance(bounds, (list, tuple))
            or len(bounds) != 4
            or any(type(v) is not int for v in bounds)
        ):
            raise SheetConflictError("Invalid ownership range")
        r0, r1, c0, c1 = bounds
        if not (0 <= r0 < r1 <= 1_000_000 and 0 <= c0 < c1 <= MAX_DATA_COLUMNS):
            raise SheetConflictError("Ownership range exceeds data grid")
        result.append(list(bounds))
    return result


def preview_adoption(worksheet, ranges, *, history_chart_id=None):
    """Read-only receipt. Pass this exact reviewed receipt as adoptions[sheet_id]."""
    bounds = _validated_ranges(ranges)
    if any(r[1] > worksheet.row_count or r[3] > worksheet.col_count for r in bounds):
        raise SheetConflictError("Adoption ranges exceed the existing worksheet grid")
    grid = _read(worksheet, max([r[1] for r in bounds] + [2]))
    annotations = _annotations(worksheet, bounds)
    if any(
        grid.get((r, MARKER_COLUMN)) not in ("", None)
        or (r, MARKER_COLUMN) in annotations
        for r in (0, 1)
    ):
        raise SheetConflictError("Reserved metadata cells are occupied")
    occupied = [
        [r + 1, c + 1, value]
        for (r, c), value in sorted(grid.items())
        if _inside(r, c, bounds)
    ]
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                occupied,
                [
                    [r, c, cell]
                    for (r, c), cell in sorted(annotations.items())
                    if _inside(r, c, bounds)
                ],
            ],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return dict(
        sheet_id=worksheet.id,
        title=worksheet.title,
        ranges=bounds,
        fingerprint=fingerprint,
        occupied_cells=occupied,
        history_chart_id=history_chart_id,
    )


def _preflight(worksheet, role, ranges, adoption):
    if worksheet is None:
        return {}
    marker_grid = _read(worksheet, 2)
    marker = marker_grid.get((0, MARKER_COLUMN))
    if marker == OWNERSHIP_MARKER:
        try:
            old = json.loads(marker_grid.get((1, MARKER_COLUMN), ""))
        except (ValueError, TypeError):
            raise SheetConflictError("Missing or invalid generated metadata") from None
        if not isinstance(old, dict) or old.get("role") != role:
            raise SheetConflictError("Wrong generated worksheet role")
        old["ranges"] = _validated_ranges(old.get("ranges"))
        if role == "timeline":
            old["helper_ranges"] = _validated_ranges(old.get("helper_ranges", []))
            if any(
                c0 != 4
                or c1 != 6
                or not any(
                    a <= r0 and r1 <= b and c <= c0 and c1 <= d
                    for a, b, c, d in old["ranges"]
                )
                for r0, r1, c0, c1 in old["helper_ranges"]
            ):
                raise SheetConflictError("Invalid timeline helper ownership")
    elif adoption is not None:
        if (
            adoption.get("sheet_id") != worksheet.id
            or adoption.get("title") != worksheet.title
        ):
            raise SheetConflictError("Adoption target does not match this worksheet")
        fresh = preview_adoption(
            worksheet,
            adoption.get("ranges"),
            history_chart_id=adoption.get("history_chart_id"),
        )
        if fresh["fingerprint"] != adoption.get("fingerprint"):
            raise SheetConflictError(
                "Adoption preview is stale; review a fresh preview"
            )
        old = dict(
            ranges=fresh["ranges"],
            row_groups=[],
            role=role,
            history_chart_id=fresh["history_chart_id"],
        )
    else:
        raise SheetConflictError(
            f"Explicit adoption is required for {worksheet.title!r} (sheet ID {worksheet.id})"
        )
    grid = _read(worksheet, max([r[1] for r in ranges + old["ranges"]] + [2]))
    for row, col in _annotations(worksheet, ranges):
        if (col == MARKER_COLUMN and row in (0, 1)) or (
            _inside(row, col, ranges) and not _inside(row, col, old["ranges"])
        ):
            raise SheetConflictError(
                f"Unowned note or validation at row {row + 1}, column {col + 1}"
            )
    for (row, col), value in grid.items():
        if _inside(row, col, ranges) and not _inside(row, col, old["ranges"]):
            raise SheetConflictError(
                f"Unowned occupied cell at row {row + 1}, column {col + 1}"
            )
    return old


def _timeline_date(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return (date(1899, 12, 30) + timedelta(days=float(value))).isoformat()
        except (ValueError, OverflowError):
            return None
    for fmt in ("%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(str(value), fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return (
            datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
        )
    except ValueError:
        pass
    return None


def _timeline_plan(worksheet, valuation_date, total_assets):
    grid = _read(worksheet, worksheet.row_count, 2) if worksheet else {}
    entries, row_by_date = {}, {}
    for row in sorted({r for r, _ in grid}):
        amount, day = grid.get((row, 0)), _timeline_date(grid.get((row, 1)))
        if day is None:
            if row == 0 and str(grid.get((row, 1), "")).lower() in (
                "date",
                "valuation date",
            ):
                continue
            raise SheetConflictError(f"Unrecognised timeline date on row {row + 1}")
        try:
            parsed = float(str(amount).replace(",", ""))
        except (ValueError, TypeError):
            raise SheetConflictError(
                f"Unrecognised timeline amount on row {row + 1}"
            ) from None
        if not math.isfinite(parsed) or day in entries:
            raise SheetConflictError(
                "Timeline contains invalid amounts or duplicate dates"
            )
        entries[day], row_by_date[day] = parsed, row
    target_row = row_by_date.get(valuation_date, max([r for r, _ in grid] + [-1]) + 1)
    entries[valuation_date] = total_assets
    history = [("Valuation date", "Tracked assets USD")]
    history.extend(
        (CellValue(day, "date"), CellValue(amount, "money"))
        for day, amount in sorted(entries.items())
    )
    history_grid, history_typed, _ = render_blocks(
        [CellBlock("history", tuple(history))]
    )
    return target_row, history_grid, history_typed


def _cells(sheet_id, row, column, values):
    return {
        "updateCells": {
            "start": dict(sheetId=sheet_id, rowIndex=row, columnIndex=column),
            "rows": [{"values": [_api_value(v) for v in line]} for line in values],
            "fields": "userEnteredValue",
        }
    }


def _history_chart_spec(sheet_id, end_row):
    def source(col):
        return {
            "sourceRange": {"sources": [_range(sheet_id, [0, end_row, col, col + 1])]}
        }

    return {
        "title": "Tracked assets over time",
        "hiddenDimensionStrategy": "SHOW_ALL",
        "basicChart": {
            "chartType": "SCATTER",
            "legendPosition": "NO_LEGEND",
            "headerCount": 1,
            "domains": [{"domain": source(4)}],
            "series": [{"series": source(5), "targetAxis": "LEFT_AXIS"}],
            "axis": [
                {"position": "BOTTOM_AXIS", "title": "Valuation date"},
                {"position": "LEFT_AXIS", "title": "Tracked assets USD"},
            ],
        },
    }


def write_portfolio_snapshot(
    spreadsheet, tab, valuation_date, total_assets, *, adoptions=None, dry_run=False
):
    """Preflight both targets, then apply one atomic Sheets batch. No suffix tabs."""
    if (
        not isinstance(total_assets, (int, float))
        or isinstance(total_assets, bool)
        or not math.isfinite(total_assets)
    ):
        raise ValueError("A finite tracked asset total is required")
    if tab.title != date.fromisoformat(valuation_date).strftime("%d %b %Y"):
        raise ValueError("Main worksheet title must match valuation date")
    adoptions = adoptions or {}
    by_title = {s.title: s for s in spreadsheet.worksheets()}
    main, timeline = by_title.get(tab.title), by_title.get("net_worth_timeline")
    grid, _, _ = render_blocks(tab.blocks)
    main_ranges = [[0, len(grid), 0, len(grid[0])]]
    target_row, history, typed_history = _timeline_plan(
        timeline, valuation_date, total_assets
    )
    timeline_ranges = [[target_row, target_row + 1, 0, 2], [0, len(history), 4, 6]]
    old_main = _preflight(
        main, "main", main_ranges, adoptions.get(main.id) if main else None
    )
    old_timeline = _preflight(
        timeline,
        "timeline",
        timeline_ranges,
        adoptions.get(timeline.id) if timeline else None,
    )
    book_meta = spreadsheet.fetch_sheet_metadata(params={"includeGridData": False})
    charts = {
        c["chartId"]: c
        for s in book_meta.get("sheets", [])
        for c in s.get("charts", [])
    }
    timeline_charts = {
        c["chartId"]
        for s in book_meta.get("sheets", [])
        if timeline and s.get("properties", {}).get("sheetId") == timeline.id
        for c in s.get("charts", [])
    }
    chart_id = old_timeline.get("history_chart_id")
    if chart_id is not None and chart_id not in timeline_charts:
        raise SheetConflictError(
            "Reviewed history chart is missing or belongs to another sheet"
        )
    next_id = max([s.id for s in by_title.values()] + [0]) + 1
    requests, created, updated = [], [], []
    targets = []
    for existing, title, rows in (
        (main, tab.title, len(grid)),
        (timeline, "net_worth_timeline", max(target_row + 1, len(history))),
    ):
        if existing is None:
            existing = SimpleNamespace(
                id=next_id, title=title, row_count=max(200, rows + 5), col_count=29
            )
            next_id += 1
            requests.append(
                {
                    "addSheet": {
                        "properties": {
                            "sheetId": existing.id,
                            "title": title,
                            "index": (
                                0
                                if title == tab.title
                                else len(by_title) + len(created)
                            ),
                            "gridProperties": {
                                "rowCount": existing.row_count,
                                "columnCount": 29,
                            },
                        }
                    }
                }
            )
            created.append(title)
        else:
            updated.append(title)
        targets.append(existing)
    main, timeline = targets
    conditional_formats = next(
        (
            s.get("conditionalFormats", [])
            for s in book_meta.get("sheets", [])
            if s.get("properties", {}).get("sheetId") == main.id
        ),
        [],
    )
    main_requests, _, _, _ = _tab_requests(
        tab, main, old_main, timeline.id, conditional_formats
    )
    requests.extend(main_requests)
    timeline_rows = max(
        timeline.row_count,
        target_row + 1,
        len(history) + 5,
        max([r[1] for r in old_timeline.get("ranges", [])] + [0]),
    )
    requests.append(
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": timeline.id,
                    "gridProperties": {
                        "rowCount": timeline_rows,
                        "columnCount": max(29, timeline.col_count),
                    },
                },
                "fields": "gridProperties.rowCount,gridProperties.columnCount",
            }
        }
    )
    # Only the helper history range is replaced. Existing A/B rows and C/D remain intact.
    for bounds in old_timeline.get("helper_ranges", []):
        requests.append(
            {
                "updateCells": {
                    "range": _range(timeline.id, bounds),
                    "fields": "userEnteredValue,userEnteredFormat",
                }
            }
        )
    serial = (date.fromisoformat(valuation_date) - date(1899, 12, 30)).days
    requests.append(_cells(timeline.id, target_row, 0, [[total_assets, serial]]))
    requests.append(_cells(timeline.id, 0, 4, history))
    for kind, r0, r1, c0, c1 in _typed_format_ranges(typed_history):
        _append_format_request(
            requests,
            timeline.id,
            r0,
            r1,
            c0 + 4,
            c1 + 4,
            {"numberFormat": _NUMBER_FORMATS[kind]},
            "userEnteredFormat.numberFormat",
        )
    for column, kind in ((0, "money"), (1, "date")):
        _append_format_request(
            requests,
            timeline.id,
            target_row,
            target_row + 1,
            column,
            column + 1,
            {"numberFormat": _NUMBER_FORMATS[kind]},
            "userEnteredFormat.numberFormat",
        )
    spec = _history_chart_spec(timeline.id, len(history))
    if chart_id is None:
        chart_id = max(list(charts) + [0]) + 1
        requests.append(
            {
                "addChart": {
                    "chart": {
                        "chartId": chart_id,
                        "spec": spec,
                        "position": {
                            "overlayPosition": {
                                "anchorCell": {
                                    "sheetId": timeline.id,
                                    "rowIndex": 1,
                                    "columnIndex": 7,
                                },
                                "widthPixels": 800,
                                "heightPixels": 420,
                            }
                        },
                    }
                }
            }
        )
    else:
        requests.append({"updateChartSpec": {"chartId": chart_id, "spec": spec}})
    owned = old_timeline.get("ranges", []) + timeline_ranges
    timeline_metadata = {
        "role": "timeline",
        "ranges": [list(r) for r in dict.fromkeys(tuple(r) for r in owned)],
        "helper_ranges": [[0, len(history), 4, 6]],
        "history_chart_id": chart_id,
    }
    requests.append(
        _cells(
            timeline.id,
            0,
            MARKER_COLUMN,
            [[OWNERSHIP_MARKER], [json.dumps(timeline_metadata, sort_keys=True)]],
        )
    )
    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": timeline.id,
                    "dimension": "COLUMNS",
                    "startIndex": 4,
                    "endIndex": 6,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }
    )
    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": timeline.id,
                    "dimension": "COLUMNS",
                    "startIndex": MARKER_COLUMN,
                    "endIndex": MARKER_COLUMN + 1,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }
    )
    receipt = dict(
        created_tabs=created,
        updated_tabs=updated,
        main_sheet_id=main.id,
        timeline_sheet_id=timeline.id,
        requests_sent=len(requests),
        dry_run=dry_run,
    )
    if not dry_run:
        spreadsheet.batch_update({"requests": requests})
    return receipt
