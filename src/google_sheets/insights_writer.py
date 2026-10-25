"""Preflight and write one portfolio snapshot plus its shared timeline."""

from __future__ import annotations

import json
import math
import hashlib
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import gspread

from src.google_sheets.insights_cells import CellValue, render_blocks
from src.google_sheets.insights_tables import InsightTab

MARKER_COLUMN = 28  # Zero-based column AC. gspread cell coordinates are one-based.
OWNERSHIP_MARKER = "portfolio_snapshot_generated_v2"
MAX_DATA_COLUMNS = MARKER_COLUMN

_COLORS = {
    name: dict(
        zip(
            ("red", "green", "blue"),
            (int(hex_value[i : i + 2], 16) / 255 for i in (0, 2, 4)),
        )
    )
    for name, hex_value in {
        "text": "242424",
        "muted": "666666",
        "header": "F1F0EC",
        "subtotal": "F7F6F2",
        "border": "DEDED8",
        "white": "FFFFFF",
    }.items()
}

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


def _compact_format(cell: CellValue) -> dict[str, str] | None:
    """Change presentation only; tiny nonzero values retain a significant digit."""
    if cell.kind == "date":
        return {"type": "DATE", "pattern": "dd mmm yyyy"}
    if cell.kind not in {"amount", "money", "weight", "percent"} or (
        isinstance(cell.value, bool)
        or not isinstance(cell.value, (int, float, Decimal))
        or not math.isfinite(cell.value)
    ):
        return None
    percent = cell.kind in {"weight", "percent"}
    units = abs(float(cell.value)) * (100 if percent else 1)
    decimals = 1 if percent else 0
    if 0 < units < (0.05 if percent else 1):
        decimals = max(1 if percent else 2, -math.floor(math.log10(units)))
    number = ("0" if percent else "#,##0") + ("." + "0" * decimals if decimals else "")
    prefix, suffix = ("", "%") if percent else ('"$"', "")
    positive = "+" if cell.kind in {"money", "percent"} else ""
    return {
        "type": "PERCENT" if percent else "CURRENCY",
        "pattern": f"{positive}{prefix}{number}{suffix};-{prefix}{number}{suffix};"
        + ("0.0%" if percent else '"$"0'),
    }


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


_LEGACY_PNL_POINTS = (
    ("NUMBER", -0.3, (round(245 / 255, 5), round(69 / 255, 5), round(69 / 255, 5))),
    ("NUMBER", 0.0, (1.0, 1.0, 1.0)),
    ("NUMBER", 0.5, (round(46 / 255, 5), round(204 / 255, 5), round(113 / 255, 5))),
)


def _legacy_pnl_gradient(rules: Any, row_limit: int = 0) -> Any:
    """Return the single-column P&L gradient from formatting.py, if still live.

    ``row_limit`` bounds the scan to the recorded generated row count so rules
    referencing absurd row ranges never match an adopted legacy tab.
    """
    for rule in rules if isinstance(rules, list) else []:
        signature = _gradient_signature(rule)
        if signature is None:
            continue
        ranges, points = signature
        if (
            len(ranges) == 1
            and ranges[0][3] == 5
            and ranges[0][4] == 6
            and (not row_limit or ranges[0][2] <= row_limit <= 1000)
            and points == _LEGACY_PNL_POINTS
        ):
            return deepcopy(rule)
    return None


def _sheet_row_groups(sheet_entry: Any) -> Any:
    """Live ROW dimension group spans with per-span counts, or None when omitted.

    The Sheets API nests a DimensionRange (startIndex/endIndex) under "range";
    flat entries still use GridRange keys (startRowIndex/endRowIndex). The API
    stacks repeated addDimensionGroup calls at the same range as extra depths,
    so equal spans count once per live entry and the writer deletes each of them.
    """
    if not isinstance(sheet_entry, dict):
        return None
    groups: dict = {}

    def take(items: Any) -> None:
        for group in items or []:
            if not isinstance(group, dict):
                continue
            span = group.get("range")
            if not isinstance(span, dict):
                span = group
            start = span.get("startRowIndex", span.get("startIndex"))
            end = span.get("endRowIndex", span.get("endIndex"))
            if isinstance(start, int) and isinstance(end, int) and start < end:
                groups[(start, end)] = groups.get((start, end), 0) + 1

    known = False
    if "rowGroups" in sheet_entry:
        take(sheet_entry.get("rowGroups"))
        known = True
    for block in sheet_entry.get("data") or []:
        if isinstance(block, dict) and "rowGroups" in block:
            take(block.get("rowGroups"))
            known = True
    return groups if known else None


