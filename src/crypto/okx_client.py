import time
import json
import hmac
import base64
import hashlib
from typing import Dict, List, Tuple, Optional

import requests

# Replace these with your actual API keys
from data.api_keys import OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE


class OKX:
    """
    OKX API wrapper for retrieving account balances and lending product information.
    """

    # Constants
    API_URL = "https://www.okx.com"
    API_VERSION = "/api/v5"

    def __init__(self) -> None:
        """
        Initializes the OKX API client.
        """
        self.api_key = OKX_API_KEY
        self.secret_key = OKX_SECRET_KEY
        self.passphrase = OKX_PASSPHRASE

        if not all([self.api_key, self.secret_key, self.passphrase]):
            raise ValueError("API key, secret key, and passphrase must be provided.")

    def _generate_signature(
        self, timestamp: str, method: str, request_path: str, body: str = ""
    ) -> str:
        """
        Generates a signature for OKX API authentication.

        Args:
            timestamp (str): The timestamp for the request.
            method (str): HTTP method (GET, POST, etc.).
            request_path (str): The API endpoint path.
            body (str): The request body.

        Returns:
            str: The generated signature.
        """
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            bytes(self.secret_key, "utf-8"),
            msg=bytes(message, "utf-8"),
            digestmod=hashlib.sha256,
        )
        d = mac.digest()
        signature = base64.b64encode(d).decode("utf-8")
        return signature

    def _get_timestamp(self) -> str:
        """
        Retrieves the current timestamp in ISO format (UTC).

        Returns:
            str: The current timestamp.
        """
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    def _send_request(
        self, method: str, endpoint: str, params: Dict = None, body: Dict = None
    ) -> Dict:
        """
        Sends a request to the OKX API.

        Args:
            method (str): HTTP method (GET, POST, etc.).
            endpoint (str): API endpoint (e.g., '/account/balance').
            params (Dict): Query parameters.
            body (Dict): Request body.

        Returns:
            Dict: The API response.

        Raises:
            Exception: If the API request fails.
        """
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

        url = f"{self.API_URL}{request_path}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, data=body_str)
            else:
                raise ValueError("Unsupported HTTP method")

            response.raise_for_status()
            data = response.json()
            if data.get("code") != "0":
                raise Exception(f"API Error: {data.get('msg')}")
            return data.get("data", [])
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP ERROR: {http_err}")
            raise
        except Exception as e:
            print(f"ERROR: API request failed: {e}")
            raise

    def get_account_balances(self) -> Dict[str, float]:
        """
        Retrieves the account balances from OKX's Funding account, filtering out balances less than 0.001.

        Returns:
            Dict[str, float]: A dictionary with asset symbols as keys and balances as values.
        """
        endpoint = "/asset/balances"
        data = self._send_request("GET", endpoint)
        balances = {}
        for detail in data:
            currency = detail.get("ccy")
            balance = float(detail.get("bal", 0))
            if balance >= 0.001:  # Only include balances >= 0.001
                balances[currency] = balance
        return balances

    def get_simple_earn_data(self) -> List[Dict]:
        """Retrieves simple earn lending positions information."""
        endpoint = "/finance/savings/balance"  # Updated endpoint
        data = self._send_request("GET", endpoint)
        return data

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
        params = {"limit": str(limit)}  # Limit the number of records
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
        print(f"Staking/DeFi Order History: {data}")
        return data


class OKXFiltered(OKX):
    """
    Extends OKX class with additional filtering and data processing capabilities.
    """

    def __init__(self) -> None:
        super().__init__()
        self.account_balances = self.get_account_balances()
        self.simple_earn_data = self.get_simple_earn_data()

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

    def get_stablecoin_balances(self) -> Dict[str, float]:
        """
        Retrieves balances of stablecoins, filtering out balances less than 1.

        Returns:
            Dict[str, float]: Filtered stablecoin balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        stablecoin_balances = {
            asset: balance
            for asset, balance in self.account_balances.items()
            if asset in STABLECOINS and balance >= 1
        }
        return stablecoin_balances

    def get_simple_earn_positions(self) -> Dict[str, Tuple[float, float]]:
        """
        Processes simple earn lending products to extract principal and effective yield.

        Returns:
            Dict[str, Tuple[float, float]]: A dictionary with assets as keys and a tuple of
            (principal, effective_yield) as values.
        """
        lending_positions = {}
        for product in self.simple_earn_data:
            asset = product.get("ccy")
            principal = float(product.get("amt", 0))
            yield_rate = float(product.get("rate", 0))
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
        protocol_type: Optional[str] = None,  # Changed default to None
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
            for key, data in defi_lending_positions.items():
                print("\n" + "=" * 40)
                print(f"Asset-Protocol: {key}")
                print("-" * 40)
                print(f"Protocol: {data['protocol']}")
                print(f"State: {data['state']}")
                print(f"Invested Amount: {data['invested_amount']:.6f}")
                print(f"APY: {data['apy']*100:.2f}%")
                print(f"Earnings: {data['earnings']:.6f}")

                if data["protocol_details"]:
                    print("\nProtocol Details:")
                    for k, v in data["protocol_details"].items():
                        print(f"  {k}: {v}")

        return defi_lending_positions

    def _process_defi_position(self, position_data: Dict, positions_dict: Dict) -> None:
        """
        Helper method to process individual DeFi position data with improved protocol handling.
        """
        # print(f"Processing position data: {position_data}")  # Debug statemen
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
            # Try different possible field names for amount
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
            "invested_amount": invested_amount,
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
        Retrieves the latest pending staking and DeFi orders.

        Args:
            limit (int, optional): Number of pending orders to retrieve, default is 5.

        Returns:
            List[Dict]: A list of the latest pending staking and DeFi orders.
        """
        active_pending_orders = self.get_active_defi_orders(state="8")

        if not active_pending_orders:
            print("No pending orders found.")
            return []

        sorted_orders = sorted(
            active_pending_orders,
            key=lambda x: int(x.get("purchasedTime", "0")),
            reverse=True,
        )

        latest_pending_orders = sorted_orders[:limit]
        return latest_pending_orders


def main():
    """Main function with improved output formatting."""
    try:
        okx_filtered = OKXFiltered()

        print("\n=== Account Overview ===")
        print("\nCrypto Balances:")
        for asset, balance in okx_filtered.get_crypto_balances().items():
            print(f"{asset}: {balance:.6f}")

        print("\nStablecoin Balances:")
        for asset, balance in okx_filtered.get_stablecoin_balances().items():
            print(f"{asset}: {balance:.2f}")

        print("\n=== Simple Earn Positions ===")
        lending_positions = okx_filtered.get_simple_earn_positions()
        for asset, (principal, yield_rate) in lending_positions.items():
            print(f"\n{asset}:")
            print(f"  Principal: {principal:.6f}")
            print(f"  Yield Rate: {yield_rate*100:.2f}%")

        # Get and print active DeFi lending positions
        okx_filtered.get_active_defi_lending_positions()

        # Get and print the latest 5 pending orders
        print("\n=== Latest Pending Orders ===")
        latest_pending_orders = okx_filtered.get_pending_defi_orders(limit=5)
        for order in latest_pending_orders:
            print(f"\nOrder ID: {order.get('ordId', 'N/A')}")
            print(f"Asset: {order.get('ccy', 'N/A')}")
            print(f"Protocol: {order.get('protocol', 'N/A')}")
            print(f"Amount: {float(order.get('amt', 0)):.6f}")
            print(f"Status: {order.get('state', 'N/A')}")

    except Exception as e:
        print(f"ERROR: An error occurred: {e}")


if __name__ == "__main__":
    main()
