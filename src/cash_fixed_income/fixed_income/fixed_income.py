import time

import src.helpers as helpers

from functools import lru_cache
from data.cash_and_fi_data import *


class Asset:
    def __init__(self, principal, interest):
        self._principal = principal  # changed to protected member
        self._interest = interest  # changed to protected member

    @property
    def principal(self):
        return self._principal

    @principal.setter
    def principal(self, value):
        self._principal = value

    @property
    def interest(self):
        return self._interest

    @interest.setter
    def interest(self, value):
        self._interest = value

    @property
    def data(self):
        return {self.__class__.__name__: (self._principal, self._interest)}

    @lru_cache(maxsize=None)
    def calculate_weighted_interest(self, data):
        """
        Calculate weighted interest for given data.

        Arguments:
        - data: Either a tuple or a tuple of tuples representing (principal, interest)

        Returns:
        - A tuple containing total principal and average interest
        """
        print(f"Weighted DEBUG: {data}")

        total_p = sum(principal for principal, _ in data)
        weighted_int = sum(principal * interest for principal, interest in data)

        avg_interest = round(weighted_int / total_p, 3)
        print(f"Object weighted interest - {total_p}, {avg_interest} \n")
        return total_p, avg_interest


class EurAsset(Asset):
    def __init__(self, principal, interest):
        super().__init__(principal, interest)

    @property
    def data(self):
        usd_amount = round(helpers.convert("EUR", "USD", self._principal))
        return {self.__class__.__name__: (usd_amount, self._interest)}


class CryptoAssets(Asset):
    def __init__(self, *data):
        if self.is_tuple_of_tuples(data):
            total_principal, average_interest = self.calculate_weighted_interest(data)
            super().__init__(total_principal, average_interest)
        else:
            principal, interest = data
            super().__init__(principal, interest)

    def is_tuple_of_tuples(self, data):
        """Check if the data is a tuple of tuples."""
        return all(isinstance(item, tuple) for item in data)


class WhiteBit(CryptoAssets):
    def __init__(self, *data):
        super().__init__(*data)


class CoinLoan(CryptoAssets):
    def __init__(self, *data):
        super().__init__(*data)


class EstateGuru(EurAsset):
    def __init__(self, principal, interest):
        super().__init__(principal, interest)


class PeerBerry(EurAsset):
    def __init__(self, *args):
        super().__init__(*args)


class FixedIncomeAssets(Asset):
    def __init__(self, *args):
        self.assets = self._combine_asset_data(args)
        print(f"initiated fixed income assets:\n{self.assets}\n")

    def _combine_asset_data(self, assets):
        combined_dict = {}
        for asset in assets:
            combined_dict.update(asset.data)
        return self._structure_data(combined_dict)

    def _structure_data(self, data_dict):
        result = {}
        for key, value in data_dict.items():
            group = PLATFORM_GROUPING.get(key)
            if group not in result:
                result[group] = {}
            result[group][key] = value
        return result

    def get_group_weighted_interest(self):
        """
        Calculate weighted interest for each group in the assets.

        Returns:
            - A dictionary with group names as keys and their respective weighted interests as values.
        """
        group_interest = {}

        for group, assets in self.assets.items():
            assets_data = tuple(assets.values())
            total_p, avg_interest = self.calculate_weighted_interest(assets_data)
            group_interest[group] = (total_p, avg_interest)
        print("--------")
        print(f"\nGroup weighted interest - {group_interest}\n")
        print("--------")
        return group_interest


class FixedIncomePortfolio:
    def __init__(self):
        self._portfolio = self._initialize_assets()
        self._gwi = self._portfolio.get_group_weighted_interest()

    def _initialize_assets(self):
        eg = EstateGuru(*ESTATE_GURU)
        pb = PeerBerry(*PEER_BERRY)
        wb = WhiteBit(*WHITE_BIT)
        cl = CoinLoan(COIN_LOAN)
        return FixedIncomeAssets(eg, pb, wb, cl)

    @property
    def summary(self):
        return self._portfolio.assets

    @property
    def group_weighted_interest(self):
        return self._gwi

    @property
    def total_prinicpal_interest_in_p2p(self):
        tuples = tuple(self._gwi.values())
        total = self._portfolio.calculate_weighted_interest(tuples)
        return total

    @property
    def yearly_earnings(self):
        principal, interest = self.total_prinicpal_interest_in_p2p
        return round(principal * interest)


if __name__ == "__main__":
    start_time = time.time()
    portfolio = FixedIncomePortfolio()
    print(f"SUMMARY - {portfolio.summary}")
    print("\n")
    print(f"GROUP WEIGHTED INTEREST - {portfolio.group_weighted_interest}")
    print("\n")
    print(f"TOTAL - {portfolio.total_prinicpal_interest_in_p2p}")
    print("\n")
    print(f"YEARLY P2P DIVIDENDS - {portfolio.yearly_earnings} $")
    print("\n")
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time} seconds")
