import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple, Any

from data.filters_constants import (
    BONDS_KEY,
    CHINA_STOCKS_KEY,
    HK_TO_ADR_MAP,
    STOCKS_KEY,
    BONDS_VALUES,
)
from src.brokers.ib import InteractiveBrokers
from src.brokers.ib_bond_data_fetcher import IBBondsClient
from src.brokers.data_fetchers.yfinance_fetcher import YFinanceFetcher

# Configure loggin
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(), logging.FileHandler("ib_dividends_debug.log")],
)

# Set specific log levels for noisy loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.INFO)
logging.getLogger("peewee").setLevel(logging.WARNING)  # Reduce peewee debug logging
logger = logging.getLogger(__name__)


# Data Models
@dataclass
class AssetInfo:
    """Represents detailed information about a financial asset."""

    market_value: float
    yield_rate: float
    yearly_income: float
    adr_symbol: Optional[str]
    asset_type: str  # "bond", "stock", or "bond_etf"


@dataclass
class PortfolioSummary:
    """Represents a summary of portfolio performance metrics."""

    monthly_total: float
    yearly_total: float
    stock_yearly: float
    asset_details: Dict[str, AssetInfo]


# Abstract Base Classes
class AssetProcessor(ABC):
    """Abstract base class for processing different types of assets."""

    @abstractmethod
    def can_process(self, symbol: str) -> bool:
        """Determines if this processor can handle the given symbol."""
        pass

    @abstractmethod
    def calculate_yearly_income(self, symbol: str, market_value: float) -> AssetInfo:
        """Calculates yearly income for the given symbol."""
        pass


class DataFetcher(ABC):
    """Abstract base class for fetching asset data."""

    @abstractmethod
    def fetch_data(self, symbol: str) -> Dict[str, Any]:
        """Fetches data for the given symbol."""
        pass


# Concrete Implementation Classes
class YFinanceDataFetcher(DataFetcher):
    """Handles fetching data for stocks and ETFs using yfinance exclusively."""

    def __init__(self, adr_map: Dict[str, str]):
        self.adr_map = adr_map
        self.yfinance_fetcher = YFinanceFetcher()

    def _get_yfinance_symbol(self, symbol: str) -> str:
        """Maps a symbol to its yfinance equivalent.

        Special cases:
        - Maps Hong Kong stocks to ADR equivalents
        - Maps 9988 to BABA (Alibaba ADR)
        - Maps IHYG to IHYG.L (iShares High Yield Corporate Bond ETF)
        - Returns original symbol for other cases
        """
        # Special case for Alibaba Hong Kong listing
        if symbol == "9988":
            return "BABA"

        # Special case for iShares High Yield Corporate Bond ETF
        if symbol == "IHYG":
            return "IHYG.L"

        # Use ADR mapping for Hong Kong stocks
        return self.adr_map.get(symbol, symbol)

    @lru_cache(maxsize=None)
    def fetch_data(self, symbol: str) -> Dict[str, Any]:
        """Fetches dividend data using yfinance exclusively.

        Args:
            symbol: The stock/ETF symbol to fetch data for

        Returns:
            Dict containing dividend yield and other relevant data
        """
        yf_symbol = self._get_yfinance_symbol(symbol)
        logger.debug(f"Fetching yfinance data for {symbol} (mapped to {yf_symbol})")

        try:
            yf_data = self.yfinance_fetcher.get_dividend_data(yf_symbol).get(
                yf_symbol, {}
            )

            if yf_data.get("success", False):
                dividend_yield = yf_data.get("dividend_yield", 0)
                dividend = yf_data.get("dividend", 0)

                logger.debug(
                    f"Successfully fetched data for {symbol}: yield={dividend_yield:.2%}, dividend={dividend}"
                )

                return {
                    "success": True,
                    "dividend_yield": dividend_yield,  # Already in decimal form (e.g., 0.05 for 5%)
                    "dividend": dividend,
                    "symbol": yf_symbol,
                }
            else:
                logger.warning(f"No dividend data available for {symbol} ({yf_symbol})")
                return {
                    "success": False,
                    "dividend_yield": 0.0,
                    "dividend": 0.0,
                    "symbol": yf_symbol,
                }

        except Exception as e:
            logger.error(
                f"Error fetching yfinance data for {symbol} ({yf_symbol}): {str(e)}"
            )
            return {
                "success": False,
                "dividend_yield": 0.0,
                "dividend": 0.0,
                "symbol": yf_symbol,
            }


