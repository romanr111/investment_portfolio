from src.brokers.ib import InteractiveBrokers
from src.helpers import convert

# Date of last dividend calculation: 28.09.2023 (Calculated for the full year)
# Date of last portfolio update: 28.09.2023
DIVS_2023 = 3.48 + 7.08 + 7.95 + 1.75

# Constants
STOCKS = {
    "SGOV": 2.7,
    "9988": 9.625,
    "RIO": 2,
    "C": 3.75,
    "INTC": 3.5,
    "COMB": 3.93,
}

# + GOOG AVG.PRICE 100.12 1.51%
# + BN avg.price 31.84$ / 1.15%
# + COF avg.price 109$ / 1.09%

CASH = 6.48 + DIVS_2023


#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


class DashaPortfolio:
    def __init__(self, broker):
        self.broker = broker

    def get_stock_prices(self):
        stock_prices = {}
        for stock in self.broker.get_all_portfolio_info():
            symbol = stock["contractDesc"]
            if symbol in STOCKS:
                price = round(stock["mktPrice"], 1)
                stock_prices[symbol] = self._convert_price_if_needed(symbol, price)
        return stock_prices

    def _convert_price_if_needed(self, symbol, price):
        if symbol == "9988":
            return convert("HKD", "USD", price)
        return price

    def get_portfolio_value(self):
        stock_prices = self.get_stock_prices()
        total_value = CASH
        for symbol, count in STOCKS.items():
            total_value += stock_prices.get(symbol, 0) * count
        return round(total_value)


if __name__ == "__main__":
    ib_broker = InteractiveBrokers()
    dasha_portfolio = DashaPortfolio(ib_broker)
    total_value = dasha_portfolio.get_portfolio_value()
    print(total_value)
    print(f"cash - {round(CASH)}")
