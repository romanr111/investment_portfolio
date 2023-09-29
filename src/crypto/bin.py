import math
from collections import defaultdict

from binance.spot import Spot
from data.crypto_data import BINANCE_LOCKED_STACKING
from data.api_keys import BINANCE_KEY, BINANCE_SECRET


class Binance:
    # Needs to be updated manually every time staking changes;

    def __init__(self) -> None:
        self.__binance_connection = Spot(api_key=BINANCE_KEY, api_secret=BINANCE_SECRET)

        if self.__binance_connection:
            print("Binace connection is successful!")
        else:
            raise Exception("Connection to Binance FAILED!")

    def get_earn_total_cash_savings(self):
        """
        Returns:
            int: Sum of cash savings in Binance Earn
        """
        return math.ceil(
            float(self.__binance_connection.savings_account()["totalAmountInUSDT"])
        )

    def _get_flexible_savings_info(self):
        """
        Returns:
            dict: Info about all flexible savings in Binance Earn
        """
        return self.__binance_connection.savings_flexible_product_position()

    def _get_fixed_savings_info(self):
        """
        Returns:
            dict: Info about all fixed savings in Binance Earn
        """
        return self.__binance_connection.savings_project_position()

    def _get_spot_account_balances(self):
        """
        Returns:
            dict: Spot account balance without zero values.
        """
        balances = self.__binance_connection.account()["balances"]
        filtered_spot = {}

        for balance in balances:
            if "LD" in balance["asset"]:
                pass
            elif float(balance["free"]) > 0.0:
                filtered_spot[balance["asset"]] = balance["free"]

        return filtered_spot


class BinanceFiltered(Binance):
    def _get_spot_account_crypto_balances(self):
        """Filters out Crypto from Crypto-Dollars in Spot account.

        Returns:
            defaultdict: Spot crypto balances.
        """
        crypto = defaultdict(int)
        balances = self._get_spot_account_balances()

        for token, balance in balances.items():
            if token not in ["USDT", "USDC", "BUSD", "PAX", "DAI", "QISWAP", "BOBA"]:
                if float(balance) > 0.0001:
                    crypto[token] = round(float(balance), 3)

        return crypto

    def collect_savings_interest_data(self):
        """
        Retrieves both flexible and fixed savings information.

        Returns:
            tuple: If there are savings data, returns a tuple of tuples with the format
                ((principal1, interest1), (principal2, interest2), ...).
                Otherwise, returns (0, 0) indicating no data.
        """
        EMPTY_DATA = (0, 0)

        flexible_data = [
            (int(loan["totalAmount"]), float(loan["annualInterestRate"]))
            for loan in self._get_flexible_savings_info()
        ]

        fixed_data = [
            (int(loan["principal"]), float(loan["interestRate"]))
            for loan in self._get_fixed_savings_info()
        ]
        combined_data = tuple(flexible_data + fixed_data)

        return combined_data or EMPTY_DATA

    def get_spot_account_cash_balance(self):
        """Filters out USDT/USDC/BUSD/PAX/DAI from all tokens.

        Returns:
            int: Total amount of uninvested cash account balance.
        """
        crypto_cash = 0
        balances = self._get_spot_account_balances()

        for token, balance in balances.items():
            if token in ["USDT", "USDC", "BUSD", "PAX", "DAI"]:
                crypto_cash += round(float(balance))

        return crypto_cash

    def sum_up_all_stablecoins(self):
        return self.get_spot_account_cash_balance()

    def get_all_crypto_balances(self):
        """Sums up all crypto in different wallets (Spot + Earn).

        Returns:
            defaultdict: Name + Amount
        """
        crypto = self._get_spot_account_crypto_balances()

        for token, amount in BINANCE_LOCKED_STACKING.items():
            crypto[token] += amount

        return crypto


if __name__ == "__main__":
    bin = BinanceFiltered()
    print(f"get_spot_account_cash_balance - {bin.get_spot_account_cash_balance()}")
    print(f"get_all_crypto_balances - {bin.get_all_crypto_balances()}")
    print(f"collect_savings_interest_data - {bin.collect_savings_interest_data()}")
