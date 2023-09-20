import src.helpers as helpers
from src.crypto.bin import BinanceFiltered
from data.endpoints import COINMARKETCAP_API, COINMARKETCAP_HEADERS
from data.crypto_data import EXTERNAL_CRYPTO

SYMBOLS = "?symbol=BTC,ETH,ADA,BNB,EOS,NEO,LUNA,MATIC,NEAR,FTM,OMG,SC"

CRYPTO_MAPPINGS = {
    "BETH": "ETH",
    "ETHW": "ETH",
    # Add more mappings as needed
}


class Crypto:
    """Handles operations related to crypto quantities."""

    binance = BinanceFiltered()

    @classmethod
    def get_all_crypto_quantity(cls):
        crypto = cls.binance.get_all_crypto_balances()

        for token, amount in EXTERNAL_CRYPTO.items():
            crypto[token] += amount

        for token, amount in crypto.items():
            crypto[token] = round(amount, 3)

        return crypto


class MarketValueFetcher:
    """Fetches and holds the market values for various cryptos."""

    coinmarketcap_crypto_info = helpers.perform_request(
        COINMARKETCAP_API, SYMBOLS, COINMARKETCAP_HEADERS
    )

    @classmethod
    def get_market_price_for(cls, crypto_name):
        mapped_name = CRYPTO_MAPPINGS.get(crypto_name, crypto_name)
        return cls.coinmarketcap_crypto_info["data"][mapped_name]["quote"]["USD"][
            "price"
        ]


class CryptoMarketValue:
    """Calculates market value for various crypto assets."""

    @classmethod
    def get_crypto_market_value(cls, crypto_quantities):
        crypto_values = {}
        for crypto, quantity in crypto_quantities.items():
            price = MarketValueFetcher.get_market_price_for(crypto)
            crypto_values[crypto] = round(quantity * price)

        return dict(sorted(crypto_values.items(), key=lambda x: x[1], reverse=True))

    @classmethod
    def get_crypto_total_market_value(cls, crypto_market_values):
        return sum(crypto_market_values.values())


if __name__ == "__main__":
    crypto_quantities = Crypto.get_all_crypto_quantity()
    market_values = CryptoMarketValue.get_crypto_market_value(crypto_quantities)
    total_market_value = CryptoMarketValue.get_crypto_total_market_value(market_values)

    print(f"Crypto Quantities - {crypto_quantities}")
    print(f"Crypto Market Values - {market_values}")
    print(f"Total Market Value - {total_market_value}")
