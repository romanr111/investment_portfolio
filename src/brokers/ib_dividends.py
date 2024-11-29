from src.brokers.ib import InteractiveBrokers
from data.endpoints import NASDAQ_API, NASDAQ_HEADERS
from data.portfolio_filters import HK_TO_ADR_MAP
from src.helpers import perform_request
from functools import lru_cache
import logging
from ib_bond_data_fetcher import IBBondsClient

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class IBDividends:
    TAX_DISCOUNT = 0.85  # 15% USA tax
    API_URL = NASDAQ_API
    HEADERS = NASDAQ_HEADERS
    RELEVANT_CATEGORIES = {"Bonds", "China", "Banks", "USA_Stocks"}
    ETF_SYMBOLS = ["MCHI", "VNQI", "SGOV", "TLT", "LQD", "HYG", "JNK", "EMB", "KWEB"]

    def __init__(self, portfolio_data):
        logger.info("Initializing IBDividends with portfolio data")
        self.portfolio_data = portfolio_data
        self._process_portfolio_data()
        self._fetch_bond_data()

    def _process_portfolio_data(self):
        """Extract individual stocks market values and identify bonds"""
        logger.debug("Processing portfolio data to extract market values")
        self.market_values = {}
        self.bond_ids = []

        for category, stocks in self.portfolio_data.items():
            if category in self.RELEVANT_CATEGORIES and isinstance(stocks, dict):
                logger.debug(f"Processing category: {category}")
                for symbol, value in stocks.items():
                    if isinstance(value, (int, float)) and symbol not in [
                        "Total_Stocks_Value"
                    ]:
                        if symbol.startswith("IBCID"):
                            self.bond_ids.append(symbol)
                        self.market_values[symbol] = value
                    elif isinstance(value, dict) and "position" in value:
                        self.market_values[symbol] = value["position"]

        logger.debug(f"Extracted market values: {self.market_values}")
        logger.debug(f"Identified bond IDs: {self.bond_ids}")

    def _fetch_bond_data(self):
        """Fetch bond yield data using IBBondsClient"""
        self.bond_yields = {}
        if self.bond_ids:
            try:
                client = IBBondsClient()
                self.bond_yields = client.get_bond_main_info(self.bond_ids)
                logger.debug(f"Retrieved bond yields: {self.bond_yields}")
            except Exception as e:
                logger.error(f"Error fetching bond data: {e}")

    def _get_api_symbol(self, symbol):
        """Convert HK symbol to ADR symbol if applicable"""
        adr_symbol = HK_TO_ADR_MAP.get(symbol, symbol)
        if adr_symbol != symbol:
            logger.debug(f"Mapped {symbol} to ADR symbol {adr_symbol}")
        return adr_symbol

    @lru_cache(maxsize=None)
    def _get_dividend_info(self, symbol):
        """Fetch dividend information for a single stock"""
        api_symbol = self._get_api_symbol(symbol)
        logger.debug(
            f"Fetching dividend info for symbol: {api_symbol} (original: {symbol})"
        )
        param = (
            f"{api_symbol}/dividends?assetclass=etf"
            if api_symbol in self.ETF_SYMBOLS
            else f"{api_symbol}/dividends?assetclass=stocks"
        )
        return perform_request(self.API_URL, param, self.HEADERS)

    def _get_yield_from_div_info(self, div_info):
        """Extract yield percentage from dividend info"""
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

    def get_yields_and_dividend_amounts(self):
        """Calculate expected dividend amounts based on yield and market value"""
        logger.info("Calculating dividend yields and amounts")
        results = {}

        for symbol, market_value in self.market_values.items():
            try:
                if symbol.startswith("IBCID"):
                    # Handle bonds
                    if symbol in self.bond_yields:
                        amount, yield_rate = self.bond_yields[symbol]
                        yearly_dividend = amount * yield_rate
                        results[symbol] = {
                            "market_value": amount,
                            "yield_rate": yield_rate,
                            "yearly_dividend": round(yearly_dividend, 2),
                            "adr_symbol": None,
                            "type": "bond",
                        }
                        logger.debug(
                            f"Bond {symbol}: Amount=${amount}, "
                            f"Yield={yield_rate:.2%}, "
                            f"Yearly Interest=${yearly_dividend:.2f}"
                        )
                else:
                    # Handle stocks
                    div_info = self._get_dividend_info(symbol)
                    yield_rate = self._get_yield_from_div_info(div_info)
                    yearly_dividend = market_value * yield_rate
                    api_symbol = self._get_api_symbol(symbol)

                    results[symbol] = {
                        "market_value": market_value,
                        "yield_rate": yield_rate,
                        "yearly_dividend": round(yearly_dividend, 2),
                        "adr_symbol": api_symbol if api_symbol != symbol else None,
                        "type": "stock",
                    }
                    logger.debug(
                        f"{symbol} ({api_symbol}): Market Value=${market_value}, "
                        f"Yield={yield_rate:.2%}, "
                        f"Yearly Dividend=${yearly_dividend:.2f}"
                    )

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                results[symbol] = {
                    "market_value": market_value,
                    "yield_rate": 0.0,
                    "yearly_dividend": 0.0,
                    "adr_symbol": self._get_api_symbol(symbol),
                    "type": "bond" if symbol.startswith("IBCID") else "stock",
                }

        return results

    def get_my_total_monthly_and_yearly_divs(self):
        """Calculate total monthly and yearly dividends"""
        logger.info("Calculating total monthly and yearly dividends")

        results = self.get_yields_and_dividend_amounts()
        yearly = sum(data["yearly_dividend"] for data in results.values())
        yearly_after_tax = yearly * self.TAX_DISCOUNT
        monthly_after_tax = yearly_after_tax / 12

        logger.info(f"Total yearly dividends before tax: ${yearly:.2f}")
        logger.info(f"Total yearly dividends after tax: ${yearly_after_tax:.2f}")
        logger.info(f"Monthly dividends after tax: ${monthly_after_tax:.2f}")

        return round(monthly_after_tax, 2), round(yearly_after_tax, 2), results


if __name__ == "__main__":
    broker = InteractiveBrokers()
    info = broker.get_portfolio_positions()
    logger.info("Portfolio positions retrieved from broker")

    pd = IBDividends(info)
    monthly, yearly, details = pd.get_my_total_monthly_and_yearly_divs()

    print("\nDividend Summary:")
    print(f"Monthly dividends (after tax): ${monthly}")
    print(f"Yearly dividends (after tax): ${yearly}")
    print("\nDetailed Dividend Analysis:")

    # Sort by type and then by symbol for organized output
    sorted_details = dict(sorted(details.items(), key=lambda x: (x[1]["type"], x[0])))

    for symbol, data in sorted_details.items():
        print(f"\n{symbol} ({data['type']}):")
        print(f"  Market Value: ${data['market_value']:,.2f}")
        print(f"  Yield Rate: {data['yield_rate']:.2%}")
        print(
            f"  Expected Yearly {data['type'].title()} Income: ${data['yearly_dividend']:,.2f}"
        )
        if data["adr_symbol"]:
            print(f"  ADR Symbol Used: {data['adr_symbol']}")
