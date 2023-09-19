import src.helpers as helpers
from src.crypto.bin import BinanceFiltered
from data.endpoints import COINMARKETCAP_API, COINMARKETCAP_HEADERS
from data.crypto_data import EXTERNAL_CRYPTO


class Crypto:
    """Grouping and of crypto related data is performed here."""

    binance = BinanceFiltered()

    @classmethod
    def get_all_free_cash_in_stablecoins(cls):
        """
        Returns:
            int: Sums up all uninvested cash in stablecoins.
        """
        return cls.binance.get_spot_account_cash_balance()

    @classmethod
    def _get_all_crypto_quantity(cls):
        """Sums up Binance crypto and crypto from other wallets that are without API support

        Returns:
           defaultdict: Maps crypto names with their total quantity.
        """
        crypto = cls.binance.get_all_crypto_balances()

        for token, amount in EXTERNAL_CRYPTO.items():
            crypto[token] += amount

        for token, amount in crypto.items():
            crypto[token] = round(amount, 3)

        return crypto


class CryptoMarketValue(Crypto):
    """Representation of crypto market value is performed here."""

    symbols = "?symbol=BTC,ETH,ADA,BNB,EOS,NEO,LUNA,MATIC,NEAR,FTM,OMG,SC"
    coinmarketcap_crypto_info = helpers.perform_request(
        COINMARKETCAP_API, symbols, COINMARKETCAP_HEADERS
    )

    @classmethod
    def get_crypto_market_value(cls):
        """Calculates market value for each crypto available in portfolio.

        Returns:
           dict: Maps crypto names with their market value.
        """
        crypto_quantity = cls._get_all_crypto_quantity()
        crypto_market_value = {}
        crypto_value = {}

        for crypto in crypto_quantity.keys():
            crypto_market_value.update(
                {crypto: cls.coinmarketcap_crypto_info["data"][crypto]["quote"]["USD"]}
            )

        for crypto, price, quantity in zip(
            list(crypto_market_value.keys()),
            list(crypto_market_value.values()),
            list(crypto_quantity.values()),
        ):
            value = round(quantity * price["price"])
            crypto_value[crypto] = value

        sorted_dict = dict(
            sorted(crypto_value.items(), key=lambda x: x[1], reverse=True)
        )

        return sorted_dict

    @classmethod
    def get_crypto_total_market_value(cls):
        """
        Returns:
           int: Calculates total market value of all crypto available in portfolio.
        """
        crypto = cls.get_crypto_market_value()
        totalValue = 0

        for crypto in crypto.values():
            totalValue += crypto

        return totalValue

    @classmethod
    def get_mining_value(cls):
        nanopool_balance = 0.03749
        assets_price = 1400
        eth_market_price = cls.coinmarketcap_crypto_info["data"]["ETH"]["quote"]["USD"][
            "price"
        ]

        eth_value = round(nanopool_balance * eth_market_price)
        total = eth_value + assets_price

        return total
