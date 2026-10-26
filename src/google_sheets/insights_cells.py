"""Typed spreadsheet values and deterministic block layout."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import math
from typing import Any, Iterable

_NUMERIC_KINDS = {
    "money",
    "percent",
    "pp",
    "number",
    "native_amount",
    "amount",
    "weight",
    "allocation_score",
    "risk_equivalent",
}
_SUPPORTED_KINDS = _NUMERIC_KINDS | {"date", "status", "link", "formula"}
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
    start_row: int | None = None
    start_column: int = 0


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
    if cell.kind == "link":
        return str(value[0])
    if cell.kind == "formula":
        return str(value)
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


def render_blocks(blocks: Iterable[CellBlock], gap_rows: int = 1) -> tuple[
    list[list[Any]],
    dict[tuple[int, int], CellValue],
    dict[str, tuple[int, int, int, int]],
]:
    """Render named blocks into a padded grid and retain typed cell coordinates.

    Returned coordinates and ranges are zero-based, with range end indices
    exclusive to match the Google Sheets API. Explicit positions allow adjacent
    blocks; implicit blocks start below all preceding blocks.
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
        start_row = (
            block.start_row
            if block.start_row is not None
            else len(grid) + (gap_rows if grid else 0)
        )
        start_column = block.start_column
        if start_row < 0 or start_column < 0:
            raise ValueError("Block coordinates must be non-negative")
        block_width = max(len(row) for row in block.rows)
        end_row, end_column = start_row + len(block.rows), start_column + block_width
        if any(
            start_row < r1 and r0 < end_row and start_column < c1 and c0 < end_column
            for r0, r1, c0, c1 in block_ranges.values()
        ):
            raise ValueError(f"Overlapping block: {block.name}")
        grid.extend([[] for _ in range(max(0, end_row - len(grid)))])
        for row_offset, row in enumerate(block.rows):
            rendered_row = grid[start_row + row_offset]
            rendered_row.extend([""] * max(0, end_column - len(rendered_row)))
            for column, value in enumerate(row):
                if isinstance(value, CellValue):
                    typed_cells[(start_row + row_offset, start_column + column)] = value
                    rendered_row[start_column + column] = _render_value(value)
                else:
                    rendered_row[start_column + column] = value
            max_columns = max(max_columns, len(rendered_row))
        block_ranges[block.name] = (start_row, end_row, start_column, end_column)

    for row in grid:
        row.extend([""] * (max_columns - len(row)))

    return grid, typed_cells, block_ranges
