from src.dasha.dasha import DashaPortfolio
from src.helpers import calculate_total_mkt_value

from src.cash_fixed_income.cash_summary import Cash
from src.google_sheets.allocation import PortfolioAllocations
from src.cash_fixed_income.fixed_income.fixed_income import FixedIncomePortfolio


class DataSource:
    def __init__(self, ib_endpoint, crypto_endpoint):
        self.ib = ib_endpoint
        self.ib_cash = self.ib.net_cash_balance
        self.crypto = crypto_endpoint
        self.cash = Cash(self.ib_cash, self.crypto)
        self.dasha = DashaPortfolio(self.ib)
        self.p2p = FixedIncomePortfolio()
        self.data = self.fetch_data()
        # TODO
        self.p_alloc = PortfolioAllocations(self.ib, self.crypto, self.cash)

    def fetch_data(self):
        data = self.ib.get_full_porfolio_data()
        data["Crypto"] = self.crypto.get_tokens_market_values()
        data["Cash"] = self.cash.total_cash
        data["portfolio_allocations"] = self.p_alloc
        data["P2P"] = self.p2p.total_prinicpal_interest_in_p2p[0]
        data["Net_Worth"] = self.calculate_net_worth()
        return data

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
