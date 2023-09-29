from src.dasha.dasha import DashaPortfolio


class PortfolioAllocations:
    def __init__(self, ib_endpoint, crypto_endpoint, cash_endpoint):
        self.ib = ib_endpoint
        self.crypto = crypto_endpoint
        self.cash = cash_endpoint
        self.dasha = DashaPortfolio(self.ib)
        self.ib_positions = self.ib.get_portfolio_positions()
        self.dasha_net_worth = self.dasha.get_portfolio_value()
        self.net_worth = self.calculate_net_worth()

    def calculate_net_worth(self):
        total_values = [
            self.total_stocks_mkt_val,
            self.bonds_mkt_value,
            self.total_reits_mkt_val,
            self.ib_gold_mkt_value,
            self.comm_mkt_value,
            self.crypto_mkt_value,
            self.cash_balance,
        ]
        return sum(total_values) - self.dasha_net_worth

    @property
    def bonds_mkt_value(self):
        return self.ib.calculate_total_mkt_value(self.ib_positions["Bonds"])

    @property
    def total_stocks_mkt_val(self):
        return self.ib_positions["Total_Stocks_Value"]

    @property
    def total_reits_mkt_val(self):
        return self.ib.calculate_total_mkt_value(self.ib_positions["REIT"])

    @property
    def ib_gold_mkt_value(self):
        return self.ib.calculate_total_mkt_value(self.ib_positions["Gold"])

    @property
    def comm_mkt_value(self):
        return self.ib.calculate_total_mkt_value(self.ib_positions["Commodities"])

    @property
    def crypto_mkt_value(self):
        return self.crypto.get_total_crypto_market_value()

    @property
    def cash_balance(self):
        return self.cash.total_cash

    def calculate_allocation(self, inv_type):
        return round((inv_type / self.net_worth) * 100)

    @property
    def stocks_allocation(self):
        return self.calculate_allocation(self.total_stocks_mkt_val)

    @property
    def bonds_allocation(self):
        return self.calculate_allocation(self.bonds_mkt_value)

    @property
    def reit_allocation(self):
        return self.calculate_allocation(self.total_reits_mkt_val)

    @property
    def gold_allocation(self):
        return self.calculate_allocation(self.ib_gold_mkt_value)

    @property
    def commodities_allocation(self):
        return self.calculate_allocation(self.comm_mkt_value)

    @property
    def crypto_allocation(self):
        return self.calculate_allocation(self.crypto_mkt_value)

    @property
    def cash_allocation(self):
        return self.calculate_allocation(self.cash_balance)

    @property
    def actual_allocations(self):
        return {
            "I4:K4": self.stocks_allocation,
            "I5:K5": self.bonds_allocation,
            "I6:K6": self.reit_allocation,
            "I7:K7": self.crypto_allocation,
            "I8:K8": self.gold_allocation,
            "I9:K9": self.commodities_allocation,
            "I11:K11": self.cash_allocation,
        }

    @property
    def expected_allocations(self):
        return {
            "Stocks": 35,
            "Bonds": 5,
            "REIT": 5,
            "Crypto": 5,
            "Gold": 1,
            "Commodities": 5,
            "Cash & Equivalents": 38,
        }


if __name__ == "__main__":
    endpoint = PortfolioAllocations()
    print("\n")
    print(endpoint.total_stocks_mkt_val)
    print(endpoint.actual_allocations)
    print(endpoint.expected_allocations)
