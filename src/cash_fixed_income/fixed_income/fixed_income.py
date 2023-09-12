import sys

sys.path.append(".")

import src.helpers as helpers

ESTATE_GURU = (3359, 0.068)
PEER_BERRY = (1772, 0.078)
WHITE_BIT = ((530, 0.3), (500, 0.2485), (1735, 0.107))
COIN_LOAN = (1, 0.1)
YOU_HODLER = (0, 0)

PLATFORM_GROUPING = {
    "EstateGuru": "p2p_lending",
    "PeerBerry": "p2p_lending",
    "WhiteBit": "crypto_lending",
    "CoinLoan": "crypto_lending",
    "YouHodler": "crypto_lending",
}


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

    def calculate_weighted_interest(self, data):
        """
        Calculate weighted interest for given data.

        Arguments:
        - data: Either a tuple or a tuple of tuples representing (principal, interest)

        Returns:
        - A tuple containing total principal and average interest
        """

        # Check if the data is a single tuple or tuple of tuples
        print(f"DEBUG: data = {data}")

        if isinstance(data[0], tuple):
            flat_data = data
        else:
            flat_data = [data]

        print(f"DEBUG: flat_data = {flat_data}")

        # Now, proceed with calculations
        total_p = sum(principal for principal, _ in flat_data)
        weighted_int = sum(principal * interest for principal, interest in flat_data)

        avg_interest = round(weighted_int / total_p, 3)
        print(f"{total_p}, {avg_interest} \n")
        return total_p, avg_interest


class FixedIncomeAsset(Asset):
    def __init__(self, *args):
        self.assets = self._combine_asset_data(args)

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
            assets_data = tuple(assets.values())  # Only pass the first element
            total_p, avg_interest = self.calculate_weighted_interest(assets_data)
            group_interest[group] = (total_p, avg_interest)
            print(f"\n weighted_interest -- {group_interest}\n")
            return group_interest


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
        elif self.is_single_tuple(data):
            principal, interest = data[0]
            super().__init__(principal, interest)
        else:
            raise ValueError("Unsupported data format")

    def is_single_tuple(self, data):
        """Check if the data is a single tuple."""
        return len(data) == 1 and isinstance(data[0], tuple)

    def is_tuple_of_tuples(self, data):
        """Check if the data is a tuple of tuples."""
        return all(isinstance(item, tuple) for item in data)

    @property
    def data(self):
        if hasattr(self, "_data"):  # if _data attribute exists
            return {self.__class__.__name__: self._data}
        return super().data


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


def get_summary():
    eg = EstateGuru(*ESTATE_GURU)
    pb = PeerBerry(*PEER_BERRY)
    wb = WhiteBit(*WHITE_BIT)
    cl = CoinLoan(COIN_LOAN)
    asset = FixedIncomeAsset(eg, pb, wb, cl)
    asset.get_group_weighted_interest()
    return asset.assets


# Run the tests and check type
result = get_summary()
print(result)
