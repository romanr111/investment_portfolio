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
        print(f"Account Balances: {balances}")
        return balances

    def get_lending_products(self) -> List[Dict]:
        """
        Retrieves flexible lending positions information.

        Returns:
            List[Dict]: A list of flexible lending positions with their details.
        """
        endpoint = "/finance/savings/balance"  # Updated endpoint
        data = self._send_request("GET", endpoint)
        print(f"Lending Products: {data}")
        return data

    def get_active_defi_orders(
        self,
        product_id: Optional[str] = None,
        protocol_type: Optional[str] = None,
        ccy: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieves active staking and DeFi orders.

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
        print(f"Active DeFi Orders: {data}")
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
        """
        Initializes the OKXFiltered object by pre-fetching and caching necessary data.
        """
        super().__init__()
        self.account_balances = self.get_account_balances()
        self.lending_products = self.get_lending_products()

    def get_crypto_balances(self) -> Dict[str, float]:
        """
        Retrieves and filters cryptocurrency balances, excluding stablecoins and balances less than 0.5.

        Returns:
            Dict[str, float]: Filtered cryptocurrency balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        crypto_balances = {
            asset: balance
            for asset, balance in self.account_balances.items()
            if asset not in STABLECOINS and balance >= 0.5  # Filter out low balances
        }
        print(f"Crypto Balances: {crypto_balances}")
        return crypto_balances

    def get_stablecoin_balances(self) -> Dict[str, float]:
        """
        Retrieves balances of stablecoins, filtering out balances less than 0.5.

        Returns:
            Dict[str, float]: Filtered stablecoin balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        stablecoin_balances = {
            asset: balance
            for asset, balance in self.account_balances.items()
            if asset in STABLECOINS and balance >= 0.5  # Filter out low balances
        }
        print(f"Stablecoin Balances: {stablecoin_balances}")
        return stablecoin_balances

    def get_lending_positions(self) -> Dict[str, Tuple[float, float]]:
        """
        Processes flexible lending products to extract principal and effective yield.

        Returns:
            Dict[str, Tuple[float, float]]: A dictionary with assets as keys and a tuple of
            (principal, effective_yield) as values.
        """
        lending_positions = {}
        for product in self.lending_products:
            asset = product.get("ccy")
            principal = float(product.get("amt", 0))
            yield_rate = float(product.get("rate", 0))  # Ensure to use the correct key
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
        print(f"Lending Positions: {lending_positions}")
        return lending_positions

    def get_active_defi_lending_positions(
        self,
        product_id: Optional[str] = None,
        protocol_type: Optional[str] = "defi",
        ccy: Optional[str] = None,
        state: Optional[str] = "1",  # Example: '1' for Earning
    ) -> Dict[str, Dict]:
        """
        Retrieves and processes active DeFi lending positions.

        Args:
            product_id (str, optional): Product ID to filter.
            protocol_type (str, optional): Protocol type, default is 'defi'.
            ccy (str, optional): Investment currency, e.g., 'BTC'.
            state (str, optional): Order state to filter, default is '1' (Earning).

        Returns:
            Dict[str, Dict]: Processed DeFi lending positions.
        """
        active_orders = self.get_active_defi_orders(
            product_id=product_id, protocol_type=protocol_type, ccy=ccy, state=state
        )
        defi_lending_positions = {}
        for order in active_orders:
            ccy = order.get("ccy")
            apy = float(order.get("apy", 0))
            invest_data = order.get("investData", [])
            earnings_data = order.get("earningData", [])

            invested_amount = sum(float(item.get("amt", 0)) for item in invest_data)
            earnings = sum(float(item.get("earnings", 0)) for item in earnings_data)

            if ccy:
                if ccy in defi_lending_positions:
                    existing = defi_lending_positions[ccy]
                    existing["invested_amount"] += invested_amount
                    existing["earnings"] += earnings
                    # Recalculate weighted APY
                    total_invested = existing["invested_amount"] + invested_amount
                    existing["apy"] = (
                        (existing["apy"] * existing["invested_amount"])
                        + (apy * invested_amount)
                    ) / total_invested
                else:
                    defi_lending_positions[ccy] = {
                        "invested_amount": invested_amount,
                        "earnings": earnings,
                        "apy": apy,
                    }
        print(f"Active DeFi Lending Positions: {defi_lending_positions}")
        return defi_lending_positions

    def get_latest_order_history(
        self,
        product_id: Optional[str] = None,
        protocol_type: Optional[str] = None,
        ccy: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict]:
        """
        Retrieves the latest 5 staking and DeFi order history records.

        Args:
            product_id (str, optional): Product ID to filter.
            protocol_type (str, optional): Protocol type, e.g., 'defi' or 'staking'.
            ccy (str, optional): Investment currency, e.g., 'BTC'.
            limit (int, optional): Number of records to retrieve, default is 5.

        Returns:
            List[Dict]: A list of the latest 5 staking and DeFi order history records.
        """
        order_history = self.get_staking_defi_order_history(
            product_id=product_id, protocol_type=protocol_type, ccy=ccy, limit=limit
        )
        print(f"Latest {limit} Order History Records: {order_history}")
        return order_history

    def get_pending_defi_orders(self, limit: int = 5) -> List[Dict]:
        """
        Retrieves the latest 5 pending staking and DeFi orders.

        Args:
            limit (int, optional): Number of pending orders to retrieve, default is 5.

        Returns:
            List[Dict]: A list of the latest 5 pending staking and DeFi orders.
        """
        # Retrieve all active orders with state=8 (Pending)
        active_pending_orders = self.get_active_defi_orders(state="8")

        if not active_pending_orders:
            print("No pending orders found.")
            return []

        # Sort orders by purchasedTime in descending order to get the latest ones
        sorted_orders = sorted(
            active_pending_orders,
            key=lambda x: int(x.get("purchasedTime", "0")),
            reverse=True,
        )

        # Limit to the latest 'limit' orders
        latest_pending_orders = sorted_orders[:limit]
        print(f"Latest {limit} Pending DeFi Orders: {latest_pending_orders}")
        return latest_pending_orders


def main():
    """Main function to execute the OKXEndpoint."""
    try:
        okx_filtered = OKXFiltered()

        # Get and print crypto balances
        crypto_balances = okx_filtered.get_crypto_balances()
        print(f"Crypto Balances: {crypto_balances}\n")

        # Get and print stablecoin balances
        stablecoin_balances = okx_filtered.get_stablecoin_balances()
        print(f"Stablecoin Balances: {stablecoin_balances}\n")

        # Get and print flexible lending positions
        lending_positions = okx_filtered.get_lending_positions()
        print(f"Lending Positions: {lending_positions}\n")

        # Get and print active DeFi lending positions
        defi_lending_positions = okx_filtered.get_active_defi_lending_positions()
        print(f"Active DeFi Lending Positions: {defi_lending_positions}\n")

        # Get and print the latest 5 pending orders
        latest_pending_orders = okx_filtered.get_pending_defi_orders(limit=5)
        print(f"Latest 5 Pending DeFi Orders: {latest_pending_orders}\n")

    except Exception as e:
        print(f"ERROR: An error occurred: {e}")


if __name__ == "__main__":
    main()
