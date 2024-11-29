import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from ib_insync import IB, BarData, Bond, Contract


@dataclass
class TradeRecord:
    """Records individual bond trade details"""

    date: date
    quantity: float
    price: float
    commission: float
    conid: int
    cusip: Optional[str] = None
    isin: Optional[str] = None


class IBConnectionManager:
    """Manages Interactive Brokers connection with singleton pattern"""

    _instance = None
    _connection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(IBConnectionManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_connection(cls) -> Optional[IB]:
        """Returns existing IB connection or creates new one"""
        if cls._connection is None or not cls._connection.isConnected():
            cls._connection = IB()
        return cls._connection

    @classmethod
    def disconnect(cls):
        """Safely disconnects from IB"""
        if cls._connection and cls._connection.isConnected():
            cls._connection.disconnect()
            cls._connection = None


class LoggerConfig:
    """Centralizes logging configuration"""

    @staticmethod
    def setup_logger(name: str, level: int = logging.WARNING) -> logging.Logger:
        # Configure IB loggers
        for logger_name in ["ib_insync", "ib_insync.wrapper", "ib_insync.client"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)

        # Setup application logger
        logger = logging.getLogger(name)
        logger.setLevel(level)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger


class MarketDataFetcher:
    """Handles all market data retrieval operations"""

    def __init__(self, host: str = "127.0.0.1", port: int = 4001):
        self.host = host
        self.port = port
        self.ib = IBConnectionManager.get_connection()
        self.logger = LoggerConfig.setup_logger("MarketDataFetcher")

    def connect(self, client_id: int) -> bool:
        """Establishes connection to IB with retry logic"""
        try:
            if self.ib.isConnected():
                return True

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.ib.connect(
                        self.host, self.port, clientId=client_id, readonly=True
                    )
                    self.logger.info("Successfully connected to IB")
                    return True
                except Exception as e:
                    if "already in use" in str(e):
                        client_id += 1
                        continue
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
                        continue
                    raise
        except Exception as e:
            self.logger.error(f"Failed to connect to IB: {str(e)}")
            return False

    def get_contract_details(self, conid: int) -> Optional[Contract]:
        """Retrieves contract details with retry logic"""
        contract = Bond(conId=conid)
        max_retries = 3

        for attempt in range(max_retries):
            try:
                qualified_contracts = self.ib.qualifyContracts(contract)
                if not qualified_contracts:
                    self.logger.error(f"Could not qualify contract with conId: {conid}")
                    return None
                return qualified_contracts[0]
            except Exception as e:
                if "read-only" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                self.logger.error(f"Error getting contract details: {str(e)}")
                return None

    def get_historical_bars(self, contract: Contract) -> Optional[List[BarData]]:
        """Retrieves historical price data for a bond"""
        try:
            self.logger.info(f"Requesting historical data for {contract.conId}")
            end_datetime = datetime.now().strftime("%Y%m%d %H:%M:%S")

            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime=end_datetime,
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

    def find_matching_bar(
        self, bars: List[BarData], avg_cost: float
    ) -> Optional[BarData]:
        """Finds the bar with matching price to average cost"""
        target_price = avg_cost / 10  # Convert from per $1000 face value to percentage
        threshold = 0.01  # 0.01% acceptable difference

        self.logger.info(f"Searching for bars matching average cost: {target_price}%")
        sorted_bars = sorted(bars, key=lambda x: x.date)

        for bar in sorted_bars:
            if abs(bar.open - target_price) <= threshold:
                self.logger.info(
                    f"Found matching bar with open price {bar.open} on {bar.date}"
                )
                return bar
            elif abs(bar.close - target_price) <= threshold:
                self.logger.info(
                    f"Found matching bar with close price {bar.close} on {bar.date}"
                )
                return bar

        closest_bar = min(
            sorted_bars,
            key=lambda x: min(abs(x.open - target_price), abs(x.close - target_price)),
        )
        self.logger.warning(
            f"No exact match found. Using closest bar on {closest_bar.date} "
            f"with prices open: {closest_bar.open}, close: {closest_bar.close}"
        )
        return closest_bar

    def find_purchase_date(self, bond_id: str, avg_cost: float) -> Optional[date]:
        """Determines the purchase date based on historical price data"""
        try:
            if not bond_id.startswith("IBCID"):
                raise ValueError("Invalid bond identifier format")

            conid = int(bond_id.replace("IBCID", ""))
            self.logger.info(
                f"Finding purchase date for bond {conid} with avg cost ${avg_cost}"
            )

            contract = self.get_contract_details(conid)
            if not contract:
                return None

            bars = self.get_historical_bars(contract)
            if not bars:
                return None

            matching_bar = self.find_matching_bar(bars, avg_cost)
            return matching_bar.date if matching_bar else None

        except Exception as e:
            self.logger.error(f"Error finding purchase date: {str(e)}")
            return None


class BondAnalytics:
    """Handles bond calculations and analytics"""

    @staticmethod
    def calculate_yield(
        purchase_date: date,
        position: float,
        average_cost: float,
        unrealized_pnl: float,
        current_date: Optional[date] = None,
    ) -> Dict[str, float]:
        """Calculates daily and annual yield metrics"""
        if current_date is None:
            current_date = date.today()

        days_held = (current_date - purchase_date).days
        if days_held <= 0:
            return {
                "daily_yield_percentage": 0.0,
                "annual_yield_percentage": 0.0,
                "days_held": 0,
            }

        initial_investment = position * average_cost
        daily_yield = (unrealized_pnl / initial_investment) / days_held
        annual_yield = daily_yield * 365

        return {
            "daily_yield_percentage": daily_yield * 100,
            "annual_yield_percentage": annual_yield * 100,
            "days_held": days_held,
        }


class BondDataFormatter:
    """Handles formatting of bond data for display and analysis"""

    @staticmethod
    def format_data(data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> str:
        """Formats bond data with proper value handling"""
        if not data:
            return "No data available"

        if isinstance(data, list):
            return "\n\n".join(
                BondDataFormatter.format_data(bond) for bond in data if bond is not None
            )

        formatted_lines = []
        for key, value in data.items():
            if value is None:
                formatted_lines.append(f"{key}: N/A")
            elif isinstance(value, float):
                if "Yield" in key:
                    formatted_lines.append(f"{key}: {value:.4f}%")
                else:
                    formatted_lines.append(f"{key}: {value:.2f}")
            elif isinstance(value, date):
                formatted_lines.append(f"{key}: {value.strftime('%Y-%m-%d')}")
            else:
                formatted_lines.append(f"{key}: {value}")

        return "\n".join(formatted_lines)

    @staticmethod
    def format_holdings(
        bond_data: List[Dict[str, Any]]
    ) -> Dict[str, Tuple[float, float]]:
        """Formats bond holdings data for portfolio analysis"""
        return {
            bond["IBCID"]: (
                bond.get("Market Value", 0),
                bond.get("Annual Yield", 0) / 100,
            )
            for bond in bond_data
            if bond and "IBCID" in bond
        }


class IBBondsClient:
    """Main client class for managing bond operations"""

    def __init__(self):
        self.market_data = MarketDataFetcher()
        self.logger = LoggerConfig.setup_logger("BondsClient")

    def get_bond_data(self, bond_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Retrieves comprehensive bond data"""
        try:
            client_id = int(time.time() % 9999)
            if not self.market_data.connect(client_id):
                return [None] * len(bond_ids)

            results = []
            for bond_id in bond_ids:
                bond_data = self._process_single_bond(bond_id)
                results.append(bond_data)

            if results:
                self.logger.info("\nFormatted Bond Data:")
                self.logger.info(BondDataFormatter.format_data(results))

            return results

        except Exception as e:
            self.logger.error(f"Error processing bonds: {e}")
            return [None] * len(bond_ids)
        finally:
            IBConnectionManager.disconnect()

    def _process_single_bond(self, bond_id: str) -> Optional[Dict[str, Any]]:
        """Processes data for a single bond"""
        try:
            if not bond_id.startswith("IBCID"):
                raise ValueError(f"Invalid bond identifier format: {bond_id}")

            conid = int(bond_id.replace("IBCID", ""))
            contract = self.market_data.get_contract_details(conid)
            if not contract:
                return None

            return self._collect_bond_data(bond_id, contract, conid)

        except Exception as e:
            self.logger.error(f"Error processing bond {bond_id}: {e}")
            return None

    def _print_bond_data(self, data: Dict[str, Any]) -> None:
        """Print bond data with clearer cost presentation"""
        print(
            f"""
    Bond: {data['IBCID']} | CUSIP: {data['CUSIP']} | ISIN: {data['ISIN']}
    Position: {data['Position']:,.2f} units | Cost: ${data['Average Cost']:,.2f} | Market Value: ${data['Market Value']:,.2f} | P&L: ${data['Unrealized PNL']:,.2f}
    Purchase Date: {data['Purchase Date']} ({data['Days Held']} days) | Annual Yield: {data['Annual Yield']:.2f}%
    """
        )

    def _collect_bond_data(
        self, bond_id: str, contract: Contract, conid: int
    ) -> Dict[str, Any]:
        """Collects and assembles all data for a bond"""
        contract_details = self.market_data.ib.reqContractDetails(contract)[0]

        # Extract security IDs
        cusip = next(
            (tv.value for tv in contract_details.secIdList if tv.tag == "CUSIP"), None
        )
        isin = next(
            (tv.value for tv in contract_details.secIdList if tv.tag == "ISIN"), None
        )
        ticker = self.market_data.ib.reqMktData(contract, "", False, False)
        self.market_data.ib.sleep(2)

        # Get position and portfolio data
        position_data = self._get_position_data(conid)

        if position_data:
            yields = BondAnalytics.calculate_yield(
                purchase_date=position_data[
                    "Purchase Date"
                ],  # Changed from purchase_date
                position=position_data["Position"],  # Changed from position
                average_cost=position_data["Average Cost"],  # Changed from avg_cost
                unrealized_pnl=position_data[
                    "Unrealized PNL"
                ],  # Changed from unrealized_pnl
            )
        else:
            yields = {
                "daily_yield_percentage": 0.0,
                "annual_yield_percentage": 0.0,
                "days_held": 0,
            }

        bond_data = {
            "Bond Type": "T-Bill",
            "IBCID": bond_id,
            "CUSIP": cusip,
            "ISIN": isin,
            "Position": position_data["Position"],
            "Average Cost": position_data["Average Cost"],
            "Market Value": position_data["Market Value"],
            "Market Price (per unit)": position_data["Market Price (per unit)"],
            "Unrealized PNL": position_data["Unrealized PNL"],
            "Purchase Date": position_data["Purchase Date"],
            "Daily Yield": yields["daily_yield_percentage"],
            "Annual Yield": yields["annual_yield_percentage"],
            "Days Held": yields["days_held"],
        }
        self._print_bond_data(bond_data)
        return bond_data

    def _get_position_data(self, conid: int) -> Dict[str, Any]:
        """Retrieves position-specific data for a bond"""
        positions = self.market_data.ib.positions()
        portfolio = self.market_data.ib.portfolio()

        position = next(
            (pos.position for pos in positions if pos.contract.conId == conid), 0
        )
        portfolio_item = next(
            (item for item in portfolio if item.contract.conId == conid), None
        )

        if not portfolio_item:
            return {
                "Position": 0,
                "Average Cost": 0,
                "Market Value": 0,
                "Market Price (per unit)": 0,
                "Unrealized PNL": 0,
                "Purchase Date": date.today(),
            }

        # Get bond ID for purchase date lookup
        bond_id = f"IBCID{conid}"
        purchase_date = self.market_data.find_purchase_date(
            bond_id, portfolio_item.averageCost
        )

        return {
            "Position": position,
            "Average Cost": portfolio_item.averageCost,
            "Market Value": portfolio_item.marketValue,
            "Market Price (per unit)": (
                portfolio_item.marketValue / position if position else 0
            ),
            "Unrealized PNL": portfolio_item.unrealizedPNL,
            "Purchase Date": purchase_date,
        }

    def get_bond_main_info(self, bond_ids: List[str]) -> Dict[str, Tuple[float, float]]:
        """Retrieves main bond information for portfolio analysis"""
        data = self.get_bond_data(bond_ids)
        return BondDataFormatter.format_holdings(data)


if __name__ == "__main__":
    bond_ids = ["IBCID707867273"]
    client = IBBondsClient()
    bond_data = client.get_bond_main_info(bond_ids)
    print(f"\nBond portfolio data: {bond_data}\n")
