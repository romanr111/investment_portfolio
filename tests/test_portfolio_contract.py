import unittest
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from src.portfolio_ledger.contract import (
    aggregate_crypto_quarter,
    build_portfolio_contract,
    calculate_car_assets,
    calculate_crypto_performance,
    calculate_lending_performance,
    classify_lending_positions,
    modified_dietz_return,
    normalize_p2p_positions,
    select_contract_start_snapshot,
    project_legacy_values,
    recover_crypto_positions,
    upgrade_legacy_combined_data,
)
from src.portfolio_ledger.storage import PortfolioLedger


UTC = timezone.utc


class CryptoContractTests(unittest.TestCase):
    def test_internal_transfer_has_zero_portfolio_quantity_impact(self) -> None:
        rows = aggregate_crypto_quarter(
            events=[
                {
                    "event_id": "move-1",
                    "occurred_at": "2026-05-01T12:00:00Z",
                    "source": "manual",
                    "account": "binance",
                    "event_type": "internal_transfer",
                    "asset": "BTC",
                    "quantity": 0.5,
                    "from_location": "binance",
                    "to_location": "cold_storage",
                }
            ],
            start_quantities={"BTC": 1.0},
            end_quantities={"BTC": 1.0},
            start_values_usd={"BTC": 60000.0},
            end_values_usd={"BTC": 70000.0},
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["net_change_quantity"], 0.0)
        self.assertEqual(rows[0]["internal_transfers_quantity"], 0.5)
        self.assertEqual(rows[0]["unexplained_quantity"], 0.0)
        self.assertEqual(rows[0]["coverage"], "complete")

    def test_matching_transfer_legs_do_not_change_crypto_return(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.import_events(
                [
                    {
                        "occurred_at": "2026-05-01T12:00:00Z",
                        "source": "binance",
                        "account": "spot",
                        "remote_id": "withdrawal-1",
                        "event_type": "withdrawal",
                        "asset": "BTC",
                        "quantity": 0.5,
                        "usd_value": 500.0,
                        "transfer_id": "on-chain-1",
                    },
                    {
                        "occurred_at": "2026-06-01T12:00:00Z",
                        "source": "okx",
                        "account": "funding",
                        "remote_id": "deposit-1",
                        "event_type": "deposit",
                        "asset": "BTC",
                        "quantity": 0.5,
                        "usd_value": 500.0,
                        "transfer_id": "on-chain-1",
                    },
                ]
            )
            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={"BTC": 1.0},
                live_crypto_market_values={"BTC": 1100.0},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=0,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                start_snapshot={
                    "data": {
                        "POSITION_DATA": {
                            "crypto": [
                                {"asset": "BTC", "quantity": 1.0, "value_usd": 1000.0}
                            ]
                        }
                    }
                },
            )

            crypto = contract["ACTIVITY_DATA"]["quarters"]["2026-Q2"]
            self.assertEqual(crypto["crypto_performance"]["return_pct"], 10.0)
            self.assertEqual(crypto["crypto"][0]["external_transfers_quantity"], 0.0)
            self.assertEqual(crypto["crypto"][0]["internal_transfers_quantity"], 1.0)

    def test_crypto_materiality_checks_both_quarter_boundaries(self) -> None:
        rows = aggregate_crypto_quarter(
            events=[],
            start_quantities={"OLD": 10.0, "DUST": 10.0},
            end_quantities={"OLD": 0.0, "DUST": 10.0},
            start_values_usd={"OLD": 150.0, "DUST": 99.0},
            end_values_usd={"OLD": 0.0, "DUST": 99.0},
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
        )

        self.assertEqual([row["asset"] for row in rows], ["OLD"])
        self.assertEqual(rows[0]["status"], "closed")

    def test_modified_dietz_weights_mid_period_contribution(self) -> None:
        result = modified_dietz_return(
            start_value=1000.0,
            end_value=1600.0,
            cash_flows=[(datetime(2026, 5, 16, tzinfo=UTC), 500.0)],
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, tzinfo=UTC),
        )

        self.assertAlmostEqual(result, 0.08, places=2)

    def test_crypto_bucket_return_uses_trade_cash_flows(self) -> None:
        result = calculate_crypto_performance(
            start_value_usd=1000.0,
            end_value_usd=1600.0,
            events=[
                {
                    "occurred_at": "2026-05-16T00:00:00Z",
                    "event_type": "buy",
                    "asset": "BTC",
                    "usd_value": 500.0,
                }
            ],
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, tzinfo=UTC),
            reconciliation_complete=True,
        )

        self.assertAlmostEqual(result["return_pct"], 8.0, places=1)
        self.assertEqual(result["net_flow_usd"], 500.0)
        self.assertEqual(result["return_method"], "modified_dietz")

    def test_crypto_bucket_income_includes_trade_fee_value(self) -> None:
        result = calculate_crypto_performance(
            start_value_usd=1000.0,
            end_value_usd=1490.0,
            events=[
                {
                    "occurred_at": "2026-05-16T00:00:00Z",
                    "event_type": "buy",
                    "asset": "BTC",
                    "usd_value": 500.0,
                    "fee_asset": "USDT",
                    "fee_quantity": 10.0,
                    "fee_usd": 10.0,
                }
            ],
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, tzinfo=UTC),
            reconciliation_complete=True,
        )

        self.assertEqual(result["income_usd"], -10.0)
        self.assertEqual(result["coverage"], "complete")

    def test_unvalued_trade_fee_makes_crypto_performance_partial(self) -> None:
        result = calculate_crypto_performance(
            start_value_usd=1000.0,
            end_value_usd=1500.0,
            events=[
                {
                    "occurred_at": "2026-05-16T00:00:00Z",
                    "event_type": "buy",
                    "asset": "BTC",
                    "usd_value": 500.0,
                    "fee_asset": "BTC",
                    "fee_quantity": 0.001,
                }
            ],
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, tzinfo=UTC),
            reconciliation_complete=True,
        )

        self.assertIsNone(result["return_pct"])
        self.assertIsNone(result["income_usd"])
        self.assertEqual(result["coverage"], "partial")

    def test_non_stable_earn_principal_is_not_crypto_lending(self) -> None:
        classified = classify_lending_positions(
            [
                {
                    "binance": {
                        "USDT": (1000.0, 0.05),
                        "ETH": (2.0, 0.03),
                    }
                }
            ]
        )

        self.assertEqual(classified["stablecoin_principal_usd"], 1000.0)
        self.assertEqual(classified["stablecoin_positions"][0]["asset"], "USDT")
        self.assertEqual(classified["volatile_earn"][0]["asset"], "ETH")
        self.assertNotIn("principal_usd", classified["volatile_earn"][0])

    def test_lending_actual_income_and_return_use_cash_flows(self) -> None:
        result = calculate_lending_performance(
            start_principal_usd=1000.0,
            end_principal_usd=1590.0,
            events=[
                {
                    "occurred_at": "2026-05-16T00:00:00Z",
                    "event_type": "lending_subscription",
                    "usd_value": 500.0,
                },
                {
                    "occurred_at": "2026-06-01T00:00:00Z",
                    "event_type": "reward",
                    "usd_value": 100.0,
                },
                {
                    "occurred_at": "2026-06-02T00:00:00Z",
                    "event_type": "fee",
                    "usd_value": 10.0,
                },
            ],
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, tzinfo=UTC),
        )

        self.assertEqual(result["income_usd"], 90.0)
        self.assertAlmostEqual(result["return_pct"], 7.2, places=1)
        self.assertEqual(result["return_method"], "modified_dietz")
        self.assertEqual(result["coverage"], "complete")

    def test_volatile_earn_reward_is_separate_from_stablecoin_lending_return(self) -> None:
        result = calculate_lending_performance(
            start_principal_usd=1000.0,
            end_principal_usd=1010.0,
            events=[
                {
                    "occurred_at": "2026-06-01T00:00:00Z",
                    "event_type": "reward",
                    "asset": "USDT",
                    "quantity": 10.0,
                    "usd_value": 10.0,
                },
                {
                    "occurred_at": "2026-06-01T00:00:00Z",
                    "event_type": "reward",
                    "asset": "BTC",
                    "quantity": 0.001,
                    "usd_value": 60.0,
                },
            ],
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, tzinfo=UTC),
        )

        self.assertEqual(result["income_usd"], 10.0)
        self.assertEqual(result["volatile_rewards"][0]["asset"], "BTC")
        self.assertEqual(result["volatile_rewards"][0]["quantity"], 0.001)
        self.assertEqual(result["volatile_rewards"][0]["usd_value"], 60.0)

    def test_lending_return_is_partial_when_account_history_is_incomplete(self) -> None:
        result = calculate_lending_performance(
            start_principal_usd=1000.0,
            end_principal_usd=1010.0,
            events=[],
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, tzinfo=UTC),
            source_coverage_complete=False,
        )

        self.assertIsNone(result["return_pct"])
        self.assertEqual(result["coverage"], "partial")

    def test_unsold_car_has_carrying_value_without_false_return(self) -> None:
        positions = calculate_car_assets(
            assets=[
                {
                    "asset_id": "car-1",
                    "name": "Ioniq 5",
                    "status": "active",
                    "purchase_date": "2026-01-10",
                }
            ],
            events=[
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-01-10",
                    "event_type": "purchase",
                    "amount_usd": 20000.0,
                },
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-01-12",
                    "event_type": "capitalized_cost",
                    "amount_usd": 2000.0,
                },
            ],
            valuations=[],
            as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
        )

        self.assertEqual(positions[0]["carrying_value_usd"], 22000.0)
        self.assertIsNone(positions[0]["return_pct"])
        self.assertEqual(positions[0]["return_method"], "unavailable")

    def test_car_sale_calculates_profit_roi_fx_and_holding_period(self) -> None:
        positions = calculate_car_assets(
            assets=[
                {
                    "asset_id": "car-1",
                    "name": "Ioniq 5",
                    "status": "active",
                    "purchase_date": "2026-01-10",
                }
            ],
            events=[
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-01-10",
                    "event_type": "purchase",
                    "amount_usd": 20000.0,
                },
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-01-12",
                    "event_type": "capitalized_cost",
                    "amount_usd": 2000.0,
                },
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-03-01",
                    "event_type": "operating_expense",
                    "amount_usd": 1000.0,
                },
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-06-10",
                    "event_type": "sale_proceeds",
                    "amount": 25000.0,
                    "currency": "EUR",
                    "fx_rate_to_usd": 1.1,
                },
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-06-10",
                    "event_type": "selling_cost",
                    "amount_usd": 500.0,
                },
            ],
            valuations=[],
            as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
        )

        sold = positions[0]
        self.assertEqual(sold["carrying_value_usd"], 0.0)
        self.assertEqual(sold["realized_profit_usd"], 5000.0)
        self.assertEqual(sold["all_in_profit_usd"], 4000.0)
        self.assertAlmostEqual(sold["roi_pct"], 22.727, places=3)
        self.assertEqual(sold["holding_days"], 151)

    def test_car_event_without_usd_or_fx_marks_coverage_partial(self) -> None:
        positions = calculate_car_assets(
            assets=[
                {
                    "asset_id": "car-1",
                    "name": "Ioniq 5",
                    "status": "active",
                    "purchase_date": "2026-01-10",
                }
            ],
            events=[
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-01-10",
                    "event_type": "purchase",
                    "amount_usd": 20000.0,
                },
                {
                    "asset_id": "car-1",
                    "occurred_at": "2026-02-01",
                    "event_type": "capitalized_cost",
                    "amount": 1000.0,
                    "currency": "EUR",
                },
            ],
            valuations=[],
            as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
        )

        self.assertEqual(positions[0]["carrying_value_usd"], 20000.0)
        self.assertEqual(positions[0]["coverage"], "partial")

    def test_p2p_position_never_exposes_expected_yield_as_return(self) -> None:
        positions = normalize_p2p_positions(
            [
                {
                    "account": "EstateGuru",
                    "balance_usd": "100",
                    "as_of_date": "2026-05-31",
                    "status": "winding_down",
                },
                {
                    "account": "EstateGuru",
                    "balance_usd": "0",
                    "as_of_date": "2026-06-30",
                    "status": "closed",
                    "closed_at": "2026-06-30",
                },
            ]
        )

        self.assertEqual(positions[0]["balance_usd"], 0.0)
        self.assertEqual(positions[0]["status"], "closed")
        self.assertIsNone(positions[0]["return_pct"])

    def test_closed_p2p_position_requires_closed_at(self) -> None:
        with self.assertRaisesRegex(ValueError, "closed_at"):
            normalize_p2p_positions(
                [
                    {
                        "account": "EstateGuru",
                        "balance_usd": "0",
                        "as_of_date": "2026-06-30",
                        "status": "closed",
                    }
                ]
            )

    def test_p2p_snapshot_ignores_rows_after_as_of_date(self) -> None:
        positions = normalize_p2p_positions(
            [
                {
                    "account": "EstateGuru",
                    "balance_usd": "100",
                    "as_of_date": "2026-06-30",
                    "status": "winding_down",
                },
                {
                    "account": "EstateGuru",
                    "balance_usd": "0",
                    "as_of_date": "2026-07-15",
                    "status": "closed",
                    "closed_at": "2026-07-15",
                },
            ],
            as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
        )

        self.assertEqual(positions[0]["balance_usd"], 100.0)
        self.assertEqual(positions[0]["status"], "winding_down")

    def test_v2_contract_prefers_ledger_and_reconciles_legacy_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.other_assets_dir.mkdir(parents=True)
            ledger.assets_path.write_text(
                "asset_id,name,status,purchase_date,legacy_carrying_value_usd\n"
                "car-1,Ioniq 5,active,2026-01-10,\n",
                encoding="utf-8",
            )
            ledger.asset_events_path.write_text(
                "event_id,asset_id,occurred_at,event_type,amount_usd\n"
                "purchase-1,car-1,2026-01-10,purchase,20000\n"
                "repair-1,car-1,2026-01-12,capitalized_cost,2000\n",
                encoding="utf-8",
            )
            ledger.p2p_dir.mkdir(parents=True)
            ledger.p2p_positions_path.write_text(
                "account,balance_usd,as_of_date,status,closed_at\n"
                "EstateGuru,0,2026-06-30,closed,2026-06-30\n",
                encoding="utf-8",
            )

            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={"BTC": 1.0},
                live_crypto_market_values={"BTC": 70000.0},
                savings_positions=[
                    {"binance": {"USDT": (1000.0, 0.05), "ETH": (2.0, 0.03)}}
                ],
                legacy_other_assets_usd=999.0,
                legacy_p2p_balance_usd=999.0,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
            )

            projected = project_legacy_values(contract)
            self.assertEqual(contract["DATA_CONTRACT_VERSION"], 2)
            self.assertEqual(projected["crypto_value_usd"], 70000.0)
            self.assertEqual(projected["crypto_lending_value_usd"], 1000.0)
            self.assertEqual(projected["p2p_value_usd"], 0.0)
            self.assertEqual(projected["other_assets_value_usd"], 22000.0)
            self.assertIn(
                "income_usd",
                contract["PERFORMANCE_DATA"]["buckets"]["Crypto Lending"],
            )

    def test_legacy_combined_data_can_be_enriched_with_v2_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            combined = {
                "CRYPTO_DATA": {
                    "Token_Quantities": {"BTC": 1.0},
                    "Crypto_Market_Values": {"BTC": 70000.0},
                    "Total_Crypto_Value": 70000.0,
                },
                "FIXED_INCOME_DATA": {
                    "fixed_income_full_data": {
                        "Crypto Landing": {
                            "binance": {"USDT": [1000.0, 0.05]}
                        }
                    },
                    "group_weighted_interest": {
                        "Crypto Landing": [1000.0, 0.05],
                        "p2p_lending": [100.0, 0.0],
                    },
                },
                "OTHER_ASSETS": {"Other Bets": 5000.0},
                "TOTAL_ASSETS": 76100.0,
            }
            start_snapshot = {
                "data": {
                    "CRYPTO_DATA": {
                        "Token_Quantities": {"BTC": 1.0},
                        "Crypto_Market_Values": {"BTC": 60000.0},
                    },
                    "FIXED_INCOME_DATA": {
                        "group_weighted_interest": {
                            "Crypto Landing": [900.0, 0.05]
                        }
                    },
                }
            }

            upgraded = upgrade_legacy_combined_data(
                combined,
                ledger=ledger,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                start_snapshot=start_snapshot,
            )

            self.assertEqual(upgraded["DATA_CONTRACT_VERSION"], 2)
            self.assertEqual(upgraded["POSITION_DATA"]["crypto"][0]["asset"], "BTC")
            self.assertEqual(upgraded["POSITION_DATA"]["p2p"][0]["status"], "legacy")
            self.assertEqual(upgraded["TOTAL_ASSETS"], 76100.0)

    def test_crypto_data_quality_matches_partial_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.save_import_state({"binance": {"coverage": "partial"}})
            ledger.import_events(
                [
                    {
                        "occurred_at": "2026-05-01T12:00:00Z",
                        "source": "binance",
                        "account": "simple_earn",
                        "remote_id": "reward-1",
                        "event_type": "reward",
                        "asset": "BTC",
                        "quantity": 0.001,
                        "usd_value": 60.0,
                    }
                ]
            )
            start_snapshot = {
                "data": {
                    "POSITION_DATA": {
                        "crypto": [
                            {"asset": "BTC", "quantity": 1.0, "value_usd": 60000.0}
                        ]
                    }
                }
            }

            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={"BTC": 1.001},
                live_crypto_market_values={"BTC": 70000.0},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=0,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                start_snapshot=start_snapshot,
            )

            self.assertEqual(
                contract["DATA_QUALITY"]["crypto"]["coverage"], "partial"
            )

    def test_future_only_p2p_ledger_keeps_legacy_balance_for_historical_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.p2p_dir.mkdir(parents=True)
            ledger.p2p_positions_path.write_text(
                "account,balance_usd,as_of_date,status,closed_at\n"
                "EstateGuru,0,2026-07-15,closed,2026-07-15\n",
                encoding="utf-8",
            )

            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={},
                live_crypto_market_values={},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=100,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
            )

            self.assertEqual(contract["POSITION_DATA"]["p2p"][0]["balance_usd"], 100)
            self.assertEqual(contract["POSITION_DATA"]["p2p"][0]["status"], "legacy")

    def test_contract_start_snapshot_uses_latest_v2_boundary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_dir = Path(temp_dir)
            payload = '{"data":{"DATA_CONTRACT_VERSION":2,"POSITION_DATA":{}}}'
            (snapshot_dir / "combined_data_2026-03-31_a.json").write_text(payload)
            (snapshot_dir / "combined_data_2026-04-03_b.json").write_text(payload)
            (snapshot_dir / "combined_data_2026-06-30_c.json").write_text(payload)

            selected = select_contract_start_snapshot(
                snapshot_dir, datetime(2026, 6, 30, tzinfo=UTC).date()
            )

            self.assertEqual(selected["path"].name, "combined_data_2026-04-03_b.json")

    def test_contract_start_snapshot_accepts_legacy_crypto_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_dir = Path(temp_dir)
            (snapshot_dir / "combined_data_2026-04-01_legacy.json").write_text(
                '{"data":{"CRYPTO_DATA":{"Token_Quantities":{"BTC":1},'
                '"Crypto_Market_Values":{"BTC":70000}}}}'
            )

            selected = select_contract_start_snapshot(
                snapshot_dir, datetime(2026, 6, 30, tzinfo=UTC).date()
            )

            self.assertEqual(selected["path"].name, "combined_data_2026-04-01_legacy.json")

    def test_unavailable_live_crypto_uses_stale_snapshot_not_zero(self) -> None:
        snapshot = {
            "data": {
                "POSITION_DATA": {
                    "crypto": [
                        {"asset": "BTC", "quantity": 1.0, "value_usd": 70000.0}
                    ]
                }
            }
        }

        quantities, values, freshness = recover_crypto_positions({}, {}, snapshot)

        self.assertEqual(quantities, {"BTC": 1.0})
        self.assertEqual(values, {"BTC": 70000.0})
        self.assertEqual(freshness, "stale")

    def test_missing_live_asset_price_uses_snapshot_value_and_marks_partial(self) -> None:
        snapshot = {
            "data": {
                "POSITION_DATA": {
                    "crypto": [
                        {"asset": "BTC", "quantity": 1.0, "value_usd": 70000.0},
                        {"asset": "ETH", "quantity": 2.0, "value_usd": 7000.0},
                    ]
                }
            }
        }

        quantities, values, freshness = recover_crypto_positions(
            {"BTC": 1.1, "ETH": 2.0},
            {"BTC": 77000.0},
            snapshot,
        )

        self.assertEqual(quantities, {"BTC": 1.1, "ETH": 2.0})
        self.assertEqual(values, {"BTC": 77000.0, "ETH": 7000.0})
        self.assertEqual(freshness, "partial")

    def test_legacy_crypto_snapshot_can_supply_transition_fallback(self) -> None:
        snapshot = {
            "data": {
                "CRYPTO_DATA": {
                    "Token_Quantities": {"BTC": 1.0},
                    "Crypto_Market_Values": {"BTC": 70000.0},
                    "Total_Crypto_Value": 70000.0,
                }
            }
        }

        quantities, values, freshness = recover_crypto_positions({}, {}, snapshot)

        self.assertEqual(quantities, {"BTC": 1.0})
        self.assertEqual(values, {"BTC": 70000.0})
        self.assertEqual(freshness, "stale")

    def test_failed_balance_source_recovers_missing_exchange_holdings(self) -> None:
        snapshot = {
            "data": {
                "POSITION_DATA": {
                    "crypto": [
                        {"asset": "BTC", "quantity": 1.0, "value_usd": 70000.0},
                        {"asset": "ETH", "quantity": 2.0, "value_usd": 7000.0},
                    ]
                }
            }
        }

        quantities, values, freshness = recover_crypto_positions(
            {"BTC": 1.1},
            {"BTC": 77000.0},
            snapshot,
            balance_sources={"BinanceClient": "ok", "WhiteBit": "failed"},
        )

        # A failed source must never be labeled "live" and its missing
        # holdings must be recovered from the snapshot instead of dropped.
        self.assertEqual(freshness, "partial")
        self.assertEqual(quantities, {"BTC": 1.1, "ETH": 2.0})
        self.assertEqual(values, {"BTC": 77000.0, "ETH": 7000.0})

    def test_mid_quarter_performance_period_caps_at_as_of_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.import_events(
                [
                    {
                        "occurred_at": "2026-07-08T12:00:00Z",
                        "source": "binance",
                        "account": "spot",
                        "remote_id": "buy-1",
                        "event_type": "buy",
                        "asset": "BTC",
                        "quantity": 0.05,
                        "usd_value": 3500.0,
                    }
                ]
            )
            start_snapshot = {
                "data": {
                    "POSITION_DATA": {
                        "crypto": [
                            {"asset": "BTC", "quantity": 1.0, "value_usd": 60000.0}
                        ]
                    }
                }
            }

            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={"BTC": 1.05},
                live_crypto_market_values={"BTC": 80850.0},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=0,
                as_of_date=datetime(2026, 7, 15, tzinfo=UTC).date(),
                start_snapshot=start_snapshot,
                crypto_freshness="live",
                crypto_balance_sources={"BinanceClient": "ok"},
            )

            quarter = contract["ACTIVITY_DATA"]["quarters"]["2026-Q3"]
            self.assertEqual(quarter["period_start"], "2026-07-01")
            # A mid-quarter run must not report the future calendar quarter
            # end as the measurement end of its weighted return.
            self.assertEqual(quarter["period_end"], "2026-07-15")
            bucket = contract["PERFORMANCE_DATA"]["buckets"]["Crypto Coins"]
            # Modified Dietz over the elapsed period only (flow on Jul 8 is
            # weighted ~0.5): 17350 / (60000 + 3500 * 0.5) ~= 28.097%.
            # Against the uncapped quarter end the weight would be ~7.5/92
            # days and the return ~27.45%.
            self.assertEqual(bucket["return_method"], "modified_dietz")
            self.assertAlmostEqual(bucket["return_pct"], 28.0972, places=3)
            self.assertEqual(
                contract["DATA_QUALITY"]["crypto"]["balance_sources"],
                {"BinanceClient": "ok"},
            )

    def test_contract_start_snapshot_rejects_snapshot_outside_boundary_window(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_dir = Path(temp_dir)
            payload = '{"data":{"DATA_CONTRACT_VERSION":2,"POSITION_DATA":{}}}'
            (snapshot_dir / "combined_data_2026-03-20_old.json").write_text(payload)
            (snapshot_dir / "combined_data_2026-08-01_new.json").write_text(payload)

            self.assertIsNone(
                select_contract_start_snapshot(
                    snapshot_dir, datetime(2026, 6, 30, tzinfo=UTC).date()
                )
            )


if __name__ == "__main__":
    unittest.main()
