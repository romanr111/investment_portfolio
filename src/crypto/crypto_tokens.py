# -------------------------------- TODO --------------------------------

from typing import Dict, List

from data.crypto_data import COLD_STORAGE
from src.crypto.binance_client import BinanceFiltered
from src.crypto.conimarketcap_fetcher import CoinMarketCapFetcher

INITIAL_TOKENS: List[str] = ["BTC", "ETH", "ADA", "BNB"]


class CryptoData:
    """Handles cryptocurrency data processing."""

    @staticmethod
    def get_all_crypto_quantity(brokers) -> Dict[str, float]:
        """
        Retrieve all cryptocurrency quantities from multiple brokers and add external balances.

        Args:
            brokers (List[]): List of broker instances.

        Returns:
            Dict[str, float]: A combined dictionary of cryptocurrency symbols and their total quantities.
        """
        combined_crypto: Dict[str, float] = {}

        for broker in brokers:
            broker_crypto = broker.get_all_crypto_balances()
            for token, amount in broker_crypto.items():
                combined_crypto[token] = combined_crypto.get(token, 0) + amount

        # Add cold storage crypto balances
        for token, amount in COLD_STORAGE.items():
            combined_crypto[token] = combined_crypto.get(token, 0) + amount

        # Round quantities to 3 decimal places
        combined_crypto = {
            token: round(amount, 3) for token, amount in combined_crypto.items()
        }

        print(f"DEBUG: Combined crypto quantities from all brokers: {combined_crypto}")
        return combined_crypto

    @staticmethod
    def get_market_value(quantities: Dict[str, float], fetcher) -> Dict[str, int]:
        """
        Calculate the market value for each cryptocurrency, including only those with a value greater than 10.

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
                value = round(quantity * price)
                if value > 10:
                    crypto_values[crypto] = value
                    print(f"DEBUG: {crypto}: {quantity} * {price} = {value}")
                else:
                    print(
                        f"DEBUG: {crypto} value {value} is not greater than 10. Skipping."
                    )
            except KeyError:
                print(f"WARNING: Skipping {crypto} due to missing price data.")
        return dict(
            sorted(crypto_values.items(), key=lambda item: item[1], reverse=True)
        )

    @staticmethod
    def get_total(data_dict: Dict[str, int]) -> int:
        """Calculate the total market value of all cryptocurrencies."""
        return sum(data_dict.values())


class CryptoEndpoint:
    """Endpoint for accessing cryptocurrency market data and free cash balances."""

    def __init__(self):
        """Initialize the CryptoEndpoint with market values and cash balances."""
        self.binance = BinanceFiltered()
        brokers = [self.binance]
        self.quantities = CryptoData.get_all_crypto_quantity(brokers)

        # Combine initial tokens with account tokens, preserving order and removing duplicates
        tokens = self._combine_tokens(INITIAL_TOKENS, list(self.quantities.keys()))

        # Initialize CoinMarketCapFetcher with the combined token list
        self.cmc_fetcher = CoinMarketCapFetcher(tokens)

        # Fetch market values
        self.market_val = CryptoData.get_market_value(self.quantities, self.cmc_fetcher)
        self.total_market_val = CryptoData.get_total(self.market_val)

    def get_tokens_market_values(self) -> Dict[str, int]:
        """Get the market values of each available crypto token."""
        return self.market_val

    def get_total_crypto_value(self) -> int:
        """Sum up market value of all cryptocurrencies."""
        return self.total_market_val

    def get_total_cash(self) -> float:
        """Get the total non-invested free cash in stablecoins."""
        # TODO: Implement this method
        pass

    @staticmethod
    def _combine_tokens(initial: List[str], account: List[str]) -> List[str]:
        """
        Combine initial tokens with account tokens, preserving order and removing duplicates.

        Args:
            initial (List[str]): Initial list of tokens.
            account (List[str]): Account's list of tokens.

        Returns:
            List[str]: Combined list of tokens.
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
        print(f"Crypto Market Values: {endpoint.get_tokens_market_values()}")
        print(f"Total Market Value: {endpoint.get_total_crypto_value()}")
    except Exception as e:
        print(f"ERROR: An error occurred: {e}")


if __name__ == "__main__":
    main()
