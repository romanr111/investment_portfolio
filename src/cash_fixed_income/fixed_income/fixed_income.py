import time
from dataclasses import dataclass
from typing import Optional

import src.helpers as helpers
from data.assets_data import *
from src.base_asset import Asset


@dataclass
class AssetInfo:
    market_value: float
    yield_rate: float
    yearly_income: float
    adr_symbol: Optional[str]
    asset_type: str


# Define platform grouping for all known assets
PLATFORM_GROUPING = {
    # Bonds
    "IBCID722427489": "bonds",
    "SGOV": "bonds",
    "TLT": "bonds",
    # Crypto platforms
    "binance": "crypto_lending",
    "okx": "crypto_lending",
    "bybit": "crypto_lending",
    "whitebit": "crypto_lending",
    # P2P lending
    "EstateGuru": "p2p_lending",
    "PeerBerry": "p2p_lending",
}


class EurAsset(Asset):
    def __init__(self, principal, interest):
        super().__init__(principal, interest)

    @property
    def data(self):
        # Convert EUR principal to USD before returning data
        usd_amount = round(helpers.convert("EUR", "USD", self._principal))
        return {self.__class__.__name__: (usd_amount, self._interest)}


class MultipleAssets(Asset):
    """
    A generic class for holding multiple keyed assets.
    Expects a dictionary: {key: (principal, interest), ...}
    """

    def __init__(self, data_dict):
        self._data_dict = data_dict

    @property
    def data(self):
        return self._data_dict


