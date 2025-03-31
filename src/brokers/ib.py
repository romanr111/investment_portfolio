import csv
from datetime import datetime
import time

from data.filters_constants import *


from data.endpoints import POSITIONS_API, SUMMARY_API
from src.helpers import calculate_total_mkt_value, convert, perform_request, sort_dict

#
# cd Documents/Development/Portfolio/clientportal.gw  && bin/run.sh root/conf.yaml
#


class InteractiveBrokers:
    def __init__(self):
        self._portfolio_positions = None
        self._enhanced_stock_data = None
        self.data_loader = DataLoader()
        self.summary = self.data_loader.perform_request(SUMMARY_API)
        self.all_portfolio_info = self.data_loader.perform_request(POSITIONS_API)
        self._cash_balance = round(self.summary["totalcashvalue"]["amount"])

    def get_full_porfolio_data(self):
        """Get complete portfolio data with minimal recalculation."""
        portfolio = self.get_portfolio_positions()
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
        total_portfolio_value = 0

        # Process all positions in a single pass
        for position in self.all_portfolio_info:
            stock = position["contractDesc"]
            mkt_value = round(position["mktValue"])

            category = categorizer.get_category(stock, mkt_value, public_reit_names)
            value = categorizer.get_value_for_category(stock, mkt_value, category)
            portfolio[category][stock] = value
            total_portfolio_value += value

            if category not in ["Bonds", "Short", "REIT", "Gold", "Commodities"]:
                total_stocks += value

        # Sort all dictionaries at once
        portfolio = {k: sort_dict(v) for k, v in portfolio.items()}
        portfolio[IB_STOCKS_VALUE] = round(total_stocks)

        # Calculate net cash balance
        short_mkt_value = calculate_total_mkt_value(portfolio[SHORT_SELLING_KEY])
        portfolio["Net_cash"] = self.cash_balance + short_mkt_value

        # Add total portfolio value including net cash
        portfolio["IB_Portfolio_Value"] = round(
            total_portfolio_value + portfolio["Net_cash"]
        )

        # Cache the result
        self._portfolio_positions = portfolio
        return portfolio

    def get_enhanced_stock_positions(self):
        """
        Get enhanced stock positions with additional details for China Stocks and Stocks categories.

        Returns:
            dict: Dictionary with 'China Stocks' and 'Stocks' categories containing detailed position information.
        """
        if self._enhanced_stock_data is not None:
            return self._enhanced_stock_data

        # Make sure portfolio positions are loaded
        if self._portfolio_positions is None:
            self._portfolio_positions = self.get_portfolio_positions()

        # Get total portfolio value
        total_portfolio_value = self._portfolio_positions["IB_Portfolio_Value"]

        # Initialize the enhanced stock data structure
        enhanced_data = {
            CHINA_STOCKS_KEY: {},
            IB_STOCKS_KEY: {},
            "metadata": {
                "total_stocks_value": self._portfolio_positions[IB_STOCKS_VALUE],
                "china_stocks_value": sum(
                    self._portfolio_positions[CHINA_STOCKS_KEY].values()
                ),
                "regular_stocks_value": sum(
                    self._portfolio_positions[IB_STOCKS_KEY].values()
                ),
                "total_portfolio_value": total_portfolio_value,
                "total_unrealized_pnl": 0,  # Will be updated as we process positions
                "total_cost_basis": 0,  # Will be updated as we process positions
            },
        }

        # Get portfolio positions to work with
        china_stocks = self._portfolio_positions[CHINA_STOCKS_KEY]
        regular_stocks = self._portfolio_positions[IB_STOCKS_KEY]
        total_stocks_value = enhanced_data["metadata"]["total_stocks_value"]

        # Process positions from the API response
        for position in self.all_portfolio_info:
            symbol = position["contractDesc"]

            # Check if this position is in China Stocks or Regular Stocks
            if symbol in china_stocks:
                category = CHINA_STOCKS_KEY
                market_value = china_stocks[symbol]
            elif symbol in regular_stocks:
                category = IB_STOCKS_KEY
                market_value = regular_stocks[symbol]
            else:
                # Skip positions that are not in China Stocks or Regular Stocks
                continue

            # Extract position details
            quantity = abs(position.get("position", 0))
            avg_price = position.get("avgPrice", 0)
            market_price = position.get("mktPrice", 0)

            # Calculate cost basis for this position
            cost_basis = avg_price * quantity

            # Update total cost basis
            enhanced_data["metadata"]["total_cost_basis"] += cost_basis

            # Calculate Unrealized P&L
            unrealized_pnl = (market_price - avg_price) * quantity

            # Calculate position-specific P&L percentage relative to its cost basis
            if cost_basis > 0:
                unrealized_pnl_percentage = (
                    (market_price - avg_price) / avg_price
                ) * 100
            else:
                unrealized_pnl_percentage = 0

            # Calculate percentages
            stocks_percentage = (
                (market_value / total_stocks_value) * 100
                if total_stocks_value > 0
                else 0
            )
            portfolio_percentage = (
                (market_value / total_portfolio_value) * 100
                if total_portfolio_value > 0
                else 0
            )

            # Create enhanced position data
            enhanced_data[category][symbol] = {
                "market_value": market_value,
                "quantity": quantity,
                "avg_price": avg_price,
                "current_price": market_price,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_percentage": round(unrealized_pnl_percentage, 2),
                "percentage_of_stocks": round(stocks_percentage, 2),
                "percentage_of_portfolio": round(portfolio_percentage, 2),
            }

            # Update total unrealized P&L
            enhanced_data["metadata"]["total_unrealized_pnl"] += unrealized_pnl

        # Calculate total unrealized P&L percentage relative to total cost basis
        total_unrealized_pnl = enhanced_data["metadata"]["total_unrealized_pnl"]
        total_cost_basis = enhanced_data["metadata"]["total_cost_basis"]

        if total_cost_basis > 0:
            enhanced_data["metadata"]["total_unrealized_pnl_percentage"] = round(
                (total_unrealized_pnl / total_cost_basis) * 100, 2
            )
        else:
            enhanced_data["metadata"]["total_unrealized_pnl_percentage"] = 0

        # Cache the result
        self._enhanced_stock_data = enhanced_data
        return enhanced_data

    def _parse_last_update_time(self, time_str):
        """
        Parse the last update time from IB format to a more readable date format.
        If parsing fails, return the original string.
        """
        if not time_str:
            return "Unknown"

        try:
            # IB may provide time in different formats, adapt as needed
            # Common format: "20240331-06:44:12"
            date_obj = datetime.strptime(time_str, "%Y%m%d-%H:%M:%S")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            # If parsing fails, return the original string
            return time_str

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

        # Test the new enhanced stock positions method
        enhanced_stocks = ib.get_enhanced_stock_positions()
        print("\n=== Enhanced Stock Positions ===")

        # Print metadata
        metadata = enhanced_stocks["metadata"]
        print(f"Total Portfolio Value: ${metadata['total_portfolio_value']}")
        print(f"Total Stocks Value: ${metadata['total_stocks_value']}")
        print(f"Total Unrealized P&L: {metadata['total_unrealized_pnl_percentage']}%")
        print(
            f"China Stocks Value: ${metadata['china_stocks_value']} ({metadata['china_stocks_value']/metadata['total_stocks_value']*100:.2f}%)"
        )
        print(
            f"Regular Stocks Value: ${metadata['regular_stocks_value']} ({metadata['regular_stocks_value']/metadata['total_stocks_value']*100:.2f}%)"
        )

        # Print China Stocks details
        print("\nChina Stocks:")
        for symbol, details in enhanced_stocks[CHINA_STOCKS_KEY].items():
            print(f"  {symbol}:")
            print(f"    Market Value: ${details['market_value']}")
            print(f"    Quantity: {details['quantity']} shares")
            print(f"    Avg Price: ${details['avg_price']:.2f}")
            print(f"    Current Price: ${details['current_price']:.2f}")
            print(f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%")
            print(f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%")
            print(f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%")

        # Print Regular Stocks details
        print("\nRegular Stocks:")
        for symbol, details in enhanced_stocks[IB_STOCKS_KEY].items():
            print(f"  {symbol}:")
            print(f"    Market Value: ${details['market_value']}")
            print(f"    Quantity: {details['quantity']} shares")
            print(f"    Avg Price: ${details['avg_price']:.2f}")
            print(f"    Current Price: ${details['current_price']:.2f}")
            print(f"    Unrealized P&L: {details['unrealized_pnl_percentage']}%")
            print(f"    % of Stocks Portfolio: {details['percentage_of_stocks']:.2f}%")
            print(f"    % of IB Portfolio: {details['percentage_of_portfolio']:.2f}%")

        print("========================\n")

    except Exception as e:
        print(f"ERROR: An error occurred: {str(e)}")

    finally:
        execution_time = time.time() - start_time
        print("\n=== Performance Metrics ===")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total Execution Time: {execution_time:.4f} seconds")


if __name__ == "__main__":
    main()
