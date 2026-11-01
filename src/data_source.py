from typing import Dict, Any
import copy
from decimal import Decimal
import logging
import json
import time
import traceback
from pathlib import Path
from datetime import datetime

from data.filters_constants import IB_BONDS_KEY
from src.brokers.ib import InteractiveBrokers
from src.brokers.ib_dividends import IBDividends
from src.brokers.data_fetchers.index_performance_fetcher import IndexPerformanceFetcher
from src.cash_fixed_income.cash_summary import CashPortfolio
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio
from src.crypto.crypto_tokens import CryptoEndpoint
from src.allocation_calculator import AllocationCalculator
from src.portfolio_ledger.contract import (
    build_portfolio_contract,
    project_legacy_values,
    recover_crypto_positions,
    recover_cash_equivalents,
    select_contract_start_snapshot,
)
from src.portfolio_ledger.storage import PortfolioLedger
from src.portfolio_ledger.sync import build_activity_sources, sync_crypto_sources
from analytics.car_category import load_block as load_car_category_block
from analytics.car_risk_proxies import load_block as load_car_proxies_block
from analytics.holy_grail_data import enrich_combined_data
from data.assets_data import OTHER_BETS

# Set up logging
logger = logging.getLogger(__name__)

FINANCIAL_FREEDOM_GOAL = 500000
COMBINED_DATA_JSON_PATH = Path("data/final_data.json")
PORTFOLIO_LEDGER_PATH = Path("data/portfolio_ledger")


def _read_previous_combined_data(path):
    """Read the existing saved snapshot before it is replaced, if usable."""
    try:
        with path.open('rb') as handle:
            raw = handle.read(20_000_001)
        if len(raw) > 20_000_000:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeDecodeError):
        return None


