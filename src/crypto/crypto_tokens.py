# TODO: To review cold storage data to be up to date;
# TODO: Probably make it one endpoint to initiate when providing data to cash and fixed income module /
# Along with providing data to spreadsheet formatter; e.g. I could initialize it and provide data as arguments to /
# other modules who needs crypto related data;

from typing import Dict, List
from data.crypto_data import COLD_STORAGE
from src.crypto.base_exchange_client import ExchangeBase
from src.crypto.binance_client import BinanceClient
from src.crypto.okx_client import OKXFiltered
from src.crypto.whitebit_client import WhiteBit
from src.crypto.bybit_client import BybitFiltered
from src.crypto.conimarketcap_fetcher import CoinMarketCapFetcher

INITIAL_TOKENS: List[str] = ["BTC", "ETH", "BNB", "ADA"]


class CryptoData:
    """Handles cryptocurrency data processing and aggregation."""

    @staticmethod
    def get_all_crypto_quantity(brokers: List[ExchangeBase]) -> Dict[str, float]:
        """
        Retrieve all cryptocurrency quantities from multiple brokers and add external balances.
        Returns quantities sorted by INITIAL_TOKENS order, followed by remaining tokens.

        Args:
            brokers: List of broker instances implementing ExchangeBase.

        Returns:
            Dict[str, float]: Combined dictionary of cryptocurrency symbols and their total quantities,
            ordered based on INITIAL_TOKENS.
        """
        combined_crypto: Dict[str, float] = {}

        for broker in brokers:
            broker_crypto = broker.get_all_crypto_balances()
            for token, amount in broker_crypto.items():
                if token not in ExchangeBase.STABLECOINS:
                    combined_crypto[token] = combined_crypto.get(token, 0) + amount

        # Add cold storage crypto balances
        for token, amount in COLD_STORAGE.items():
            if token not in ExchangeBase.STABLECOINS:
                combined_crypto[token] = combined_crypto.get(token, 0) + amount

        sorted_crypto = {}

        # First add tokens from INITIAL_TOKENS if they exist in quantities
        for token in INITIAL_TOKENS:
            if token in combined_crypto:
                sorted_crypto[token] = round(
                    combined_crypto[token], ExchangeBase.ROUND_DECIMALS
                )

        # Then add remaining tokens
        for token, amount in combined_crypto.items():
            if token not in INITIAL_TOKENS:
                sorted_crypto[token] = round(amount, ExchangeBase.ROUND_DECIMALS)

        return sorted_crypto

    @staticmethod
    def get_free_cash_balances(brokers: List[ExchangeBase]) -> Dict[str, float]:
        """
        Get total free cash (stablecoin) balances across all brokers.

        Args:
            brokers: List of broker instances implementing ExchangeBase.

        Returns:
            Dict[str, float]: Combined stablecoin balances.
        """
        combined_cash: Dict[str, float] = {}

        for broker in brokers:
            balances = broker.get_spot_account_balances()
            print(f"balances --> {balances}")
            stablecoin_balances = {
                asset: balance
                for asset, balance in balances.items()
                if asset in ExchangeBase.STABLECOINS and balance >= 1
            }
            for asset, balance in stablecoin_balances.items():
                combined_cash[asset] = combined_cash.get(asset, 0) + balance

        return {asset: round(bal, 2) for asset, bal in combined_cash.items()}

    @staticmethod
    def get_market_value(
        quantities: Dict[str, float], fetcher: CoinMarketCapFetcher, min_value: int = 10
    ) -> Dict[str, int]:
        """
        Calculate market value for each cryptocurrency.

        Args:
            quantities: Cryptocurrency quantities.
            fetcher: Instance to fetch market prices.
            min_value: Minimum value threshold (default: 10).

        Returns:
            Dict[str, int]: Sorted dictionary of cryptocurrencies and their market values.
        """
        crypto_values: Dict[str, int] = {}

        for crypto, quantity in quantities.items():
            try:
                price = fetcher.get_market_price_for(crypto)
                value = round(quantity * price)
                if value >= min_value:
                    crypto_values[crypto] = value
            except KeyError:
                print(f"WARNING: Missing price data for {crypto}")
                continue

        return dict(sorted(crypto_values.items(), key=lambda x: x[1], reverse=True))


class CryptoEndpoint:
    """Endpoint for accessing aggregated cryptocurrency data across exchanges."""

    def __init__(self):
        """Initialize CryptoEndpoint with all necessary components."""
        self.brokers: List[ExchangeBase] = [
            BinanceClient(),
            OKXFiltered(),
            BybitFiltered(),
            WhiteBit(),
        ]
        self.quantities = CryptoData.get_all_crypto_quantity(self.brokers)
        tokens = self._combine_tokens(INITIAL_TOKENS, list(self.quantities.keys()))
        print(f"Crypto quantities --> {self.quantities}")

        self.cmc_fetcher = CoinMarketCapFetcher(tokens)
        self.market_values = CryptoData.get_market_value(
            self.quantities, self.cmc_fetcher
        )
        self.free_cash = CryptoData.get_free_cash_balances(self.brokers)

    def get_tokens_market_values(self) -> Dict[str, int]:
        return self.market_values

    def get_total_crypto_value(self) -> int:
        return sum(self.market_values.values())

    def get_total_cash(self) -> float:
        return sum(self.free_cash.values())

    @staticmethod
    def _combine_tokens(initial: List[str], account: List[str]) -> List[str]:
        """
        Combine initial tokens with account tokens, preserving order and removing duplicates.

        Args:
            initial: Initial list of tokens.
            account: Account's list of tokens.

        Returns:
            Combined list of tokens.
        """
        seen = set(initial)
        combined = initial.copy()

        for token in account:
            if token not in seen:
                combined.append(token)
                seen.add(token)

        return combined


def main():
    """Main function to demonstrate usage."""
    try:
        endpoint = CryptoEndpoint()
        market_values = endpoint.get_tokens_market_values()

        print("\nCrypto Market Values:")
        for token, value in market_values.items():
            print(f"{token}: ${value:,}")
        print(f"Total Crypto Value: ${endpoint.get_total_crypto_value():,}")

        print(f"\nTotal Free Cash: ${endpoint.get_total_cash():,.2f}")

    except Exception as e:
        print(f"ERROR: An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
