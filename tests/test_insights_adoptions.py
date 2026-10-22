import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.fake_sheets import FakeSpreadsheet
from src.google_sheets.spreadsheet_structure import (
    load_adoptions_file,
    preview_portfolio_adoptions,
)


class LoadAdoptionsFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)

    def _write(self, payload):
        path = os.path.join(self.tmp, "adoptions.json")
        with open(path, "w") as handle:
            json.dump(payload, handle)
        return path

    def test_string_sheet_ids_become_int_keys_for_the_writer(self):
        payload = {"7": {"sheet_id": 7, "fingerprint": "abc"}}
        parsed = load_adoptions_file(self._write(payload))
        self.assertEqual(parsed, {7: {"sheet_id": 7, "fingerprint": "abc"}})

    def test_invalid_adoptions_files_are_rejected(self):
        path = os.path.join(self.tmp, "malformed.json")
        with open(path, "w") as handle:
            handle.write("{not json")
        with self.assertRaises(ValueError):
            load_adoptions_file(path)
        for payload in ([1, 2], {"7": "not a receipt"}, {"main": {"sheet_id": 7}}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    load_adoptions_file(self._write(payload))


class PreviewPortfolioAdoptionsTests(unittest.TestCase):
    def _preview(self, book, titles):
        with mock.patch(
            "src.google_sheets.spreadsheet_structure.PortfolioUpdater",
            lambda credentials_path, name: self._fake_updater(book),
        ):
            return preview_portfolio_adoptions("unused.json", "Portfolio", titles)

    @staticmethod
    def _fake_updater(spreadsheet):
        return SimpleNamespace(spreadsheet=spreadsheet)

    def test_previews_are_keyed_by_string_sheet_id_with_json_receipts(self):
        book = FakeSpreadsheet()
        main = book.add_worksheet("04 Oct 2026")
        previews = self._preview(book, ["04 Oct 2026"])

        self.assertEqual(list(previews), [str(main.id)])
        receipt = previews[str(main.id)]
        self.assertEqual(receipt["sheet_id"], main.id)
        self.assertEqual(receipt["title"], "04 Oct 2026")
        # A new tab has no occupied cells; ranges clip to the marker column.
        self.assertEqual(receipt["occupied_cells"], [])
        self.assertEqual(receipt["ranges"], [[0, main.row_count, 0, 28]])

    def test_occupied_cells_and_fingerprint_capture_existing_content(self):
        book = FakeSpreadsheet()
        book.add_worksheet("04 Oct 2026")
        sheet = book.worksheet("04 Oct 2026")
        sheet.values[(1, 1)] = "Holdings"

        previews = self._preview(book, ["04 Oct 2026"])
        receipt = previews[str(sheet.id)]
        self.assertEqual(receipt["occupied_cells"], [[1, 1, "Holdings"]])
        self.assertTrue(receipt["fingerprint"])

    def test_unknown_title_fails_before_any_write(self):
        book = FakeSpreadsheet()
        with self.assertRaises(Exception):
            self._preview(book, ["missing tab"])
        self.assertEqual(book.batch_updates, [])

    def test_preview_round_trips_through_a_file_into_int_keyed_adoptions(self):
        book = FakeSpreadsheet()
        main = book.add_worksheet("04 Oct 2026")
        previews = self._preview(book, ["04 Oct 2026"])

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "adoptions.json")
            with open(path, "w") as handle:
                json.dump(previews, handle)
            adoptions = load_adoptions_file(path)
        self.assertEqual(list(adoptions), [main.id])
        self.assertEqual(
            adoptions[main.id]["fingerprint"], previews[str(main.id)]["fingerprint"]
        )


if __name__ == "__main__":
    unittest.main()