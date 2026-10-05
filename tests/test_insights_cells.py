import unittest
from datetime import date

from src.google_sheets.insights_cells import CellBlock, CellValue, render_blocks


class InsightsCellsTests(unittest.TestCase):
    def test_render_blocks_preserves_numeric_values_and_typed_coordinates(self):
        grid, typed_cells, ranges = render_blocks(
            [
                CellBlock(
                    "overview",
                    rows=(
                        ("Overview",),
                        ("Tracked assets", CellValue(125000.75, "money")),
                        ("IB return - YTD - TWR", CellValue(0.0705, "percent")),
                        ("As of", CellValue(date(2026, 10, 4), "date")),
                    ),
                ),
                CellBlock(
                    "holdings",
                    rows=(("Asset", "Value USD"), ("AAA", CellValue(0.003, "money"))),
                ),
            ]
        )

        self.assertEqual(grid[1][1], 125000.75)
        self.assertEqual(grid[2][1], 0.0705)
        self.assertEqual(grid[3][1], 46299)
        self.assertEqual(grid[6][1], 0.003)
        self.assertEqual(typed_cells[(1, 1)].kind, "money")
        self.assertEqual(typed_cells[(2, 1)].kind, "percent")
        self.assertEqual(typed_cells[(3, 1)].kind, "date")
        self.assertEqual(typed_cells[(6, 1)].kind, "money")
        self.assertEqual(ranges["overview"], (0, 4, 0, 2))
        self.assertEqual(ranges["holdings"], (5, 7, 0, 2))

    def test_unavailable_status_remains_text_instead_of_becoming_zero(self):
        grid, typed_cells, _ = render_blocks(
            [CellBlock("liquidity", rows=(("Runway", CellValue("Unavailable", "status")),))]
        )

        self.assertEqual(grid[0][1], "Unavailable")
        self.assertEqual(typed_cells[(0, 1)].kind, "status")

    def test_boolean_cannot_be_rendered_as_a_financial_number(self):
        grid, _, _ = render_blocks(
            [CellBlock("values", ((CellValue(True, "money"),),))]
        )

        self.assertEqual(grid, [["Unavailable"]])


if __name__ == "__main__":
    unittest.main()
