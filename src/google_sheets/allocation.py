class PortfolioAllocations:
    def __init__(self, data):
        self.data = data

    def calculate_allocation(self, inv_type):
        return round((inv_type / self.net_worth) * 100)

    @property
    def stocks_allocation(self):
        return self.calculate_allocation(self.data.total_stocks_mkt_val)

    @property
    def bonds_allocation(self):
        return self.calculate_allocation(self.data.bonds_mkt_value)

    @property
    def reit_allocation(self):
        return self.calculate_allocation(self.data.total_reits_mkt_val)

    @property
    def gold_allocation(self):
        return self.calculate_allocation(self.data.ib_gold_mkt_value)

    @property
    def commodities_allocation(self):
        return self.calculate_allocation(self.data.comm_mkt_value)

    @property
    def crypto_allocation(self):
        return self.calculate_allocation(self.data.crypto_mkt_value)

    @property
    def cash_allocation(self):
        return self.calculate_allocation(self.data.cash_balance)

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