class BondProcessor(AssetProcessor):
    """Processes bond-specific assets."""

    def __init__(self, bond_data_client: IBBondsClient):
        self.bond_client = bond_data_client
        self.bond_data: Dict[str, Tuple[Any, float]] = {}

    def fetch_bond_data(self, bond_ids: List[str]) -> None:
        """Fetches data for a list of bond IDs."""
        try:
            self.bond_data = self.bond_client.get_bond_main_info(bond_ids)
        except Exception as e:
            logger.error(f"Error fetching bond data: {e}")
            self.bond_data = {}

    def can_process(self, symbol: str) -> bool:
        """Determines if symbol is a bond (starts with 'IBCID')."""
        return symbol.startswith("IBCID")

    def calculate_yearly_income(self, symbol: str, market_value: float) -> AssetInfo:
        """Calculates yearly income for bonds.

        Args:
            symbol: The bond symbol (e.g., 'IBCID12345')
            market_value: The current market value of the bond position

        Returns:
            AssetInfo with yield_rate as a decimal (e.g., 0.0427 for 4.27%)
            and yearly_income calculated using the decimal yield rate.
        """
        if symbol not in self.bond_data:
            return AssetInfo(
                market_value=market_value,
                yield_rate=0.0,
                yearly_income=0.0,
                adr_symbol=None,
                asset_type="bond",
            )

        _, yield_rate = self.bond_data[symbol]

        # Ensure yield_rate is a decimal (e.g., 0.0427 for 4.27%)
        # The yield_rate from IB is already in decimal form
        yearly_income = market_value * yield_rate

        return AssetInfo(
            market_value=market_value,
            yield_rate=yield_rate,  # Store as decimal (e.g., 0.0427)
            yearly_income=round(yearly_income, 2),
            adr_symbol=None,
            asset_type="bond",
        )


class StockProcessor(AssetProcessor):
    """Processes stock and ETF assets using yfinance exclusively."""

    TAX_DISCOUNT = 0.85  # 15% USA tax

    def __init__(self, data_fetcher: YFinanceDataFetcher):
        self.data_fetcher = data_fetcher

    def can_process(self, symbol: str) -> bool:
        """Processes anything that's not a bond."""
        return not symbol.startswith("IBCID")

    def calculate_yearly_income(self, symbol: str, market_value: float) -> AssetInfo:
        """Calculates yearly income for stocks and ETFs using yfinance.

        Args:
            symbol: The stock or ETF symbol
            market_value: The current market value of the position

        Returns:
            AssetInfo: Contains yield_rate (as decimal, e.g., 0.055 for 5.5%) and yearly_income
        """
        symbol_upper = symbol.upper()
        is_bond_etf = symbol_upper in BONDS_VALUES
        asset_type = "bond_etf" if is_bond_etf else "stock"

        # Default values
        default_info = AssetInfo(
            market_value=market_value,
            yield_rate=0.0,
            yearly_income=0.0,
            adr_symbol=self.data_fetcher.adr_map.get(symbol),
            asset_type=asset_type,
        )

        try:
            # Fetch data using yfinance
            dividend_data = self.data_fetcher.fetch_data(symbol)

            if not dividend_data.get("success", False):
                logger.warning(f"No dividend data available for {symbol_upper}")
                return default_info

            # Get yield rate (already in decimal form from yfinance)
            yield_rate = dividend_data.get("dividend_yield", 0.0)

            if yield_rate <= 0:
                logger.debug(f"Zero or negative yield for {symbol_upper}: {yield_rate}")
                return default_info

            # Calculate yearly income
            # Bond ETFs don't get tax discount applied
            tax_multiplier = 1.0 if is_bond_etf else self.TAX_DISCOUNT
            yearly_income = market_value * yield_rate * tax_multiplier

            logger.info(
                f"Calculated income for {symbol_upper}: "
                f"yield={yield_rate:.2%}, "
                f"market_value=${market_value:,.2f}, "
                f"tax_multiplier={tax_multiplier}, "
                f"yearly_income=${yearly_income:,.2f}"
            )

            return AssetInfo(
                market_value=market_value,
                yield_rate=yield_rate,  # Store as decimal (e.g., 0.055)
                yearly_income=round(yearly_income, 2),
                adr_symbol=self.data_fetcher.adr_map.get(symbol),
                asset_type=asset_type,
            )

        except Exception as e:
            logger.error(f"Error calculating yearly income for {symbol}: {e}")
            logger.debug(f"Error details: {type(e).__name__} - {str(e)}")
            return default_info


