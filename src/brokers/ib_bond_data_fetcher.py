# IB Gateway dependant
from datetime import datetime
import math
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union, Generator

from ib_insync import IB, BarData, Bond, Contract

# Constants for connection management
BASE_CLIENT_ID = 1000
MAX_RETRIES = 3
RETRY_DELAY = 3
AUTH_TIMEOUT = 30


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


class IBConnectionPool:
    """Manages a pool of IB connections"""

    _instance = None
    _connections: Dict[int, IB] = {}
    _last_client_id = BASE_CLIENT_ID

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(IBConnectionPool, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_next_client_id(cls) -> int:
        """Returns the next available client ID"""
        cls._last_client_id += 1
        return cls._last_client_id

    @classmethod
    def get_connection(cls, host: str, port: int) -> Tuple[int, IB]:
        """Gets an available connection or creates a new one"""
        # Clean up disconnected sessions
        cls._cleanup_disconnected()

        # Try to find an existing available connection
        for client_id, ib in cls._connections.items():
            if not ib.isConnected():
                try:
                    ib.connect(host, port, clientId=client_id, readonly=True)
                    return client_id, ib
                except Exception:
                    continue

        # Create new connection if none available
        client_id = cls.get_next_client_id()
        ib = IB()
        cls._connections[client_id] = ib
        return client_id, ib

    @classmethod
    def _cleanup_disconnected(cls):
        """Removes disconnected sessions from the pool"""
        disconnected = [
            client_id
            for client_id, ib in cls._connections.items()
            if not ib.isConnected()
        ]
        for client_id in disconnected:
            del cls._connections[client_id]

    @classmethod
    def disconnect_all(cls):
        """Disconnects all connections in the pool"""
        for ib in cls._connections.values():
            if ib.isConnected():
                ib.disconnect()
        cls._connections.clear()


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
    """Handles all market data retrieval operations with improved connection management"""

    def __init__(self, host: str = "127.0.0.1", port: int = 4001):
        self.host = host
        self.port = port
        self.logger = LoggerConfig.setup_logger("MarketDataFetcher")
        self._connection_pool = IBConnectionPool()
        self.ib = None
        self.client_id = None

    @contextmanager
    def connection(self) -> Generator[IB, None, None]:
        """Context manager for handling IB connections"""
        try:
            self.client_id, self.ib = self._connection_pool.get_connection(
                self.host, self.port
            )
            if not self.ib.isConnected():
                self._connect_with_retry()
            yield self.ib
        finally:
            if self.ib and self.ib.isConnected():
                self.ib.disconnect()

    def _connect_with_retry(self) -> bool:
        """Establishes connection to IB with retry logic"""
        for attempt in range(MAX_RETRIES):
            try:
                self.ib.connect(
                    self.host,
                    self.port,
                    clientId=self.client_id,
                    readonly=True,
                    timeout=AUTH_TIMEOUT,
                )
                # Wait for connection to fully establish
                self.ib.sleep(1)

                if not self.ib.isConnected():
                    raise ConnectionError("Connection failed to establish")

                self.logger.info(
                    f"Successfully connected to IB with client ID {self.client_id}"
                )

                # Wait for data to be ready
                for _ in range(5):  # Wait up to 5 seconds
                    if len(self.ib.positions()) > 0 or len(self.ib.portfolio()) > 0:
                        return True
                    self.ib.sleep(1)

                # If we got here, we're connected but no data yet
                self.logger.warning("Connected but no position/portfolio data received")
                return True

            except Exception as e:
                self.logger.warning(
                    f"Connection attempt {attempt + 1} failed: {str(e)}"
                )
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2**attempt)  # Exponential backoff
                    self.logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                raise ConnectionError(
                    f"Failed to connect after {MAX_RETRIES} attempts: {str(e)}"
                )
        return False

    def get_contract_details(self, conid: int) -> Optional[Contract]:
        """Retrieves and qualifies a T-Bill contract using data dynamically fetched from IB."""
        contract = Contract()
        contract.conId = conid
        contract.secType = "BILL"
        contract.exchange = "SMART"
        contract.currency = "USD"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # First, request contract details to discover maturity and other fields
                details = self.ib.reqContractDetails(contract)
                if not details:
                    self.logger.error(
                        f"Could not find contract details for conId: {conid}"
                    )
                    return None

                # Extract additional info from the returned contract details
                fetched_contract = details[0].contract

                # Update the contract object dynamically without hardcoding values
                if fetched_contract.lastTradeDateOrContractMonth:
                    contract.lastTradeDateOrContractMonth = (
                        fetched_contract.lastTradeDateOrContractMonth
                    )
                if fetched_contract.symbol:
                    contract.symbol = fetched_contract.symbol
                if fetched_contract.localSymbol:
                    contract.localSymbol = fetched_contract.localSymbol
                if fetched_contract.tradingClass:
                    contract.tradingClass = fetched_contract.tradingClass

                # Now that the contract is fully specified, qualify it
                qualified_contracts = self.ib.qualifyContracts(contract)
                if not qualified_contracts:
                    self.logger.error(
                        f"Could not fully qualify contract for conId: {conid}"
                    )
                    return None

                return qualified_contracts[0]

            except Exception as e:
                if "read-only" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                self.logger.error(
                    f"Error getting contract details for conId {conid}: {str(e)}"
                )
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
    def format_holdings(
        bond_data: List[Dict[str, Any]]
    ) -> Dict[str, Tuple[float, float]]:
        """Formats bond holdings data for portfolio analysis with improved error handling"""
        holdings = {}

        # Handle case where entire list is None
        if not bond_data:
            return holdings

        for bond in bond_data:
            # Skip None entries or invalid data
            if not bond or not isinstance(bond, dict):
                continue

            # Get IBCID, default to None if missing
            bond_id = bond.get("IBCID")
            if not bond_id:
                continue

            # Get market value and yield with safe defaults
            market_value = bond.get("Market Value", 0.0)
            annual_yield = bond.get("Annual Yield", 0.0)

            # Ensure we have numeric values
            try:
                market_value = float(market_value)
                annual_yield = (
                    float(annual_yield) / 100.0
                )  # Convert percentage to decimal
            except (TypeError, ValueError):
                continue

            holdings[bond_id] = (market_value, annual_yield)

        return holdings

    @staticmethod
    def format_data(data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> str:
        """Formats bond data with proper value handling and error checking"""
        if not data:
            return "No data available"

        if isinstance(data, list):
            formatted = []
            for item in data:
                if item is not None:
                    formatted.append(BondDataFormatter.format_data(item))
            return "\n\n".join(formatted) if formatted else "No data available"

        formatted_lines = []
        for key, value in data.items():
            if value is None:
                formatted_lines.append(f"{key}: N/A")
            elif isinstance(value, float):
                if any(
                    yield_term in key.lower()
                    for yield_term in ["yield", "rate", "percentage"]
                ):
                    formatted_lines.append(f"{key}: {value:.4f}%")
                else:
                    formatted_lines.append(f"{key}: {value:.2f}")
            elif isinstance(value, (date, datetime)):
                formatted_lines.append(f"{key}: {value.strftime('%Y-%m-%d')}")
            else:
                formatted_lines.append(f"{key}: {value}")

        return "\n".join(formatted_lines)


class IBBondsClient:
    def __init__(self):
        self.market_data = MarketDataFetcher()
        self.logger = LoggerConfig.setup_logger(
            "BondsClient", level=logging.INFO
        )  # Changed to INFO level
        self.ib = None

    def get_bond_data(self, bond_ids: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Retrieves comprehensive bond data using managed connection with improved error handling"""
        try:
            with self.market_data.connection() as ib:
                self.ib = ib
                self.logger.info(f"Processing {len(bond_ids)} bonds...")

                results = []
                for bond_id in bond_ids:
                    try:
                        bond_data = self._process_single_bond(bond_id, ib)
                        if bond_data:
                            results.append(bond_data)
                        else:
                            self.logger.warning(f"No data retrieved for bond {bond_id}")
                            results.append(None)
                    except Exception as e:
                        self.logger.error(f"Error processing bond {bond_id}: {str(e)}")
                        results.append(None)
                        continue
                        # Log overall results summary
                valid_results = len([r for r in results if r is not None])
                self.logger.info(
                    f"Processed {valid_results} out of {len(bond_ids)} bonds successfully"
                )
                return results

        except Exception as e:
            self.logger.error(f"Error processing bonds: {str(e)}")
            return [None] * len(bond_ids)
        finally:
            self.ib = None

    def _process_single_bond(self, bond_id: str, ib: IB) -> Optional[Dict[str, Any]]:
        """Processes data for a single bond with improved error handling"""
        try:
            if not bond_id.startswith("IBCID"):
                raise ValueError(f"Invalid bond identifier format: {bond_id}")

            conid = int(bond_id.replace("IBCID", ""))

            qualified_contract = self.market_data.get_contract_details(conid)
            if not qualified_contract:
                self.logger.error(f"Could not qualify contract with conId: {conid}")
                return None

            self.logger.info(
                f"Contract details: "
                f"conId={qualified_contract.conId}, "
                f"symbol={qualified_contract.symbol}, "
                f"exchange={qualified_contract.exchange}, "
                f"lastTradeDateOrContractMonth={qualified_contract.lastTradeDateOrContractMonth}"
            )

            contract_details = ib.reqContractDetails(qualified_contract)
            if not contract_details:
                self.logger.error(f"No contract details found for {bond_id}")
                return None

            # Get position data first
            position_data = self._get_position_data(conid)
            if not position_data:
                self.logger.error(f"No position data found for {bond_id}")
                return None

            # Extract security IDs from contract details
            cusip = None
            isin = None
            if contract_details and contract_details[0].secIdList:
                for sec_id in contract_details[0].secIdList:
                    if sec_id.tag == "CUSIP":
                        cusip = sec_id.value
                    elif sec_id.tag == "ISIN":
                        isin = sec_id.value

            # Get all required dates
            purchase_date = position_data.get("Purchase Date", date.today())
            maturity_date = position_data.get("Maturity Date")
            current_date = date.today()
            days_held = (current_date - purchase_date).days

            # Calculate yield
            face_value = 1000.0
            purchase_price = position_data.get("Average Cost", 0.0)
            position_qty = position_data.get("Position", 0.0)
            market_value = position_data.get("Market Value", 0.0)
            unrealized_pnl = position_data.get("Unrealized PNL", 0.0)

            # Calculate yield based on available data
            if maturity_date and purchase_price > 0:
                days_to_maturity = (maturity_date - purchase_date).days
                if days_to_maturity > 0:
                    annual_yield = (
                        ((face_value - purchase_price) / purchase_price)
                        * (365.0 / days_to_maturity)
                        * 100.0
                    )
                else:
                    annual_yield = 0.0
            else:
                yields = BondAnalytics.calculate_yield(
                    purchase_date=purchase_date,
                    position=position_qty,
                    average_cost=purchase_price,
                    unrealized_pnl=unrealized_pnl,
                )
                annual_yield = yields.get("annual_yield_percentage", 0.0)

            # Clamp negative yields
            annual_yield = max(annual_yield, 0.0)

            # Combine all data with safe defaults
            bond_data = {
                "IBCID": bond_id,
                "CUSIP": cusip,
                "ISIN": isin,
                "Position": position_qty,
                "Average Cost": purchase_price,
                "Market Value": market_value,
                "Unrealized PNL": unrealized_pnl,
                "Purchase Date": purchase_date,
                "Days Held": days_held,
                "Annual Yield": annual_yield,
                "Maturity Date": maturity_date,
            }

            self._print_bond_data(bond_data)
            return bond_data

        except Exception as e:
            self.logger.error(f"Error processing bond {bond_id}: {str(e)}")
            return None

    def cleanup(self):
        """Cleanup method to be called when done with the client"""
        IBConnectionPool.disconnect_all()

    def _print_bond_data(self, data: Dict[str, Any]) -> None:
        """Print bond data with clearer cost presentation and error handling"""
        try:
            print(
                f"""
        Bond: {data.get('IBCID', 'N/A')} | CUSIP: {data.get('CUSIP', 'N/A')} | ISIN: {data.get('ISIN', 'N/A')}
        Position: {data.get('Position', 0):,.2f} units | Cost: ${data.get('Average Cost', 0):,.2f} | Market Value: ${data.get('Market Value', 0):,.2f} | P&L: ${data.get('Unrealized PNL', 0):,.2f}
        Purchase Date: {data.get('Purchase Date', 'N/A')} ({data.get('Days Held', 0)} days) | Maturity Date: {data.get('Maturity Date', 'N/A')} | Annual Yield: {data.get('Annual Yield', 0):.2f}%
        """
            )
        except Exception as e:
            self.logger.error(f"Error printing bond data: {str(e)}")
            print("Error printing bond data. See logs for details.")

    def _collect_bond_data(
        self, bond_id: str, contract: Contract, conid: int, ib: IB
    ) -> Dict[str, Any]:
        # We still request contractDetails to get CUSIP/ISIN
        contract_details = ib.reqContractDetails(contract)[0]

        # Extract security IDs
        cusip = next(
            (tv.value for tv in contract_details.secIdList if tv.tag == "CUSIP"), None
        )
        isin = next(
            (tv.value for tv in contract_details.secIdList if tv.tag == "ISIN"), None
        )

        # Request market data (if available)
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(2)

        # Get position and portfolio data (which now includes Maturity Date)
        position_data = self._get_position_data(conid)
        purchase_date = position_data["Purchase Date"]
        maturity_date = position_data["Maturity Date"]
        purchase_price = position_data["Average Cost"]
        position_qty = position_data["Position"]

        # If T-Bill or zero-coupon
        face_value = 1000.0
        if maturity_date and purchase_price > 0:
            days_to_maturity = (maturity_date - purchase_date).days
            if days_to_maturity > 0:
                annual_yield = (
                    ((face_value - purchase_price) / purchase_price)
                    * (365.0 / days_to_maturity)
                    * 100.0
                )
            else:
                annual_yield = 0.0
        else:
            # fallback to IB analytics or coupon logic
            yields = BondAnalytics.calculate_yield(
                purchase_date=purchase_date,
                position=position_qty,
                average_cost=purchase_price,
                unrealized_pnl=position_data["Unrealized PNL"],
            )
            annual_yield = yields["annual_yield_percentage"]

        # clamp negative yields if you prefer
        annual_yield = max(annual_yield, 0.0)

        # compute the 'market value' as if it were near face value or use IB's data
        market_value = position_data["Market Value"]  # but you might re-scale if needed

        bond_data = {
            "IBCID": bond_id,
            "Position": position_qty,
            "Average Cost": purchase_price,
            "Market Value": market_value,
            "Unrealized PNL": position_data["Unrealized PNL"],
            "Purchase Date": purchase_date,
            "Days Held": (date.today() - purchase_date).days,
            "Annual Yield": annual_yield,
            "Maturity Date": maturity_date,
        }

        # If no market price is available, compute yield-to-maturity from Maturity Date if present
        if (
            math.isnan(bond_data["Market Price (per unit)"])
            and bond_data["Maturity Date"]
        ):
            maturity_date = bond_data["Maturity Date"]
            purchase_date = bond_data["Purchase Date"]
            days_held = bond_data["Days Held"]
            days_total = (maturity_date - purchase_date).days
            purchase_price = bond_data["Average Cost"]
            face_value = 1000.0

            if days_total > 0:
                # Compute yield-to-maturity based on purchase price and face value
                annual_yield = (
                    ((face_value - purchase_price) / purchase_price)
                    * (365.0 / days_total)
                    * 100.0
                )
            else:
                # If no future maturity, no yield
                annual_yield = 0.0

            daily_yield = annual_yield / 365.0
            annual_yield_dec = annual_yield / 100.0

            # Compute current theoretical price after days_held
            # Closer to maturity = higher price than at purchase if yield > 0
            if days_total > days_held and annual_yield_dec > 0:
                current_price = face_value / (
                    1.0 + annual_yield_dec * ((days_total - days_held) / 365.0)
                )
            else:
                # If no future days or zero yield, fallback to purchase price
                current_price = purchase_price

            # Compute market value and unrealized PNL
            market_value = int(round(current_price * bond_data["Position"]))
            unrealized_pnl = market_value - int(
                round(purchase_price * bond_data["Position"])
            )

            # Update bond data
            bond_data["Market Price (per unit)"] = current_price
            bond_data["Market Value"] = market_value
            bond_data["Annual Yield"] = annual_yield
            bond_data["Daily Yield"] = daily_yield
            bond_data["Unrealized PNL"] = unrealized_pnl

            # Since Unrealized PNL depends on actual market data, we can approximate:
            # Unrealized PNL = Market Value - (Purchase Price * Position)
            unrealized_pnl = market_value - (purchase_price * bond_data["Position"])
            bond_data["Unrealized PNL"] = unrealized_pnl

        self._print_bond_data(bond_data)
        return bond_data

    def _get_position_data(self, conid: int) -> Dict[str, Any]:
        """Get position data for a specific contract ID with corrected market value calculation"""
        if not self.ib or not self.ib.isConnected():
            raise ConnectionError("No active IB connection")

        positions = self.ib.reqPositions()

        position_data = next(
            (pos for pos in positions if pos.contract.conId == conid), None
        )

        if not position_data:
            self.logger.warning(f"No position found for conid: {conid}")
            return {
                "Position": 0,
                "Average Cost": 0,
                "Market Value": 0,
                "Unrealized PNL": 0,
                "Purchase Date": date.today(),
                "Maturity Date": None,
            }

        pos_contract = position_data.contract

        # Store maturity date before qualification
        original_maturity = pos_contract.lastTradeDateOrContractMonth

        # Ensure necessary fields for contract qualification
        if not pos_contract.exchange:
            pos_contract.exchange = "SMART"
        if not pos_contract.symbol:
            pos_contract.symbol = "US-T"
        if not pos_contract.secType:
            pos_contract.secType = "BILL"

        # Qualify the contract
        qualified_pos_contracts = self.ib.qualifyContracts(pos_contract)
        if not qualified_pos_contracts:
            self.logger.error(f"Could not qualify position contract for conid: {conid}")
            return {
                "Position": position_data.position,
                "Average Cost": position_data.avgCost,
                "Market Value": 0,
                "Unrealized PNL": 0,
                "Purchase Date": date.today(),
                "Maturity Date": None,
            }

        pos_contract = qualified_pos_contracts[0]

        # Restore original maturity date if lost during qualification
        if not pos_contract.lastTradeDateOrContractMonth and original_maturity:
            pos_contract.lastTradeDateOrContractMonth = original_maturity

        # Get market data
        ticker = self.ib.reqMktData(
            pos_contract,
            genericTickList="100,101,104,106,165,221,225,232,236",
            snapshot=False,
        )

        # Wait for market data
        timeout = 5
        while timeout > 0 and math.isnan(ticker.marketPrice()):
            self.ib.sleep(1)
            timeout -= 1
            if timeout % 2 == 0:
                self.logger.info(
                    f"Waiting for market data... {timeout} seconds remaining"
                )

        # Calculate market value using FACE VALUE of $1000
        FACE_VALUE = 1000.0
        position_size = position_data.position
        avg_cost = position_data.avgCost

        # Get the market price - it comes as a percentage of face value
        market_price_pct = ticker.marketPrice()
        if math.isnan(market_price_pct) or market_price_pct == 0:
            self.logger.warning(
                f"Could not get market price for {conid}, using average cost"
            )
            # Convert average cost to percentage of face value
            market_price_pct = (avg_cost / FACE_VALUE) * 100

        # Calculate the actual price per bond
        price_per_bond = (market_price_pct / 100) * FACE_VALUE

        # Calculate total market value
        market_value = price_per_bond * position_size

        # Calculate cost basis and unrealized PNL
        cost_basis = avg_cost * position_size
        unrealized_pnl = market_value - cost_basis

        # Get purchase date
        bond_id = f"IBCID{conid}"
        purchase_date = self.market_data.find_purchase_date(bond_id, avg_cost)
        if not purchase_date:
            purchase_date = date.today()

        # Parse maturity date if available
        maturity_date = None
        if (
            pos_contract.lastTradeDateOrContractMonth
            and len(pos_contract.lastTradeDateOrContractMonth) == 8
        ):
            try:
                maturity_date = datetime.strptime(
                    pos_contract.lastTradeDateOrContractMonth, "%Y%m%d"
                ).date()
            except ValueError:
                self.logger.warning(
                    f"Invalid maturity date format: {pos_contract.lastTradeDateOrContractMonth}"
                )

        return {
            "Position": position_size,
            "Average Cost": avg_cost,
            "Market Value": market_value,
            "Unrealized PNL": unrealized_pnl,
            "Purchase Date": purchase_date,
            "Maturity Date": maturity_date,
        }

    def get_bond_main_info(self, bond_ids: List[str]) -> Dict[str, Tuple[float, float]]:
        """Retrieves main bond information for portfolio analysis with improved error handling"""
        try:
            data = self.get_bond_data(bond_ids)
            holdings = BondDataFormatter.format_holdings(data)

            return holdings
        except Exception as e:
            self.logger.error(f"Error in get_bond_main_info: {e}")
            return {}


if __name__ == "__main__":
    bond_ids = ["IBCID722427489"]
    client = IBBondsClient()
    try:
        bond_data = client.get_bond_main_info(bond_ids)
        print(f"\nBond portfolio data: {bond_data}\n")
    finally:
        client.cleanup()
