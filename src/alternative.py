from abc import ABC, abstractmethod
from data.api_keys import PHYS_GOLD_API_KEY
from data.endpoints import PHYS_GOLD_ENDPOINT
from data.assets_data import INVESTMENT_EQUIPMENT, GLD_GRAMS_AVAILABLE
import src.helpers as helpers

CURRENCY = "USD"
METAL = "XAU"
PARAM = METAL + "/" + CURRENCY
GLD_HEADER = {"x-access-token": PHYS_GOLD_API_KEY}


class DataFetcher(ABC):
    @abstractmethod
    def fetch_data(self, endpoint, param, headers):
        pass


class PhysGoldDataFetcher(DataFetcher):
    @classmethod
    def fetch_data(cls, endpoint, param):
        return helpers.perform_request(endpoint, param, header=GLD_HEADER)


class InvestmentEquipment:
    _VALUE = INVESTMENT_EQUIPMENT

    @property
    def value(self):
        return self._VALUE


class PhysGold:
    def __init__(self, fetcher: DataFetcher):
        self.fetcher = fetcher
        self.response = self.fetcher.fetch_data(PHYS_GOLD_ENDPOINT, PARAM)

    def get_phys_gold_g_price(self):
        price = self.response["prev_close_price"]
        gram = round(price) / 31.1
        return gram

    def get_total_phys_gold_value(self):
        gram_price = self.get_phys_gold_g_price()
        ua_market = 1.07
        total = gram_price * GLD_GRAMS_AVAILABLE * ua_market
        return round(total)


if __name__ == "__main__":
    fetcher = PhysGoldDataFetcher()
    phys_gold = PhysGold(fetcher)

    print(f"Gold Price per Gram: {phys_gold.get_phys_gold_g_price()}")
    print(f"Total Physical Gold Value: {phys_gold.get_total_phys_gold_value()}")
