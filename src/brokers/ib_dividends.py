from ib import InteractiveBrokers
from data.endpoints import NASDAQ_API, NASDAQ_HEADERS
from src.helpers import perform_request
from functools import lru_cache


class BaseDividends:
    API_URL = NASDAQ_API
    HEADERS = NASDAQ_HEADERS

    def __init__(self, stocks_quantity):
        self.stocks_quantity = stocks_quantity
        self._replace_700_key()

    def _replace_700_key(self):
        if "700" in self.stocks_quantity:
            self.stocks_quantity["TCEHY"] = self.stocks_quantity["700"]
            del self.stocks_quantity["700"]

    @lru_cache(maxsize=None)  # This caches the results of _get_dividend_info
    def _get_dividend_info(self, stock):
        etfs = ["MCHI", "VNQI", "SGOV", "TLT", "LQD", "HYG", "JNK", "EMB"]
        param = (
            f"{stock}/dividends?assetclass=etf"
            if stock in etfs
            else f"{stock}/dividends?assetclass=stocks"
        )
        return perform_request(self.API_URL, param, self.HEADERS)

    def _is_valid_dividend_info(self, div_info):
        return (
            div_info["status"]["rCode"] == 200
            and div_info["data"] != "null"
            and div_info["data"] is not None
            and div_info["data"]["annualizedDividend"] != "N/A"
        )

    def get_annualized_div_per_one_stock(self):
        dividends = {}
        for stock in self.stocks_quantity:
            div_info = self._get_dividend_info(stock)
            if self._is_valid_dividend_info(div_info):
                dividends[stock] = div_info["data"]["annualizedDividend"]
        return dividends

    def get_my_yearly_dividends_per_stock(self):
        div_per_stock = self.get_annualized_div_per_one_stock()
        return {
            k: round(float(v) * int(self.stocks_quantity[k]))
            for k, v in div_per_stock.items()
        }

    def get_my_total_monthly_and_yearly_divs(self):
        div_per_position = self.get_my_yearly_dividends_per_stock()
        tax_discount = 0.8  # 15% USA tax, 5% Ukraine tax
        yearly = sum(div * tax_discount for div in div_per_position.values())
        return round(yearly / 12), round(yearly)


class PublicDividends(BaseDividends):
    def __init__(self, broker):
        stocks_quantity = broker.get_stocks_quantity()
        super().__init__(stocks_quantity)


if __name__ == "__main__":
    broker = InteractiveBrokers()
    pd = PublicDividends(broker)
    print(pd.get_my_total_monthly_and_yearly_divs())
    print(pd.get_my_yearly_dividends_per_stock())
