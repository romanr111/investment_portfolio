from src.brokers.ib import InteractiveBrokers
from src.cash_fixed_income.cash_summary import CashPortfolio
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio
from src.crypto.crypto_tokens import CryptoEndpoint
from src.brokers.ib_dividends import AssetInfo, IBDividends
from src.dasha.dasha import DashaPortfolio
from src.google_sheets.allocation import PortfolioAllocations
from src.helpers import calculate_total_mkt_value


class DataSource:
    def __init__(self):
        # Initialize data sources
        """
        self.ib = InteractiveBrokers()
        self.crypto = CryptoEndpoint()
        self.crypto_savings = self.crypto.all_crypto_savings
        self.ib_data = self.ib.get_full_porfolio_data()
        self.ib_bonds = self.ib_data.get("Bonds", {})
        self.ib_div = IBDividends(self.ib_data)
        monthly_total, yearly_total, asset_details = (
            self.ib_div.get_my_total_monthly_and_yearly_divs()
        )
        self.monthly_dividends = monthly_total
        self.yearly_dividends = yearly_total
        self.dividend_details = asset_details
        """

        self.ib_bonds = {"IBCID722427489": 22819, "SGOV": 3715, "TLT": 2263}
        self.crypto_savings = [
            {"binance": {"USDC": (501, 0.1597), "USDT": (6583, 0.0978)}},
            {"okx": {"USDT": (3048, 0.1303), "USDC": (2069, 0.1468)}},
            {"bybit": {"USDC": (503, 0.138), "USDT": (543, 0.107)}},
            {"whitebit": {"USDT": (3864, 0.1561), "USDC": (7404, 0.156)}},
        ]
        print(f"self.dividend_details --> {self.dividend_details}")
        print(f"self.ib_bond --> {self.ib_bonds}")
        print(f"self.crypto_savings --> {self.crypto_savings}")
        self.fixed_income = FixedIncomePortfolio(
            self.ib_bonds, self.dividend_details, self.crypto_savings
        )
        print("\n Summary Output:")
        print(self.fixed_income.summary)
        # self.cash = CashPortfolio(
        #    self.ib_data["Net_cash"],
        #    self.crypto.free_cash,
        # )
        # self.dasha = DashaPortfolio(self.ib)

    def get_combined_data(self):
        """
        Returns a combined dictionary with all portfolio data.
        """
        combined_data = {
            "IB_Portfolio": self.ib_data,
            "Crypto_Holdings": {
                "Total_Value": self.crypto.get_total_crypto_value(),
                "Market_Values": self.crypto.crypto_market_values,
                "Token_Quantities": self.crypto.quantities,
                "Savings": self.crypto.all_crypto_savings,
            },
            "IB Dividends Data": self.dividend_details,
            # Cash and liquid assets
            "Total_Cash": self.cash.total_cash,
            "Cash_Breakdown": self.cash.as_dict(),
        }
        """
        # Calculate total portfolio value across all sources
        combined_data["Total_Portfolio_Value"] = sum(
            [
                combined_data["Total_Cash"],
                combined_data["IB_Portfolio"][
                    "Total_Stocks_Value"
                ],  # Use the correct path
                combined_data["Crypto_Holdings"]["Total_Value"],
            ]
        )"""

        return combined_data


if __name__ == "__main__":
    data_source = DataSource()
    # portfolio_data = data_source.get_combined_data()
    # print(f"portfolio_data: {portfolio_data}")
