from typing import Dict, List, Tuple
import logging
import time
import traceback
from data.assets_data import COLD_STORAGE
from src.crypto.base_exchange_client import ExchangeBase
from src.crypto.binance_client import BinanceClient
from src.crypto.okx_client import OKXFiltered
from src.crypto.whitebit_client import WhiteBit
from src.crypto.bybit_client import BybitFiltered
from src.crypto.conimarketcap_fetcher import CoinMarketCapFetcher

# Set up logging
logger = logging.getLogger(__name__)

# Global configuration
API_CALL_TIMEOUT = 10  # seconds
INITIAL_TOKENS: List[str] = ["BTC", "ETH", "BNB", "ADA"]


class CryptoData:
    """Handles cryptocurrency data processing and aggregation."""

    @staticmethod
    def get_all_savings_positions(
        brokers: List[ExchangeBase],
    ) -> List[Dict[str, Tuple[float, float]]]:
        """
        Collects savings positions from all brokers into a list.

        Args:
            brokers: List of broker instances implementing ExchangeBase.

        Returns:
            List[Dict[str, Tuple[float, float]]]: List of savings positions from each broker
        """
        logger.debug("Getting all savings positions from brokers")
        positions = []

        for broker in brokers:
            logger.debug(f"Getting savings positions from {broker.__class__.__name__}")
            try:
                start_time = time.time()
                broker_positions = broker.get_savings_positions()
                logger.debug(
                    f"get_savings_positions for {broker.__class__.__name__} took {time.time() - start_time:.2f} seconds"
                )
                if broker_positions:
                    positions.append(broker_positions)
                logger.debug(
                    f"Retrieved {len(broker_positions) if broker_positions else 0} positions"
                )
            except Exception as e:
                logger.error(
                    f"Error getting savings positions from {broker.__class__.__name__}: {str(e)}"
                )
                logger.error(f"Stack trace: {traceback.format_exc()}")

        logger.debug(f"Total savings positions: {len(positions)}")
        return positions

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
        logger.debug("Getting all crypto quantities from brokers")
        combined_crypto: Dict[str, float] = {}

        for broker in brokers:
            logger.debug(f"Getting crypto balances from {broker.__class__.__name__}")
            try:
                start_time = time.time()
                broker_crypto = broker.get_all_crypto_balances()
                logger.debug(
                    f"get_all_crypto_balances for {broker.__class__.__name__} took {time.time() - start_time:.2f} seconds"
                )
                for token, amount in broker_crypto.items():
                    if token not in ExchangeBase.STABLECOINS:
                        combined_crypto[token] = combined_crypto.get(token, 0) + amount
                logger.debug(
                    f"Retrieved {len(broker_crypto)} tokens from {broker.__class__.__name__}"
                )
            except Exception as e:
                logger.error(
                    f"Error getting crypto balances from {broker.__class__.__name__}: {str(e)}"
                )
                logger.error(f"Stack trace: {traceback.format_exc()}")

        # Add cold storage crypto balances
        logger.debug("Adding cold storage balances")
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

        logger.debug(f"Total unique tokens: {len(sorted_crypto)}")
        return sorted_crypto

    @staticmethod
    def calculate_free_cash_balance(brokers: List[ExchangeBase]) -> int:
        """
        Get total free cash balance across all brokers.
        Sums up integer balances from get_cash_balance().
        """
        logger.debug("Calculating free cash balance from brokers")
        total_balance = 0

        for broker in brokers:
            try:
                logger.debug(f"Getting cash balance from {broker.__class__.__name__}")
                balance = broker.get_cash_balance()
                if balance >= 1:
                    total_balance += balance
                logger.debug(
                    f"Retrieved cash balance: {balance} from {broker.__class__.__name__}"
                )
            except Exception as e:
                logger.error(
                    f"Error getting cash balance from {broker.__class__.__name__}: {str(e)}",
                    exc_info=True,
                )

        logger.debug(f"Total free cash balance: {total_balance}")
        return total_balance

    @staticmethod
    def get_market_value(
        quantities: Dict[str, float],
        fetcher: CoinMarketCapFetcher,
        min_value: int = 1,
    ) -> Dict[str, int]:
        """
        Get market values for cryptocurrencies based on their quantities.

        Args:
            quantities: Dictionary of cryptocurrency symbols and their quantities.
            fetcher: Price fetcher object to get market prices.
            min_value: Minimum value to include in the result (default 1 USD).

        Returns:
            Dict[str, int]: Sorted dictionary of cryptocurrencies and their market values.
        """
        logger.debug("Calculating market values for crypto quantities")
        crypto_values: Dict[str, int] = {}

        for crypto, quantity in quantities.items():
            if crypto == "UAH":
                continue
            try:
                logger.debug(f"Getting market price for {crypto}")
                price = fetcher.get_market_price_for(crypto)

                # Skip if price is None or not available
                if price is None:
                    logger.warning(f"No price data available for {crypto}")
                    continue

                value = round(quantity * price)
                if value >= min_value:
                    crypto_values[crypto] = value
                logger.debug(
                    f"{crypto}: quantity={quantity}, price=${price}, value=${value}"
                )
            except KeyError:
                logger.warning(f"Missing price data for {crypto}")
                continue
            except Exception as e:
                logger.error(
                    f"Error getting market price for {crypto}: {str(e)}", exc_info=True
                )

        logger.debug(f"Calculated market values for {len(crypto_values)} tokens")
        return dict(sorted(crypto_values.items(), key=lambda x: x[1], reverse=True))


