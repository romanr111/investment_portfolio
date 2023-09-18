import sys
from ib import InteractiveBrokers
from endpoints import NASDAQ_API
from endpoints import NASDAQ_HEADERS

sys.path.append("/Users/roman/Documents/Development/Portfolio/helpers/")
from helpers.requests_handler import RequestsHandler

ib = InteractiveBrokers()
request = RequestsHandler()

stocks_quantity = ib.get_stocks_quantity()


class Dividends:
    def get_yearly_dividend_per_stock(self):
        dividends = {}

        for stock in stocks_quantity.keys():
            if stock in ["MCHI", "VNQI"]:
                param = stock + "/dividends?assetclass=etf"
                div_info = request.perform_request(NASDAQ_API, param, NASDAQ_HEADERS)
            else:
                param = stock + "/dividends?assetclass=stocks"
                div_info = request.perform_request(NASDAQ_API, param, NASDAQ_HEADERS)

            is_dividend_exist = False
            if (
                (div_info["status"]["rCode"] == 200)
                and (div_info["data"] != "null")
                and div_info["data"] != None
            ):
                if div_info["data"]["annualizedDividend"] != "N/A":
                    is_dividend_exist = True
            if is_dividend_exist:
                dividends.update({stock: div_info["data"]["annualizedDividend"]})

        return dividends

    def get_my_dividends_per_stock(self):
        div_per_stock = self.get_yearly_dividend_per_stock()
        my_div_per_stock = {}

        for k, v in div_per_stock.items():
            for key, value in stocks_quantity.items():
                if k == key:
                    my_div_per_stock.update({k: round(float(v) * int(value))})
        print(my_div_per_stock)
        return my_div_per_stock

    def get_my_monthly_and_yearly_dividends(self):
        div_per_position = self.get_my_dividends_per_stock()
        yearly = 0
        tax_adjustment = 0.8
        for div in div_per_position.values():
            yearly += div * tax_adjustment
        monthly = round(yearly / 12)

        return monthly, yearly
