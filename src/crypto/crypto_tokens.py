from typing import Dict, List, Optional, Tuple
import logging
import time
import traceback
from data.assets_data import COLD_STORAGE
from src.crypto.base_exchange_client import ExchangeBase
from src.crypto.binance_client import BinanceClient
from src.crypto.okx_client import OKXFiltered
from src.crypto.whitebit_client import WhiteBit, WhiteBitFallback

# from src.crypto.bybit_client import BybitFiltered  # Commented out: disable Bybit
from src.crypto.telegram_client import TelegramClient
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
                    positions.append({
                        platform: {asset: values for asset, values in savings.items()
                                   if asset.upper() not in ExchangeBase.CASH_EQUIVALENTS}
                        for platform, savings in broker_positions.items()
                    })
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
    def get_all_crypto_quantity(
        brokers: List[ExchangeBase],
        source_status: Optional[Dict[str, str]] = None,
    ) -> Dict[str, float]:
        """
        Retrieve all cryptocurrency quantities from multiple brokers and add external balances.
        Returns quantities sorted by INITIAL_TOKENS order, followed by remaining tokens.

        When `source_status` is given, it records "ok"/"failed" per broker class
        name so callers can distinguish a genuinely empty aggregate from one
        whose data is incomplete because a balance source failed.

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
                if source_status is not None:
                    source_status[broker.__class__.__name__] = "ok"
            except Exception as e:
                logger.error(
                    f"Error getting crypto balances from {broker.__class__.__name__}: {str(e)}"
                )
                logger.error(f"Stack trace: {traceback.format_exc()}")
                if source_status is not None:
                    source_status[broker.__class__.__name__] = "failed"

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
    def calculate_free_cash_balance(
        brokers: List[ExchangeBase], cash_equivalent_values: Optional[Dict[str, float]] = None
    ) -> int:
        """
        Get total free cash balance across all brokers.
        Sums up integer balances from get_cash_balance().
        """
        logger.debug("Calculating free cash balance from brokers")
        if cash_equivalent_values is not None:
            cash_equivalent_values.clear()
            cash_equivalent_values.update({asset.upper(): round(float(amount))
                for asset, amount in COLD_STORAGE.items()
                if asset.upper() in ExchangeBase.CASH_EQUIVALENTS})
        total_balance = round(sum(
            float(amount) for asset, amount in COLD_STORAGE.items()
            if asset.upper() in ExchangeBase.CASH_EQUIVALENTS
        ))

        for broker in brokers:
            try:
                logger.debug(f"Getting cash balance from {broker.__class__.__name__}")
                balance = broker.get_cash_balance()
                if balance >= 1:
                    total_balance += balance
                # USD1 Earn principal is cash, not an interest-bearing bucket.
                savings_positions = broker.get_savings_positions()
                cash_earn = sum(
                    float(values[0])
                    for savings in savings_positions.values()
                    for asset, values in savings.items()
                    if asset.upper() in ExchangeBase.CASH_EQUIVALENTS
                )
                total_balance += round(cash_earn)
                if cash_equivalent_values is not None:
                    for asset in ExchangeBase.CASH_EQUIVALENTS:
                        spot = getattr(broker, "cash_equivalent_balances", {}).get(asset, 0)
                        cash_equivalent_values[asset] = cash_equivalent_values.get(asset, 0) + float(spot)
                    for savings in savings_positions.values():
                        for asset, values in savings.items():
                            if asset.upper() in ExchangeBase.CASH_EQUIVALENTS:
                                cash_equivalent_values[asset.upper()] = (
                                    cash_equivalent_values.get(asset.upper(), 0) + round(float(values[0]))
                                )
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
        self.balance_source_status: Dict[str, str] = {}
        self.crypto_market_values = {}
        self.free_cash = 0
        self.cash_equivalent_values = {}
        self.all_crypto_savings = []

        try:
            logger.debug("Creating broker instances")

            # Initialize each broker with safety checks
            self._safe_init_binance()
            self._safe_init_okx()
            # self._safe_init_bybit()  # Commented out: disable Bybit initialization
            self._safe_init_whitebit()
            self._safe_init_telegram()

            # Skip rest of initialization if no brokers were initialized
            if not self.brokers:
                logger.warning("No crypto brokers were successfully initialized")
                return

            logger.debug("Getting all crypto quantities - start")
            start_time = time.time()
            try:
                fetch_status: Dict[str, str] = {}
                self.quantities = CryptoData.get_all_crypto_quantity(
                    self.brokers, fetch_status
                )
                self.balance_source_status.update(fetch_status)
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
                self.free_cash = CryptoData.calculate_free_cash_balance(
                    self.brokers, self.cash_equivalent_values
                )
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
            self.balance_source_status["BinanceClient"] = "failed"

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
            self.balance_source_status["OKXFiltered"] = "failed"

    def _safe_init_bybit(self):
        """Bybit initialization is disabled."""
        # Intentionally disabled
        return

    def _safe_init_whitebit(self):
        """Initialize WhiteBit with error handling and fallback to hardcoded data."""
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
            logger.warning("Attempting to use WhiteBit fallback with hardcoded data")

            try:
                logger.debug("Initializing WhiteBitFallback - start")
                start_time = time.time()
                whitebit_fallback = WhiteBitFallback()
                self.brokers.append(whitebit_fallback)
                logger.debug(
                    f"WhiteBitFallback initialized in {time.time() - start_time:.2f} seconds"
                )
                logger.info(
                    "WhiteBit fallback successfully initialized with hardcoded data"
                )
            except Exception as fallback_error:
                logger.error(
                    f"Error initializing WhiteBitFallback: {str(fallback_error)}"
                )
                logger.error(f"Stack trace: {traceback.format_exc()}")
                logger.warning("Continuing without WhiteBit")
                self.balance_source_status["WhiteBit"] = "failed"

    def _safe_init_telegram(self):
        """Initialize TelegramClient with error handling."""
        try:
            logger.debug("Initializing TelegramClient - start")
            start_time = time.time()
            telegram_client = TelegramClient()
            self.brokers.append(telegram_client)
            logger.debug(
                f"TelegramClient initialized in {time.time() - start_time:.2f} seconds"
            )
        except Exception as e:
            logger.error(f"Error initializing TelegramClient: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            logger.warning("Continuing without TelegramClient")
            self.balance_source_status["TelegramClient"] = "failed"

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
