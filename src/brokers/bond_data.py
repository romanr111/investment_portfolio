import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from ib_insync import *


@dataclass
class TradeRecord:
    """Data class to store trade information"""

    date: date
    quantity: float
    price: float
    commission: float
    conid: int
    cusip: Optional[str] = None
    isin: Optional[str] = None


class IBConnection:
    """Singleton class to manage IB connection"""

    _instance = None
    _ib = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(IBConnection, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_ib(cls) -> Optional[IB]:
        if cls._ib is None or not cls._ib.isConnected():
            cls._ib = IB()
        return cls._ib

    @classmethod
    def disconnect(cls):
        if cls._ib and cls._ib.isConnected():
            cls._ib.disconnect()
            cls._ib = None


class PurchaseDateFetcher:
    def __init__(self, host: str = "127.0.0.1", port: int = 4001, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib_connection = IBConnection()
        self.logger = self._setup_logger()

    @property
    def ib(self) -> IB:
        return self.ib_connection.get_ib()

    def _setup_logger(self) -> logging.Logger:
        """Setup logging configuration with control over IB loggers"""
        # Set IB loggers to WARNING level
        logging.getLogger("ib_insync").setLevel(logging.WARNING)
        logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)
        logging.getLogger("ib_insync.client").setLevel(logging.WARNING)

        # Configure PurchaseDateFetcher logger
        logger = logging.getLogger("PurchaseDateFetcher")
        logger.setLevel(logging.WARNING)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def connect(self) -> bool:
        """Establish connection to IB Gateway/TWS"""
        try:
            if self.ib.isConnected():
                return True

            self.logger.info(f"Connecting to IB at {self.host}:{self.port}")

            # Try to connect with increasing delays
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.ib.connect(
                        self.host, self.port, clientId=self.client_id, readonly=True
                    )
                    self.logger.info("Successfully connected to IB")
                    return True
                except Exception as e:
                    if "already in use" in str(e):
                        self.client_id += 1  # Try next client ID
                        continue
                    elif attempt < max_retries - 1:
                        time.sleep(2**attempt)  # Exponential backoff
                        continue
                    raise

        except Exception as e:
            self.logger.error(f"Failed to connect to IB: {str(e)}")
            return False

    def _get_contract_details(self, conid: int) -> Optional[Contract]:
        """Get contract details from IB"""
        try:
            contract = Bond(conId=conid)
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    qualified_contracts = self.ib.qualifyContracts(contract)
                    if not qualified_contracts:
                        self.logger.error(
                            f"Could not qualify contract with conId: {conid}"
                        )
                        return None
                    return qualified_contracts[0]
                except Exception as e:
                    if "read-only" in str(e).lower() and attempt < max_retries - 1:
                        time.sleep(2**attempt)
                        continue
                    raise

        except Exception as e:
            self.logger.error(f"Error getting contract details: {str(e)}")
            return None

    def _get_historical_bars(self, contract: Contract) -> Optional[List[BarData]]:
        """Get historical bars data"""
        try:
            self.logger.info(f"Requesting historical data for {contract.conId}")
            endDateTime = datetime.now().strftime("%Y%m%d %H:%M:%S")

            # Try BID data directly since we know TRADES might not be available
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime=endDateTime,
                durationStr="2 Y",
                barSizeSetting="1 day",
                whatToShow="BID",
                useRTH=True,
                formatDate=1,
            )

            if not bars:
                self.logger.warning("No historical data found")
                return None

            return bars

        except Exception as e:
            self.logger.error(f"Error getting historical data: {str(e)}")
            return None

    def _find_matching_bar(
        self, bars: List[BarData], avg_cost: float
    ) -> Optional[BarData]:
        """Find bar with matching price to average cost"""
        # Convert average cost per $1000 face value to percentage format
        target_price = avg_cost / 10  # Convert from 986.99 to 98.699%

        self.logger.info(f"Searching for bars matching average cost: {target_price}%")

        # Define acceptable price difference threshold (0.01%)
        threshold = 0.01

        # Sort bars by date to ensure we get the earliest matching bar
        sorted_bars = sorted(bars, key=lambda x: x.date)

        for bar in sorted_bars:
            # Check both open and close prices
            if abs(bar.open - target_price) <= threshold:
                self.logger.warning(
                    f"Found matching bar with open price {bar.open} on {bar.date}"
                )
                return bar
            elif abs(bar.close - target_price) <= threshold:
                self.logger.info(
                    f"Found matching bar with close price {bar.close} on {bar.date}"
                )
                return bar

        # If no exact match found, find the closest bar
        closest_bar = min(
            sorted_bars,
            key=lambda x: min(abs(x.open - target_price), abs(x.close - target_price)),
        )
        self.logger.error(
            f"No exact match found. Closest bar on {closest_bar.date} "
            f"with prices open: {closest_bar.open}, close: {closest_bar.close}"
        )
        return closest_bar

    def get_purchase_date(self, bond_id: str, avg_cost: float) -> Optional[date]:
        """
        Get purchase date based on matching historical price data to average cost

        Args:
            bond_id (str): Bond identifier (e.g., "IBCID668652380")
            avg_cost (float): Average cost per $1000 face value (e.g., 986.99)

        Returns:
            Optional[date]: Purchase date if found, None otherwise
        """
        try:
            if not bond_id.startswith("IBCID"):
                raise ValueError("Invalid bond identifier format")

            conid = int(bond_id.replace("IBCID", ""))
            self.logger.info(
                f"Searching purchase date for bond {conid} with avg cost ${avg_cost}"
            )

            if not self.ib.isConnected():
                if not self.connect():
                    return None

            contract = self._get_contract_details(conid)
            if not contract:
                return None

            # Get historical bars
            bars = self._get_historical_bars(contract)
            if not bars:
                return None

            # Find matching bar based on average cost
            matching_bar = self._find_matching_bar(bars, avg_cost)
            if matching_bar:
                return matching_bar.date

            self.logger.warning("Could not determine purchase date from price data")
            return None

        except Exception as e:
            self.logger.error(f"Error in get_purchase_date: {str(e)}")
            return None

        finally:
            if self.ib.isConnected():
                self.ib.disconnect()