class DataSource:
    def __init__(self, *, refresh_holy_grail_history: bool = True):
        self._refresh_holy_grail_history = refresh_holy_grail_history
        try:
            start_time = time.time()
            self._data_timestamp = time.time()
            self._initialize_data_sources()
            self._prepare_portfolio_data()
            self._calculate_stock_dividends()
            self._setup_fixed_income()
            self._setup_cash()
            self._sync_crypto_activity()
            self._prepare_portfolio_contract()
            self._fetch_index_performance()
            self.total_assets = self.calculate_total_assets()
            self.ff_progress = self.calculate_ff_goal_progress()
            logger.info(
                f"DataSource initialized in {time.time() - start_time:.2f} seconds"
            )
            logger.info(
                f"Data timestamp: {datetime.fromtimestamp(self._data_timestamp).isoformat()}"
            )
        except Exception as e:
            logger.error(f"Error in DataSource initialization: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def force_refresh(self) -> Dict:
        """Force refresh all data sources and return fresh data.

        This method re-initializes all connections and fetches fresh data from APIs.
        Use this when you want to ensure absolutely current data.
        """
        logger.info("Forcing data refresh - reinitializing all data sources")
        start_time = time.time()

        # Re-initialize everything with fresh data
        self._data_timestamp = time.time()
        self._initialize_data_sources()
        self._prepare_portfolio_data()
        self._calculate_stock_dividends()
        self._setup_fixed_income()
        self._setup_cash()
        self._sync_crypto_activity()
        self._prepare_portfolio_contract()
        self._fetch_index_performance()
        self.total_assets = self.calculate_total_assets()
        self.ff_progress = self.calculate_ff_goal_progress()

        logger.info(
            f"Force refresh completed in {time.time() - start_time:.2f} seconds"
        )
        return self.get_combined_data(force_refresh=True)

    def get_data(self) -> Dict:
        """
        Retrieve complete portfolio data with sector allocations and analytics.

        This is the main interface method that provides a comprehensive view of the entire
        investment portfolio. It aggregates data from multiple sources including Interactive
        Brokers, cryptocurrency exchanges, fixed income instruments, and cash positions.

        Returns:
            Dict: A comprehensive portfolio data dictionary containing:
                - IB_DATA: Interactive Brokers portfolio positions, values, and categories
                - IB_PERFORMANCE: IBKR YTD TWR from Flex Web Service Activity Statement
                - INDEX_PERFORMANCE: YTD performance for major market indices (S&P 500, NASDAQ, Euro Stoxx 50, Hang Seng)
                - CRYPTO_DATA: Cryptocurrency holdings, market values, and token quantities
                - FIXED_INCOME_DATA: Bonds, dividends, and income-generating assets
                - CASH_DATA: Cash balances across different accounts and platforms
                - TOTAL_ASSETS: Sum of all portfolio assets
                - FIN_FREEDOM_GOAL_PROGRESS: Progress toward financial freedom goal
                - ALLOCATIONS: Sector-based portfolio allocation analysis
        """
        data = self.get_combined_data()
        calculator = AllocationCalculator(data)
        data["ALLOCATIONS"] = calculator.get_sorted_sector_allocations()
        print(f"\nFull portfolio data returned by DataSource: {data}\n")
        return data

    def _initialize_data_sources(self) -> None:
        """Initialize primary data source connections."""
        try:
            self.ib = InteractiveBrokers()
            self.crypto = CryptoEndpoint()
            self.crypto_savings = self.crypto.all_crypto_savings
            self.index_performance_fetcher = IndexPerformanceFetcher()
            logger.info(f"Crypto savings {self.crypto_savings}")
        except Exception as e:
            logger.error(f"Error in _initialize_data_sources: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def _prepare_portfolio_data(self) -> None:
        """Prepare Interactive Brokers portfolio and dividend data."""
        try:
            self.ib_data = self.ib.get_full_porfolio_data()
            self.ib_bonds = self.ib_data.get(IB_BONDS_KEY, {})
            self.ib_div = IBDividends(self.ib_data)
            self._process_dividend_data()
        except Exception as e:
            logger.error(f"Error in _prepare_portfolio_data: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def _process_dividend_data(self) -> None:
        """Process dividend data from Interactive Brokers."""
        (
            self.monthly_dividends,
            self.yearly_dividends,
            self.stock_yearly_div,
            self.dividend_details,
        ) = self.ib_div.get_my_total_monthly_and_yearly_divs()

    def _calculate_stock_dividends(self) -> None:
        """Calculate stock dividend yields."""
        self.ib_stocks_value = self.ib_data["Total Stocks Value"]
        self.stocks_yearly_dividend_yield = round(
            (self.stock_yearly_div / self.ib_stocks_value) * 100, 2
        )

    def _setup_fixed_income(self) -> None:
        """Initialize and process fixed income data."""
        self.fixed_income_endpoint = FixedIncomePortfolio(
            self.ib_bonds, self.dividend_details, self.crypto_savings
        )
        self.fi_data = self.fixed_income_endpoint.get_combined_fixed_income_data()
        self._update_fixed_income_with_stocks()

    def _setup_cash(self) -> None:
        """Initialize cash."""
        self.cash = CashPortfolio(
            self.ib_data["Net_cash"],
            self.crypto.free_cash,
        )

    def _prepare_portfolio_contract(self) -> None:
        if not hasattr(self, "ledger"):
            self.ledger = PortfolioLedger(PORTFOLIO_LEDGER_PATH)
        as_of_date = datetime.now().date()
        start_snapshot_result = select_contract_start_snapshot(
            Path("data/snapshots"), as_of_date
        )
        latest_snapshot = None
        latest_snapshot_path = Path("data/snapshots/combined_data_latest.json")
        if latest_snapshot_path.exists():
            try:
                with latest_snapshot_path.open(encoding="utf-8") as handle:
                    latest_snapshot = json.load(handle)
            except (OSError, json.JSONDecodeError) as error:
                logger.warning("Could not read latest combined_data snapshot: %s", error)
        balance_sources = dict(getattr(self.crypto, "balance_source_status", {}) or {})
        crypto_quantities, crypto_values, crypto_freshness = recover_crypto_positions(
            self.crypto.quantities,
            self.crypto.crypto_market_values,
            latest_snapshot,
            balance_sources=balance_sources,
        )
        live_cash = dict(getattr(self.crypto, "cash_equivalent_values", {}) or {})
        recovered_cash = recover_cash_equivalents(
            live_cash, latest_snapshot, balance_sources=balance_sources
        )
        recovered_amount = sum(recovered_cash.values()) - sum(live_cash.values())
        if recovered_amount > 0:
            self.cash.crypto_cash += Decimal(str(recovered_amount))
        self.crypto.cash_equivalent_values = recovered_cash
        legacy_p2p = self.fi_data.get("group_weighted_interest", {}).get(
            "p2p_lending", (0, 0)
        )
        if isinstance(legacy_p2p, (list, tuple)):
            legacy_p2p = legacy_p2p[0] if legacy_p2p else 0
        self.portfolio_contract = build_portfolio_contract(
            ledger=self.ledger,
            live_crypto_quantities=crypto_quantities,
            live_crypto_market_values=crypto_values,
            savings_positions=self.crypto_savings,
            legacy_other_assets_usd=float(OTHER_BETS),
            legacy_p2p_balance_usd=float(legacy_p2p or 0),
            as_of_date=as_of_date,
            start_snapshot=(
                start_snapshot_result["data"] if start_snapshot_result else None
            ),
            crypto_freshness=crypto_freshness,
            crypto_balance_sources=balance_sources,
        )

        if any(status not in (None, "", "ok") for status in balance_sources.values()):
            self.portfolio_contract["DATA_QUALITY"]["cash"] = {
                "coverage": "partial", "freshness": "snapshot_fallback"
            }

    def _sync_crypto_activity(self) -> None:
        self.ledger = PortfolioLedger(PORTFOLIO_LEDGER_PATH)
        sources = build_activity_sources(
            self.crypto.brokers,
            self.ledger.load_sources_config(),
        )
        if not sources:
            self.crypto_sync_results = {}
            return
        today = datetime.now().date()
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start_at = datetime(today.year, quarter_start_month, 1).astimezone()
        end_at = datetime.now().astimezone()
        self.crypto_sync_results = sync_crypto_sources(
            self.ledger,
            sources,
            start_at,
            end_at,
        )

    def _fetch_index_performance(self) -> None:
        """Fetch index performance data for major market indices."""
        try:
            logger.info("Fetching index performance data...")
            self.index_performance_data = (
                self.index_performance_fetcher.get_all_indices_performance()
            )

            # Log successful fetches
            successful_count = sum(
                1
                for data in self.index_performance_data.values()
                if data.get("success", False)
            )
            total_count = len(self.index_performance_data)

            logger.info(
                f"Index performance fetched: {successful_count}/{total_count} indices successful"
            )

            # Log individual results
            for index_key, data in self.index_performance_data.items():
                if data.get("success") and data.get("rate_of_return_pct") is not None:
                    logger.info(f"{data['name']}: {data['rate_of_return_pct']}% YTD")
                else:
                    logger.warning(
                        f"{data['name']}: Failed to fetch - {data.get('error', 'Unknown error')}"
                    )

        except Exception as e:
            logger.error(f"Error fetching index performance: {str(e)}")
            self.index_performance_data = {}

    def _update_fixed_income_with_stocks(self) -> None:
        """Update fixed income data with stock-related calculations."""
        self._add_stock_principal_data()
        self._calculate_total_earnings()

    def _add_stock_principal_data(self) -> None:
        """Add stock principal and interest data to fixed income."""
        self.fi_data["stocks_principal_and_interest"] = {
            "total_principal": self.ib_stocks_value,
            "weighted_interest": self.stocks_yearly_dividend_yield,
        }
        self.fi_data["stocks_monthly"] = int(self.stock_yearly_div / 12)
        self.fi_data["stocks_yearly"] = int(self.stock_yearly_div)

    def _calculate_total_earnings(self) -> None:
        """Calculate total monthly and yearly earnings."""
        monthly = (
            self.fi_data["monthly_earnings_fixed_income"]
            + self.fi_data["stocks_monthly"]
        )
        yearly = (
            self.fi_data["yearly_earnings_fixed_income"] + self.fi_data["stocks_yearly"]
        )

        self.fi_data.update(
            {"total_monthly": int(monthly), "total_yearly": int(yearly)}
        )

    def calculate_total_assets(self) -> int:
        """Calculate total portfolio assets value."""
        # IB_Portfolio_Value already includes Net_cash, so exclude it from the
        # standalone cash total to avoid counting the IB cash position twice.
        non_ib_cash_total = self.cash.total_cash - self.cash.ib_cash

        projected = (
            project_legacy_values(self.portfolio_contract)
            if hasattr(self, "portfolio_contract")
            else {
                "crypto_value_usd": self.crypto.get_total_crypto_value(),
                "crypto_lending_value_usd": self.fi_data[
                    "group_weighted_interest"
                ]["Crypto Landing"][0],
                "p2p_value_usd": self.fi_data["group_weighted_interest"][
                    "p2p_lending"
                ][0],
                "other_assets_value_usd": float(OTHER_BETS),
            }
        )
        asset_values = [
            self.ib_data["IB_Portfolio_Value"],
            projected["crypto_value_usd"],
            projected["crypto_lending_value_usd"],
            projected["p2p_value_usd"],
            float(non_ib_cash_total),
            projected["other_assets_value_usd"],
        ]
        total = int(sum(asset_values))
        return total

    def calculate_ff_goal_progress(self):
        current = self.total_assets
        goal_progress = round((current / FINANCIAL_FREEDOM_GOAL) * 100, 2)
        progress = str(goal_progress) + "%"
        return progress

    def get_combined_data(self, force_refresh: bool = False) -> Dict:
        """Get combined portfolio data including all assets and calculations.

        Args:
            force_refresh: If True, forces fresh data fetch even if recently updated

        Returns:
            Dict: Combined portfolio data with live values from APIs and constants
        """
        current_time = time.time()
        data_age_seconds = current_time - self._data_timestamp

        # Log data age for transparency
        logger.info(
            f"Data age: {data_age_seconds:.1f} seconds ({data_age_seconds/60:.1f} minutes)"
        )

        # Validate data freshness (warn if data is older than 5 minutes)
        if data_age_seconds > 300:  # 5 minutes
            logger.warning(
                f"Data is {data_age_seconds/60:.1f} minutes old. Consider refreshing."
            )

        asset_allocation = self._calculate_asset_allocation()

        contract = getattr(self, "portfolio_contract", {})
        projected = (
            project_legacy_values(contract)
            if contract
            else {
                "crypto_value_usd": self.crypto.get_total_crypto_value(),
                "crypto_lending_value_usd": self.fi_data.get(
                    "group_weighted_interest", {}
                ).get("Crypto Landing", (0,))[0],
                "p2p_value_usd": self.fi_data.get("group_weighted_interest", {}).get(
                    "p2p_lending", (0,)
                )[0],
                "other_assets_value_usd": float(OTHER_BETS),
            }
        )
        fixed_income_data = copy.deepcopy(self.fi_data)
        group_interest = fixed_income_data.setdefault("group_weighted_interest", {})
        legacy_crypto_rate = group_interest.get("Crypto Landing", (0, 0))
        legacy_crypto_rate = (
            legacy_crypto_rate[1]
            if isinstance(legacy_crypto_rate, (list, tuple))
            and len(legacy_crypto_rate) > 1
            else 0
        )
        group_interest["Crypto Landing"] = (
            projected["crypto_lending_value_usd"],
            legacy_crypto_rate,
        )
        legacy_p2p_rate = group_interest.get("p2p_lending", (0, 0))
        legacy_p2p_rate = (
            legacy_p2p_rate[1]
            if isinstance(legacy_p2p_rate, (list, tuple))
            and len(legacy_p2p_rate) > 1
            else 0
        )
        group_interest["p2p_lending"] = (
            projected["p2p_value_usd"],
            legacy_p2p_rate,
        )
        canonical_crypto_positions = contract.get("POSITION_DATA", {}).get("crypto", [])
        canonical_crypto_values = {
            position["asset"]: position.get("value_usd", 0.0)
            for position in canonical_crypto_positions
        }
        canonical_crypto_quantities = {
            position["asset"]: position.get("quantity", 0.0)
            for position in canonical_crypto_positions
        }

        data = {
            "IB_DATA": self.ib_data,
            "ENHANCED_STOCKS": (
                self.ib.get_stock_positions_analytics()
                if callable(getattr(self.ib, "get_stock_positions_analytics", None))
                else {}
            ),
            "IB_PERFORMANCE": getattr(self.ib, "performance_ytd", {}),
            "INDEX_PERFORMANCE": getattr(self, "index_performance_data", {}),
            "CRYPTO_DATA": {
                "Total_Crypto_Value": projected["crypto_value_usd"],
                "Crypto_Market_Values": canonical_crypto_values,
                "Token_Quantities": canonical_crypto_quantities,
            },
            "FIXED_INCOME_DATA": fixed_income_data,
            "CASH_DATA": {
                "Total": self.cash.total_cash,
                "Breakdown": self.cash.as_dict(),
                "Cash_Equivalents": dict(getattr(self.crypto, "cash_equivalent_values", {}) or {}),
            },
            "OTHER_ASSETS": {
                "Other Bets": projected["other_assets_value_usd"],
            },
            "TOTAL_ASSETS": self.total_assets,
            "FINANCIAL_FREEDOM_GOAL_TARGET": FINANCIAL_FREEDOM_GOAL,
            "FIN_FREEDOM_GOAL_PROGRESS": self.ff_progress,
            "ASSET_ALLOCATION": asset_allocation,
            "DATA_METADATA": {
                "timestamp": self._data_timestamp,
                "age_seconds": data_age_seconds,
                "source": "live_api_calls",
                "last_updated": datetime.fromtimestamp(
                    self._data_timestamp
                ).isoformat(),
            },
        }
        data.update(contract)
        previous = _read_previous_combined_data(COMBINED_DATA_JSON_PATH)
        data = enrich_combined_data(
            data,
            as_of_date=datetime.fromtimestamp(self._data_timestamp).date().isoformat(),
            allow_network=getattr(self, "_refresh_holy_grail_history", False),
            previous_combined_data=previous,
            car_category=load_car_category_block(),
            car_proxies=load_car_proxies_block(),
        )
        self._save_combined_data_to_json(data)
        return data

    def _calculate_asset_allocation(self) -> Dict[str, Any]:
        """Calculate asset allocation data with values and percentages."""
        projected = (
            project_legacy_values(self.portfolio_contract)
            if hasattr(self, "portfolio_contract")
            else {
                "crypto_value_usd": self.crypto.get_total_crypto_value(),
                "crypto_lending_value_usd": self.fi_data.get(
                    "group_weighted_interest", {}
                ).get("Crypto Landing", (0,))[0],
                "p2p_value_usd": self.fi_data.get("group_weighted_interest", {}).get(
                    "p2p_lending", (0,)
                )[0],
                "other_assets_value_usd": float(OTHER_BETS),
            }
        )
        allocation_fixed_income = copy.deepcopy(self.fi_data)
        allocation_group_interest = allocation_fixed_income.setdefault(
            "group_weighted_interest", {}
        )
        allocation_group_interest["Crypto Landing"] = (
            projected["crypto_lending_value_usd"],
            0.0,
        )
        allocation_group_interest["p2p_lending"] = (
            projected["p2p_value_usd"],
            0.0,
        )
        calculator = AllocationCalculator(
            {
                "IB_DATA": self.ib_data,
                "CRYPTO_DATA": {
                    "Total_Crypto_Value": projected["crypto_value_usd"],
                },
                "FIXED_INCOME_DATA": allocation_fixed_income,
                "CASH_DATA": {
                    "Total": self.cash.total_cash,
                },
                "OTHER_ASSETS": {
                    "Other Bets": projected["other_assets_value_usd"],
                },
                "TOTAL_ASSETS": self.total_assets,
            }
        )
        allocation_data = calculator.get_sorted_sector_allocations()

        # Build asset allocation structure with values and percentages
        asset_allocation = {"net_worth": self.total_assets, "allocations": {}}

        # Calculate actual values for each category
        def _to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def _sum_dict_values(values):
            if not isinstance(values, dict):
                return 0.0
            return sum(_to_float(v) for v in values.values())

        actual_values = {
            "Bonds": _sum_dict_values(self.ib_data.get("Bonds", {})),
            "Stocks": _to_float(self.ib_data.get("Total Stocks Value", 0)),
            "Commodities": _sum_dict_values(self.ib_data.get("Commodities", {})),
            "Precious Metals": _sum_dict_values(
                self.ib_data.get("Precious Metals", {})
            ),
            "Crypto Coins": _to_float(
                projected["crypto_value_usd"]
            ),
            "Crypto Lending": _to_float(projected["crypto_lending_value_usd"]),
            "P2P Lending": _to_float(projected["p2p_value_usd"]),
            "REIT": _sum_dict_values(self.ib_data.get("REIT", {})),
            "Cash": _to_float(self.cash.total_cash),
            "Other Bets": _to_float(
                projected["other_assets_value_usd"]
            ),
        }

        # Build allocations with both value and percentage
        allocation_breakdown = allocation_data.get("allocation_breakdown", {})
        for category, percentage in allocation_breakdown.items():
            if category in actual_values and actual_values[category] > 0:
                asset_allocation["allocations"][category] = {
                    "value": actual_values[category],
                    "percentage": percentage,
                }

        return asset_allocation

    def _save_combined_data_to_json(self, data: Dict) -> None:
        COMBINED_DATA_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with COMBINED_DATA_JSON_PATH.open("w", encoding="utf-8") as json_file:
            json.dump(data, json_file, indent=2, ensure_ascii=False, default=str)
        logger.info("Combined data exported to JSON: %s", COMBINED_DATA_JSON_PATH)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting DataSource test run")
    data_source = DataSource()
    portfolio_data = data_source.get_data()
    print()
    print(portfolio_data)
    print()
    logger.info("DataSource test run completed")
