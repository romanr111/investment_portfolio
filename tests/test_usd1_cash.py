import unittest
from datetime import date
from pathlib import Path
import tempfile
from src.portfolio_ledger.contract import build_portfolio_contract, classify_lending_positions
from src.portfolio_ledger.storage import PortfolioLedger
from unittest.mock import patch
from src.crypto.base_exchange_client import ExchangeBase
from src.crypto.crypto_tokens import CryptoData


class Broker(ExchangeBase):
    def __init__(self):
        pass
    def _validate_connection(self):
        return True
    def get_cash_balance(self):
        return sum(self.filter_out_stablecoin_balances({"USD1": 1000, "BTC": .1}).values())
    def get_all_crypto_balances(self):
        return {"USD1": 1231, "BTC": .1}
    def get_savings_positions(self):
        return {"binance": {"USD1": (231, .05), "USDT": (100, .04)}}


class USD1CashTests(unittest.TestCase):
    @patch("src.crypto.crypto_tokens.COLD_STORAGE", {})
    def test_usd1_spot_and_earn_are_cash_without_lending_double_count(self):
        broker = Broker()
        self.assertEqual(CryptoData.calculate_free_cash_balance([broker]), 1231)
        self.assertEqual(CryptoData.get_all_crypto_quantity([broker]), {"BTC": .1})
        self.assertEqual(CryptoData.get_all_savings_positions([broker]),
                         [{"binance": {"USDT": (100, .04)}}])


    def test_contract_and_snapshot_recovery_never_put_usd1_in_crypto_or_lending(self):
        from src.portfolio_ledger.contract import recover_crypto_positions
        classified = classify_lending_positions([{"binance": {"USD1": (100, .05)}}])
        self.assertEqual(classified["stablecoin_principal_usd"], 0)
        self.assertEqual(classified["volatile_earn"], [])
        old = {"CRYPTO_DATA": {"Token_Quantities": {"USD1": 100, "BTC": 1},
                              "Crypto_Market_Values": {"USD1": 100, "BTC": 1000}}}
        quantities, values, _ = recover_crypto_positions({}, {}, old)
        self.assertNotIn("USD1", quantities)
        self.assertNotIn("USD1", values)
        with tempfile.TemporaryDirectory() as temp:
            contract = build_portfolio_contract(
                ledger=PortfolioLedger(Path(temp)),
                live_crypto_quantities={"USD1": 100, "BTC": 1},
                live_crypto_market_values={"USD1": 100, "BTC": 1000},
                savings_positions=[{"binance": {"USD1": (100, .05)}}],
                legacy_other_assets_usd=0, legacy_p2p_balance_usd=0,
                as_of_date=date(2026, 9, 30), start_snapshot=old,
            )
        self.assertEqual([p["asset"] for p in contract["POSITION_DATA"]["crypto"]], ["BTC"])
        rows = contract["ACTIVITY_DATA"]["quarters"]["2026-Q3"]["crypto"]
        self.assertEqual([r["asset"] for r in rows], ["BTC"])


    def test_exchange_specific_filters_treat_usd1_as_cash(self):
        from src.crypto.okx_client import OKXFiltered
        from src.crypto.bybit_client import Bybit
        client = OKXFiltered.__new__(OKXFiltered)
        client.account_balances = {"USD1": 100, "BTC": .1}
        client.get_savings_positions = lambda: {"okx": {"USD1": (30, .05), "ETH": (1, .02)}}
        self.assertEqual(client.get_cash_balance(), 100)
        self.assertEqual(client.get_all_crypto_balances(), {"BTC": .1, "ETH": 1})
        self.assertIn("USD1", Bybit.STABLECOINS)


    def test_saved_data_reclassification_is_idempotent_and_preserves_totals(self):
        import copy
        from src.portfolio_ledger import contract as module
        self.assertTrue(callable(getattr(module, "reclassify_cash_equivalents", None)))
        original = {"data": {
            "CRYPTO_DATA": {"Total_Crypto_Value": 100,
                "Crypto_Market_Values": {"USD1": 70, "BTC": 30},
                "Token_Quantities": {"USD1": 70, "BTC": 1}},
            "CASH_DATA": {"Total": 200, "Breakdown": {"crypto_cash": 0, "cash": 200}},
            "TOTAL_ASSETS": 300,
            "ASSET_ALLOCATION": {"net_worth": 300, "allocations": {
                "Cash": {"value": 200, "percentage": 66.7},
                "Crypto Coins": {"value": 100, "percentage": 33.3}}},
            "POSITION_DATA": {"crypto": [{"asset": "USD1", "value_usd": 70},
                                          {"asset": "BTC", "value_usd": 30}]},
            "ACTIVITY_DATA": {"quarters": {"2026-Q3": {"crypto": [
                {"asset": "USD1", "end_value_usd": 70}, {"asset": "BTC", "end_value_usd": 30}]}}},
        }}
        untouched = copy.deepcopy(original)
        result = module.reclassify_cash_equivalents(original)
        self.assertEqual(original, untouched)
        d = result["data"]
        self.assertEqual(d["TOTAL_ASSETS"], 300)
        self.assertEqual(d["CASH_DATA"]["Total"], 270)
        self.assertEqual(d["CRYPTO_DATA"]["Total_Crypto_Value"], 30)
        self.assertEqual(d["ASSET_ALLOCATION"]["allocations"]["Cash"]["percentage"], 90)
        self.assertEqual([r["asset"] for r in d["ACTIVITY_DATA"]["quarters"]["2026-Q3"]["crypto"]], ["BTC"])
        self.assertEqual(module.reclassify_cash_equivalents(result), result)


    @patch("src.crypto.crypto_tokens.COLD_STORAGE", {"USD1": 10})
    def test_manual_cash_equivalents_are_not_lost(self):
        self.assertEqual(CryptoData.calculate_free_cash_balance([]), 10)

    def test_reclassified_data_updates_report_and_history_without_usd1(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "portfolio_yic_reports"))
        from generate_quarterly_report import build_alternative_asset_tables
        from src.portfolio_ledger.contract import reclassify_cash_equivalents
        from src.portfolio_history.unified_history import combined_data_to_unified_snapshot_rows
        data = {"CRYPTO_DATA": {"Total_Crypto_Value": 1100,
            "Crypto_Market_Values": {"USD1": 100, "BTC": 1000},
            "Token_Quantities": {"USD1": 100, "BTC": 1}},
            "CASH_DATA": {"Total": 0}, "TOTAL_ASSETS": 1100,
            "ASSET_ALLOCATION": {"net_worth": 1100, "allocations": {
                "Cash": {"value": 0}, "Crypto Coins": {"value": 1100}}},
            "ACTIVITY_DATA": {"quarters": {"2026-Q3": {"crypto": [
                {"asset": "USD1", "end_value_usd": 100},
                {"asset": "BTC", "start_value_usd": 900, "end_value_usd": 1000}]}}}}
        table = build_alternative_asset_tables(data, "2026-Q3")[0]
        self.assertEqual([row[0] for row in table.rows], ["BTC"])
        self.assertEqual(table.rows[0][2], "100.00%")
        corrected = reclassify_cash_equivalents(data)
        history = {r["asset_bucket"]: r["market_value"] for r in
            combined_data_to_unified_snapshot_rows(corrected, "2026-09-30")}
        self.assertEqual(history["Cash"], 100)
        self.assertEqual(history["Crypto Coins"], 1000)


    def test_real_binance_cached_balances_move_usd1_spot_and_earn_to_cash(self):
        from src.crypto.binance_client import BinanceClient
        client = BinanceClient.__new__(BinanceClient)
        client.spot_balances = {"USD1": 1000, "BTC": .1}
        client.get_funding_wallet_balance = lambda: {}
        client.flexible_savings = {"rows": [
            {"asset": "USD1", "totalAmount": "231", "latestAnnualPercentageRate": ".05"},
            {"asset": "USDT", "totalAmount": "100", "latestAnnualPercentageRate": ".04"}]}
        client.fixed_savings = {"rows": []}
        with patch("src.crypto.crypto_tokens.COLD_STORAGE", {}):
            tracked = {}
            self.assertEqual(CryptoData.calculate_free_cash_balance([client], tracked), 1231)
            self.assertEqual(tracked, {"USD1": 1231})
            self.assertNotIn("USD1", client.get_all_crypto_balances())
            self.assertEqual(CryptoData.get_all_savings_positions([client]),
                             [{"binance": {"USDT": (100, .04)}}])


    def test_whitebit_cash_is_in_dollars_not_cents(self):
        from src.crypto.whitebit_client import WhiteBit
        client = WhiteBit.__new__(WhiteBit)
        client.get_trade_balance = lambda asset: {"available": "100" if asset == "USD1" else "0"}
        self.assertEqual(client.get_cash_balance(), 100)


    def test_failed_source_keeps_cached_cash_without_double_counting(self):
        from src.portfolio_ledger import contract as module
        self.assertTrue(callable(getattr(module, "recover_cash_equivalents", None)))
        cached = {"data": {"CASH_DATA": {"Cash_Equivalents": {"USD1": 1231}}}}
        self.assertEqual(module.recover_cash_equivalents({"USD1": 20}, cached,
            balance_sources={"binance": "failed"}), {"USD1": 1231})
        self.assertEqual(module.recover_cash_equivalents({"USD1": 20}, cached,
            balance_sources={"binance": "ok"}), {"USD1": 20})
        self.assertEqual(module.recover_cash_equivalents({"USD1": 1500}, cached,
            balance_sources={"binance": "failed"}), {"USD1": 1500})


    def test_data_source_restores_cached_cash_once_with_partial_quality(self):
        import os, json
        from decimal import Decimal
        from types import SimpleNamespace
        from src.data_source import DataSource
        from src.cash_fixed_income.cash_summary import CashPortfolio
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            snapshots = base / "data/snapshots"
            snapshots.mkdir(parents=True)
            (snapshots / "combined_data_latest.json").write_text(json.dumps({"data": {
                "CASH_DATA": {"Cash_Equivalents": {"USD1": 1231}},
                "CRYPTO_DATA": {"Token_Quantities": {"BTC": 1},
                                "Crypto_Market_Values": {"BTC": 1000}}}}))
            obj = DataSource.__new__(DataSource)
            obj.ledger = PortfolioLedger(base / "ledger")
            obj.crypto = SimpleNamespace(quantities={"BTC": 1},
                crypto_market_values={"BTC": 1000}, cash_equivalent_values={"USD1": 20},
                balance_source_status={"binance": "failed"})
            obj.crypto_savings = []
            obj.fi_data = {"group_weighted_interest": {}}
            obj.cash = CashPortfolio.__new__(CashPortfolio)
            for name in ("cash", "lended", "debt", "private", "ib_cash", "crypto_cash", "mono", "wise"):
                setattr(obj.cash, name, Decimal(0))
            obj.cash.crypto_cash = Decimal(20)
            old_cwd = os.getcwd()
            try:
                os.chdir(base)
                with patch("src.data_source.select_contract_start_snapshot", return_value=None):
                    obj._prepare_portfolio_contract()
                    self.assertEqual(obj.cash.total_cash, Decimal(1231))
                    self.assertEqual(obj.portfolio_contract["DATA_QUALITY"]["cash"]["coverage"], "partial")
                    obj._prepare_portfolio_contract()
                    self.assertEqual(obj.cash.total_cash, Decimal(1231))
                    self.assertEqual(obj.portfolio_contract["DATA_QUALITY"]["cash"]["coverage"], "partial")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
