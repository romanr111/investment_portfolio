from src.cash_fixed_income import mono, wise
from src.crypto.crypto import Crypto

from data.cash_and_fi_data import CASH, LENDED, DEBT, PRIVAT


class Cash:
    """
    Class representing cash from various sources.
    """

    def __init__(self, ib_cash=0):
        self.cash = CASH
        self.lended_amount = LENDED
        self.own_debt = DEBT
        self.private_funds = PRIVAT
        self.ib_cash_amount = ib_cash
        self.mono = mono.Mono()
        self.wise = wise.Wise()
        self.crypto = Crypto()

    def as_dict(self):
        instance_vars = vars(self).copy()

        # Replacing object representations with their actual values
        instance_vars["mono"] = self.mono.get_total_balance_in_usd()
        instance_vars["wise"] = self.wise.get_total_balance_in_usd()
        instance_vars["crypto"] = self.crypto.get_all_free_cash_in_stablecoins()
        print(f"cash dict -> {instance_vars}")
        return instance_vars

    @property
    def total_cash(self):
        return sum(val for val in self.as_dict().values())


if __name__ == "__main__":
    example = 100
    cash = Cash(ib_cash=example)
    print(f"TOTAL FREE CASH = {cash.total_cash}")
