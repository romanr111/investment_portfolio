import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.portfolio_history.unified_history import (
    build_unified_history_frame,
    combined_data_to_unified_snapshot_rows,
    save_combined_data_snapshot_json,
    save_unified_history,
    sheet_tab_values_to_unified_rows,
    validate_required_buckets,
    upsert_combined_data_history,
    merge_history_frames,
)


class UnifiedHistoryTests(unittest.TestCase):
    def test_combined_data_snapshot_rows_have_core_buckets(self) -> None:
        combined = {
            "IB_DATA": {
                "Bonds": {"TLT": 100},
                "Stocks": {"AAPL": 50},
                "China Stocks": {"9988": 10},
                "Total Stocks Value": 60,
                "Precious Metals": {"IAU": 5},
                "Commodities": {"COMB": 7},
            },
            "CRYPTO_DATA": {"Total_Crypto_Value": 20},
            "FIXED_INCOME_DATA": {
                "group_weighted_interest": {
                    "Crypto Landing": (30, 0.1),
                    "p2p_lending": (40, 0.08),
                }
            },
            "CASH_DATA": {"Total": Decimal("3")},
            "OTHER_ASSETS": {"Other Bets": 11},
            "PERFORMANCE_DATA": {
                "buckets": {
                    "Crypto Lending": {
                        "return_pct": 5.2,
                        "net_flow_usd": 100,
                        "return_method": "modified_dietz",
                        "data_quality": "complete",
                    },
                    "P2P Lending": {
                        "return_pct": None,
                        "net_flow_usd": None,
                        "return_method": "unavailable",
                        "data_quality": "complete",
                    },
                }
            },
        }
        rows = combined_data_to_unified_snapshot_rows(combined, "2026-02-22")
        self.assertEqual(len(rows), 9)
        by_bucket = {row["asset_bucket"]: row for row in rows}
        self.assertEqual(by_bucket["Stocks"]["market_value"], 60)
        self.assertEqual(by_bucket["Other Bets"]["market_value"], 11)
        self.assertEqual(by_bucket["P2P Lending"]["market_value"], 40)
        self.assertEqual(by_bucket["Crypto Lending"]["return_pct"], 5.2)
        self.assertEqual(by_bucket["Crypto Lending"]["net_flow_usd"], 100)
        self.assertEqual(
            by_bucket["Crypto Lending"]["return_method"], "modified_dietz"
        )
        self.assertEqual(by_bucket["P2P Lending"]["return_method"], "unavailable")

    def test_sheet_tab_values_to_unified_rows(self) -> None:
        values = [
            ["", "", "", "", "", "", "Stocks", "1000"],
            ["", "", "", "", "", "", "Crypto Landing", "2500"],
            ["", "", "", "", "", "", "REIT", "0"],
        ]
        rows = sheet_tab_values_to_unified_rows(values, "31 Dec 2025")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["asset_bucket"], "Crypto Lending")
        self.assertEqual(rows[0]["date"], "2025-12-31")

    def test_sheet_tab_values_support_legacy_hi_columns(self) -> None:
        values = [
            ["", "", "", "", "", "", "", "Stocks", "23048"],
            ["", "", "", "", "", "", "", "Crypto", "15456"],
            ["", "", "", "", "", "", "", "Mining", "13040"],
            ["", "", "", "", "", "", "", "Cash & Equivalents", "13901"],
        ]
        rows = sheet_tab_values_to_unified_rows(values, "31 Mar 2021")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["asset_bucket"], "Stocks")
        self.assertEqual(rows[1]["asset_bucket"], "Crypto Coins")
        self.assertEqual(rows[2]["asset_bucket"], "Other Bets")
        self.assertEqual(rows[3]["asset_bucket"], "Cash")

    def test_build_unified_history_blank_returns(self) -> None:
        rows = [
            {
                "date": "2025-12-31",
                "asset_bucket": "Stocks",
                "market_value": 100.0,
                "return_pct": 0.1,
                "currency": "USD",
                "source_type": "google_sheets",
                "source_ref": "31 Dec 2025",
            },
            {
                "date": "2026-01-31",
                "asset_bucket": "Stocks",
                "market_value": 110.0,
                "return_pct": 0.1,
                "currency": "USD",
                "source_type": "google_sheets",
                "source_ref": "31 Jan 2026",
            },
        ]
        frame = build_unified_history_frame(rows, return_source="blank")
        self.assertTrue(frame["return_pct"].isna().all())
        self.assertIn("ingested_at_utc", frame.columns)

    def test_build_unified_history_pct_change(self) -> None:
        rows = [
            {
                "date": "2025-12-31",
                "asset_bucket": "Stocks",
                "market_value": 100.0,
                "return_pct": pd.NA,
                "currency": "USD",
                "source_type": "google_sheets",
                "source_ref": "31 Dec 2025",
            },
            {
                "date": "2026-01-31",
                "asset_bucket": "Stocks",
                "market_value": 110.0,
                "return_pct": pd.NA,
                "currency": "USD",
                "source_type": "google_sheets",
                "source_ref": "31 Jan 2026",
            },
        ]
        frame = build_unified_history_frame(rows, return_source="pct-change")
        jan = frame.loc[frame["date"] == "2026-01-31"].iloc[0]
        self.assertAlmostEqual(float(jan["return_pct"]), 0.1, places=10)

    def test_explicit_return_methods_override_legacy_pct_change(self) -> None:
        rows = [
            {
                "date": "2026-01-01",
                "asset_bucket": "Crypto Lending",
                "market_value": 1000.0,
                "return_pct": 2.5,
                "net_flow_usd": 100.0,
                "return_method": "modified_dietz",
                "data_quality": "complete",
                "currency": "USD",
                "source_type": "combined_data",
                "source_ref": "snapshot",
            },
            {
                "date": "2026-01-01",
                "asset_bucket": "P2P Lending",
                "market_value": 100.0,
                "return_pct": pd.NA,
                "net_flow_usd": pd.NA,
                "return_method": "unavailable",
                "data_quality": "complete",
                "currency": "USD",
                "source_type": "combined_data",
                "source_ref": "snapshot",
            },
        ]

        frame = build_unified_history_frame(
            rows, return_source="pct-change", history_frequency="raw"
        )

        lending = frame.loc[frame["asset_bucket"] == "Crypto Lending"].iloc[0]
        p2p = frame.loc[frame["asset_bucket"] == "P2P Lending"].iloc[0]
        self.assertEqual(lending["return_pct"], 2.5)
        self.assertEqual(lending["net_flow_usd"], 100.0)
        self.assertEqual(lending["return_method"], "modified_dietz")
        self.assertTrue(pd.isna(p2p["return_pct"]))

    def test_build_unified_history_monthly_uses_last_tab_of_month(self) -> None:
        rows = [
            {
                "date": "2025-10-01",
                "asset_bucket": "Stocks",
                "market_value": 100.0,
                "return_pct": pd.NA,
                "currency": "USD",
                "source_type": "google_sheets",
                "source_ref": "01 Oct 2025",
            },
            {
                "date": "2025-10-05",
                "asset_bucket": "Stocks",
                "market_value": 120.0,
                "return_pct": pd.NA,
                "currency": "USD",
                "source_type": "google_sheets",
                "source_ref": "05 Oct 2025",
            },
            {
                "date": "2025-11-15",
                "asset_bucket": "Stocks",
                "market_value": 130.0,
                "return_pct": pd.NA,
                "currency": "USD",
                "source_type": "google_sheets",
                "source_ref": "15 Nov 2025",
            },
        ]
        frame = build_unified_history_frame(rows, history_frequency="monthly")
        self.assertEqual(frame["date"].tolist(), ["2025-10-31", "2025-11-30"])
        self.assertAlmostEqual(float(frame.iloc[0]["market_value"]), 120.0, places=8)

    def test_validate_required_buckets_raises(self) -> None:
        frame = pd.DataFrame(
            [
                {"date": "2025-12-31", "asset_bucket": "Stocks"},
                {"date": "2025-12-31", "asset_bucket": "Bonds"},
            ]
        )
        with self.assertRaises(ValueError):
            validate_required_buckets(frame, required_buckets=("Stocks", "Bonds", "Cash"))

    def test_snapshot_and_history_files_are_written(self) -> None:
        combined = {"foo": "bar"}
        rows = [
            {
                "date": "2025-12-31",
                "asset_bucket": "Stocks",
                "market_value": 100.0,
                "return_pct": pd.NA,
                "currency": "USD",
                "source_type": "combined_data",
                "source_ref": "DataSource.get_combined_data",
            }
        ]
        frame = build_unified_history_frame(rows)

        with tempfile.TemporaryDirectory() as tmp_dir:
            snapshot_path = save_combined_data_snapshot_json(combined, tmp_dir, "2025-12-31")
            self.assertTrue(snapshot_path.exists())
            self.assertTrue((Path(tmp_dir) / "combined_data_latest.json").exists())

            csv_path = Path(tmp_dir) / "history.csv"
            jsonl_path = Path(tmp_dir) / "history.jsonl"
            save_unified_history(frame, str(csv_path), str(jsonl_path))
            self.assertTrue(csv_path.exists())
            self.assertTrue(jsonl_path.exists())

    def test_historical_snapshot_can_leave_latest_pointer_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            latest_path = Path(tmp_dir) / "combined_data_latest.json"
            latest_path.write_text('{"marker":"current"}', encoding="utf-8")

            snapshot_path = save_combined_data_snapshot_json(
                {"marker": "historical"},
                tmp_dir,
                "2025-12-31",
                update_latest=False,
            )

            self.assertTrue(snapshot_path.exists())
            self.assertEqual(
                latest_path.read_text(encoding="utf-8"), '{"marker":"current"}'
            )

    def test_current_combined_data_upsert_replaces_same_day_sheet_row(self) -> None:
        combined = {
            "IB_DATA": {"Total Stocks Value": 0},
            "CRYPTO_DATA": {"Total_Crypto_Value": 0},
            "FIXED_INCOME_DATA": {
                "group_weighted_interest": {
                    "Crypto Landing": (30, 0),
                    "p2p_lending": (0, 0),
                }
            },
            "CASH_DATA": {"Total": 0},
            "OTHER_ASSETS": {"Other Bets": 0},
            "PERFORMANCE_DATA": {
                "buckets": {
                    "Crypto Lending": {
                        "return_pct": 1.2,
                        "net_flow_usd": 5,
                        "return_method": "modified_dietz",
                        "data_quality": "complete",
                    }
                }
            },
        }
        existing = pd.DataFrame(
            [
                {
                    "date": "2026-06-30",
                    "asset_bucket": "Crypto Lending",
                    "market_value": 999,
                    "return_pct": pd.NA,
                    "currency": "USD",
                    "source_type": "google_sheets",
                    "source_ref": "30 Jun 2026",
                    "ingested_at_utc": "2026-06-30T00:00:00Z",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "history.csv"
            jsonl_path = Path(tmp_dir) / "history.jsonl"
            existing.to_csv(csv_path, index=False)

            frame = upsert_combined_data_history(
                combined,
                str(csv_path),
                str(jsonl_path),
                as_of_date="2026-06-30",
            )

            lending = frame.loc[frame["asset_bucket"] == "Crypto Lending"].iloc[0]
            self.assertEqual(lending["market_value"], 30)
            self.assertEqual(lending["source_type"], "combined_data")
            self.assertEqual(lending["return_method"], "modified_dietz")

    def test_local_combined_history_wins_over_google_sheet_row(self) -> None:
        sheet = pd.DataFrame(
            [
                {
                    "date": "2026-06-30",
                    "asset_bucket": "Crypto Lending",
                    "market_value": 999.0,
                    "return_pct": pd.NA,
                    "currency": "USD",
                    "source_type": "google_sheets",
                }
            ]
        )
        local = pd.DataFrame(
            [
                {
                    "date": "2026-06-30",
                    "asset_bucket": "Crypto Lending",
                    "market_value": 30.0,
                    "return_pct": 1.2,
                    "currency": "USD",
                    "source_type": "combined_data",
                }
            ]
        )

        merged = merge_history_frames(sheet, local)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged.iloc[0]["market_value"], 30.0)
        self.assertEqual(merged.iloc[0]["source_type"], "combined_data")


if __name__ == "__main__":
    unittest.main()
