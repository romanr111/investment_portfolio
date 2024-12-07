from src.brokers.ib import InteractiveBrokers
from data.endpoints import NASDAQ_API, NASDAQ_HEADERS
from data.portfolio_filters import HK_TO_ADR_MAP
from src.helpers import perform_request
from functools import lru_cache
import logging
from ib_bond_data_fetcher import IBBondsClient

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
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
        self.market_values = {}
        self.bond_ids = []

        for category, stocks in self.portfolio_data.items():
            if category in self.RELEVANT_CATEGORIES and isinstance(stocks, dict):
                for symbol, value in stocks.items():
                    if isinstance(value, (int, float)) and symbol not in [
                        "Total_Stocks_Value"
                    ]:
                        if symbol.startswith("IBCID"):
                            self.bond_ids.append(symbol)
                        self.market_values[symbol] = value
                    elif isinstance(value, dict) and "position" in value:
                        self.market_values[symbol] = value["position"]

    def _fetch_bond_data(self):
        """Fetch bond yield data using IBBondsClient"""
        self.bond_yields = {}
        if self.bond_ids:
            try:
                client = IBBondsClient()
                self.bond_yields = client.get_bond_main_info(self.bond_ids)
            except Exception as e:
                logger.error(f"Error fetching bond data: {e}")

    def _get_api_symbol(self, symbol):
        """Convert HK symbol to ADR symbol if applicable"""
        return HK_TO_ADR_MAP.get(symbol, symbol)

    @lru_cache(maxsize=None)
    def _get_dividend_info(self, symbol):
        """Fetch dividend information for a single stock"""
        api_symbol = self._get_api_symbol(symbol)
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
                else:
                    # Handle stocks
                    div_info = self._get_dividend_info(symbol)
                    yield_rate = self._get_yield_from_div_info(div_info)
                    yearly_dividend = (
                        market_value * yield_rate * self.TAX_DISCOUNT
                    )  # Apply tax discount here
                    api_symbol = self._get_api_symbol(symbol)

                    results[symbol] = {
                        "market_value": market_value,
                        "yield_rate": yield_rate,
                        "yearly_dividend": round(yearly_dividend, 2),
                        "adr_symbol": api_symbol if api_symbol != symbol else None,
                        "type": "stock",
                    }

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
        results = self.get_yields_and_dividend_amounts()

        # Calculate totals (amounts are already after tax for stocks)
        bond_yearly = sum(
            data["yearly_dividend"]
            for symbol, data in results.items()
            if symbol.startswith("IBCID")
        )

        stock_yearly = sum(
            data["yearly_dividend"]
            for symbol, data in results.items()
            if not symbol.startswith("IBCID")
        )

        total_yearly = bond_yearly + stock_yearly
        monthly_total = total_yearly / 12

        logger.info(f"Total yearly bond income (no tax): ${bond_yearly:.2f}")
        logger.info(f"Total yearly stock dividends after tax: ${stock_yearly:.2f}")
        logger.info(f"Total combined yearly income: ${total_yearly:.2f}")
        logger.info(f"Monthly total: ${monthly_total:.2f}")

        return round(monthly_total, 2), round(total_yearly, 2), results


if __name__ == "__main__":
    broker = InteractiveBrokers()
    info = broker.get_portfolio_positions()
    logger.info("Portfolio positions retrieved from broker")

    pd = IBDividends(info)
    monthly, yearly, details = pd.get_my_total_monthly_and_yearly_divs()

    print("\nDividend Summary:")

    sorted_details = dict(sorted(details.items(), key=lambda x: (x[1]["type"], x[0])))

    for symbol, data in sorted_details.items():
        print(f"\n{symbol} ({data['type']}):")
        print(f"  Market Value: ${data['market_value']:,.2f}")
        print(f"  Yield Rate: {data['yield_rate']:.2%}")
        income_type = "Interest" if data["type"] == "bond" else "Dividend"
        print(f"  Expected Yearly {income_type}: ${data['yearly_dividend']:,.2f}")
        if data["adr_symbol"]:
            print(f"  ADR Symbol Used: {data['adr_symbol']}")
