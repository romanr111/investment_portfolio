import csv

import data.portfolio_filters as filters
from abc import ABC, abstractmethod
from src.helpers import perform_request, sort_dict, convert
from data.endpoints import SUMMARY_API, POSITIONS_API

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


class Broker(ABC):
    @abstractmethod
    def get_all_portfolio_info(self):
        pass


class InteractiveBrokers(Broker):
    def __init__(self):
        self.summary = perform_request(SUMMARY_API, verify=False)
        self.all_portfolio_info = perform_request(POSITIONS_API, verify=False)

    def _get_category(self, stock, mkt_value, public_reit_names):
        category_conditions = {
            "Short": mkt_value < 0,
            "China": stock in filters.CHINA or stock in filters.CHINA_ADR,
            "Banks": stock in filters.BANKS,
            "REIT": stock in public_reit_names or stock in filters.REITS,
            "Gold": stock in filters.GOLD,
            "Bonds": stock in filters.BONDS,
            "Commodities": stock in filters.COMM,
        }

        for category, condition in category_conditions.items():
            if condition:
                return category

        # Default category
        return "USA_Stocks"

    def _get_value_for_category(self, stock, mkt_value, category):
        if category == "China" and stock in filters.CHINA:
            return round(convert("HKD", "USD", mkt_value))
        return mkt_value

    def _get_public_reits_names(self, file_path="data/List_U.S._REITs.csv"):
        """
        Extract REITs names from the given CSV file.

        :param file_path: Path to the CSV file.
        :return: List of REIT names.
        """
        reit_list = []

        try:
            with open(file_path, "r") as f:
                csv_reader = csv.reader(f)
                reit_list = [str(row[0]) for row in csv_reader]

        except FileNotFoundError:
            print(f"Error: File {file_path} not found.")
        except Exception as e:
            print(f"An error occurred: {e}")

        return reit_list

    @property
    def cash_balance(self):
        balance = round(self.summary["totalcashvalue"]["amount"])
        return balance

    def get_all_portfolio_info(self):
        return self.all_portfolio_info

    def get_portfolio_positions(self):
        public_reit_names = self._get_public_reits_names()

        portfolio = {
            "Bonds": {},
            "China": {},
            "Banks": {},
            "USA_Stocks": {},
            "Short": {},
            "REIT": {},
            "Gold": {},
            "Commodities": {},
        }

        for position in self.all_portfolio_info:
            stock, mkt_value = position["contractDesc"], round(position["mktValue"])
            category = self._get_category(stock, mkt_value, public_reit_names)
            value = self._get_value_for_category(stock, mkt_value, category)
            portfolio[category].update({stock: value})

        portfolio["REIT"].update({"LAND": 200})  # Update this once, not inside the loop

        for k, dict_ in portfolio.items():
            portfolio[k] = sort_dict(dict_)

        return portfolio

    def calculate_total_mkt_value(self, dict):
        return round(sum([value for value in dict.values()]))

    def get_stocks_quantity(self):
        stocks = {
            stock["contractDesc"]: round(stock["position"])
            for stock in self.all_portfolio_info
        }
        return stocks

    def get_full_porfolio_data(self):
        portfolio = self.get_portfolio_positions()
        short_mkt_value = self.calculate_total_mkt_value(portfolio["Short"])
        net_cash = self.cash_balance + short_mkt_value
        portfolio.update({"Net_cash": net_cash})
        print(f"\n")
        print(f"--- IB ---")
        print(f"Short total: {short_mkt_value}")
        print(f"Cash total: {self.cash_balance}")
        print(f"Net cash: {net_cash}")
        print(f"\n")
        print(f"{portfolio}")
        print(f"\n")
        print(f"--- IB ---")

        return portfolio


if __name__ == "__main__":
    ib = InteractiveBrokers()
    x = ib.get_full_porfolio_data()
