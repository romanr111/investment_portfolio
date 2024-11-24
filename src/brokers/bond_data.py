import requests
from ib_insync import *
from datetime import datetime, date, timedelta
import math
import traceback
from typing import Optional, Tuple, Dict, Any
import random
import time
import pandas_datareader.data as web


def format_tbill_symbol(cusip: str) -> str:
    """
    Format T-Bill CUSIP into FRED series ID
    """
    if not cusip.startswith("912797"):
        return cusip

    # Map common T-Bill terms to FRED series IDs
    term_mapping = {
        "4W": "DTB4WK",  # 4-week
        "8W": "DTB8WK",  # 8-week
        "13W": "DTB3",  # 13-week
        "26W": "DTB6",  # 26-week
        "52W": "DTB1YR",  # 52-week
    }

    # For simplicity, default to 13-week T-Bill
    return term_mapping.get("13W", "DTB3")


def get_bond_market_data(cusip: str) -> Dict[str, Any]:
    """
    Get current market data for a bond
    """
    try:
        # For T-Bills, fetch yield from FRED
        if cusip.startswith("912797"):
            term = get_tbill_term_from_cusip(cusip)
            fred_series = term_to_fred_series(term)
            today = datetime.today()
            start_date = today - timedelta(days=7)  # Get data from the past week
            df = web.DataReader(fred_series, "fred", start_date, today)
            if not df.empty:
                latest_rate = df.iloc[-1].iloc[0]
                market_data = {
                    "YTM": latest_rate,  # Yield to Maturity
                    "Last Price": None,
                    "Bid": None,
                    "Ask": None,
                    "Volume": None,
                    "Previous Close": None,
                }
            else:
                market_data = {
                    "YTM": None,
                    "Last Price": None,
                    "Bid": None,
                    "Ask": None,
                    "Volume": None,
                    "Previous Close": None,
                }
            return market_data
        else:
            # Handle other bond types (you can implement this as needed)
            return {
                "Last Price": None,
                "Bid": None,
                "Ask": None,
                "Volume": None,
                "Previous Close": None,
                "YTM": None,
            }

    except Exception as e:
        print(f"Error fetching market data: {str(e)}")
        traceback.print_exc()

    # Return default values if anything fails
    return {
        "Last Price": None,
        "Bid": None,
        "Ask": None,
        "Volume": None,
        "Previous Close": None,
        "YTM": None,
    }


def fetch_bond_details_from_cusip(
    cusip: str,
) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    """
    Fetch bond details from CUSIP.
    For T-Bills, fetch the yield from FRED.
    """
    try:
        if cusip.startswith("912797"):  # T-Bill
            # Parse T-Bill details directly from CUSIP
            tbill_info = parse_tbill_cusip(cusip)
            maturity_date = tbill_info.get("maturity_date")
            issue_date = tbill_info.get("issue_date")
            term = tbill_info.get("term")

            # Get current T-Bill rate from FRED
            today = datetime.today()
            start_date = today - timedelta(days=7)  # Get data from the past week
            fred_series = term_to_fred_series(term)
            df = web.DataReader(fred_series, "fred", start_date, today)
            if not df.empty:
                latest_rate = df.iloc[-1].iloc[0]
                coupon = latest_rate
            else:
                coupon = None

            return maturity_date, issue_date, coupon

        else:
            # Handle other bond types (you can implement this as needed)
            return None, None, None

    except Exception as e:
        print(f"Error fetching bond details: {str(e)}")
        traceback.print_exc()
        return None, None, None


def parse_tbill_cusip(cusip: str) -> Dict[str, Any]:
    """
    Parse T-Bill CUSIP to extract issue and maturity information
    """
    if not cusip.startswith("912797"):
        return {}

    try:
        # For demonstration purposes, we'll assume a 13-week T-Bill
        # In practice, you would need a mapping from CUSIP to term
        term = "13W"  # Default to 13-week T-Bill

        # Calculate maturity date based on term
        issue_date = date.today()
        if term == "4W":
            maturity_date = issue_date + timedelta(weeks=4)
        elif term == "8W":
            maturity_date = issue_date + timedelta(weeks=8)
        elif term == "13W":
            maturity_date = issue_date + timedelta(weeks=13)
        elif term == "26W":
            maturity_date = issue_date + timedelta(weeks=26)
        elif term == "52W":
            maturity_date = issue_date + timedelta(weeks=52)
        else:
            maturity_date = issue_date + timedelta(weeks=13)  # Default to 13 weeks

        return {
            "maturity_date": maturity_date.strftime("%Y-%m-%d"),
            "issue_date": issue_date.strftime("%Y-%m-%d"),
            "cusip_type": "TBILL",
            "term": term,
        }

    except Exception as e:
        print(f"Error parsing T-Bill CUSIP: {str(e)}")

    return {}


