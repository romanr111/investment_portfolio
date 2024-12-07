import logging
from functools import lru_cache

from ib_bond_data_fetcher import IBBondsClient

from data.endpoints import NASDAQ_API, NASDAQ_HEADERS
from data.portfolio_filters import HK_TO_ADR_MAP
from src.brokers.ib import InteractiveBrokers
from src.helpers import perform_request

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Data Models
@dataclass
class AssetInfo:
    market_value: float
    yield_rate: float
    yearly_income: float
    adr_symbol: Optional[str]
    asset_type: str


@dataclass
class PortfolioSummary:
    monthly_total: float
    yearly_total: float
    asset_details: Dict[str, AssetInfo]


# Abstract Base Classes
class AssetProcessor(ABC):
    @abstractmethod
    def can_process(self, symbol: str) -> bool:
        pass

    @abstractmethod
    def calculate_yearly_income(self, symbol: str, market_value: float) -> AssetInfo:
        pass


class DataFetcher(ABC):
    @abstractmethod
    def fetch_data(self, symbol: str) -> Dict:
        pass


class BondProcessor(AssetProcessor):
    def __init__(self, bond_data_client):
        self.bond_client = bond_data_client
        self.bond_data = {}

    def fetch_bond_data(self, bond_ids: List[str]):
        try:
            self.bond_data = self.bond_client.get_bond_main_info(bond_ids)
        except Exception as e:
            logger.error(f"Error fetching bond data: {e}")
            self.bond_data = {}

    def can_process(self, symbol: str) -> bool:
        return symbol.startswith("IBCID")

    def calculate_yearly_income(self, symbol: str, market_value: float) -> AssetInfo:
        if symbol not in self.bond_data:
            return AssetInfo(
                market_value=market_value,
                yield_rate=0.0,
                yearly_income=0.0,
                adr_symbol=None,
                asset_type="bond",
            )

        amount, yield_rate = self.bond_data[symbol]
        yearly_income = amount * yield_rate

        return AssetInfo(
            market_value=amount,
            yield_rate=yield_rate,
            yearly_income=round(yearly_income, 2),
            adr_symbol=None,
            asset_type="bond",
        )


class StockDataFetcher(DataFetcher):
    def __init__(self, api_url, headers, etf_symbols, adr_map):
        self.api_url = api_url
        self.headers = headers
        self.etf_symbols = etf_symbols
        self.adr_map = adr_map

    def _get_api_symbol(self, symbol: str) -> str:
        return self.adr_map.get(symbol, symbol)

    @lru_cache(maxsize=None)
    def fetch_data(self, symbol: str) -> Dict:
        api_symbol = self._get_api_symbol(symbol)
        asset_class = "etf" if api_symbol in self.etf_symbols else "stocks"
        param = f"{api_symbol}/dividends?assetclass={asset_class}"
        return perform_request(self.api_url, param, self.headers)


class StockProcessor(AssetProcessor):
    TAX_DISCOUNT = 0.85  # 15% USA tax

    def __init__(self, data_fetcher: DataFetcher):
        self.data_fetcher = data_fetcher

    def can_process(self, symbol: str) -> bool:
        return not symbol.startswith("IBCID")

    def _get_yield_from_div_info(self, div_info: Dict) -> float:
        try:
            if (
                div_info["status"]["rCode"] == 200
                and div_info["data"] is not None
                and div_info["data"].get("yield") not in (None, "N/A")
            ):
                yield_str = div_info["data"]["yield"].rstrip("%")
                return float(yield_str) / 100
            return 0.0
        except Exception as e:
            logger.error(f"Error extracting yield: {e}")
            return 0.0

    def calculate_yearly_income(self, symbol: str, market_value: float) -> AssetInfo:
        div_info = self.data_fetcher.fetch_data(symbol)
        yield_rate = self._get_yield_from_div_info(div_info)
        yearly_income = market_value * yield_rate * self.TAX_DISCOUNT
        api_symbol = self.data_fetcher._get_api_symbol(symbol)

        return AssetInfo(
            market_value=market_value,
            yield_rate=yield_rate,
            yearly_income=round(yearly_income, 2),
            adr_symbol=api_symbol if api_symbol != symbol else None,
            asset_type="stock",
        )


class PortfolioAnalyzer:
    def __init__(self, processors: List[AssetProcessor]):
        self.processors = processors

    def _get_processor(self, symbol: str) -> AssetProcessor:
        for processor in self.processors:
            if processor.can_process(symbol):
                return processor
        raise ValueError(f"No processor found for symbol: {symbol}")

    def analyze_portfolio(self, market_values: Dict[str, float]) -> PortfolioSummary:
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
            if data.asset_type == "stock"
        )

        total_yearly = bond_yearly + stock_yearly
        monthly_total = total_yearly / 12

        logger.info(f"Total yearly bond income (no tax): ${bond_yearly:.2f}")
        logger.info(f"Total yearly stock dividends after tax: ${stock_yearly:.2f}")
        logger.info(f"Total combined yearly income: ${total_yearly:.2f}")
        logger.info(f"Monthly total: ${monthly_total:.2f}")

        return PortfolioSummary(
            monthly_total=round(monthly_total, 2),
            yearly_total=round(total_yearly, 2),
            asset_details=results,
        )


class IBDividends:
    def __init__(self, portfolio_data: Dict):
        self.portfolio_data = portfolio_data
        self.market_values, self.bond_ids = self._extract_portfolio_data()

        # Initialize components
        stock_data_fetcher = StockDataFetcher(
            NASDAQ_API,
            NASDAQ_HEADERS,
            ["MCHI", "VNQI", "SGOV", "TLT", "LQD", "HYG", "JNK", "EMB", "KWEB"],
            HK_TO_ADR_MAP,
        )

        bond_processor = BondProcessor(IBBondsClient())
        bond_processor.fetch_bond_data(self.bond_ids)

        stock_processor = StockProcessor(stock_data_fetcher)

        self.analyzer = PortfolioAnalyzer([bond_processor, stock_processor])

    def _extract_portfolio_data(self) -> Tuple[Dict[str, float], List[str]]:
        market_values = {}
        bond_ids = []

        relevant_categories = {"Bonds", "China", "Banks", "USA_Stocks"}

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

    def get_my_total_monthly_and_yearly_divs(
        self,
    ) -> Tuple[float, float, Dict[str, AssetInfo]]:
        summary = self.analyzer.analyze_portfolio(self.market_values)
        return summary.monthly_total, summary.yearly_total, summary.asset_details


if __name__ == "__main__":
    broker = InteractiveBrokers()
    info = broker.get_portfolio_positions()
    logger.info("Portfolio positions retrieved from broker")

    pd = IBDividends(info)
    monthly, yearly, details = pd.get_my_total_monthly_and_yearly_divs()

    print("\nDividend Summary:")
    sorted_details = dict(
        sorted(details.items(), key=lambda x: (x[1].asset_type, x[0]))
    )

    for symbol, data in sorted_details.items():
        print(f"\n{symbol} ({data.asset_type}):")
        print(f"  Market Value: ${data.market_value:,.2f}")
        print(f"  Yield Rate: {data.yield_rate:.2%}")
        income_type = "Interest" if data.asset_type == "bond" else "Dividend"
        print(f"  Expected Yearly {income_type}: ${data.yearly_income:,.2f}")
        if data.adr_symbol:
            print(f"  ADR Symbol Used: {data.adr_symbol}")
