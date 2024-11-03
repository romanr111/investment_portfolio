from abc import ABC, abstractmethod
from typing import Dict, List

import src.helpers as helpers
from src.crypto.bin import BinanceFiltered
from data.endpoints import COINMARKETCAP_API, COINMARKETCAP_HEADERS
from data.crypto_data import COLD_STORAGE

# Initial tokens to preserve at the beginning
INITIAL_TOKENS: List[str] = ["BTC", "ETH", "ADA", "BNB"]

# Mapping for token name adjustments
CRYPTO_MAPPINGS: Dict[str, str] = {
    "BETH": "ETH",
}


class DataFetcher(ABC):
    """Abstract base class for data fetching."""

    @abstractmethod
    def fetch_data(self) -> Dict:
        """Fetch data from a data source."""
        pass


class DataProcessor(ABC):
    """Abstract base class for data processing."""

    @abstractmethod
    def get_market_price_for(self, crypto_name: str) -> float:
        """Get the market price for a given cryptocurrency."""
        pass


class CoinMarketCapFetcher(DataFetcher):
    """Fetches cryptocurrency data from the CoinMarketCap API."""

    def __init__(self, tokens: List[str]):
        """
        Initialize the fetcher with a list of cryptocurrency symbols.

        Args:
            tokens (List[str]): List of cryptocurrency symbols.
        """
        self.tokens = tokens
        self._crypto_info: Dict = {}

    def fetch_data(self) -> Dict:
        """Fetch data from CoinMarketCap API if not already fetched."""
        if not self._crypto_info:
            symbols = ",".join(self.tokens)
            params = f"?symbol={symbols}"
            try:
                self._crypto_info = helpers.perform_request(
                    COINMARKETCAP_API, params, COINMARKETCAP_HEADERS
                )
                print("INFO: Data fetched successfully.")
            except Exception as e:
                print(f"ERROR: Failed to fetch data: {e}")
                raise
        return self._crypto_info

    def get_market_price_for(self, crypto_name: str) -> float:
        """
        Get the USD market price for a given cryptocurrency.

        Args:
            crypto_name (str): The symbol of the cryptocurrency.

        Returns:
            float: The USD price of the cryptocurrency.

        Raises:
            KeyError: If the cryptocurrency data is not found.
        """
        if not self._crypto_info:
            self.fetch_data()
        name = CRYPTO_MAPPINGS.get(crypto_name, crypto_name)
        try:
            price = self._crypto_info["data"][name]["quote"]["USD"]["price"]
            return price
        except KeyError as e:
            print(f"ERROR: Price data for {name} not found: {e}")
            raise KeyError(f"Price data for {name} not found.") from e


class CryptoData:
    """Handles cryptocurrency data processing."""

    @classmethod
    def get_all_crypto_quantity(cls, broker: BinanceFiltered) -> Dict[str, float]:
        """
        Retrieve all cryptocurrency quantities from the broker and add external balances.

        Args:
            broker (BinanceFiltered): The broker instance.

        Returns:
            Dict[str, float]: A dictionary of cryptocurrency symbols and their quantities.
        """
        crypto = broker.get_all_crypto_balances()

        # Add cold storage crypto balances
        for token, amount in COLD_STORAGE.items():
            crypto[token] = crypto.get(token, 0) + amount

        # Round quantities to 3 decimal places
        for token in crypto:
            crypto[token] = round(crypto[token], 3)

        print(f"DEBUG: All crypto quantities: {crypto}")
        return crypto

    @classmethod
    def get_market_value(
        cls, quantities: Dict[str, float], fetcher: DataProcessor
    ) -> Dict[str, int]:
        """
        Calculate the market value for each cryptocurrency.

        Args:
            quantities (Dict[str, float]): Cryptocurrency quantities.
            fetcher (DataProcessor): An instance to fetch market prices.

        Returns:
            Dict[str, int]: A sorted dictionary of cryptocurrencies and their market values.
        """
        crypto_values: Dict[str, int] = {}
        for crypto, quantity in quantities.items():
            try:
                price = fetcher.get_market_price_for(crypto)
                crypto_values[crypto] = round(quantity * price)
                print(
                    f"DEBUG: {crypto}: {quantity} * {price} = {crypto_values[crypto]}"
                )
            except KeyError:
                print(f"WARNING: Skipping {crypto} due to missing price data.")
        sorted_values = dict(
            sorted(crypto_values.items(), key=lambda item: item[1], reverse=True)
        )
        return sorted_values

    @classmethod
    def get_total(cls, data_dict: Dict[str, int]) -> int:
        """
        Calculate the total market value.

        Args:
            data_dict (Dict[str, int]): Dictionary of market values.

        Returns:
            int: Total market value.
        """
        total = sum(data_dict.values())
        return total

    @classmethod
    def get_all_free_cash_in_stablecoins(cls, accounts: List[BinanceFiltered]) -> float:
        """
        Calculate the total free/non-invested cash in stablecoins across all accounts.

        Args:
            accounts (List[BinanceFiltered]): List of account instances.

        Returns:
            float: Total free cash in stablecoins.
        """
        total = 0.0
        for account in accounts:
            account_total = account.sum_up_all_stablecoins()
            total += account_total
            print(f"DEBUG: Account {account} stablecoins total: {account_total}")
        print(f"INFO: Total free cash in stablecoins: {total}")
        return total


class CryptoEndpoint:
    """Endpoint for accessing cryptocurrency market data and free cash balances."""

    def __init__(self):
        """
        Initialize the CryptoEndpoint with market values and cash balances.
        """
        self.binance = BinanceFiltered()
        self.quantities = CryptoData.get_all_crypto_quantity(self.binance)

        # Tokens from the Binance account
        account_tokens = list(self.quantities.keys())

        # Combine initial tokens with account tokens, preserving order and removing duplicates
        tokens = self._combine_tokens(INITIAL_TOKENS, account_tokens)

        # Initialize CoinMarketCapFetcher with the combined token list
        self.cmc_fetcher = CoinMarketCapFetcher(tokens)

        # Fetch market values
        self.market_val = CryptoData.get_market_value(self.quantities, self.cmc_fetcher)
        self.total_market_val = CryptoData.get_total(self.market_val)
        self.cash = CryptoData.get_all_free_cash_in_stablecoins([self.binance])

    def get_tokens_market_values(self) -> Dict[str, int]:
        """
        Get the market values of each available crypto token.
        """
        return self.market_val

    def get_total_crypto_value(self) -> int:
        """
        Sums up market value of all cryptocurrencies.
        """
        return self.total_market_val

    def get_total_cash(self) -> float:
        """
        Get the total non invested free cash in stablecoins.
        """
        return self.cash

    @staticmethod
    def _combine_tokens(initial: List[str], account: List[str]) -> List[str]:
        """
        Combine initial tokens with account tokens, preserving order and removing duplicates.
        """
        combined = initial.copy()
        for token in account:
            if token not in combined:
                combined.append(token)
        return combined


def main():
    """Main function to execute the CryptoEndpoint."""
    try:
        endpoint = CryptoEndpoint()
        print(f"Crypto Market Values - {endpoint.get_tokens_market_values()}")
        print(f"Total Market Value - {endpoint.get_total_crypto_value()}")
        print(f"Total Crypto Cash - {endpoint.get_total_cash()}")
    except Exception as e:
        print(f"ERROR: An error occurred: {e}")


if __name__ == "__main__":
    main()
