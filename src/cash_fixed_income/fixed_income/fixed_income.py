import time
from dataclasses import dataclass
from typing import Optional

import src.helpers as helpers
from data.assets_data import *
from src.base_asset import Asset

from data.filters_constants import (
    BONDS_KEY,
    CRYPTO_LENDING_KEY,
    P2P_LENDING_KEY,
    PLATFORM_GROUPING,
    OTHER_KEY,
)


@dataclass
class AssetInfo:
    market_value: float
    yield_rate: float
    yearly_income: float
    adr_symbol: Optional[str]
    asset_type: str


class EurAsset(Asset):
    def __init__(self, principal, interest):
        super().__init__(principal, interest)

    @property
    def data(self):
        usd_amount = round(helpers.convert("EUR", "USD", self._principal))
        return {self.__class__.__name__: (usd_amount, self._interest)}


class MultipleAssets(Asset):
    def __init__(self, data_dict):
        self._data_dict = data_dict

    @property
    def data(self):
        return self._data_dict


class FixedIncomeAssets(Asset):
    def __init__(self, *asset_objects):
        self.assets = self._combine_asset_data(asset_objects)

    def _combine_asset_data(self, assets):
        combined = {}
        for asset in assets:
            combined.update(asset.data)
        return self._structure_data(combined)

    def _structure_data(self, data_dict):
        result = {}
        for key, value in data_dict.items():
            group = None

            if key.startswith("IBCID"):
                group = BONDS_KEY

            if not group:
                for group_name, items in PLATFORM_GROUPING.items():
                    if key in items:
                        group = group_name
                        break

            if not group and "_" in key:
                platform, token = key.split("_", 1)
                for group_name, items in PLATFORM_GROUPING.items():
                    if platform in items:
                        group = group_name
                        break
                if not group:
                    group = CRYPTO_LENDING_KEY
                result.setdefault(group, {}).setdefault(platform, {})
                result[group][platform][token] = value
            else:
                if not group:
                    group = OTHER_KEY
                if group not in result:
                    result[group] = {}
                if "_" not in key:
                    result[group][key] = value

        return result

    def calculate_group_weighted_interest(self):
        group_interest = {}
        for group, assets_data in self.assets.items():
            if group == CRYPTO_LENDING_KEY:
                items = []
                for platform_data in assets_data.values():
                    items.extend(platform_data.values())
                total_p, avg_int = self.calculate_weighted_interest(tuple(items))
            else:
                total_p, avg_int = self.calculate_weighted_interest(
                    tuple(assets_data.values())
                )
            group_interest[group] = (total_p, round(avg_int, 3))
        return group_interest


class CryptoAssets(MultipleAssets):
    pass


class EstateGuru(EurAsset):
    def __init__(self, principal, interest):
        super().__init__(principal, interest)


class PeerBerry(EurAsset):
    def __init__(self, *args):
        super().__init__(*args)