class BondsClientIB:

    def calculate_bond_yield(
        self,
        purchase_date: date,
        initial_investment: float,
        unrealized_pnl: float,
        current_date: Optional[date] = None,
    ) -> Dict[str, float]:
        """
        Calculate daily and annual yield for a bond position.

        Args:
            purchase_date (date): Date of bond purchase
            initial_investment (float): Initial investment amount
            unrealized_pnl (float): Unrealized profit/loss
            current_date (date, optional): Current date for calculation

        Returns:
            dict: Dictionary containing daily and annual yields as percentages
        """
        if current_date is None:
            current_date = date.today()

        # Calculate days held
        days_held = (current_date - purchase_date).days
        if days_held <= 0:
            return {
                "daily_yield_percentage": 0.0,
                "annual_yield_percentage": 0.0,
                "days_held": 0,
            }

        # Calculate daily yield
        daily_yield = (unrealized_pnl / initial_investment) / days_held

        # Calculate annual yield (assuming 365 days)
        annual_yield = daily_yield * 365

        return {
            "daily_yield_percentage": daily_yield * 100,
            "annual_yield_percentage": annual_yield * 100,
            "days_held": days_held,
        }

    def get_bond_data(self, bond_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Enhanced get_bond_data function with yield calculations for multiple bonds

        Args:
            bond_ids (List[str]): List of bond identifiers (e.g., ["IBCID707867273", "IBCID668652380"])

        Returns:
            List[Optional[Dict[str, Any]]]: List of dictionaries containing bond data, or None for failed retrievals
        """
        fetcher = None
        results = []

        try:
            fetcher = PurchaseDateFetcher(client_id=int(time.time() % 9999))

            if not fetcher.connect():
                print("Failed to connect to IB Gateway/TWS.")
                return [None] * len(bond_ids)

            for bond_id in bond_ids:
                try:
                    if not bond_id.startswith("IBCID"):
                        raise ValueError(f"Invalid bond identifier format: {bond_id}")

                    conId = int(bond_id.replace("IBCID", ""))
                    bond_contract = Bond(conId=conId)
                    qualified_contracts = fetcher.ib.qualifyContracts(bond_contract)

                    if not qualified_contracts:
                        raise ValueError(
                            f"Could not qualify bond contract with ID: {conId}"
                        )

                    bond_contract = qualified_contracts[0]
                    contract_details = fetcher.ib.reqContractDetails(bond_contract)

                    if not contract_details:
                        raise ValueError("Could not fetch contract details")

                    details = contract_details[0]
                    cusip = next(
                        (tv.value for tv in details.secIdList if tv.tag == "CUSIP"),
                        None,
                    )
                    isin = next(
                        (tv.value for tv in details.secIdList if tv.tag == "ISIN"), None
                    )

                    ticker = fetcher.ib.reqMktData(bond_contract, "", False, False)
                    fetcher.ib.sleep(2)

                    positions = fetcher.ib.positions()
                    portfolio = fetcher.ib.portfolio()

                    position_size = next(
                        (
                            pos.position
                            for pos in positions
                            if pos.contract.conId == conId
                        ),
                        0,
                    )

                    portfolio_item = next(
                        (item for item in portfolio if item.contract.conId == conId),
                        None,
                    )

                    if portfolio_item:
                        avg_cost = portfolio_item.averageCost
                        market_value = portfolio_item.marketValue
                        unrealized_pnl = portfolio_item.unrealizedPNL
                    else:
                        avg_cost = market_value = unrealized_pnl = 0

                    purchase_date = fetcher.get_purchase_date(bond_id, avg_cost)
                    initial_investment = position_size * avg_cost

                    yields = (
                        self.calculate_bond_yield(
                            purchase_date=purchase_date,
                            initial_investment=initial_investment,
                            unrealized_pnl=unrealized_pnl,
                        )
                        if purchase_date
                        else {
                            "daily_yield_percentage": 0.0,
                            "annual_yield_percentage": 0.0,
                            "days_held": 0,
                        }
                    )

                    bond_data = {
                        "Bond Type": "T-Bill",
                        "IBCID": bond_id,
                        "CUSIP": cusip,
                        "ISIN": isin,
                        "Purchase Date": purchase_date,
                        "Position": position_size,
                        "Average Cost": avg_cost,
                        "Market Value": market_value,
                        "Market Price (per unit)": (
                            market_value / position_size if position_size else 0
                        ),
                        "Unrealized PNL": unrealized_pnl,
                        "Days Held": yields["days_held"],
                        "Daily Yield": yields["daily_yield_percentage"],
                        "Annual Yield": yields["annual_yield_percentage"],
                    }

                    results.append(bond_data)

                except Exception as e:
                    print(f"Error processing bond {bond_id}: {e}")
                    results.append(None)

            if results:
                print("\nFormatted Bond Data:")
                print(self.format_bond_data(results))
            return results

        except Exception as e:
            print(f"An error occurred: {e}")
            return [None] * len(bond_ids)

        finally:
            if fetcher and fetcher.ib.isConnected():
                fetcher.ib.disconnect()

    def format_bond_data(
        self, data: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> str:
        """Format bond data for display with proper handling of None/NaN values

        Args:
            data: Either a single bond data dictionary or a list of bond data dictionaries

        Returns:
            Formatted string representation of the bond data
        """
        if not data:
            return "No data available"

        # If data is a list, process each bond separately
        if isinstance(data, list):
            return "\n\n".join(
                self.format_bond_data(bond) for bond in data if bond is not None
            )

        formatted_output = []
        for key, value in data.items():
            if value is None:
                formatted_output.append(f"{key}: N/A")
            elif isinstance(value, float):
                if "Yield" in key:
                    formatted_output.append(f"{key}: {value:.4f}%")
                else:
                    formatted_output.append(f"{key}: {value:.2f}")
            elif isinstance(value, date):
                formatted_output.append(f"{key}: {value.strftime('%Y-%m-%d')}")
            else:
                formatted_output.append(f"{key}: {value}")

        return "\n".join(formatted_output)


# In your main execution code:
if __name__ == "__main__":
    bond_ids = ["IBCID707867273"]
    bonds_client = BondsClientIB()
    bond_data_list = bonds_client.get_bond_data(bond_ids)
    print(f"\nraw bond data - {bond_data_list}\n")