def _tab_requests(
    tab: InsightTab,
    worksheet: Any,
    old_metadata: dict[str, Any],
    timeline_id: int,
    conditional_formats: list[dict[str, Any]],
    live_row_groups: dict = None,
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

    # Establish the body style before section and headline overrides.
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
            "backgroundColor": _COLORS["white"],
            "textFormat": {
                "fontFamily": "Arial",
                "fontSize": 11,
                "bold": False,
                "foregroundColor": _COLORS["text"],
            },
        },
        "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment,userEnteredFormat.backgroundColor,userEnteredFormat.textFormat(fontFamily,fontSize,bold,foregroundColor)",
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
                "backgroundColor": _COLORS["header"],
                "textFormat": {
                    "fontFamily": "Arial",
                    "foregroundColor": _COLORS["text"],
                    "bold": True,
                    "fontSize": 12,
                },
                "borders": {"bottom": {"style": "SOLID", "color": _COLORS["border"]}},
            },
            "userEnteredFormat(backgroundColor,textFormat,borders)",
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
                    "backgroundColor": _COLORS["header"],
                    "textFormat": {
                        "fontFamily": "Arial",
                        "fontSize": 11,
                        "bold": True,
                        "foregroundColor": _COLORS["text"],
                    },
                    "wrapStrategy": "WRAP",
                    "horizontalAlignment": "LEFT",
                },
                "userEnteredFormat(backgroundColor,textFormat,wrapStrategy,horizontalAlignment)",
            )
            numeric_columns = {
                column
                for (row, column), cell in typed_cells.items()
                if header_row < row < end
                and first_column <= column < width
                and cell.kind in _NUMBER_FORMATS
            }
            for column in sorted(numeric_columns):
                _append_format_request(
                    requests,
                    sheet_id,
                    header_row,
                    header_row + 1,
                    column,
                    column + 1,
                    {"horizontalAlignment": "RIGHT"},
                    "userEnteredFormat.horizontalAlignment",
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
                "backgroundColor": _COLORS["subtotal"],
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
    # A tab adopted from the legacy formatting.py rule keeps its own
    # single-column P&L gradient; when nothing was recorded yet, replace it on
    # this run instead of leaving two competing gradients on the tab.
    if not _gradient_signature(old_metadata.get("pnl_gradient")):
        row_count_for_legacy_scan = (
            old_metadata.get("rows", 0) if isinstance(old_metadata, dict) else 0
        )
        legacy = _legacy_pnl_gradient(
            conditional_formats, max(row_count_for_legacy_scan, 0)
        )
        if legacy is not None:
            old_metadata = {**old_metadata, "pnl_gradient": deepcopy(legacy)}
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

    if "compact_allocation" in block_ranges:
        compact_end = block_ranges.get("details", (row_count,))[0]
        for (row, column), cell in typed_cells.items():
            number_format = _compact_format(cell) if row < compact_end else None
            if number_format:
                _append_format_request(
                    requests,
                    sheet_id,
                    row,
                    row + 1,
                    column,
                    column + 1,
                    {"numberFormat": number_format},
                    "userEnteredFormat.numberFormat",
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
    else:
        # Generator tabs that no longer render the filtered section keep any
        # earlier basic filter from blocking rows that are still on the grid.
        requests.append({"clearBasicFilter": {"sheetId": sheet_id}})

    previous_groups = old_metadata.get("row_groups", [])
    if isinstance(previous_groups, list):
        for group in previous_groups:
            if not isinstance(group, dict):
                continue
            start = group.get("start")
            end = group.get("end")
            if not (isinstance(start, int) and isinstance(end, int) and start < end):
                continue
            if live_row_groups is not None:
                deletes = live_row_groups.get((start, end), 0)
                if not deletes:
                    # Recorded ranges the tab no longer groups: never send a
                    # deleteDimensionGroup the API cannot match. Restore row
                    # visibility inside the existing grid, then leave it alone.
                    if end <= row_count:
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
                    continue
            else:
                deletes = 1
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
            # deleteDimensionGroup lowers the depth of the group over the exact
            # span, so stacked duplicates each need their own delete request.
            for _ in range(deletes):
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
    if "compact_allocation" in block_ranges:
        start, _, first_column, _ = block_ranges["compact_allocation"]
        _append_format_request(
            requests,
            sheet_id,
            start,
            start + 1,
            first_column + 1,
            first_column + 2,
            {"textFormat": {"fontSize": 20, "bold": True}},
            "userEnteredFormat.textFormat(fontSize,bold)",
        )
        summary_value = typed_cells.get((0, 1))
        if summary_value is not None and summary_value.kind == "weight":
            _append_format_request(
                requests,
                sheet_id,
                0,
                1,
                1,
                2,
                {"textFormat": {"fontSize": 16, "bold": True}},
                "userEnteredFormat.textFormat(fontSize,bold)",
            )
        _, end, first_column, last_column = block_ranges["compact_income"]
        for row, size, bold, color in (
            (end - 2, 14, True, _COLORS["text"]),
            (end - 1, 11, False, _COLORS["muted"]),
        ):
            _append_format_request(
                requests,
                sheet_id,
                row,
                row + 1,
                first_column,
                last_column,
                {
                    "textFormat": {
                        "fontSize": size,
                        "bold": bold,
                        "foregroundColor": color,
                    }
                },
                "userEnteredFormat.textFormat(fontSize,bold,foregroundColor)",
            )
        _append_format_request(
            requests,
            sheet_id,
            0,
            1,
            8,
            9,
            {
                "textFormat": {
                    "fontSize": 11,
                    "bold": False,
                    "foregroundColor": _COLORS["muted"],
                }
            },
            "userEnteredFormat.textFormat(fontSize,bold,foregroundColor)",
        )
        # Rows span all four panels: only a wholly empty row is a separator.
        row_heights = [(0, 42), (1, 36)]
        status_rows = {
            row for (row, _), cell in typed_cells.items() if cell.kind == "status"
        }
        for row in range(2, block_ranges.get("details", (row_count,))[0]):
            values = grid[row][:12]
            if all(value in ("", None) for value in values):
                row_heights.append((row, 12))
            elif any(
                isinstance(value, str) and "\n" in value for value in values
            ):
                # An explicit multiline label (e.g. the balance-change row) renders
                # as two deliberate lines; Sheets does not refit these rows, so
                # give them the same height as the two-line header above.
                row_heights.append((row, 36))
            elif row not in status_rows and not any(
                isinstance(value, str)
                and len(value) > max(10, tab.column_widths[column] // 10)
                for column, value in enumerate(values)
            ):
                # Potentially wrapped text keeps the automatic height above.
                row_heights.append((row, 24))
        for row, height in row_heights:
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row,
                            "endIndex": row + 1,
                        },
                        "properties": {"pixelSize": height},
                        "fields": "pixelSize",
                    }
                }
            )
    return requests, metadata, row_count, 0


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


