# -------------------------------- TODO --------------------------------
from data.api_keys import WHITEBIT_API_KEY, WHITEBIT_API_SECRET
import base64
import hashlib
import hmac
import json
import time
from typing import Optional, Dict, Any

import requests


class WhiteBitAPI:
    def __init__(
        self, api_key: str, secret_key: str, base_url: str = "https://whitebit.com"
    ):
        """
        Initialize the WhiteBit API client.

        Args:
            api_key: Your WhiteBit API key
            secret_key: Your WhiteBit secret key
            base_url: API base URL (default: 'https://whitebit.com')
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")  # Remove trailing slash if present

    def _generate_auth_headers(
        self, endpoint: str, data: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Generate authentication headers for WhiteBit API requests.

        Args:
            endpoint: API endpoint path
            data: Request data dictionary

        Returns:
            Dictionary containing the required headers
        """
        # Add required fields to data
        data["request"] = endpoint
        data["nonce"] = time.time_ns() // 1_000_000
        data["nonceWindow"] = True

        # Create payload
        data_json = json.dumps(data, separators=(",", ":"))
        payload = base64.b64encode(data_json.encode("ascii"))

        # Generate signature
        signature = hmac.new(
            self.secret_key.encode("ascii"), payload, hashlib.sha512
        ).hexdigest()

        return {
            "Content-type": "application/json",
            "X-TXC-APIKEY": self.api_key,
            "X-TXC-PAYLOAD": payload,
            "X-TXC-SIGNATURE": signature,
        }, data_json

    def get_trade_balance(self, ticker: Optional[str] = None) -> Dict[str, Any]:
        """
        Get trading account balance.

        Args:
            ticker: Optional cryptocurrency ticker (e.g., 'BTC')

        Returns:
            Dictionary containing balance information
        """
        endpoint = "/api/v4/trade-account/balance"
        data = {}
        if ticker:
            data["ticker"] = ticker

        headers, data_json = self._generate_auth_headers(endpoint, data)
        response = requests.post(
            f"{self.base_url}{endpoint}", headers=headers, data=data_json
        )
        response.raise_for_status()
        return response.json()

    def get_investments_history(
        self,
        investment_id: Optional[str] = None,
        ticker: Optional[str] = None,
        status: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get investments history.

        Args:
            investment_id: Optional investment identifier
            ticker: Optional invest plan source currency's ticker
            status: Optional investment status (1 - active, 2 - closed)
            limit: Number of records to return (Default: 100, Min: 1, Max: 100)
            offset: Starting position (Default: 0, Min: 0, Max: 10000)

        Returns:
            Dictionary containing investment history records
        """
        endpoint = "/api/v4/main-account/smart/investments"

        # Create request body exactly as shown in the documentation
        data = {
            "request": endpoint,
            "nonce": str(
                time.time_ns() // 1_000_000
            ),  # Convert nonce to string as shown in docs
        }

        # Add optional parameters only if they are provided
        if investment_id:
            data["id"] = investment_id
        if ticker:
            data["ticker"] = ticker
        if status is not None:
            data["status"] = status
        if limit is not None:
            data["limit"] = min(max(limit, 1), 100)
        if offset is not None:
            data["offset"] = min(max(offset, 0), 10000)

        # Convert to JSON string
        data_json = json.dumps(data, separators=(",", ":"))

        # Create payload
        payload = base64.b64encode(data_json.encode("ascii"))

        # Generate signature
        signature = hmac.new(
            self.secret_key.encode("ascii"), payload, hashlib.sha512
        ).hexdigest()

        # Prepare headers
        headers = {
            "Content-type": "application/json",
            "X-TXC-APIKEY": self.api_key,
            "X-TXC-PAYLOAD": payload,
            "X-TXC-SIGNATURE": signature,
        }

        # Make request
        response = requests.post(
            f"{self.base_url}{endpoint}", headers=headers, data=data_json
        )

        # Add debug information
        if response.status_code != 200:
            print(f"Request URL: {self.base_url}{endpoint}")
            print(f"Request Headers: {headers}")
            print(f"Request Data: {data}")
            print(f"Response Status: {response.status_code}")
            print(f"Response Text: {response.text}")

        response.raise_for_status()
        return response.json()


# Example usage:
if __name__ == "__main__":
    # Initialize the API client
    api = WhiteBitAPI(api_key=WHITEBIT_API_KEY, secret_key=WHITEBIT_API_SECRET)

    # Get balance for all currencies
    # try:
    # balances = api.get_trade_balance()
    # print("Trade Balances:")
    # print(json.dumps(balances, indent=2))
    # except requests.exceptions.RequestException as e:
    # print(f"Error fetching balances: {e}")

    # Get investment history
    try:
        investments = api.get_investments_history(
            ticker="USDT", status=1, limit=10  # Active investments
        )
        print("\nInvestment History:")
        print(json.dumps(investments, indent=2))
    except requests.exceptions.RequestException as e:
        print(f"Error fetching investments: {e}")
