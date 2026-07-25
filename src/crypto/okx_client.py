# -------------------------------- DONE --------------------------------
from decimal import Decimal
import time
import json
import hmac
import base64
import hashlib
from typing import Dict, List, Tuple, Optional
import requests
from data.api_keys import OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE
from src.crypto.base_exchange_client import ExchangeBase


class OKXClient(ExchangeBase):
    """OKX API wrapper with common exchange functionality."""

    API_URL = "https://www.okx.com"
    API_VERSION = "/api/v5"

    def __init__(self) -> None:
        """Initialize OKX client and validate connection."""
        self.api_key = OKX_API_KEY
        self.secret_key = OKX_SECRET_KEY
        self.passphrase = OKX_PASSPHRASE

        if not all([self.api_key, self.secret_key, self.passphrase]):
            raise ValueError("API key, secret key, and passphrase must be provided.")

        super().__init__()
        self.account_balances = self.get_spot_account_balances()
        self.simple_earn_data = self.get_simple_earn_data()

    def _validate_connection(self) -> bool:
        """Validate OKX API connection."""
        return all([self.api_key, self.secret_key, self.passphrase])

    def _generate_signature(
        self, timestamp: str, method: str, request_path: str, body: str = ""
    ) -> str:
        """Generate signature for OKX API authentication."""
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            bytes(self.secret_key, "utf-8"),
            msg=bytes(message, "utf-8"),
            digestmod=hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format (UTC)."""
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    def _send_request(
        self, method: str, endpoint: str, params: Dict = None, body: Dict = None
    ) -> Dict:
        """Send request to OKX API."""
        timestamp = self._get_timestamp()
        body_str = json.dumps(body) if body else ""
        params_str = (
            f"?{'&'.join([f'{k}={v}' for k, v in params.items()])}" if params else ""
        )
        request_path = f"{self.API_VERSION}{endpoint}{params_str}"

        signature = self._generate_signature(timestamp, method, request_path, body_str)
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

        try:
            response = requests.request(
                method,
                f"{self.API_URL}{request_path}",
                headers=headers,
                data=body_str if method.upper() == "POST" else None,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") != "0":
                raise Exception(f"API Error: {data.get('msg')}")
            return data.get("data", [])
        except Exception as e:
            print(f"ERROR: API request failed: {e}")
            raise

    def get_spot_account_balances(self) -> Dict[str, float]:
        """Get all account balances."""
        endpoint = "/asset/balances"
        data = self._send_request("GET", endpoint)
        raw_balances = {
            detail.get("ccy"): float(detail.get("bal", 0)) for detail in data
        }
        balances = self._filter_small_balances(raw_balances)
        return balances

    def _get_simple_earn_market_rates(self) -> Dict[str, float]:
        """Get current market rates for Simple Earn products."""
        endpoint = "/finance/savings/lending-rate-summary"
        data = self._send_request("GET", endpoint)

        rates = {}
        for item in data:
            ccy = item.get("ccy")
            rate = float(
                item.get("estRate", item.get("avgRate", item.get("preRate", 0)))
            )
            rates[ccy] = rate / 100 if rate > 0 else 0
        return rates

    def get_simple_earn_data(self) -> List[Dict]:
        """Get Simple Earn lending positions with current rates."""
        endpoint = "/finance/savings/balance"
        data = self._send_request("GET", endpoint)
        market_rates = self._get_simple_earn_market_rates()

        for position in data:
            ccy = position.get("ccy")
            decimal_rate = market_rates.get(ccy, 0)
            position["rate"] = decimal_rate
        return data

    # Rest of the DeFi-related methods remain unchanged as they're OKX-specific
    def get_active_defi_orders(
        self,
        product_id: Optional[str] = None,
        protocol_type: Optional[str] = None,
        ccy: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[Dict]:
        endpoint = "/finance/staking-defi/orders-active"
        params = {
            k: v
            for k, v in {
                "productId": product_id,
                "protocolType": protocol_type,
                "ccy": ccy,
                "state": state,
            }.items()
            if v is not None
        }
        return self._send_request("GET", endpoint, params=params)

    def get_active_defi_orders(
        self,
        product_id: Optional[str] = None,
        protocol_type: Optional[str] = None,
        ccy: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieves active On-chain earn and DeFi orders.

        Args:
            product_id (str, optional): Product ID to filter.
            protocol_type (str, optional): Protocol type (e.g., 'defi', 'staking').
            ccy (str, optional): Investment currency, e.g., 'BTC'.
            state (str, optional): Order state to filter.

        Returns:
            List[Dict]: A list of active staking and DeFi orders.
        """
        endpoint = "/finance/staking-defi/orders-active"
        params = {}
        if product_id:
            params["productId"] = product_id
        if protocol_type:
            params["protocolType"] = protocol_type
        if ccy:
            params["ccy"] = ccy
        if state:
            params["state"] = state

        data = self._send_request("GET", endpoint, params=params)
        return data

    def get_staking_defi_order_history(
        self,
        product_id: Optional[str] = None,
        protocol_type: Optional[str] = None,
        ccy: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        limit: Optional[int] = 5,
    ) -> List[Dict]:
        """
        Retrieves staking and DeFi order history.

        Args:
            product_id (str, optional): Product ID to filter.
            protocol_type (str, optional): Protocol type (e.g., 'defi', 'staking').
            ccy (str, optional): Investment currency, e.g., 'BTC'.
            after (str, optional): Pagination parameter to get records earlier than the specified ordId.
            before (str, optional): Pagination parameter to get records newer than the specified ordId.
            limit (int, optional): Number of results to retrieve, default is 5. Maximum is 100.

        Returns:
            List[Dict]: A list of staking and DeFi order history records.
        """
        endpoint = "/finance/staking-defi/orders-history"
        params = {"limit": str(limit)}
        if product_id:
            params["productId"] = product_id
        if protocol_type:
            params["protocolType"] = protocol_type
        if ccy:
            params["ccy"] = ccy
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        data = self._send_request("GET", endpoint, params=params)
        return data


