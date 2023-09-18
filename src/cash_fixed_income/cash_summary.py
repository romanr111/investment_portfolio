from src.cash_fixed_income import mono, wise
from src.crypto.crypto import Crypto


class Cash:
    def __init__(self, ib_cash):
        self.cash = 10000
        self.lended = 700
        self.my_debt = -3000
        self.privat = 100
        self.mono = mono.Mono()
        self.wise = wise.Wise()
        self.ib_cash = ib_cash
        self.crypto_cash = Crypto()

    def calculate_all_non_invested_cash(self):
        all_cash = {
            "Cash": self.cash,
            "Lended": self.lended,
            "My_Debt": self.my_debt,
            "Mono": self.mono.get_total_balance_in_usd(),
            "Privat": self.privat,
        }
        print(all_cash)
        total_cash = 0
        for cash in all_cash.values():
            total_cash += cash

        return total_cash


if __name__ == "__main__":
    c = Cash(ib_cash=100)
    print(c.calculate_all_non_invested_cash())
