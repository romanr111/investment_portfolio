from abc import ABC, abstractmethod
import src.helpers as helpers
from src.crypto.bin import BinanceFiltered
from data.endpoints import COINMARKETCAP_API, COINMARKETCAP_HEADERS
from data.crypto_data import EXTERNAL_CRYPTO

SYMBOLS = "?symbol=BTC,ETH,ADA,BNB,EOS,NEO,LUNA,MATIC,NEAR,FTM,OMG,SC,ETHW"
CRYPTO_MAPPINGS = {
    "BETH": "ETH",
}


class DataFetcher(ABC):
    @abstractmethod
    def fetch_data(self):
        pass


class DataProcessor(ABC):
    @abstractmethod
    def get_market_price_for(self, crypto_name):
        pass


class CoinMarketCapFetcher(DataFetcher, DataProcessor):
    _info = None

    @classmethod
    def fetch_data(cls):
        if cls._info is None:
            cls._info = helpers.perform_request(
                COINMARKETCAP_API, SYMBOLS, COINMARKETCAP_HEADERS
            )
        return cls._info

    @classmethod
    def get_market_price_for(cls, crypto_name):
        if cls._info is None:
            cls.fetch_data()
        mapped_name = CRYPTO_MAPPINGS.get(crypto_name, crypto_name)
        return cls._info["data"][mapped_name]["quote"]["USD"]["price"]


class CryptoData:
    @classmethod
    def get_all_crypto_quantity(cls, broker):
        crypto = broker.get_all_crypto_balances()

        for token, amount in EXTERNAL_CRYPTO.items():
            crypto[token] += amount

        for token, amount in crypto.items():
            crypto[token] = round(amount, 3)

        return crypto

    @classmethod
    def get_market_value(cls, quantities, fetcher: DataProcessor):
        crypto_values = {}
        for crypto, quantity in quantities.items():
            price = fetcher.get_market_price_for(crypto)
            crypto_values[crypto] = round(quantity * price)
        return dict(sorted(crypto_values.items(), key=lambda x: x[1], reverse=True))

    @classmethod
    def get_total(cls, data_dict):
        return sum(data_dict.values())

    @classmethod
    def get_all_free_cash_in_stablecoins(cls, accounts):
        total = 0
        for account in accounts:
            total += account.sum_up_all_stablecoins()
        return total


class CryptoEndpoint:
    def __init__(self):
        self.binance = BinanceFiltered()
        self.cmc_fetcher = CoinMarketCapFetcher()
        self.quantities = CryptoData.get_all_crypto_quantity(self.binance)
        self.market_val = CryptoData.get_market_value(self.quantities, self.cmc_fetcher)
        self.total_market_val = CryptoData.get_total(self.market_val)
        self.cash = CryptoData.get_all_free_cash_in_stablecoins([self.binance])

    def get_crypto_market_values(self):
        return self.market_val

    def get_total_crypto_market_value(self):
        return self.total_market_val

    def get_total_cash(self):
        return self.cash


if __name__ == "__main__":
    endpoint = CryptoEndpoint()
    print(f"Crypto Market Values - {endpoint.get_crypto_market_values()}")
    print(f"Total Market Value - {endpoint.get_total_crypto_market_value()}")
    print(f"Total Crypto Cash - {endpoint.get_total_cash()}")
