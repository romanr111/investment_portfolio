from typing import Dict

from data.filters_constants import IB_BONDS_KEY
from src.brokers.ib import InteractiveBrokers
from src.brokers.ib_dividends import IBDividends
from src.cash_fixed_income.cash_summary import CashPortfolio
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio
from src.crypto.crypto_tokens import CryptoEndpoint
from src.allocation_calculator import get_sorted_sector_allocations
from src.dasha.dasha import DashaPortfolio

FINANCIAL_FREEDOM_GOAL = 500000


class DataSource:
    def __init__(self):
        self._initialize_data_sources()
        self._prepare_portfolio_data()
        self._calculate_stock_dividends()
        self._setup_fixed_income()
        self._setup_cash_and_dasha()
        self.total_assets = self.calculate_total_assets()
        self.ff_progress = self.calculate_ff_goal_progress()

    def _initialize_data_sources(self) -> None:
        """Initialize primary data source connections."""
        self.ib = InteractiveBrokers()
        self.crypto = CryptoEndpoint()
        self.crypto_savings = self.crypto.all_crypto_savings

    def _prepare_portfolio_data(self) -> None:
        """Prepare Interactive Brokers portfolio and dividend data."""
        self.ib_data = self.ib.get_full_porfolio_data()
        self.ib_bonds = self.ib_data.get(IB_BONDS_KEY, {})
        self.ib_div = IBDividends(self.ib_data)
        self._process_dividend_data()

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

    def _setup_cash_and_dasha(self) -> None:
        """Initialize cash and Dasha portfolio components."""
        self.cash = CashPortfolio(
            self.ib_data["Net_cash"],
            self.crypto.free_cash,
        )
        self.dasha = DashaPortfolio(self.ib)

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
        ]
        return int(sum(asset_values))

    def calculate_ff_goal_progress(self):
        current = self.total_assets
        goal_progress = round((current / FINANCIAL_FREEDOM_GOAL) * 100, 2)
        return str(goal_progress) + "%"

    def get_combined_data(self) -> Dict:
        """Get combined portfolio data including all assets and calculations."""
        return {
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
            "TOTAL_ASSETS": self.total_assets,
            "FIN_FREEDOM_GOAL_PROGRESS": self.ff_progress,
        }

    def get_data(self) -> Dict:
        data = self.get_combined_data()
        allocations = get_sorted_sector_allocations(data)
        data["ALLOCATIONS"] = allocations
        return data


if __name__ == "__main__":
    data_source = DataSource()
    portfolio_data = data_source.get_data()
    print()
    print(portfolio_data)
    print()