class FixedIncomePortfolio:
    def __init__(self, ib_bonds, ib_div_details, crypto_savings):
        self.ib_div_details = ib_div_details
        self.bonds_data = self._prepare_bonds(ib_bonds)
        self.savings_data = self._prepare_crypto_savings(crypto_savings)
        self._portfolio = self._initialize_assets()
        self._group_interest = self._portfolio.calculate_group_weighted_interest()

    def _prepare_bonds(self, ib_bonds):
        bond_dict = {}
        for symbol, asset_info in self.ib_div_details.items():
            if symbol in ib_bonds:
                bond_dict[symbol] = (
                    asset_info.market_value,
                    round(asset_info.yield_rate, 3),
                )
        return bond_dict

    def _prepare_crypto_savings(self, savings_data):
        platforms = {}
        for platform_dict in savings_data:
            for platform, assets in platform_dict.items():
                platforms.setdefault(platform, {})
                for currency, (amount, interest) in assets.items():
                    platforms[platform][currency] = (amount, round(interest, 3))
        return platforms

    def _flatten_savings_for_assets(self):
        flat = {}
        for platform, tokens in self.savings_data.items():
            for token, (amount, interest) in tokens.items():
                flat[f"{platform}_{token}"] = (amount, interest)
        return flat

    def _initialize_assets(self):
        eg = EstateGuru(*ESTATE_GURU)
        pb = PeerBerry(*PEER_BERRY)
        bond_assets = MultipleAssets(self.bonds_data)
        crypto_assets = MultipleAssets(self._flatten_savings_for_assets())
        return FixedIncomeAssets(bond_assets, crypto_assets, eg, pb)

    @property
    def summary(self):
        return {
            BONDS_KEY: self.bonds_data,
            CRYPTO_LENDING_KEY: self.savings_data,
            P2P_LENDING_KEY: {
                "EstateGuru": ESTATE_GURU,
                "PeerBerry": PEER_BERRY,
            },
        }

    @property
    def group_weighted_interest(self):
        return self._group_interest

    @property
    def total_principal_and_interest(self):
        relevant_groups = {
            k: v
            for k, v in self._group_interest.items()
            if k in [CRYPTO_LENDING_KEY, P2P_LENDING_KEY, BONDS_KEY]
        }
        total_p, avg_int = self._portfolio.calculate_weighted_interest(
            tuple(relevant_groups.values())
        )
        return total_p, avg_int

    @property
    def yearly_earnings_fixed_income(self):
        relevant_groups = {
            k: v
            for k, v in self._group_interest.items()
            if k in [CRYPTO_LENDING_KEY, P2P_LENDING_KEY, BONDS_KEY]
        }
        total = 0
        for principal, interest in relevant_groups.values():
            total += round(principal * interest)
        return total

    @property
    def calculated_income(self):
        data = {}
        for group, (principal, interest) in self._group_interest.items():
            if group in [BONDS_KEY, CRYPTO_LENDING_KEY, P2P_LENDING_KEY]:
                data[group] = round(principal * interest)
        return data

    def get_combined_fixed_income_data(self):
        return {
            "group_weighted_interest": self.group_weighted_interest,
            "calculated_income": self.calculated_income,
            "fixed_inc_principal_and_interest": {
                "principal": self.total_principal_and_interest[0],
                "interest": self.total_principal_and_interest[1],
            },
            "monthly_earnings_fixed_income": int(
                self.yearly_earnings_fixed_income / 12
            ),
            "yearly_earnings_fixed_income": self.yearly_earnings_fixed_income,
            "fixed_income_full_data": self._portfolio.assets,
        }


if __name__ == "__main__":
    start_time = time.time()
    data_source = FixedIncomePortfolio(
        ib_bonds={"IBCID722427489": 22819, "SGOV": 3715, "TLT": 2263},
        ib_div_details={
            "IBCID722427489": AssetInfo(
                market_value=22816,
                yield_rate=0.043932803489795696,
                yearly_income=1002.37,
                adr_symbol=None,
                asset_type="bond",
            ),
            "SGOV": AssetInfo(
                market_value=3715,
                yield_rate=0.0451,
                yearly_income=142.41,
                adr_symbol=None,
                asset_type="bond",
            ),
            "TLT": AssetInfo(
                market_value=2263,
                yield_rate=0.0414,
                yearly_income=79.63,
                adr_symbol=None,
                asset_type="bond",
            ),
            "KWEB": AssetInfo(
                market_value=4139,
                yield_rate=0.0013,
                yearly_income=4.57,
                adr_symbol=None,
                asset_type="stock",
            ),
            "PDD": AssetInfo(
                market_value=999,
                yield_rate=0.0,
                yearly_income=0.0,
                adr_symbol=None,
                asset_type="stock",
            ),
            "C": AssetInfo(
                market_value=3896,
                yield_rate=0.031,
                yearly_income=102.66,
                adr_symbol=None,
                asset_type="stock",
            ),
            "UPS": AssetInfo(
                market_value=754,
                yield_rate=0.0519,
                yearly_income=33.26,
                adr_symbol=None,
                asset_type="stock",
            ),
        },
        crypto_savings=[
            {"binance": {"USDC": (501, 0.1597), "USDT": (6583, 0.0978)}},
            {"okx": {"USDT": (3048, 0.1303), "USDC": (2069, 0.1468)}},
            {"bybit": {"USDC": (503, 0.138), "USDT": (543, 0.107)}},
            {"whitebit": {"USDT": (3864, 0.1561), "USDC": (7404, 0.156)}},
        ],
    )

    print()
    print("Combined Fixed Income Data:", data_source.get_combined_fixed_income_data())
    print()

    end_time = time.time()
    print(f"Execution time: {end_time - start_time:.4f} seconds")