def _timeline_plan(worksheet, valuation_date):
    """Find the legacy A=value/B=date row without adopting or restyling the tab."""
    grid = _read(worksheet, worksheet.row_count, 2) if worksheet else {}
    entries, row_by_date = {}, {}
    last_series_row = None
    for row in sorted({r for r, _ in grid}):
        amount, day = grid.get((row, 0)), _timeline_date(grid.get((row, 1)))
        if row == 0 and str(grid.get((row, 1), "")).lower() in (
            "date",
            "valuation date",
        ):
            continue
        if amount in ("", None) or day is None:
            # The legacy series is a contiguous leading block; the first gap
            # ends it. Legacy tabs may carry unrelated helper series (notes,
            # formulas, other apps' dates) below that are never ours to
            # validate, parse, or overwrite.
            break
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
        last_series_row = row
    fallback = (
        last_series_row + 1
        if last_series_row is not None
        else max([r for r, _ in grid] + [-1]) + 1
    )
    target_row, existing_date = row_by_date.get(valuation_date, fallback), (
        valuation_date in row_by_date
    )
    if not existing_date and grid.get((target_row, 1)) not in ("", None):
        raise SheetConflictError(
            f"Timeline append cell is occupied on row {target_row + 1}"
        )
    return target_row, existing_date


def _cells(sheet_id, row, column, values):
    return {
        "updateCells": {
            "start": dict(sheetId=sheet_id, rowIndex=row, columnIndex=column),
            "rows": [{"values": [_api_value(v) for v in line]} for line in values],
            "fields": "userEnteredValue",
        }
    }


def write_portfolio_snapshot(
    spreadsheet, tab, valuation_date, total_assets, *, adoptions=None, dry_run=False
):
    """Render the main tab and update only value/date data in the legacy timeline."""
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
    target_row, existing_date = _timeline_plan(timeline, valuation_date)
    old_main = _preflight(
        main, "main", main_ranges, adoptions.get(main.id) if main else None
    )
    book_meta = spreadsheet.fetch_sheet_metadata(params={"includeGridData": False})
    next_id = max([s.id for s in by_title.values()] + [0]) + 1
    requests, created, updated = [], [], []
    targets = []
    for existing, title, rows in (
        (main, tab.title, len(grid)),
        (timeline, "net_worth_timeline", target_row + 1),
    ):
        if existing is None:
            existing = SimpleNamespace(
                id=next_id,
                title=title,
                row_count=max(200, rows + 5),
                col_count=29 if title == tab.title else 2,
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
                                "columnCount": existing.col_count,
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
    main_entry = next(
        (
            s
            for s in book_meta.get("sheets", [])
            if s.get("properties", {}).get("sheetId") == main.id
        ),
        {},
    )
    conditional_formats = main_entry.get("conditionalFormats", [])
    main_requests, _, _, _ = _tab_requests(
        tab,
        main,
        old_main,
        timeline.id,
        conditional_formats,
        live_row_groups=_sheet_row_groups(main_entry),
    )
    requests.extend(main_requests)
    # Preserve legacy charts, dimensions, formatting and adjacent formulas. Only
    # grow rows when appending past the existing grid; same-date updates touch A.
    if target_row >= timeline.row_count:
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": timeline.id,
                        "gridProperties": {"rowCount": target_row + 1},
                    },
                    "fields": "gridProperties.rowCount",
                }
            }
        )
    values = [[total_assets]] if existing_date else [[total_assets, tab.title]]
    requests.append(_cells(timeline.id, target_row, 0, values))
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
