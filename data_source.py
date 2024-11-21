from src.brokers.ib import InteractiveBrokers
from src.cash_fixed_income.cash_summary import Cash
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio
from src.crypto.crypto_tokens import CryptoEndpoint
from src.dasha.dasha import DashaPortfolio
from src.google_sheets.allocation import PortfolioAllocations
from src.helpers import calculate_total_mkt_value


class DataSource:
    def __init__(self):
        self.ib = InteractiveBrokers()
        self.crypto = CryptoEndpoint()
        # self.dasha = DashaPortfolio(self.ib)
        # self.p2p = FixedIncomePortfolio() to pass crypto ojbect; also ib object to get bonds info;
        # self.cash = Cash() To pass ib and crypto objects;
        self.data = self.collect_all_portfolio_data()
        # TODO why here?
        # self.p_alloc = PortfolioAllocations(self.ib, self.crypto, self.cash)

    def collect_all_portfolio_data(self):
        data = self.ib.get_full_porfolio_data()

        # Add crypto-related data
        data.update(
            {
                "Crypto Quantities": self.crypto.quantities,
                "Crypto Market Values": self.crypto.crypto_market_values,
                "Total Crypto Value": self.crypto.get_total_crypto_value(),
                "Crypto Free Cash": self.crypto.free_cash,
                "Crypto Savings": self.crypto.all_crypto_savings,
            }
        )
        return data

    #################################

    def calculate_net_worth(self):
        total_values = [
            self.total_stocks_mkt_val,
            self.bonds_mkt_value,
            self.total_reits_mkt_val,
            self.ib_gold_mkt_value,
            self.comm_mkt_value,
            self.crypto_mkt_value,
            self.p2p,
            self.cash_balance,
        ]
        return sum(total_values) - self.dasha_net_worth

    @property
    def bonds_mkt_value(self):
        return calculate_total_mkt_value(self.data["Bonds"])

    @property
    def total_stocks_mkt_val(self):
        return calculate_total_mkt_value(self.data["Total_Stocks_Value"])

    @property
    def total_reits_mkt_val(self):
        return calculate_total_mkt_value(self.data["REIT"])

    @property
    def ib_gold_mkt_value(self):
        return calculate_total_mkt_value(self.data["Gold"])

    @property
    def comm_mkt_value(self):
        return calculate_total_mkt_value(self.data["Commodities"])

    @property
    def crypto_mkt_value(self):
        return self.crypto.get_total_crypto_value()

    @property
    def cash_balance(self):
        return self.cash.total_cash


def main():
    """Main function demonstrating the Bybit client functionality."""
    try:
        print("\n=== Initializing Data ===")
        data_source = DataSource()
        print(data_source.collect_all_portfolio_data())

    except Exception as e:
        print(f"Error in main: {e}")
        print(f"\nAn error occurred: {e}")
    finally:
        print("\n=== Program Completed ===")


if __name__ == "__main__":
    main()
