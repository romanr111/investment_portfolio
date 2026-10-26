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
    classify_internal_transfer_legs,
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


    def test_legacy_lending_boundary_ignores_non_stablecoin_earn(self) -> None:
        # v1 "Crypto Landing" totals mix stablecoin earn with volatile
        # holdings; using that total as the v2 stablecoin start principal
        # manufactures a phantom period return.
        stablecoin_snapshot = {
            "data": {
                "FIXED_INCOME_DATA": {
                    "group_weighted_interest": {"Crypto Landing": (160, 0.05)},
                    "fixed_income_full_data": {
                        "Crypto Landing": {
                            "whitebit": {"ETH": [30, 0.0], "USDT": [100, 0.05]},
                            "binance": {"USDC": [30, 0.04]},
                        }
                    },
                }
            }
        }
        volatile_only_snapshot = {
            "data": {
                "FIXED_INCOME_DATA": {
                    "group_weighted_interest": {"Crypto Landing": (30, 0.05)},
                    "fixed_income_full_data": {
                        "Crypto Landing": {"whitebit": {"ETH": [30, 0.0]}}
                    },
                }
            }
        }
        savings_positions = [
            {"whitebit": {"USDT": (100.0, 0.05)}},
            {"binance": {"USDC": (30.0, 0.04)}},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.save_import_state(
                {
                    "whitebit": {
                        "lending": {"coverage": "complete"},
                        "coverage": "complete",
                    },
                    "binance": {
                        "lending": {"coverage": "complete"},
                        "coverage": "complete",
                    },
                }
            )
            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={},
                live_crypto_market_values={},
                savings_positions=list(savings_positions),
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=0,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                start_snapshot=stablecoin_snapshot,
                crypto_freshness="snapshot",
            )
            lending = contract["PERFORMANCE_DATA"]["buckets"]["Crypto Lending"]
            # Start principal counts only USDT/USDC (130, not 160): with the
            # legacy mixed total the same quarter would report ~-18.75%.
            self.assertEqual(lending["return_method"], "modified_dietz")
            self.assertAlmostEqual(lending["return_pct"], 0.0, places=6)
            self.assertEqual(lending["data_quality"], "complete")

            contract = build_portfolio_contract(
                ledger=PortfolioLedger(Path(temp_dir)),
                live_crypto_quantities={},
                live_crypto_market_values={},
                savings_positions=list(savings_positions),
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=0,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                start_snapshot=volatile_only_snapshot,
                crypto_freshness="snapshot",
            )
            lending = contract["PERFORMANCE_DATA"]["buckets"]["Crypto Lending"]
            # No stablecoin assets in the boundary snapshot: coverage must
            # downgrade to partial instead of claiming a real return.
            self.assertIsNone(lending["return_pct"])
            self.assertEqual(lending["data_quality"], "partial")

    def test_fee_bearing_transfer_legs_match_on_net_quantity(self) -> None:
        # Exchanges deduct network fees inside the withdrawal amount, so the
        # received quantity is the debited quantity minus the leg's fee. The
        # legs must still match, and the fee must be counted exactly once.
        events = classify_internal_transfer_legs(
            [
                {
                    "event_id": "wd-1",
                    "occurred_at": "2026-05-01T12:00:00Z",
                    "source": "okx",
                    "account": "funding",
                    "remote_id": "wd-1",
                    "event_type": "withdrawal",
                    "asset": "USDT",
                    "quantity": 1.0,
                    "usd_value": 1.0,
                    "fee_asset": "USDT",
                    "fee_quantity": 0.001,
                    "fee_usd": 0.001,
                    "transfer_id": "on-chain-1",
                },
                {
                    "event_id": "dp-1",
                    "occurred_at": "2026-05-01T13:00:00Z",
                    "source": "binance",
                    "account": "spot",
                    "remote_id": "dp-1",
                    "event_type": "deposit",
                    "asset": "USDT",
                    "quantity": 0.999,
                    "usd_value": 0.999,
                    "fee_asset": None,
                    "fee_quantity": 0.0,
                    "fee_usd": None,
                    "transfer_id": "on-chain-1",
                },
            ]
        )

        self.assertEqual(events[0]["event_type"], "internal_transfer")
        self.assertEqual(events[1]["event_type"], "internal_transfer")

        rows = aggregate_crypto_quarter(
            events=events,
            start_quantities={"USDT": 1.0},
            end_quantities={"USDT": 0.999},
            start_values_usd={"USDT": 1.0},
            end_values_usd={"USDT": 0.999},
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
            # Default $100 materiality would skip these $1 positions.
            materiality_usd=0.0,
        )

        self.assertEqual(rows[0]["external_transfers_quantity"], 0.0)
        # The network fee leaves the portfolio, so it surfaces once as fees.
        self.assertAlmostEqual(rows[0]["fees_quantity"], 0.001, places=9)
        self.assertAlmostEqual(rows[0]["net_change_quantity"], -0.001, places=9)
        self.assertEqual(rows[0]["unexplained_quantity"], 0.0)
        self.assertEqual(rows[0]["coverage"], "complete")

    def test_fee_bearing_legs_stay_external_when_quantities_disagree(self) -> None:
        events = classify_internal_transfer_legs(
            [
                {
                    "event_id": "wd-1",
                    "occurred_at": "2026-05-01T12:00:00Z",
                    "source": "okx",
                    "account": "funding",
                    "remote_id": "wd-1",
                    "event_type": "withdrawal",
                    "asset": "ETH",
                    "quantity": 1.0,
                    "fee_asset": "ETH",
                    "fee_quantity": 0.5,
                    "transfer_id": "on-chain-2",
                },
                {
                    "event_id": "dp-1",
                    "occurred_at": "2026-05-01T13:00:00Z",
                    "source": "binance",
                    "account": "spot",
                    "remote_id": "dp-1",
                    "event_type": "deposit",
                    "asset": "ETH",
                    "quantity": 0.999,
                    "fee_asset": None,
                    "fee_quantity": 0.0,
                    "transfer_id": "on-chain-2",
                },
            ]
        )

        # Net of its 0.5 fee the withdrawal moved 0.5, not 0.999: the legs
        # describe different quantities and must stay external.
        self.assertEqual(events[0]["event_type"], "withdrawal")
        self.assertEqual(events[1]["event_type"], "deposit")

    def test_four_decimal_rounding_does_not_break_reconciliation(self) -> None:
        # Positions round to 4 decimals on every pass, so a 0.000054321 token
        # reward can round the end balance up by a full 0.0001. That dust must
        # not fail reconciliation, which previously required 1e-8 precision.
        rows = aggregate_crypto_quarter(
            events=[
                {
                    "event_id": "reward-1",
                    "occurred_at": "2026-05-01T12:00:00Z",
                    "source": "binance",
                    "account": "spot",
                    "remote_id": "reward-1",
                    "event_type": "reward",
                    "asset": "ETH",
                    "quantity": 0.000054321,
                    "usd_value": 0.1,
                }
            ],
            start_quantities={"ETH": 1.0},
            end_quantities={"ETH": 1.0001},
            start_values_usd={"ETH": 3000.0},
            end_values_usd={"ETH": 3000.3},
            period_start=datetime(2026, 4, 1, tzinfo=UTC),
            period_end=datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
        )

        self.assertAlmostEqual(rows[0]["rewards_quantity"], 0.000054321, places=9)
        self.assertEqual(rows[0]["unexplained_quantity"], 0.0)
        self.assertEqual(rows[0]["coverage"], "complete")

    def test_events_cursor_coverage_gates_activity_rows_in_both_directions(
        self,
    ) -> None:
        # A source can import events completely while lending backfill is
        # still partial (or the reverse). The top-level "coverage" mixes both
        # capabilities, so activity rows must follow the events cursor.
        buy_event = [
            {
                "occurred_at": "2026-05-01T12:00:00Z",
                "source": "okx",
                "account": "funding",
                "remote_id": "buy-1",
                "event_type": "buy",
                "asset": "BTC",
                "quantity": 0.01,
                "usd_value": 50.0,
            }
        ]
        start_snapshot = {
            "data": {
                "POSITION_DATA": {
                    "crypto": [
                        {"asset": "BTC", "quantity": 1.0, "value_usd": 5000.0}
                    ]
                }
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = PortfolioLedger(Path(temp_dir))
            ledger.import_events(buy_event)

            ledger.save_import_state(
                {
                    "okx": {
                        "events": {"coverage": "partial"},
                        "coverage": "complete",
                    }
                }
            )
            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={"BTC": 1.01},
                live_crypto_market_values={"BTC": 5100.0},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=0,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                start_snapshot=start_snapshot,
                crypto_freshness="live",
            )
            row = contract["ACTIVITY_DATA"]["quarters"]["2026-Q2"]["crypto"][0]
            self.assertEqual(row["coverage"], "partial")

            ledger.save_import_state(
                {
                    "okx": {
                        "events": {"coverage": "complete"},
                        "lending": {"coverage": "partial"},
                        "coverage": "partial",
                    }
                }
            )
            contract = build_portfolio_contract(
                ledger=ledger,
                live_crypto_quantities={"BTC": 1.01},
                live_crypto_market_values={"BTC": 5100.0},
                savings_positions=[],
                legacy_other_assets_usd=0,
                legacy_p2p_balance_usd=0,
                as_of_date=datetime(2026, 6, 30, tzinfo=UTC).date(),
                start_snapshot=start_snapshot,
                crypto_freshness="live",
            )
            row = contract["ACTIVITY_DATA"]["quarters"]["2026-Q2"]["crypto"][0]
            self.assertEqual(row["coverage"], "complete")


if __name__ == "__main__":
    unittest.main()
