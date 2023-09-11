import sys

sys.path.append(".")
import src.helpers as helpers
import requests

from support_data.api_keys import BEARER_TOKEN

PROFILE_ID = 21629358
BALANCE_IDS = {
    "USD": 39868508,
    "EUR": 20834458,
}


class Wise:
    def __init__(self):
        self.balances = self.fetch_balances()

    def fetch_balances(self):
        balances = {}
        for currency, balance_id in BALANCE_IDS.items():
            url = f"https://api.transferwise.com/v4/profiles/{PROFILE_ID}/balances/{balance_id}"
            headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
            response = requests.get(url, headers=headers)

            # Check for a successful response
            if response.status_code == 200:
                balances[currency] = response.json()[
                    "amount"
                ]  # Assuming 'amount' is the field in the response
            else:
                print(f"Content --> {response.content}")
                response.raise_for_status()
        return balances

    def get_eur_to_usd_balance(self):
        """Returns USD balance and USD representation of EUR asset."""
        eur_to_usd = 0
        if "EUR" in self.balances:
            eur_to_usd = helpers.convert("EUR", "USD", self.balances["EUR"]["value"])
        return eur_to_usd

    def get_usd_balance(self):
        """Extract and return the USD balance from the balances dictionary."""
        return self.balances.get("USD", {}).get("value", 0)

    def get_total_balance_in_usd(self):
        """Sums up USD and converted EUR balances."""
        total = round(self.get_usd_balance() + self.get_eur_to_usd_balance())
        print(f"Total Wise Balance: {total}")
        return total
