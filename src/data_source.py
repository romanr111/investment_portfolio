from typing import Dict
import logging
import json
import time
import traceback
from pathlib import Path

from data.filters_constants import IB_BONDS_KEY
from src.brokers.ib import InteractiveBrokers
from src.brokers.ib_dividends import IBDividends
from src.cash_fixed_income.cash_summary import CashPortfolio
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio
from src.crypto.crypto_tokens import CryptoEndpoint
from src.allocation_calculator import AllocationCalculator
from data.assets_data import OTHER_BETS

# Set up logging
logger = logging.getLogger(__name__)

FINANCIAL_FREEDOM_GOAL = 500000
COMBINED_DATA_JSON_PATH = Path("data/combined_data.json")

#
# cd Documents/Development/Portfolio/clientportal.gw  && arch -x86_64 /bin/zsh bin/run.sh root/conf.yaml
#


class DataSource:
    def __init__(self):
        try:
            start_time = time.time()
            self._initialize_data_sources()
            self._prepare_portfolio_data()
            self._calculate_stock_dividends()
            self._setup_fixed_income()
            self._setup_cash()
            self.total_assets = self.calculate_total_assets()
            self.ff_progress = self.calculate_ff_goal_progress()
            logger.info(
                f"DataSource initialized in {time.time() - start_time:.2f} seconds"
            )
        except Exception as e:
            logger.error(f"Error in DataSource initialization: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise

    def get_data(self) -> Dict:
        """
        Retrieve complete portfolio data with sector allocations and analytics.

        This is the main interface method that provides a comprehensive view of the entire
        investment portfolio. It aggregates data from multiple sources including Interactive
        Brokers, cryptocurrency exchanges, fixed income instruments, and cash positions.

        Returns:
            Dict: A comprehensive portfolio data dictionary containing:
                - IB_DATA: Interactive Brokers portfolio positions, values, and categories
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
        asset_values = [
            self.ib_data["IB_Portfolio_Value"],
            self.crypto.get_total_crypto_value(),
            self.fi_data["group_weighted_interest"]["Crypto Landing"][0],
            self.fi_data["group_weighted_interest"]["p2p_lending"][0],
            float(self.cash.total_cash),
            float(OTHER_BETS),
        ]
        total = int(sum(asset_values))
        return total

    def calculate_ff_goal_progress(self):
        current = self.total_assets
        goal_progress = round((current / FINANCIAL_FREEDOM_GOAL) * 100, 2)
        progress = str(goal_progress) + "%"
        return progress

    def get_combined_data(self) -> Dict:
        """Get combined portfolio data including all assets and calculations."""
        data = {
            "IB_DATA": self.ib_data,
            "CRYPTO_DATA": {
                "Total_Crypto_Value": self.crypto.get_total_crypto_value(),
                "Crypto_Market_Values": self.crypto.crypto_market_values,
                "Token_Quantities": self.crypto.quantities,
            },
            "FIXED_INCOME_DATA": self.fi_data,
            "CASH_DATA": {
                "Total": self.cash.total_cash,
                "Breakdown": self.cash.as_dict(),
            },
            "OTHER_ASSETS": {
                "Other Bets": int(OTHER_BETS),
            },
            "TOTAL_ASSETS": self.total_assets,
            "FIN_FREEDOM_GOAL_PROGRESS": self.ff_progress,
        }
        self._save_combined_data_to_json(data)
        return data

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