class FixedIncomeAssets(Asset):
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
            if key in PLATFORM_GROUPING:
                group = PLATFORM_GROUPING[key]
                if group not in result:
                    result[group] = {}
                result[group][key] = value
            else:
                # Possibly a crypto platform & token combination like 'binance_USDC'
                if "_" in key:
                    platform, token = key.split("_", 1)
                    group = PLATFORM_GROUPING.get(platform, "crypto_lending")
                    if group not in result:
                        result[group] = {}
                    if platform not in result[group]:
                        result[group][platform] = {}
                    result[group][platform][token] = value
                else:
                    # If no underscore and no PLATFORM_GROUPING match, it's other
                    group = "other"
                    if group not in result:
                        result[group] = {}
                    result[group][key] = value
        return result

    def get_group_weighted_interest(self):
        group_interest = {}
        for group, assets in self.assets.items():
            if group == "crypto_lending":
                # Flatten crypto tokens
                flat_values = []
                for platform, tokens in assets.items():
                    flat_values.extend(tokens.values())
                assets_data = tuple(flat_values)
            else:
                assets_data = tuple(assets.values())

            total_p, avg_interest = self.calculate_weighted_interest(assets_data)
            group_interest[group] = (total_p, avg_interest)
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
        self.bonds_data = self._process_bonds(ib_bonds, ib_div_details)
        self.savings_data = self._process_crypto_savings(
            crypto_savings
        )  # Nested structure
        # self.stock_data is set in _process_bonds
        self._portfolio = self._initialize_assets()
        self._gwi = self._portfolio.get_group_weighted_interest()

    def _process_bonds(self, ib_bonds, div_details):
        bond_dict = {}
        stock_dict = {}
        bond_symbols = set(ib_bonds.keys())

        for symbol, asset_info in div_details.items():
            if symbol in bond_symbols:
                # It's a bond
                bond_dict[symbol] = (asset_info.market_value, asset_info.yield_rate)
            else:
                # It's a stock
                stock_dict[symbol] = (asset_info.market_value, asset_info.yield_rate)

        self.stock_data = stock_dict  # Store stocks separately
        print(f"processed_bonds - {bond_dict}")
        print(f"processed_stocks - {stock_dict}")
        return bond_dict

    def _process_crypto_savings(self, savings_data):
        savings_dict = {}
        for platform_dict in savings_data:
            for platform, assets in platform_dict.items():
                if platform not in savings_dict:
                    savings_dict[platform] = {}
                for currency, (amount, interest) in assets.items():
                    savings_dict[platform][currency] = (amount, interest)
        print(f"processed Crypto savings  - {savings_dict}")
        return savings_dict

    def _flatten_savings_for_assets(self, nested_savings):
        flat_savings = {}
        for platform, tokens in nested_savings.items():
            for token, (amount, interest) in tokens.items():
                key = f"{platform}_{token}"
                flat_savings[key] = (amount, interest)
        return flat_savings

    def _initialize_assets(self):
        eg = EstateGuru(*ESTATE_GURU)
        pb = PeerBerry(*PEER_BERRY)

        bond_assets = MultipleAssets(self.bonds_data)
        flat_savings = self._flatten_savings_for_assets(self.savings_data)
        crypto_assets = MultipleAssets(flat_savings)

        # Notice we do NOT pass stocks into FixedIncomeAssets
        # because we don't want them in group weighted interest.
        return FixedIncomeAssets(bond_assets, crypto_assets, eg, pb)

    @property
    def summary(self):
        return {
            "bonds": self.bonds_data,
            "stocks": self.stock_data,
            "crypto_lending": self.savings_data,
            "p2p": {"EstateGuru": ESTATE_GURU, "PeerBerry": PEER_BERRY},
        }

    @property
    def group_weighted_interest(self):
        # Stocks are not included here
        return self._gwi

    @property
    def total_prinicpal_interest_in_p2p(self):
        # Here we consider only fixed income categories: bonds, crypto_lending, p2p_lending
        # Stocks and other groups are excluded.
        filtered_groups = {
            k: v for k, v in self._gwi.items() if k not in ["stocks", "other"]
        }
        tuples = tuple(filtered_groups.values())
        return self._portfolio.calculate_weighted_interest(tuples)

    @property
    def yearly_earnings_fixed_income(self):
        # Calculate yearly earnings from group_interest (no stocks)
        filtered_groups = {
            k: v for k, v in self._gwi.items() if k not in ["stocks", "other"]
        }
        yearly = 0
        for principal, interest in filtered_groups.values():
            yearly += round(principal * interest)
        return yearly

    def _calculate_stocks_yearly_income(self):
        # Use yearly_income field from ib_div_details for all stock keys
        total_stock_income = 0
        for symbol in self.stock_data.keys():
            asset_info = self.ib_div_details[symbol]
            total_stock_income += asset_info.yearly_income
        return round(total_stock_income)

    @property
    def yearly_earnings_stocks(self):
        # Now we rely on yearly_income directly from ib_div_details
        return self._calculate_stocks_yearly_income()

    @property
    def calculated_income(self):
        """
        Return a dictionary {group: yearly_income}
        - bonds, crypto_lending, p2p_lending from group weighted interest
        - stocks from yearly_income field of ib_div_details
        """
        income_dict = {}
        # fixed income groups
        for group, (principal, interest) in self._gwi.items():
            if group not in ["stocks", "other"]:
                income_dict[group] = round(principal * interest)

        # Add stocks income from yearly_income
        stocks_income = self._calculate_stocks_yearly_income()
        income_dict["stocks"] = stocks_income

        return income_dict


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
                asset_type="stock",
            ),
            "TLT": AssetInfo(
                market_value=2263,
                yield_rate=0.0414,
                yearly_income=79.63,
                adr_symbol=None,
                asset_type="stock",
            ),
            "9988": AssetInfo(
                market_value=5395,
                yield_rate=0.0116,
                yearly_income=53.19,
                adr_symbol="BABA",
                asset_type="stock",
            ),
            "700": AssetInfo(
                market_value=5303,
                yield_rate=0.0073,
                yearly_income=32.91,
                adr_symbol="TCEHY",
                asset_type="stock",
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
            "COF": AssetInfo(
                market_value=1878,
                yield_rate=0.0128,
                yearly_income=20.43,
                adr_symbol=None,
                asset_type="stock",
            ),
            "NKE": AssetInfo(
                market_value=3632,
                yield_rate=0.0203,
                yearly_income=62.67,
                adr_symbol=None,
                asset_type="stock",
            ),
            "GOOG": AssetInfo(
                market_value=3350,
                yield_rate=0.0046,
                yearly_income=13.1,
                adr_symbol=None,
                asset_type="stock",
            ),
            "BN": AssetInfo(
                market_value=2336,
                yield_rate=0.0054,
                yearly_income=10.72,
                adr_symbol=None,
                asset_type="stock",
            ),
            "CVS": AssetInfo(
                market_value=2105,
                yield_rate=0.0481,
                yearly_income=86.06,
                adr_symbol=None,
                asset_type="stock",
            ),
            "HUM": AssetInfo(
                market_value=1690,
                yield_rate=0.0126,
                yearly_income=18.1,
                adr_symbol=None,
                asset_type="stock",
            ),
            "COP": AssetInfo(
                market_value=1653,
                yield_rate=0.0302,
                yearly_income=42.43,
                adr_symbol=None,
                asset_type="stock",
            ),
            "CVX": AssetInfo(
                market_value=1554,
                yield_rate=0.042,
                yearly_income=55.48,
                adr_symbol=None,
                asset_type="stock",
            ),
            "INTC": AssetInfo(
                market_value=1502,
                yield_rate=0.024,
                yearly_income=30.64,
                adr_symbol=None,
                asset_type="stock",
            ),
            "IBKR": AssetInfo(
                market_value=1161,
                yield_rate=0.0054,
                yearly_income=5.33,
                adr_symbol=None,
                asset_type="stock",
            ),
            "ADBE": AssetInfo(
                market_value=1106,
                yield_rate=0.0,
                yearly_income=0.0,
                adr_symbol=None,
                asset_type="stock",
            ),
            "CP": AssetInfo(
                market_value=828,
                yield_rate=0.0,
                yearly_income=0.0,
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
    print(f"SUMMARY - {data_source.summary}")
    print("\nGroup weighted interest -", data_source.group_weighted_interest, "\n")
    print("Calculated Income:", data_source.calculated_income)
    print("\nTOTAL (fixed income) -", data_source.total_prinicpal_interest_in_p2p)
    print(
        "\nYEARLY P2P DIVIDENDS (Fixed Income) -",
        data_source.yearly_earnings_fixed_income,
        "$",
    )
    print("YEARLY STOCK DIVIDENDS -", data_source.yearly_earnings_stocks, "$")
    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"\nExecution time: {elapsed_time} seconds")