class CryptoEndpoint:
    """Endpoint for accessing aggregated cryptocurrency data across exchanges."""

    def __init__(self):
        """Initialize CryptoEndpoint with all necessary components."""
        logger.debug("Initializing CryptoEndpoint - constructor start")

        # Initialize with default empty values
        self.brokers: List[ExchangeBase] = []
        self.quantities = {}
        self.crypto_market_values = {}
        self.free_cash = 0
        self.all_crypto_savings = []

        try:
            logger.debug("Creating broker instances")

            # Initialize each broker with safety checks
            self._safe_init_binance()
            self._safe_init_okx()
            self._safe_init_bybit()
            self._safe_init_whitebit()

            # Skip rest of initialization if no brokers were initialized
            if not self.brokers:
                logger.warning("No crypto brokers were successfully initialized")
                return

            logger.debug("Getting all crypto quantities - start")
            start_time = time.time()
            try:
                self.quantities = CryptoData.get_all_crypto_quantity(self.brokers)
                logger.debug(
                    f"Crypto quantities retrieved in {time.time() - start_time:.2f} seconds"
                )
            except Exception as e:
                logger.error(f"Error getting crypto quantities: {str(e)}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.quantities = {}

            # Skip rest of initialization if no quantities were retrieved
            if not self.quantities:
                logger.warning("No crypto quantities were retrieved")
                return

            logger.debug("Initializing CoinMarketCapFetcher - start")
            start_time = time.time()
            try:
                self.cmc_fetcher = CoinMarketCapFetcher(self.quantities)
                logger.debug(
                    f"CoinMarketCapFetcher initialized in {time.time() - start_time:.2f} seconds"
                )
            except Exception as e:
                logger.error(f"Error initializing CoinMarketCapFetcher: {str(e)}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                # Create empty market values
                self.crypto_market_values = {}
                self.free_cash = 0
                self.all_crypto_savings = []
                return

            logger.debug("Getting market values - start")
            start_time = time.time()
            try:
                self.crypto_market_values = CryptoData.get_market_value(
                    self.quantities, self.cmc_fetcher
                )
                logger.debug(
                    f"Market values retrieved in {time.time() - start_time:.2f} seconds"
                )
            except Exception as e:
                logger.error(f"Error getting market values: {str(e)}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.crypto_market_values = {}

            logger.debug("Calculating free cash - start")
            start_time = time.time()
            try:
                self.free_cash = CryptoData.calculate_free_cash_balance(self.brokers)
                logger.debug(
                    f"Free cash calculated in {time.time() - start_time:.2f} seconds"
                )
            except Exception as e:
                logger.error(f"Error calculating free cash: {str(e)}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.free_cash = 0

            logger.debug("Getting all crypto savings - start")
            start_time = time.time()
            try:
                self.all_crypto_savings = CryptoData.get_all_savings_positions(
                    self.brokers
                )
                logger.debug(
                    f"Crypto savings retrieved in {time.time() - start_time:.2f} seconds"
                )
            except Exception as e:
                logger.error(f"Error getting crypto savings: {str(e)}")
                logger.error(f"Stack trace: {traceback.format_exc()}")
                self.all_crypto_savings = []

            logger.debug("CryptoEndpoint initialization completed")
        except Exception as e:
            logger.error(f"Error in CryptoEndpoint initialization: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")

    def _safe_init_binance(self):
        """Initialize BinanceClient with error handling."""
        try:
            logger.debug("Initializing BinanceClient - start")
            start_time = time.time()
            binance_client = BinanceClient()
            self.brokers.append(binance_client)
            logger.debug(
                f"BinanceClient initialized in {time.time() - start_time:.2f} seconds"
            )
        except Exception as e:
            logger.error(f"Error initializing BinanceClient: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            logger.warning("Continuing without BinanceClient")

    def _safe_init_okx(self):
        """Initialize OKXFiltered with error handling."""
        try:
            logger.debug("Initializing OKXFiltered - start")
            start_time = time.time()
            okx_client = OKXFiltered()
            self.brokers.append(okx_client)
            logger.debug(
                f"OKXFiltered initialized in {time.time() - start_time:.2f} seconds"
            )
        except Exception as e:
            logger.error(f"Error initializing OKXFiltered: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            logger.warning("Continuing without OKXFiltered")

    def _safe_init_bybit(self):
        """Initialize BybitFiltered with error handling."""
        try:
            logger.debug("Initializing BybitFiltered - start")
            start_time = time.time()
            bybit_client = BybitFiltered()
            self.brokers.append(bybit_client)
            logger.debug(
                f"BybitFiltered initialized in {time.time() - start_time:.2f} seconds"
            )
        except Exception as e:
            logger.error(f"Error initializing BybitFiltered: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            logger.warning("Continuing without BybitFiltered")

    def _safe_init_whitebit(self):
        """Initialize WhiteBit with error handling."""
        try:
            logger.debug("Initializing WhiteBit - start")
            start_time = time.time()
            whitebit_client = WhiteBit()
            self.brokers.append(whitebit_client)
            logger.debug(
                f"WhiteBit initialized in {time.time() - start_time:.2f} seconds"
            )
        except Exception as e:
            logger.error(f"Error initializing WhiteBit: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            logger.warning("Continuing without WhiteBit")

    def get_total_crypto_value(self) -> int:
        logger.debug("Calculating total crypto value")
        total = sum(self.crypto_market_values.values())
        logger.debug(f"Total crypto value: {total}")
        return total


def main():
    """Main function to demonstrate usage."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting CryptoEndpoint test run")
    try:
        crypto_endpoint = CryptoEndpoint()
        print(f"\nCrypto quantities --> {crypto_endpoint.quantities}")

        print("\nCrypto Market Values:")
        for token, value in crypto_endpoint.crypto_market_values.items():
            print(f"{token}: ${value:,}")

        print(f"\nTotal Crypto Value: ${crypto_endpoint.get_total_crypto_value():,}")

        print(f"\nTotal Free Cash: {crypto_endpoint.free_cash}")

        print(f"\n All Crypto Savings: {crypto_endpoint.all_crypto_savings}")
        logger.info("CryptoEndpoint test run completed successfully")
    except Exception as e:
        logger.error(f"ERROR: An error occurred: {str(e)}", exc_info=True)
        print(f"ERROR: An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
