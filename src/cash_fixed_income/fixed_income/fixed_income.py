import sys

sys.path.append(".")

import src.helpers as helpers

PLATFORM_GROUPING = {
    "EstateGuru": "p2p_lending",
    "PeerBerry": "p2p_lending",
}


class FixedIncomeAsset:
    def __init__(self, *args):
        self.assets = self._combine_asset_data(args)

    def _combine_asset_data(self, assets):
        combined_dict = {}
        for asset in assets:
            combined_dict.update(asset.usd_data)
        return self._structure_data(combined_dict)

    def _structure_data(self, data_dict):
        result = {}
        for key, value in data_dict.items():
            group = PLATFORM_GROUPING.get(key, key)
            if group not in result:
                result[group] = {}
            result[group][key] = value
        return result

    def get_weighted_interest(self):
        group_interest = {}

        for group, assets in self.assets.items():
            total_principal = sum(principal for principal, _ in assets.values())
            weighted_interest = sum(
                principal * interest for principal, interest in assets.values()
            )

            avg_interest = round(weighted_interest / total_principal, 3)
            group_interest[group] = (total_principal, avg_interest)
        print(f"\n weighted_interest -- {group_interest}\n")
        return group_interest


class EurAsset:
    def __init__(self, balance, interest_rate):
        self.balance = balance
        self.interest_rate = interest_rate

    @property
    def usd_data(self):
        usd_amount = round(helpers.convert("EUR", "USD", self.balance))
        return {self.__class__.__name__: (usd_amount, self.interest_rate)}


class EstateGuru(EurAsset):
    def __init__(self):
        super().__init__(3712, 0.09)


class PeerBerry(EurAsset):
    def __init__(self):
        super().__init__(10129, 0.1)


def test_fixed_income_asset():
    estate_guru = EstateGuru()
    peerberry = PeerBerry()
    asset = FixedIncomeAsset(estate_guru, peerberry)
    asset.get_weighted_interest()
    return asset.assets


# Run the tests and check type
result = test_fixed_income_asset()
print(result)