def get_tbill_term_from_cusip(cusip: str) -> str:
    """
    Map CUSIP to T-Bill term.
    This is a placeholder function; in practice, you would have a mapping.
    """
    # For simplicity, return 13W for all T-Bills
    return "13W"


def term_to_fred_series(term: str) -> str:
    """
    Map T-Bill term to FRED series ID
    """
    term_mapping = {
        "4W": "DTB4WK",  # 4-week
        "8W": "DTB8WK",  # 8-week
        "13W": "DTB3",  # 13-week
        "26W": "DTB6",  # 26-week
        "52W": "DTB1YR",  # 52-week
    }
    return term_mapping.get(term, "DTB3")  # Default to 13-week


def get_bond_data_with_yield(
    bond_id: str, max_wait: int = 10
) -> Optional[Dict[str, Any]]:
    """
    Get comprehensive bond data including yields

    Args:
        bond_id: IB Contract ID prefixed with 'IBCID'
        max_wait: Maximum time to wait for IB connection

    Returns:
        Dictionary containing bond data or None if error occurs
    """
    ib = IB()
    try:
        # Connect to IB TWS/Gateway
        ib.connect("127.0.0.1", 4001, clientId=1, readonly=True, timeout=max_wait)

        # Validate bond_id format
        if not bond_id.startswith("IBCID"):
            raise ValueError("Bond ID must start with 'IBCID'")

        conId = int(bond_id.replace("IBCID", ""))

        # Create and qualify bond contract
        bond_contract = Bond(conId=conId, currency="USD", exchange="SMART")
        qualified_contracts = ib.qualifyContracts(bond_contract)

        if not qualified_contracts:
            raise ValueError(f"Could not qualify bond contract: {conId}")

        bond_contract = qualified_contracts[0]

        # Get contract details
        details = ib.reqContractDetails(bond_contract)[0]

        # Extract CUSIP
        cusip = next(
            (secId.value for secId in details.secIdList if secId.tag == "CUSIP"), None
        )

        if not cusip:
            raise ValueError("CUSIP not found in contract details")

        # Fetch bond details
        maturity_date_str, issue_date_str, coupon = fetch_bond_details_from_cusip(cusip)

        # Get market data
        market_data = get_bond_market_data(cusip)

        # Initialize data structure
        data = {
            "Bond Symbol": bond_contract.symbol,
            "Bond Details": bond_contract,
            "Bond Type": details.bondType,
            "CUSIP": cusip,
            "Issue Date": issue_date_str,
            "Maturity": maturity_date_str,
            "Coupon": coupon,
            "Position": 0,
            "Average Cost": 0,
            "Market Value": 0,
            "Realized PNL": 0,
            "Unrealized PNL": 0,
            "Days to Maturity": None,
            "Discount Yield": None,
            "Bond Equivalent Yield": None,
            "Current Yield": None,
            **market_data,
        }

        # Get position and portfolio data
        positions = {p.contract.conId: p.position for p in ib.positions()}
        portfolio = {p.contract.conId: p for p in ib.portfolio()}

        if conId in positions:
            data["Position"] = positions[conId]

        if conId in portfolio:
            portfolio_item = portfolio[conId]
            data["Average Cost"] = portfolio_item.averageCost
            data["Market Value"] = portfolio_item.marketValue
            data["Realized PNL"] = portfolio_item.realizedPNL
            data["Unrealized PNL"] = portfolio_item.unrealizedPNL

        # Calculate yields if we have maturity date
        if maturity_date_str and data["Average Cost"] > 0:
            try:
                maturity_date = datetime.strptime(maturity_date_str, "%Y-%m-%d").date()
                days_to_maturity = (maturity_date - date.today()).days
                data["Days to Maturity"] = days_to_maturity

                if days_to_maturity > 0:
                    if details.bondType == "TBILL":
                        # Calculate T-Bill specific yields
                        discount_yield, bey = calculate_tbill_yields(
                            price=data["Average Cost"],
                            days_to_maturity=days_to_maturity,
                        )
                        data["Discount Yield"] = discount_yield
                        data["Bond Equivalent Yield"] = bey
                        data["Current Yield"] = None  # T-Bills don't have current yield
                    else:
                        # Calculate yields for other bonds
                        discount_yield, bey, current_yield = calculate_yields(
                            price=data["Average Cost"],
                            face_value=1000,
                            days_to_maturity=days_to_maturity,
                            coupon=coupon,
                            bond_type=details.bondType,
                        )
                        data["Discount Yield"] = discount_yield
                        data["Bond Equivalent Yield"] = bey
                        data["Current Yield"] = current_yield

            except ValueError as e:
                print(f"Error processing maturity date: {e}")

        # Add additional market data if available
        if market_data.get("YTM"):
            data["YTM"] = market_data["YTM"]  # Already in percentage

        return data

    except Exception as e:
        print(f"Error fetching bond data: {str(e)}")
        traceback.print_exc()
        return None

    finally:
        if ib and ib.isConnected():
            ib.disconnect()


