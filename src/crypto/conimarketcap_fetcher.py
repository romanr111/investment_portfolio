from typing import Dict, List

import src.helpers as helpers
from data.endpoints import COINMARKETCAP_API, COINMARKETCAP_HEADERS

# Token name adjustments
CRYPTO_MAPPINGS: Dict[str, str] = {
    "BETH": "ETH",
    "WBETH": "ETH",
}


class CoinMarketCapFetcher:
    """Fetches and processes cryptocurrency data from the CoinMarketCap API."""

    def __init__(self, tokens: List[str]):
        """
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
            self._crypto_info = helpers.perform_request(
                COINMARKETCAP_API, params, COINMARKETCAP_HEADERS
            )
            print("INFO: Data fetched successfully.")
        return self._crypto_info

    def get_market_price_for(self, crypto_name: str) -> float:
        """
        Get the USD market price for a given cryptocurrency.

        Args:
            crypto_name (str): The symbol of the cryptocurrency.

        Returns:
            float: The USD price of the cryptocurrency, or None if not found.
        """
        self.fetch_data()
        name = CRYPTO_MAPPINGS.get(crypto_name, crypto_name)
        try:
            price = self._crypto_info["data"][name]["quote"]["USD"]["price"]
            return price
        except KeyError:
            print(f"WARNING: Price data for {name} not found.")
            return None
