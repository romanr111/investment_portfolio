import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.portfolio_ledger.storage import PortfolioLedger
from src.portfolio_ledger.sync import sync_crypto_sources
from src.portfolio_ledger.sync import build_activity_sources
from src.portfolio_ledger.cli import parse_args
from src.portfolio_ledger.sources import (
    BinanceActivitySource,
    OKXActivitySource,
    WhiteBitActivitySource,
    normalize_binance_trade,
    normalize_okx_fill,
    normalize_whitebit_trade,
)


class PortfolioLedgerTests(unittest.TestCase):
    def test_import_events_deduplicates_exchange_remote_id(self) -> None:
        event = {
            "occurred_at": "2026-04-15T12:00:00Z",
            "source": "binance",
            "account": "spot",
            "remote_id": "trade-42",
            "event_type": "buy",
            "asset": "BTC",
            "quantity": 0.01,
            "quote_asset": "USDT",
            "quote_quantity": 600.0,
            "usd_value": 600.0,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))

            first = ledger.import_events([event])
            second = ledger.import_events([event])

            self.assertEqual(first.imported_count, 1)
            self.assertEqual(second.imported_count, 0)
            stored = ledger.load_crypto_events()
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["event_id"], "binance:spot:trade-42")


    def test_manual_amount_and_fee_usd_are_parsed_as_numeric_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.crypto_dir.mkdir(parents=True)
            ledger.manual_events_path.write_text(
                "event_id,occurred_at,source,account,event_type,asset,quantity,"
                "amount_usd,fee_usd\n"
                "manual-1,2026-04-01T00:00:00Z,manual,cold_storage,"
                "reward,USDT,5,5,0.1\n",
                encoding="utf-8",
            )

            event = ledger.load_crypto_events()[0]

            self.assertEqual(event["amount_usd"], 5.0)
            self.assertEqual(event["usd_value"], 5.0)
            self.assertEqual(event["fee_usd"], 0.1)

    def test_unknown_crypto_event_type_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "event_type"):
                ledger.import_events(
                    [
                        {
                            "event_id": "bad-1",
                            "occurred_at": "2026-04-01T00:00:00Z",
                            "source": "manual",
                            "account": "cold_storage",
                            "event_type": "rewrad",
                            "asset": "BTC",
                            "quantity": 0.1,
                        }
                    ]
                )

    def test_binance_trade_normalization_preserves_fee_and_quote(self) -> None:
        event = normalize_binance_trade(
            {
                "id": 77,
                "time": 1776240000000,
                "qty": "0.01",
                "quoteQty": "600.00",
                "commission": "0.00001",
                "commissionAsset": "BTC",
                "isBuyer": True,
            },
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
        )

        self.assertEqual(event["event_type"], "buy")
        self.assertEqual(event["asset"], "BTC")
        self.assertEqual(event["quote_quantity"], 600.0)
        self.assertEqual(event["fee_asset"], "BTC")
        self.assertEqual(event["fee_quantity"], 0.00001)
        self.assertIsNone(event["fee_usd"])

    def test_okx_fill_normalization_uses_fill_price_for_quote_value(self) -> None:
        event = normalize_okx_fill(
            {
                "tradeId": "88",
                "instId": "ETH-USDT",
                "side": "sell",
                "fillSz": "2",
                "fillPx": "3500",
                "fee": "-0.5",
                "feeCcy": "USDT",
                "ts": "1776240000000",
            }
        )

        self.assertEqual(event["event_type"], "sell")
        self.assertEqual(event["asset"], "ETH")
        self.assertEqual(event["quote_quantity"], 7000.0)
        self.assertEqual(event["fee_quantity"], 0.5)
        self.assertEqual(event["fee_usd"], 0.5)


    def test_incremental_sync_reuses_cursor_and_remains_idempotent(self) -> None:
        class FakeSource:
            source_name = "fake"

            def __init__(self) -> None:
                self.event_cursors = []

            def fetch_events(self, start_at, end_at, cursor=None):
                self.event_cursors.append(cursor)
                return (
                    [
                        {
                            "occurred_at": "2026-04-15T12:00:00Z",
                            "source": "fake",
                            "account": "spot",
                            "remote_id": "1",
                            "event_type": "reward",
                            "asset": "BTC",
                            "quantity": 0.001,
                        }
                    ],
                    {"after": "1"},
                )

            def fetch_lending_events(self, start_at, end_at, cursor=None):
                return [], {"after": "lending-1"}

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            source = FakeSource()
            start = datetime(2026, 4, 1, tzinfo=timezone.utc)
            end = datetime(2026, 6, 30, tzinfo=timezone.utc)

            first = sync_crypto_sources(ledger, [source], start, end)
            second = sync_crypto_sources(ledger, [source], start, end)

            self.assertEqual(first["fake"]["imported_count"], 1)
            self.assertEqual(second["fake"]["imported_count"], 0)
            self.assertIsNone(source.event_cursors[0])
            self.assertEqual(source.event_cursors[1], {"after": "1"})
            self.assertEqual(
                ledger.load_import_state()["fake"]["lending"],
                {"after": "lending-1"},
            )

    def test_sync_imports_successful_capability_when_other_capability_fails(self) -> None:
        class PartiallyAvailableSource:
            source_name = "partial"

            def fetch_events(self, start_at, end_at, cursor=None):
                return (
                    [
                        {
                            "occurred_at": "2026-04-15T12:00:00Z",
                            "source": "partial",
                            "account": "spot",
                            "remote_id": "event-1",
                            "event_type": "reward",
                            "asset": "BTC",
                            "quantity": 0.001,
                        }
                    ],
                    {"after": "event-1", "coverage": "complete"},
                )

            def fetch_lending_events(self, start_at, end_at, cursor=None):
                raise RuntimeError("provider rejected lending history")

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            result = sync_crypto_sources(
                ledger,
                [PartiallyAvailableSource()],
                datetime(2026, 4, 1, tzinfo=timezone.utc),
                datetime(2026, 6, 30, tzinfo=timezone.utc),
            )["partial"]

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["imported_count"], 1)
            self.assertEqual(result["failed_capabilities"], ["lending"])
            self.assertEqual(len(ledger.load_crypto_events()), 1)
            state = ledger.load_import_state()["partial"]
            self.assertEqual(state["events"]["after"], "event-1")
            self.assertEqual(state["coverage"], "partial")


    def test_partial_cursor_does_not_advance_incremental_window(self) -> None:
        class PartialCoverageSource:
            source_name = "partial-cursor"

            def __init__(self) -> None:
                self.event_cursors = []

            def fetch_events(self, start_at, end_at, cursor=None):
                self.event_cursors.append(cursor)
                return [], {"last_end_ms": 999, "coverage": "partial"}

            def fetch_lending_events(self, start_at, end_at, cursor=None):
                return [], {"last_end_ms": 999, "coverage": "complete"}

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            source = PartialCoverageSource()
            start = datetime(2026, 4, 1, tzinfo=timezone.utc)
            end = datetime(2026, 6, 30, tzinfo=timezone.utc)

            sync_crypto_sources(ledger, [source], start, end)
            sync_crypto_sources(ledger, [source], start, end)

            self.assertEqual(source.event_cursors, [None, {}])
            self.assertEqual(ledger.load_import_state()["partial-cursor"]["coverage"], "partial")

    def test_activity_sources_preserve_transfer_ids_for_reconciliation(self) -> None:
        class BinanceApi:
            def get_deposit_history(self, **kwargs):
                return [
                    {
                        "coin": "BTC",
                        "amount": "0.5",
                        "txId": "on-chain-1",
                        "insertTime": 1776240000000,
                    }
                ]

            def get_withdraw_history(self, **kwargs):
                return []

        binance = BinanceActivitySource(
            type("Wrapper", (), {"client": BinanceApi()})(), symbols=[]
        )
        binance_events, _ = binance.fetch_events(
            datetime(2026, 4, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 30, tzinfo=timezone.utc),
        )

        class OKXApi:
            def _send_request(self, method, endpoint, params=None):
                if endpoint == "/asset/withdrawal-history":
                    return [
                        {
                            "ccy": "BTC",
                            "amt": "0.5",
                            "fee": "0",
                            "txId": "on-chain-1",
                            "ts": "1776240000000",
                        }
                    ]
                return []

        okx_events, _ = OKXActivitySource(OKXApi()).fetch_events(
            datetime(2026, 4, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(binance_events[0]["transfer_id"], "on-chain-1")
        self.assertEqual(okx_events[0]["transfer_id"], "on-chain-1")


if __name__ == "__main__":
    unittest.main()
