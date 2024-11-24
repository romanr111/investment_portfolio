import csv
from datetime import datetime
import time
from abc import ABC, abstractmethod

import data.portfolio_filters as filters
from data.endpoints import POSITIONS_API, SUMMARY_API
from src.helpers import calculate_total_mkt_value, convert, perform_request, sort_dict

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


class InteractiveBrokers:
    BOND_YIELD_ENDPOINT = "https://localhost:5000/v1/api/bond/yield/"

    def __init__(self):
        self.data_loader = DataLoader()
        self.summary = self.data_loader.perform_request(SUMMARY_API)
        self.all_portfolio_info = self.data_loader.perform_request(POSITIONS_API)
        self._cash_balance = round(self.summary["totalcashvalue"]["amount"])
        self._portfolio_positions = None
        self._bond_yields = {}
        self.yields = self.get_all_bond_yields()

    def get_full_porfolio_data(self):
        """Get complete portfolio data with minimal recalculation."""
        portfolio = self.get_portfolio_positions()
        portfolio["Net_cash"] = self.net_cash_balance

        # Wrap the portfolio data in a nested dictionary
        wrapped_portfolio = {"interactive_brokers": portfolio}
        # Single consolidated log output
        print("\n=== IB Portfolio Summary ===")
        print(wrapped_portfolio)
        print("========================\n")

        return wrapped_portfolio

    def _fetch_bond_yields_from_positions(self):
        """Extract bond yields directly from portfolio info."""
        bond_yields = {}
        for position in self.all_portfolio_info:
            if position["contractDesc"].startswith("IBCID"):
                # Assuming yield is stored in position data as a percentage
                bond_yields[position["contractDesc"]] = (
                    position.get("yield", position.get("marketPrice", 0)) / 100
                )  # Convert to decimal
        return bond_yields

    def get_bond_yield(self, bond_id):
        """Get yield for a specific bond from cached data."""
        return {"yield": self._bond_yields.get(bond_id, 0)}

    def get_all_bond_yields(self):
        """Return all cached bond yields."""
        return self._bond_yields

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
        short_mkt_value = calculate_total_mkt_value(self._portfolio_positions["Short"])
        return self.cash_balance + short_mkt_value

    def get_portfolio_positions(self):
        if self._portfolio_positions is not None:
            return self._portfolio_positions

        # Initialize portfolio structure
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
        portfolio["Total_Stocks_Value"] = round(total_stocks)

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
        if stock.startswith("IBCID"):
            return "Bonds"

        category_conditions = {
            "Short": mkt_value < 0,
            "China": (stock in filters.CHINA or stock in filters.CHINA_ADR),
            "Banks": stock in filters.BANKS,
            "REIT": stock in public_reit_names or stock in filters.REITS,
            "Gold": stock in filters.GOLD,
            "Bonds": stock in filters.BONDS,
            "Commodities": stock in filters.COMM,
        }

        for category, condition in category_conditions.items():
            if condition:
                return category

        return "USA_Stocks"

    @staticmethod
    def get_value_for_category(stock, mkt_value, category):
        if category == "China" and stock in filters.CHINA:
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