class PortfolioAnalyzer:
    """Analyzes portfolio data using appropriate processors."""

    def __init__(self, processors: List[AssetProcessor]):
        self.processors = processors

    def _get_processor(self, symbol: str) -> AssetProcessor:
        """Returns appropriate processor for given symbol."""
        for processor in self.processors:
            if processor.can_process(symbol):
                return processor
        raise ValueError(f"No processor found for symbol: {symbol}")

    def analyze_portfolio(self, market_values: Dict[str, float]) -> PortfolioSummary:
        """Analyzes portfolio and returns summary."""
        results: Dict[str, AssetInfo] = {}

        for symbol, market_value in market_values.items():
            try:
                processor = self._get_processor(symbol)
                results[symbol] = processor.calculate_yearly_income(
                    symbol, market_value
                )
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                continue

        bond_yearly = sum(
            data.yearly_income for data in results.values() if data.asset_type == "bond"
        )
        stock_yearly = sum(
            data.yearly_income
            for data in results.values()
            if data.asset_type in ["stock", "bond_etf"]
        )

        total_yearly = bond_yearly + stock_yearly
        monthly_total = total_yearly / 12

        # Log summary information
        print("\n[IB]")
        logger.info(f"Total yearly bond income (no tax): ${bond_yearly:.2f}")
        logger.info(f"Total yearly stock/ETF dividends after tax: ${stock_yearly:.2f}")
        logger.info(f"Total combined yearly income: ${total_yearly:.2f}")
        logger.info(f"Monthly total: ${monthly_total:.2f}")
        print("[IB]")

        return PortfolioSummary(
            monthly_total=round(monthly_total, 2),
            yearly_total=round(total_yearly, 2),
            stock_yearly=round(stock_yearly, 2),
            asset_details=results,
        )


class IBDividends:
    """Main class for handling Interactive Brokers dividend calculations."""

    def __init__(self, portfolio_data: Dict[str, Any]):
        self.portfolio_data = portfolio_data
        self.market_values, self.bond_ids = self._extract_portfolio_data()

        # Initialize components - now using only yfinance
        yfinance_data_fetcher = YFinanceDataFetcher(HK_TO_ADR_MAP)

        bond_processor = BondProcessor(IBBondsClient())
        bond_processor.fetch_bond_data(self.bond_ids)

        stock_processor = StockProcessor(yfinance_data_fetcher)

        self.analyzer = PortfolioAnalyzer([bond_processor, stock_processor])

    def get_my_total_monthly_and_yearly_divs(
        self,
    ) -> Tuple[float, float, float, Dict[str, AssetInfo]]:
        """Calculates and returns dividend summary information."""
        summary = self.analyzer.analyze_portfolio(self.market_values)

        print("\nIB Dividend Summary:")
        sorted_details = dict(
            sorted(summary.asset_details.items(), key=lambda x: (x[1].asset_type, x[0]))
        )

        for symbol, data in sorted_details.items():
            print(f"\n{symbol} ({data.asset_type}):")
            print(f"  Market Value: ${data.market_value:,.2f}")
            # Convert decimal yield to percentage for display (e.g., 0.05 -> 5.00%)
            print(f"  Yield Rate: {data.yield_rate * 100:.2f}%")
            income_type = "Interest" if data.asset_type == "bond" else "Dividend"
            print(f"  Expected Yearly {income_type}: ${data.yearly_income:,.2f}")
            if data.adr_symbol:
                print(f"  ADR Symbol Used: {data.adr_symbol}")

        return (
            summary.monthly_total,
            summary.yearly_total,
            summary.stock_yearly,
            summary.asset_details,
        )

    def _extract_portfolio_data(self) -> Tuple[Dict[str, float], List[str]]:
        """Extracts market values and bond IDs from portfolio data."""
        market_values: Dict[str, float] = {}
        bond_ids: List[str] = []

        relevant_categories = {BONDS_KEY, CHINA_STOCKS_KEY, STOCKS_KEY}

        for category, stocks in self.portfolio_data.items():
            if category in relevant_categories and isinstance(stocks, dict):
                for symbol, value in stocks.items():
                    if (
                        isinstance(value, (int, float))
                        and symbol != "Total_Stocks_Value"
                    ):
                        if symbol.startswith("IBCID"):
                            bond_ids.append(symbol)
                        market_values[symbol] = value
                    elif isinstance(value, dict) and "position" in value:
                        market_values[symbol] = value["position"]

        return market_values, bond_ids


def main():
    """Main entry point for the script."""
    # Get portfolio data
    broker = InteractiveBrokers()
    info = broker.get_portfolio_positions()
    logger.info("Portfolio positions retrieved from broker")

    # Initialize IBDividends and get dividend info
    pd = IBDividends(info)
    monthly, yearly, stock_yearly, details = pd.get_my_total_monthly_and_yearly_divs()


if __name__ == "__main__":
    main()
