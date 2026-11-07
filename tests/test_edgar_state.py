"""Offline tests for state loading/saving and seen-accession bookkeeping."""
import json
import tempfile
import unittest
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.edgar import state

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edgar"
FIXED_NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)


def _submissions_fixture():
    return json.loads((FIXTURES / "submissions_fixture.json").read_text(encoding="utf-8"))


class NewAccessionsTests(unittest.TestCase):
    def _record(self):
        return {
            "ticker": "TESTA",
            "seen_accessions": [],
            "seen_cap": state.DEFAULT_SEEN_CAP,
            "last_rf_accession": None,
            "last_rf_baseline": None,
        }

    def test_first_contact_keeps_backfill_window_and_marks_older_seen(self):
        submissions = _submissions_fixture()
        new_filings, record = state.new_accessions(
            submissions, self._record(), max_backfill_days=7, now=FIXED_NOW
        )
        recent = state.recent_filings(submissions)
        # Four filings sit inside the 7-day window ending 2026-11-07 (back to 2026-10-31).
        self.assertEqual(len(new_filings), 4)
        self.assertEqual([f["accession"] for f in new_filings[:2]], ["0001010-26-000007", "0001010-26-000006"])
        # The two older filings are marked seen (no alerts).
        self.assertIn("0001010-26-000003", record["seen_accessions"])
        self.assertIn("0001010-25-000001", record["seen_accessions"])
        self.assertEqual(len(record["seen_accessions"]), len(recent))
        self.assertEqual(record["last_accession"], "0001010-26-000007")
        self.assertEqual(record["last_filing_date"], "2026-11-06")

    def test_second_run_reports_nothing_new(self):
        submissions = _submissions_fixture()
        _new, record = state.new_accessions(
            submissions, self._record(), max_backfill_days=7, now=FIXED_NOW
        )
        new_filings, record = state.new_accessions(
            submissions, record, max_backfill_days=7, now=FIXED_NOW
        )
        self.assertEqual(new_filings, [])
        self.assertEqual(record["last_accession"], "0001010-26-000007")

    def test_new_filing_lands_after_seen(self):
        submissions = _submissions_fixture()
        _new, record = state.new_accessions(
            submissions, self._record(), max_backfill_days=7, now=FIXED_NOW
        )
        filings = state.recent_filings(submissions)
        later = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001010-26-000008"] + [f["accession"] for f in filings],
                    "form": ["8-K"] + [f["form"] for f in filings],
                    "filingDate": ["2026-11-07"] + [f["filing_date"] for f in filings],
                    "items": ["1.05"] + [f["items"] for f in filings],
                    "primaryDocument": ["x.htm"] + [f["primary_document"] for f in filings],
                }
            }
        }
        new_filings, record = state.new_accessions(
            later, record, max_backfill_days=7, now=FIXED_NOW
        )
        self.assertEqual([f["accession"] for f in new_filings], ["0001010-26-000008"])

    def test_seen_store_respects_fifo_cap(self):
        submissions = _submissions_fixture()
        _new, record = state.new_accessions(
            submissions, self._record(), max_backfill_days=3650, now=FIXED_NOW, seen_cap=3
        )
        # Newest entries win; overflow is dropped from the oldest end.
        self.assertEqual(record["seen_accessions"], [
            "0001010-26-000007", "0001010-26-000006", "0001010-26-000005",
        ])

    def test_recent_filings_handles_missing_columns(self):
        self.assertEqual(state.recent_filings({}), [])
        self.assertEqual(state.recent_filings({"filings": {"recent": {}}}), [])


class StateFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.state_path = Path(self.temp) / "state.json"

    def test_save_load_roundtrip_is_atomically_written(self):
        payload = state.empty_state()
        payload["run_count"] = 3
        payload["ciks"]["0000001010"] = {"ticker": "TESTA", "seen_accessions": ["a"]}
        state.save(self.state_path, payload)
        loaded = state.load(self.state_path)
        self.assertEqual(loaded["run_count"], 3)
        self.assertEqual(loaded["ciks"]["0000001010"]["seen_accessions"], ["a"])
        self.assertEqual(loaded["$version"], state.STATE_VERSION)
        leftovers = [p for p in Path(self.temp).iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [], "no temp files remain after the atomic save")

    def test_missing_file_yields_fresh_state(self):
        loaded = state.load(self.state_path)
        self.assertEqual(loaded, state.empty_state())

    def test_corrupted_file_yields_fresh_state(self):
        self.state_path.write_text("{not json", encoding="utf-8")
        loaded = state.load(self.state_path)
        self.assertEqual(loaded, state.empty_state())

    def test_missing_keys_are_merged_from_defaults(self):
        self.state_path.write_text('{"run_count": 2}', encoding="utf-8")
        loaded = state.load(self.state_path)
        self.assertEqual(loaded["run_count"], 2)
        self.assertIn("universe", loaded)
        self.assertEqual(loaded["$version"], state.STATE_VERSION)


if __name__ == "__main__":
    unittest.main()
