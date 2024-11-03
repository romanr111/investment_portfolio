import time
import json
import hmac
import base64
import hashlib
from typing import Dict, List, Tuple

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
        Retrieves the account balances from OKX.

        Returns:
            Dict[str, float]: A dictionary with asset symbols as keys and balances as values.
        """
        endpoint = "/account/balance"
        data = self._send_request("GET", endpoint)
        balances = {}
        for entry in data:
            for detail in entry.get("details", []):
                currency = detail.get("ccy")
                balance = float(detail.get("eq", 0))
                if balance > 0:
                    balances[currency] = balances.get(currency, 0) + balance
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
        Retrieves and filters cryptocurrency balances, excluding stablecoins.

        Returns:
            Dict[str, float]: Filtered cryptocurrency balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        crypto_balances = {
            asset: balance
            for asset, balance in self.account_balances.items()
            if asset not in STABLECOINS and balance > 0
        }
        print(f"Crypto Balances: {crypto_balances}")
        return crypto_balances

    def get_stablecoin_balances(self) -> Dict[str, float]:
        """
        Retrieves balances of stablecoins.

        Returns:
            Dict[str, float]: Stablecoin balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        stablecoin_balances = {
            asset: balance
            for asset, balance in self.account_balances.items()
            if asset in STABLECOINS and balance > 0
        }
        print(f"Stablecoin Balances: {stablecoin_balances}")
        return stablecoin_balances

    def get_lending_positions(self) -> Dict[str, Tuple[float, float]]:
        """
        Processes lending products to extract principal and effective yield.

        Returns:
            Dict[str, Tuple[float, float]]: A dictionary with assets as keys and a tuple of
            (principal, effective_yield) as values.
        """
        lending_positions = {}
        for product in self.lending_products:
            asset = product.get("ccy")
            principal = float(product.get("amt", 0))
            yield_rate = float(product.get("apy", 0))
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

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """
        Retrieves all crypto balances from the account, excluding stablecoins.

        Returns:
            Dict[str, float]: Aggregated crypto balances.
        """
        return self.get_crypto_balances()

    def get_total_crypto_balance(self) -> float:
        """
        Calculates the total crypto balance excluding stablecoins.

        Returns:
            float: Total crypto balance.
        """
        return sum(self.get_crypto_balances().values())


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

        # Get and print lending positions
        lending_positions = okx_filtered.get_lending_positions()
        print(f"Lending Positions: {lending_positions}\n")
    except Exception as e:
        print(f"ERROR: An error occurred: {e}")


if __name__ == "__main__":
    main()