def calculate_tbill_yields(
    price: float, days_to_maturity: int
) -> Tuple[Optional[float], Optional[float]]:
    """
    Calculate T-Bill specific yields including Discount Yield and Bond Equivalent Yield (BEY)

    Args:
        price: Clean price of the T-Bill (per $1000 face value)
        days_to_maturity: Number of days until maturity

    Returns:
        Tuple of (discount_yield, bond_equivalent_yield)
        Both yields are expressed as percentages

    Notes:
        - T-Bills are zero-coupon instruments sold at a discount
        - Face value is typically $1000
        - Discount yield uses 360-day year (bank year)
        - Bond Equivalent Yield uses 365-day year (calendar year)
    """
    try:
        if days_to_maturity <= 0:
            return None, None

        # Convert price to per $100 basis if it's per $1000
        price_per_hundred = price / 10 if price > 200 else price

        # Discount Yield calculation
        # DY = [(Face Value - Purchase Price) / Face Value] × [360 / Days to Maturity] × 100
        discount_yield = (
            ((100 - price_per_hundred) / 100) * (360 / days_to_maturity) * 100
        )

        # Bond Equivalent Yield calculation
        # BEY = [(Face Value - Purchase Price) / Purchase Price] × [365 / Days to Maturity] × 100
        bond_equivalent_yield = (
            ((100 - price_per_hundred) / price_per_hundred)
            * (365 / days_to_maturity)
            * 100
        )

        # Round to 3 decimal places
        discount_yield = round(discount_yield, 3)
        bond_equivalent_yield = round(bond_equivalent_yield, 3)

        return discount_yield, bond_equivalent_yield

    except ZeroDivisionError:
        print("Error: Days to maturity cannot be zero")
        return None, None
    except Exception as e:
        print(f"Error calculating T-Bill yields: {str(e)}")
        return None, None


def calculate_yields(
    price: float,
    face_value: float,
    days_to_maturity: int,
    coupon: float,
    bond_type: str,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate yields for bonds other than T-Bills.

    Args:
        price: Price of the bond.
        face_value: Face value of the bond.
        days_to_maturity: Days until the bond matures.
        coupon: Annual coupon rate (as a percentage).
        bond_type: Type of the bond.

    Returns:
        Tuple of (discount_yield, bond_equivalent_yield, current_yield)
    """
    try:
        if days_to_maturity <= 0:
            return None, None, None

        # Current Yield
        current_yield = (coupon / price) * 100

        # Yield to Maturity (approximate)
        # This is a simplified calculation and may not be accurate for all bonds
        annual_coupon_payment = (coupon / 100) * face_value
        years_to_maturity = days_to_maturity / 365
        total_return = (face_value - price) + (
            annual_coupon_payment * years_to_maturity
        )
        ytm = (total_return / price) / years_to_maturity * 100

        # Round the yields
        current_yield = round(current_yield, 3)
        ytm = round(ytm, 3)

        return None, ytm, current_yield

    except Exception as e:
        print(f"Error calculating bond yields: {str(e)}")
        return None, None, None


def format_bond_data(data: Optional[Dict[str, Any]]) -> str:
    """
    Format bond data for display

    Args:
        data: Dictionary containing bond data

    Returns:
        Formatted string of bond data
    """
    if not data:
        return "No bond data available"

    formatted_output = []
    for key, value in data.items():
        if (
            key
            in [
                "Discount Yield",
                "Bond Equivalent Yield",
                "Current Yield",
                "Coupon",
                "YTM",
            ]
            and value is not None
        ):
            formatted_output.append(f"{key}: {value:.3f}%")
        elif isinstance(value, float):
            formatted_output.append(f"{key}: {value:.2f}")
        else:
            formatted_output.append(f"{key}: {value}")

    return "\n".join(formatted_output)


if __name__ == "__main__":
    bond_id = "IBCID668652380"
    bond_data = get_bond_data_with_yield(bond_id)
    print("\nFormatted Bond Data:")
    print(format_bond_data(bond_data))
