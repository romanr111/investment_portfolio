from data.portfolio_filters import IB_BONDS_KEY
from src.brokers.ib import InteractiveBrokers
from src.cash_fixed_income.cash_summary import CashPortfolio
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio
from src.crypto.crypto_tokens import CryptoEndpoint
from src.brokers.ib_dividends import IBDividends
from src.dasha.dasha import DashaPortfolio
from src.google_sheets.allocation import PortfolioAllocations
from src.helpers import calculate_total_mkt_value


#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


class DataSource:
    def __init__(self):
        # 1. Initialize data sources
        self.ib = InteractiveBrokers()
        self.crypto = CryptoEndpoint()

        # 2. Prepare bond, dividend, and crypto data
        self.crypto_savings = self.crypto.all_crypto_savings
        self.ib_data = self.ib.get_full_porfolio_data()
        self.ib_bonds = self.ib_data.get(IB_BONDS_KEY, {})
        self.ib_div = IBDividends(self.ib_data)
        (
            self.monthly_dividends,
            self.yearly_dividends,
            self.stock_yearly,  # TODO: to include this data into the fixed income???
            self.dividend_details,
        ) = self.ib_div.get_my_total_monthly_and_yearly_divs()

        # 4. Build the FixedIncomePortfolio
        self.fixed_income_endpoint = FixedIncomePortfolio(
            self.ib_bonds, self.dividend_details, self.crypto_savings
        )
        self.fixed_income_data = (
            self.fixed_income_endpoint.get_combined_fixed_income_data()
        )
        print("\nFixed Income Summary:")
        print(self.fixed_income_data)

        # 6. Handle cash and dasha
        self.cash = CashPortfolio(
            self.ib_data["Net_cash"],
            self.crypto.free_cash,
        )
        self.dasha = DashaPortfolio(self.ib)

    def get_combined_data(self):
        """
        Returns a combined dictionary with all portfolio data including fixed income
        and dividend information.
        """
        return {
            "IB_DATA": self.ib_data,
            "CRYPTO_DATA": {
                "Total_Crypto_Value": self.crypto.get_total_crypto_value(),
                "Crypto_Market_Values": self.crypto.crypto_market_values,
                "Token_Quantities": self.crypto.quantities,
            },
            "FIXED_INCOME_DATA": {
                "Summary": self.fixed_income_data,
                "Yearly_Earnings": {
                    # Fixed_Income": #self.yearly_earnings_fixed_income,
                    # "Stocks": #self.yearly_earnings_stocks,
                    # "Total": #self.yearly_earnings_fixed_income
                    # + self.yearly_earnings_stocks,
                },
                "Calculated_Income": None,  # self.calculated_income,
                "Group_Weighted_Interest": None,  # self.group_weighted_interest,
                "Summary": None,  # self.fixed_income.summary,
            },
            "CASH_DATA": {
                "Total": self.cash.total_cash,
                "Breakdown": self.cash.as_dict(),
            },
        }

        # Calculate total portfolio value
        # combined_data["Total_Portfolio_Value"] = sum(
        #    [
        #        combined_data["Cash"]["Total"],
        #       combined_data["IB_Portfolio"]["Total_Stocks_Value"],
        #       combined_data["Crypto_Holdings"]["Total_Value"],
        #       # Add any fixed income principal values if they're not already included in IB_Portfolio
        #   ]
        # )

        return combined_data


if __name__ == "__main__":
    data_source = DataSource()
    portfolio_data = data_source.get_combined_data()
    print(portfolio_data)