class OKXFiltered(OKXClient):
    """
    Extends OKX class with additional filtering and data processing capabilities.
    """

    def __init__(self) -> None:
        super().__init__()

    def get_crypto_balances(self) -> Dict[str, float]:
        """
        Retrieves and filters cryptocurrency balances, excluding stablecoins and balances less than 0.001.

        Returns:
            Dict[str, float]: Filtered cryptocurrency balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        crypto_balances = {
            asset: balance
            for asset, balance in self.account_balances.items()
            if asset not in STABLECOINS and balance >= 0.001
        }
        return crypto_balances

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """Get aggregated crypto balances from spot and savings."""
        crypto_balances = dict(self.get_crypto_balances())
        savings_positions = self.get_savings_positions().get("okx", {})
        stablecoins = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        for asset, (principal, _) in savings_positions.items():
            if asset not in stablecoins:
                crypto_balances[asset] = (
                    crypto_balances.get(asset, 0.0) + float(principal)
                )
        return crypto_balances

    def get_cash_balance(self) -> int:
        """
        Calculates total balance of stablecoins, filtering out balances less than 1.

        Returns:
            int: Sum of rounded stablecoin balances, or 0 if no qualifying balances exist.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}

        stablecoin_balances = {
            asset: round(float(balance))
            for asset, balance in self.account_balances.items()
            if asset in STABLECOINS and float(balance) >= 1
        }

        return sum(stablecoin_balances.values()) if stablecoin_balances else 0

    def get_simple_earn_positions(self) -> Dict[str, Tuple[float, float]]:
        """
        Processes simple earn lending products to extract principal and effective yield.

        Returns:
            Dict[str, Tuple[float, float]]: A dictionary with assets as keys and a
            (principal, effective_yield) as values.
        """
        lending_positions = {}
        for product in self.simple_earn_data:
            asset = product.get("ccy")
            principal = float(Decimal(product.get("amt", 0)))
            # Convert rate from decimal to percentage (e.g., 0.0005 -> 0.055 for 5.5%)
            yield_rate = float(product.get("rate", 0)) * 100
            if principal > 0:
                if asset in lending_positions:
                    existing_principal, existing_yield = lending_positions[asset]
                    total_principal = existing_principal + principal
                    weighted_yield = (
                        existing_principal * existing_yield + principal * yield_rate
                    ) / total_principal
                    lending_positions[asset] = (total_principal, weighted_yield)
                else:
                    lending_positions[asset] = (principal, yield_rate)
        return lending_positions

    def get_defi_protocol_list(self) -> List[Dict]:
        """
        Retrieves the list of supported DeFi protocols and their products.
        """
        endpoint = "/finance/staking-defi/offers"
        params = {"protocolType": "defi"}
        data = self._send_request("GET", endpoint, params=params)
        return data

    def get_active_defi_lending_positions(
        self,
        product_id: Optional[str] = None,
        protocol_type: Optional[str] = None,
        ccy: Optional[str] = None,
    ) -> Dict[str, Dict]:
        """
        Retrieves all active DeFi lending positions without filtering by protocol type.
        """
        active_orders = self.get_active_defi_orders(
            product_id=product_id, protocol_type=protocol_type, ccy=ccy
        )

        defi_lending_positions = {}

        # Process active orders
        for order in active_orders:
            self._process_defi_position(order, defi_lending_positions)

        # Print summary with improved formatting
        if not defi_lending_positions:
            print("\nNo active DeFi lending positions found.")
        else:
            print("\n=== Active DeFi Lending Positions ===")

        return defi_lending_positions

    def _process_defi_position(self, position_data: Dict, positions_dict: Dict) -> None:
        """
        Helper method to process individual DeFi position data with improved protocol handling.
        """
        ccy = position_data.get("ccy")
        protocol = position_data.get(
            "protocol", position_data.get("protocolName", "unknown")
        )
        state = position_data.get("state", "unknown")
        apy = float(position_data.get("apy", position_data.get("earningRate", 0)))

        # Handle different data structures for amount
        invested_amount = 0
        if "investData" in position_data:
            invest_data = position_data.get("investData", [])
            invested_amount = sum(float(item.get("amt", 0)) for item in invest_data)
        else:
            amount_fields = ["balance", "investAmount", "amt", "amount"]
            for field in amount_fields:
                if field in position_data:
                    invested_amount = float(position_data.get(field, 0))
                    break

        # Handle different data structures for earnings
        earnings = 0
        if "earningData" in position_data:
            earnings_data = position_data.get("earningData", [])
            earnings = sum(float(item.get("earnings", 0)) for item in earnings_data)
        else:
            earnings = float(position_data.get("earnings", 0))

        # Skip positions with zero investment
        if invested_amount <= 0:
            return

        position_key = f"{ccy}-{protocol}"

        position_info = {
            "protocol": protocol,
            "state": state,
            "invested_amount": round(invested_amount),
            "earnings": earnings,
            "apy": apy,
            "protocol_details": {},
        }

        # Add protocol-specific details
        protocol_lower = protocol.lower()
        if protocol_lower == "compound":
            position_info["protocol_details"].update(
                {
                    "supply_rate": float(position_data.get("supplyRate", 0)),
                    "collateral_factor": float(
                        position_data.get("collateralFactor", 0)
                    ),
                    "market": position_data.get("market", ""),
                    "product_id": position_data.get("productId", ""),
                }
            )
        elif protocol_lower == "aave":
            position_info["protocol_details"].update(
                {
                    "market": position_data.get("market", ""),
                    "product_id": position_data.get("productId", ""),
                    "network": position_data.get("chain", ""),
                    "version": position_data.get("version", "v3"),
                }
            )

        # Aggregate or add position
        if position_key in positions_dict:
            existing = positions_dict[position_key]
            total_invested = existing["invested_amount"] + invested_amount
            weighted_apy = (
                (
                    (
                        existing["invested_amount"] * existing["apy"]
                        + invested_amount * apy
                    )
                    / total_invested
                )
                if total_invested > 0
                else 0
            )

            existing.update(
                {
                    "invested_amount": total_invested,
                    "earnings": existing["earnings"] + earnings,
                    "apy": weighted_apy,
                }
            )
        else:
            positions_dict[position_key] = position_info

    def get_pending_defi_orders(self, limit: int = 5) -> List[Dict]:
        """
        Retrieves the latest pending staking and DeFi orders with amount >= 1.

        Args:
            limit (int, optional): Number of pending orders to retrieve, default is 5.

        Returns:
            List[Dict]: A list of the latest pending staking and DeFi orders.
        """
        active_pending_orders = self.get_active_defi_orders(state="8")

        # Filter orders with amount >= 1
        filtered_orders = [
            order for order in active_pending_orders if float(order.get("amt", 0)) >= 1
        ]

        if not filtered_orders:
            print("No pending orders found with amount >= 1.")
            return []

        sorted_orders = sorted(
            filtered_orders,
            key=lambda x: int(x.get("purchasedTime", "0")),
            reverse=True,
        )

        latest_pending_orders = sorted_orders[:limit]
        return latest_pending_orders

    def get_savings_positions(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """
        Combines all earning positions from Simple Earn and DeFi products with detailed logging.

        Returns:
            Dict[str, Tuple[float, float]]: Dictionary with assets as keys and
            (principal, yield_rate) as values.
        """
        print("\n=== Aggregated Earnings Report ===\n")
        combined_positions = {}

        # Process Simple Earn positions
        print("Processing Simple Earn positions...")
        print()
        simple_earn_positions = self.get_simple_earn_positions()

        for asset, (principal, yield_rate) in simple_earn_positions.items():
            print(f"Simple Earn Position - {asset}:")
            print(f"  Principal: {principal}")
            print(f"  Rate: {yield_rate*100:.2f}%")

            if principal > 0:
                combined_positions = self.aggregate_positions(
                    combined_positions, (asset, principal, yield_rate)
                )
                print(
                    f"  Updated combined position for {asset}: {combined_positions[asset]}\n"
                )

        # Process DeFi positions
        print("\nProcessing DeFi positions...")
        defi_positions = self.get_active_defi_lending_positions()

        for position_key, position_data in defi_positions.items():
            asset = position_key.split("-")[0]
            principal = float(position_data["invested_amount"])
            yield_rate = float(position_data["apy"])

            print()
            print(f"DeFi Position - {asset}:")
            print(f"  Principal: {principal}")
            print(f"  Rate: {yield_rate*100:.2f}%")

            if principal > 0:
                combined_positions = self.aggregate_positions(
                    combined_positions, (asset, principal, yield_rate)
                )

        print("\n" + "=" * 40)
        print("Final OKX Lending Combined Positions:")
        print("" + "=" * 40)
        final_positions = {
            asset: (float(principal), yield_rate)
            for asset, (principal, yield_rate) in combined_positions.items()
        }
        for asset, (principal, rate) in final_positions.items():
            print(f"{asset}:")
            print(f"  Total Principal: {principal}")
            print(f"  Weighted Rate: {rate*100:.2f}%")

        return {"okx": final_positions}


def main():
    """Main function with cleaner output structure."""
    try:
        okx_filtered = OKXFiltered()

        print("\n=== Account Overview ===")

        # Display crypto balances
        crypto_balances = okx_filtered.get_all_crypto_balances()
        if crypto_balances:
            print("\nCrypto Balances:")
            for asset, balance in crypto_balances.items():
                print(f"{asset}: {balance:.6f}")
        else:
            print("\nNo significant crypto balances found.")

        # Display stablecoin balances
        cash = okx_filtered.get_cash_balance()
        if cash:
            print(f"\n Cash Balances: {cash}")
        else:
            print("\nNo significant stablecoin balances found.")

        okx_filtered.get_savings_positions()

        # Display pending orders if any exist
        print("\n=== Latest Pending Orders (Amount >= 1) ===")
        latest_pending_orders = okx_filtered.get_pending_defi_orders(limit=5)
        if not latest_pending_orders:
            print("No pending orders found.")

    except Exception as e:
        print(f"ERROR: An error occurred: {str(e)}")
        raise


if __name__ == "__main__":
    main()
