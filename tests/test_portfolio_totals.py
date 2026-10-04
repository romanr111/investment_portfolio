"""Tests for portfolio total assets and allocation reconciliation.

Verifies that DataSource.calculate_total_assets does not double-count IB cash
and that PortfolioTableBuilder allocation rows reconcile to net worth.
"""
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import tempfile

from data.assets_data import OTHER_BETS
from src.allocation_calculator import AllocationCalculator
from src.data_source import DataSource
from src.google_sheets.spreadsheet_structure import PortfolioTableBuilder
from src.portfolio_ledger.contract import build_portfolio_contract
from src.portfolio_ledger.storage import PortfolioLedger


def _extract_allocation_rows(table):
    rows = {}
    for row in table:
        if (
            len(row) > 8
            and row[6]
            and row[6] != "Net worth"
            and str(row[8]).endswith("%")
        ):
            rows[row[6]] = row[7]
    return rows


def _sum_allocation_row_values(rows):
    return sum(int(float(value)) for value in rows.values())


class TestPortfolioTotals(unittest.TestCase):

    def test_combined_data_exposes_v2_contract_without_removing_legacy_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_source = DataSource.__new__(DataSource)
            data_source._data_timestamp = 1.0
            data_source.ib_data = {"Total Stocks Value": 0}
            data_source.ib = SimpleNamespace(performance_ytd={})
            data_source.index_performance_data = {}
            data_source.crypto = SimpleNamespace(
                get_total_crypto_value=lambda: 40,
                crypto_market_values={"BTC": 40},
                quantities={"BTC": 0.001},
            )
            data_source.crypto_savings = []
            data_source.fi_data = {
                "group_weighted_interest": {
                    "Crypto Landing": (80, 0.05),
                    "p2p_lending": (30, 0.0),
                }
            }
            data_source.cash = SimpleNamespace(total_cash=Decimal("0"), as_dict=lambda: {})
            data_source.ff_progress = "0%"
            data_source._calculate_asset_allocation = lambda: {
                "net_worth": 150,
                "allocations": {},
            }
            data_source._save_combined_data_to_json = lambda data: None
            data_source.portfolio_contract = build_portfolio_contract(
                ledger=PortfolioLedger(Path(temp_dir)),
                live_crypto_quantities={"BTC": 0.001},
                live_crypto_market_values={"BTC": 40},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=30,
                as_of_date=__import__("datetime").date(2026, 6, 30),
            )
            data_source.total_assets = 150

            combined = data_source.get_combined_data()

            self.assertEqual(combined["DATA_CONTRACT_VERSION"], 2)
            self.assertIn("POSITION_DATA", combined)
            self.assertIn("ACTIVITY_DATA", combined)
            self.assertIn("PERFORMANCE_DATA", combined)
            self.assertIn("DATA_QUALITY", combined)
            self.assertEqual(combined["CRYPTO_DATA"]["Total_Crypto_Value"], 40)
            self.assertIn("FIXED_INCOME_DATA", combined)
            self.assertIn("OTHER_ASSETS", combined)

    def test_asset_allocation_uses_canonical_lending_and_p2p_values(self):
        data_source = DataSource.__new__(DataSource)
        data_source.ib_data = {
            "Total Stocks Value": 0,
            "Bonds": {},
            "Commodities": {},
            "Precious Metals": {},
            "REIT": {},
        }
        data_source.crypto = SimpleNamespace(get_total_crypto_value=lambda: 0)
        data_source.fi_data = {
            "group_weighted_interest": {
                "Crypto Landing": (80, 0.05),
                "p2p_lending": (30, 0.0),
            }
        }
        data_source.cash = SimpleNamespace(total_cash=Decimal("0"))
        data_source.total_assets = 100
        data_source.portfolio_contract = {
            "POSITION_DATA": {
                "crypto": [],
                "crypto_lending": [{"principal_usd": 100}],
                "p2p": [{"balance_usd": 0}],
                "other_assets": [{"carrying_value_usd": 0}],
            }
        }

        allocation = data_source._calculate_asset_allocation()

        self.assertEqual(allocation["allocations"]["Crypto Lending"]["value"], 100)
        self.assertEqual(
            allocation["allocations"]["Crypto Lending"]["percentage"], 100.0
        )
        self.assertNotIn("P2P Lending", allocation["allocations"])

    def test_calculate_total_assets_excludes_ib_cash_from_cash_total(self):
        data_source = DataSource.__new__(DataSource)
        data_source.ib_data = {"IB_Portfolio_Value": 111230, "Net_cash": 8358}
        data_source.crypto = SimpleNamespace(get_total_crypto_value=lambda: 4627)
        data_source.fi_data = {
            "group_weighted_interest": {
                "Crypto Landing": (18295.1125, 0.0),
                "p2p_lending": (2295, 0.0),
            }
        }
        data_source.cash = SimpleNamespace(
            total_cash=Decimal("8610"),
            ib_cash=Decimal("8358"),
        )

        expected_total = int(
            111230 + 4627 + 18295.1125 + 2295
            + float(Decimal("8610") - Decimal("8358"))
            + float(OTHER_BETS)
        )

        self.assertEqual(data_source.calculate_total_assets(), expected_total)

    def test_build_central_columns_uses_actual_cash_value_for_allocation_rows(self):
        data = {
            "FIN_FREEDOM_GOAL_PROGRESS": "0%",
            "TOTAL_ASSETS": 1000,
            "ALLOCATIONS": {
                "allocation_breakdown": {
                    "Stocks": 40.0,
                    "Bonds": 30.0,
                    "Cash": 30.0,
                }
            },
            "IB_DATA": {
                "Total Stocks Value": 400,
                "Bonds": {"BOND": 300},
                "China Stocks": {},
                "Stocks": {},
                "Commodities": {},
                "Precious Metals": {},
                "REIT": {},
            },
            "CRYPTO_DATA": {"Total_Crypto_Value": 0},
            "FIXED_INCOME_DATA": {
                "group_weighted_interest": {
                    "Crypto Landing": (0, 0.0),
                    "p2p_lending": (0, 0.0),
                }
            },
            "CASH_DATA": {"Total": 50},
            "OTHER_ASSETS": {"Other Bets": 0},
        }

        table = PortfolioTableBuilder(data).build_central_columns([])
        rows = _extract_allocation_rows(table)

        self.assertEqual(rows["Stocks"], "400")
        self.assertEqual(rows["Bonds"], "300")
        self.assertEqual(rows["Cash"], "50")

    def test_allocation_rows_reconcile_with_net_worth_using_actual_category_values(self):
        data = {
            "FIN_FREEDOM_GOAL_PROGRESS": "0%",
            "TOTAL_ASSETS": 1330,
            "IB_DATA": {
                "Total Stocks Value": 400,
                "Bonds": {"BOND": 300},
                "China Stocks": {},
                "Stocks": {},
                "Commodities": {"COMB": 100},
                "Precious Metals": {"IAU": 50},
                "REIT": {},
            },
            "CRYPTO_DATA": {"Total_Crypto_Value": 40},
            "FIXED_INCOME_DATA": {
                "group_weighted_interest": {
                    "Crypto Landing": (80, 0.0),
                    "p2p_lending": (30, 0.0),
                }
            },
            "CASH_DATA": {"Total": 260},
            "OTHER_ASSETS": {"Other Bets": 70},
        }
        data["ALLOCATIONS"] = AllocationCalculator(data).get_sorted_sector_allocations()

        table = PortfolioTableBuilder(data).build_central_columns([])
        rows = _extract_allocation_rows(table)

        self.assertEqual(rows["Stocks"], "400")
        self.assertEqual(rows["Bonds"], "300")
        self.assertEqual(rows["Other Bets"], "70")
        self.assertEqual(rows["Crypto Lending"], "80")
        self.assertEqual(rows["Precious Metals"], "50")
        self.assertEqual(rows["Cash"], "260")
        self.assertEqual(rows["Crypto Coins"], "40")
        self.assertEqual(rows["Commodities"], "100")
        self.assertEqual(rows["P2P Lending"], "30")
        self.assertEqual(_sum_allocation_row_values(rows), data["TOTAL_ASSETS"])



    def test_get_combined_data_preserves_legacy_p2p_rate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_source = DataSource.__new__(DataSource)
            data_source._data_timestamp = 1.0
            data_source.ib_data = {"Total Stocks Value": 0}
            data_source.ib = SimpleNamespace(
                performance_ytd={}, get_stock_positions_analytics=lambda: {}
            )
            data_source.index_performance_data = {}
            data_source.crypto = SimpleNamespace(
                get_total_crypto_value=lambda: 40,
                crypto_market_values={"BTC": 40},
                quantities={"BTC": 0.001},
            )
            data_source.crypto_savings = []
            data_source.fi_data = {
                "group_weighted_interest": {
                    "Crypto Landing": (80, 0.05),
                    "p2p_lending": (30, 0.11),
                }
            }
            data_source.cash = SimpleNamespace(total_cash=Decimal("0"), as_dict=lambda: {})
            data_source.ff_progress = "0%"
            data_source._calculate_asset_allocation = lambda: {
                "net_worth": 130,
                "allocations": {},
            }
            data_source._save_combined_data_to_json = lambda data: None
            data_source.portfolio_contract = build_portfolio_contract(
                ledger=PortfolioLedger(Path(temp_dir)),
                live_crypto_quantities={"BTC": 0.001},
                live_crypto_market_values={"BTC": 40},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=30,
                as_of_date=__import__("datetime").date(2026, 6, 30),
            )
            data_source.total_assets = 130

            combined = data_source.get_combined_data()

            # The v2 projection replaces the P2P balance but must keep the
            # legacy weighted rate; zeroing it blanked the rate column in
            # Google Sheets.
            p2p = combined["FIXED_INCOME_DATA"]["group_weighted_interest"][
                "p2p_lending"
            ]
            self.assertEqual(p2p[0], 30)
            self.assertAlmostEqual(p2p[1], 0.11)




if __name__ == "__main__":
    unittest.main()
