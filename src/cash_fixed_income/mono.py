import sys

sys.path.append(".")

import src.helpers as helpers
from data.endpoints import MONO_API, MONO_PERSONAL_TOKEN

# Constants for currency codes
UAH_CODE = 980
USD_CODE = 840
EUR_CODE = 978


class Mono:
    def __init__(self):
        self.account_info = helpers.perform_request(
            api=MONO_API,
            header=MONO_PERSONAL_TOKEN,
        )
        self.accounts = self.account_info.get("accounts", [])

    def get_balance_for_currency(self, currency_code):
        balance = 0
        for acc in self.accounts:
            if acc["currencyCode"] == currency_code and acc["balance"] > 0:
                balance += acc["balance"] / 100
                if acc["creditLimit"] > 0 and currency_code == UAH_CODE:
                    balance -= acc["creditLimit"] / 100
        return balance

    def get_total_balance_in_usd(self):
        uah = round(self.get_balance_for_currency(UAH_CODE))
        usd = round(self.get_balance_for_currency(USD_CODE))
        eur = round(self.get_balance_for_currency(EUR_CODE))

        inaccuracy = 0.9861
        uah_to_usd = helpers.convert("UAH", "USD", uah) * inaccuracy
        eur_to_usd = helpers.convert("EUR", "USD", eur) if eur > 0 else 0

        total_balance = round(usd + uah_to_usd + eur_to_usd)

        print("\n")
        print("--- Mono ---")
        print("\n")
        print(f"UAH - {uah}")
        print("\n")
        print(f"USD - {usd}")
        print("\n")
        print(f"EUR - {eur}")
        print("\n")
        print(f"Total - {total_balance}")

        return total_balance
