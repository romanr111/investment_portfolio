import csv
from datetime import datetime
import time

from data.portfolio_filters import *


from data.endpoints import POSITIONS_API, SUMMARY_API
from src.helpers import calculate_total_mkt_value, convert, perform_request, sort_dict

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


class InteractiveBrokers:
    def __init__(self):
        self._portfolio_positions = None
        self.data_loader = DataLoader()
        self.summary = self.data_loader.perform_request(SUMMARY_API)
        self.all_portfolio_info = self.data_loader.perform_request(POSITIONS_API)
        self._cash_balance = round(self.summary["totalcashvalue"]["amount"])

    def get_full_porfolio_data(self):
        """Get complete portfolio data with minimal recalculation."""
        portfolio = self.get_portfolio_positions()
        portfolio["Net_cash"] = self.net_cash_balance
        print("\n=== IB Portfolio Summary ===")
        print(portfolio)
        print("========================\n")
        return portfolio

    def get_all_portfolio_info(self):
        """Implementation of abstract method from Broker class"""
        return self.all_portfolio_info

    @property
    def cash_balance(self):
        return self._cash_balance

    @property
    def net_cash_balance(self):
        if self._portfolio_positions is None:
            self._portfolio_positions = self.get_portfolio_positions()
        short_mkt_value = calculate_total_mkt_value(
            self._portfolio_positions[SHORT_SELLING_KEY]
        )
        return self.cash_balance + short_mkt_value

    def get_portfolio_positions(self):
        if self._portfolio_positions is not None:
            return self._portfolio_positions

        # Initialize portfolio structure
        portfolio = {
            IB_BONDS_KEY: {},
            CHINA_STOCKS_KEY: {},
            IB_STOCKS_KEY: {},
            SHORT_SELLING_KEY: {},
            REIT_KEY: {},
            GOLD_KEY: {},
            COMMODITIES_KEY: {},
        }

        # Load REIT names once
        public_reit_names = REITLoader.load_reits_from_csv()
        categorizer = StockCategorizer()
        total_stocks = 0

        # Process all positions in a single pass
        for position in self.all_portfolio_info:
            stock = position["contractDesc"]
            mkt_value = round(position["mktValue"])

            category = categorizer.get_category(stock, mkt_value, public_reit_names)
            value = categorizer.get_value_for_category(stock, mkt_value, category)
            portfolio[category][stock] = value

            # Calculate total stocks value in the same loop
            if category not in ["Bonds", "Short", "REIT", "Gold", "Commodities"]:
                total_stocks += value

        # Sort all dictionaries at once
        portfolio = {k: sort_dict(v) for k, v in portfolio.items()}
        portfolio[IB_STOCKS_VALUE] = round(total_stocks)

        # Cache the result
        self._portfolio_positions = portfolio
        return portfolio

    def get_stocks_quantity(self):
        return {
            stock["contractDesc"]: round(stock["position"])
            for stock in self.all_portfolio_info
        }


class DataLoader:
    @staticmethod
    def perform_request(api_endpoint):
        return perform_request(api_endpoint, verify=False)


class REITLoader:
    @staticmethod
    def load_reits_from_csv(file_path="data/List_U.S._REITs.csv"):
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


class StockCategorizer:
    @staticmethod
    def get_category(stock, mkt_value, public_reit_names):
        # First check for bond IDs and Chinese ETFs/ADRs
        if stock.startswith("IBCID") and mkt_value > 0:
            return IB_BONDS_KEY

        category_conditions = {
            CHINA_STOCKS_KEY: (stock in CHINA_TICKERS or stock in CHINA_ADR),
            REIT_KEY: stock in public_reit_names or stock in REITS,
            GOLD_KEY: stock in GOLD,
            IB_BONDS_KEY: stock in BONDS_VALUES,
            COMMODITIES_KEY: stock in COMM,
            SHORT_SELLING_KEY: mkt_value < 0,
        }

        for category, condition in category_conditions.items():
            if condition:
                return category

        return IB_STOCKS_KEY

    @staticmethod
    def get_value_for_category(stock, mkt_value, category):
        if category == CHINA_STOCKS_KEY and stock in CHINA_TICKERS:
            return round(convert("HKD", "USD", mkt_value))
        return mkt_value


def main():
    start_time = time.time()

    try:
        ib = InteractiveBrokers()
        ib.get_full_porfolio_data()

    except Exception as e:
        print(f"ERROR: An error occurred: {str(e)}")

    finally:
        execution_time = time.time() - start_time
        print("\n=== Performance Metrics ===")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total Execution Time: {execution_time:.4f} seconds")


if __name__ == "__main__":
    main()
