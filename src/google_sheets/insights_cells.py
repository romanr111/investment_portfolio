"""Typed spreadsheet values and deterministic block layout."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import math
from typing import Any, Iterable


_NUMERIC_KINDS = {"money", "percent", "pp", "number"}
_SUPPORTED_KINDS = _NUMERIC_KINDS | {"date", "status"}
_SHEETS_DATE_EPOCH = date(1899, 12, 30)


@dataclass(frozen=True)
class CellValue:
    value: Any
    kind: str

    def __post_init__(self) -> None:
        if self.kind not in _SUPPORTED_KINDS:
            raise ValueError(f"Unsupported cell kind: {self.kind}")


@dataclass(frozen=True)
class CellBlock:
    name: str
    rows: tuple[tuple[Any, ...], ...]


def _date_serial(value: Any) -> int:
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        value = date.fromisoformat(value)
    if not isinstance(value, date):
        raise ValueError(f"Date cell needs a date or ISO date string: {value!r}")
    return (value - _SHEETS_DATE_EPOCH).days


def _render_value(cell: CellValue) -> Any:
    value = cell.value
    if cell.kind == "status":
        return "Unavailable" if value is None else str(value)
    if cell.kind == "date":
        return _date_serial(value)
    if cell.kind in _NUMERIC_KINDS:
        if value is None or isinstance(value, bool):
            return "Unavailable"
        number = float(value) if isinstance(value, Decimal) else value
        if not isinstance(number, (int, float)) or not math.isfinite(number):
            return "Unavailable"
        return number
    return value


def render_blocks(
    blocks: Iterable[CellBlock], gap_rows: int = 1
) -> tuple[list[list[Any]], dict[tuple[int, int], CellValue], dict[str, tuple[int, int, int, int]]]:
    """Render named blocks into a padded grid and retain typed cell coordinates.

    Returned coordinates and ranges are zero-based, with range end indices
    exclusive to match the Google Sheets API.
    """
    if gap_rows < 0:
        raise ValueError("gap_rows must be non-negative")

    grid: list[list[Any]] = []
    typed_cells: dict[tuple[int, int], CellValue] = {}
    block_ranges: dict[str, tuple[int, int, int, int]] = {}
    max_columns = 0

    for block in blocks:
        if block.name in block_ranges:
            raise ValueError(f"Duplicate block name: {block.name}")
        if not block.rows:
            continue
        if grid:
            grid.extend([[] for _ in range(gap_rows)])

        start_row = len(grid)
        block_width = max(len(row) for row in block.rows)
        for row_offset, row in enumerate(block.rows):
            rendered_row = []
            for column, value in enumerate(row):
                if isinstance(value, CellValue):
                    typed_cells[(start_row + row_offset, column)] = value
                    rendered_row.append(_render_value(value))
                else:
                    rendered_row.append(value)
            max_columns = max(max_columns, len(rendered_row))
            grid.append(rendered_row)
        block_ranges[block.name] = (start_row, len(grid), 0, block_width)

    for row in grid:
        row.extend([""] * (max_columns - len(row)))

    return grid, typed_cells, block_ranges
