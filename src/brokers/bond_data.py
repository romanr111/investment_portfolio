from ib_insync import *
from datetime import datetime, date
import math


def calculate_tbill_yield(
    purchase_price, market_value, days_left=90
):  # Default to 90 days for 13-week T-Bill
    """
    Calculate T-Bill yields using both discount and investment yield methods
    """
    face_value = 1000

    # Bank Discount Yield (standard for T-Bills)
    discount_yield = (
        ((face_value - purchase_price) / face_value) * (360 / days_left) * 100
    )

    # Bond Equivalent Yield (investment yield)
    bond_equivalent_yield = (
        ((face_value - purchase_price) / purchase_price) * (365 / days_left) * 100
    )

    # Simple yield based on current market value
    if market_value > 0:
        current_yield = (
            ((face_value - market_value / 24) / (market_value / 24))
            * (365 / days_left)
            * 100
        )
    else:
        current_yield = 0

    return discount_yield, bond_equivalent_yield, current_yield


def get_bond_data_with_yield(bond_id):
    ib = IB()
    try:
        ib.connect("127.0.0.1", 4001, clientId=1, readonly=True)

        if bond_id.startswith("IBCID"):
            conId = int(bond_id.replace("IBCID", ""))
        else:
            raise ValueError("Invalid bond identifier format.")

        # Create bond contract
        bond_contract = Bond(conId=conId)

        # First, get basic contract details
        qualified_contracts = ib.qualifyContracts(bond_contract)
        if not qualified_contracts:
            raise ValueError(f"Could not qualify bond contract with ID: {conId}")

        bond_contract = qualified_contracts[0]

        # Get detailed contract specifications
        contract_details = ib.reqContractDetails(bond_contract)
        if not contract_details:
            raise ValueError("Could not fetch contract details")

        details = contract_details[0]

        # Request market data
        ticker = ib.reqMktData(bond_contract, "", False, False)
        ib.sleep(2)  # Wait for market data

        # Get positions and portfolio data
        positions = ib.positions()
        portfolio = ib.portfolio()

        position_size = 0
        avg_cost = 0
        market_value = 0
        unrealized_pnl = 0

        for position in positions:
            if position.contract.conId == conId:
                position_size = position.position
                break

        for item in portfolio:
            if item.contract.conId == conId:
                avg_cost = item.averageCost
                market_value = item.marketValue
                unrealized_pnl = item.unrealizedPNL
                break

        # Print all available fields for debugging
        print("\nContract Details Fields:")
        for attr in dir(details):
            if not attr.startswith("_"):
                value = getattr(details, attr)
                if not callable(value):
                    print(f"{attr}: {value}")

        # Calculate estimated maturity based on average T-Bill duration
        # Most T-Bills are 4, 13, 26, or 52 weeks
        # We'll estimate based on the price difference from par
        price_diff = 1000 - avg_cost
        estimated_days = None

        if 2 <= price_diff <= 4:
            estimated_days = 28  # 4-week T-Bill
        elif 4 < price_diff <= 10:
            estimated_days = 91  # 13-week T-Bill
        elif 10 < price_diff <= 20:
            estimated_days = 182  # 26-week T-Bill
        elif price_diff > 20:
            estimated_days = 364  # 52-week T-Bill

        # Calculate yields
        discount_yield, bond_equivalent_yield, current_yield = calculate_tbill_yield(
            avg_cost, market_value, estimated_days
        )

        data = {
            "Bond Type": "T-Bill",
            "Position": position_size,
            "Average Cost": avg_cost,
            "Market Value": market_value,
            "Market Price (per unit)": (
                market_value / position_size if position_size else 0
            ),
            "Unrealized PNL": unrealized_pnl,
            "Estimated Days to Maturity": estimated_days,
            "Discount Yield (360-day)": discount_yield,
            "Bond Equivalent Yield (365-day)": bond_equivalent_yield,
            "Current Yield": current_yield,
        }

        return data

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    finally:
        if ib.isConnected():
            ib.disconnect()


def format_bond_data(data):
    """Format bond data for display with proper handling of None/NaN values"""
    if not data:
        return "No data available"

    formatted_output = []
    for key, value in data.items():
        if isinstance(value, float):
            if key in [
                "Discount Yield (360-day)",
                "Bond Equivalent Yield (365-day)",
                "Current Yield",
            ]:
                formatted_output.append(f"{key}: {value:.3f}%")
            else:
                formatted_output.append(f"{key}: {value:.2f}")
        else:
            formatted_output.append(f"{key}: {value}")

    return "\n".join(formatted_output)


if __name__ == "__main__":
    bond_id = "IBCID668652380"
    bond_data = get_bond_data_with_yield(bond_id)
    print("\nFormatted Bond Data:")
    print(format_bond_data(bond_data))
