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


class Crypto:
    """Handles operations related to crypto quantities."""

    @classmethod
    def get_all_crypto_quantity(cls, binance):
        crypto = binance.get_all_crypto_balances()

        for token, amount in EXTERNAL_CRYPTO.items():
            crypto[token] += amount

        for token, amount in crypto.items():
            crypto[token] = round(amount, 3)

        return crypto


class CryptoValue:
    @classmethod
    def get_market_value(cls, quantities, fetcher: DataProcessor):
        crypto_values = {}
        for crypto, quantity in quantities.items():
            price = fetcher.get_market_price_for(crypto)
            crypto_values[crypto] = round(quantity * price)
        return dict(sorted(crypto_values.items(), key=lambda x: x[1], reverse=True))

    @classmethod
    def get_crypto_total_market_value(cls, crypto_market_values):
        return sum(crypto_market_values.values())


if __name__ == "__main__":
    binance = BinanceFiltered()
    quantities = Crypto.get_all_crypto_quantity(binance)
    fetcher = CoinMarketCapFetcher()
    market_values = CryptoValue.get_market_value(quantities, fetcher)
    total_market_value = CryptoValue.get_crypto_total_market_value(market_values)

    print(f"Crypto Quantities - {quantities}")
    print(f"Crypto Market Values - {market_values}")
    print(f"Total Market Value - {total_market_value}")
