import json
import tempfile
import unittest
from pathlib import Path

from src.google_sheets.insights_refresh import (
    load_insights_config,
    load_snapshot,
    select_previous_snapshot,
)


class InsightsRefreshTests(unittest.TestCase):
    def test_snapshot_replay_unwraps_data_and_preserves_additive_target_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "combined_data_2026-09-30_20260930T180000Z.json"
            path.write_text(
                json.dumps(
                    {
                        "as_of_date": "2026-09-30",
                        "saved_at_utc": "2026-09-30T18:00:00+00:00",
                        "data": {
                            "TOTAL_ASSETS": 500,
                            "FINANCIAL_FREEDOM_GOAL_TARGET": 1000,
                        },
                    }
                ),
                encoding="utf-8",
            )

            snapshot = load_snapshot(path)

        self.assertEqual(snapshot.as_of_date, "2026-09-30")
        self.assertEqual(snapshot.data["FINANCIAL_FREEDOM_GOAL_TARGET"], 1000)

    def test_previous_snapshot_is_strictly_earlier_and_same_date_choice_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            snapshots = (
                ("2026-09-30_20260930T120000Z", "2026-09-30T12:00:00+00:00", 1),
                ("2026-09-30_20260930T180000Z", "2026-09-30T18:00:00+00:00", 2),
                ("2026-10-04_20261004T120000Z", "2026-10-04T12:00:00+00:00", 3),
                ("2026-10-05_20261005T120000Z", "2026-10-05T12:00:00+00:00", 4),
            )
            for filename, saved_at, value in snapshots:
                (directory / f"combined_data_{filename}.json").write_text(
                    json.dumps(
                        {
                            "as_of_date": filename[:10],
                            "saved_at_utc": saved_at,
                            "data": {"TOTAL_ASSETS": value},
                        }
                    ),
                    encoding="utf-8",
                )
            (directory / "combined_data_latest.json").write_text("{}", encoding="utf-8")

            selected = select_previous_snapshot(directory, "2026-10-04")

        self.assertEqual(selected.as_of_date, "2026-09-30")
        self.assertEqual(selected.data["TOTAL_ASSETS"], 2)
        self.assertTrue(selected.path.name.endswith("20260930T180000Z.json"))

    def test_config_reader_uses_only_supported_local_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "insights_config.json"
            path.write_text(
                json.dumps(
                    {
                        "allocation_targets_pct": {"Stocks": 50},
                        "essential_monthly_spending_usd": 2000,
                        "base_currency": "EUR",
                        "credentials": "must not enter generator config",
                    }
                ),
                encoding="utf-8",
            )

            config = load_insights_config(path)

        self.assertEqual(config["allocation_targets_pct"], {"Stocks": 50})
        self.assertEqual(config["essential_monthly_spending_usd"], 2000)
        self.assertNotIn("base_currency", config)
        self.assertNotIn("credentials", config)


if __name__ == "__main__":
    unittest.main()
