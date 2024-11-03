from src.cash_fixed_income import mono, wise
from src.crypto.crypto_tokens import CryptoEndpoint

from data.assets_data import CASH, LENDED, DEBT, PRIVAT


class Cash:
    """
    Class representing cash from various sources.
    """

    def __init__(self, ib_cash, crypto_obj):
        self.cash = CASH
        self.lended_amount = LENDED
        self.own_debt = DEBT
        self.private_funds = PRIVAT
        self.mono = mono.Mono()
        self.wise = wise.Wise()
        self.ib_cash = ib_cash
        self.crypto = crypto_obj

    def as_dict(self):
        instance_vars = vars(self).copy()
        # Replacing object representations with their actual values
        instance_vars["mono"] = self.mono.get_total_balance_in_usd()
        instance_vars["wise"] = self.wise.get_total_balance_in_usd()
        instance_vars["crypto"] = self.crypto.get_total_cash()
        print(f"cash dict -> {instance_vars}")
        return instance_vars

    @property
    def total_cash(self):
        return sum(val for val in self.as_dict().values())


if __name__ == "__main__":
    ib_cash = 100
    crypto = CryptoEndpoint()
    cash = Cash(ib_cash, crypto)
    print(f"TOTAL FREE CASH = {cash.total_cash}")
