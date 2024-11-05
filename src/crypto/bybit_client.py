import time
import hmac
import hashlib
import logging
from typing import Dict, List
import requests

from data.api_keys import BYBIT_API_KEY, BYBIT_API_SECRET

# Configure Logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for detailed logs
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bybit_api.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class Bybit:
    """
    Bybit API wrapper for retrieving account balances and earning product information.
    """

    # Constants
    API_URL = "https://api.bybit.com"
    API_VERSION = "/v5"

    def __init__(self) -> None:
        """
        Initializes the Bybit API client.
        """
        self.api_key = BYBIT_API_KEY
        self.api_secret = BYBIT_API_SECRET

        if not all([self.api_key, self.api_secret]):
            raise ValueError(
                "API key and secret key must be set in environment variables."
            )

    def _generate_signature(self, params: Dict, timestamp: int) -> str:
        """
        Generates a signature for Bybit API authentication following v5 specifications.

        Args:
            params (Dict): Query parameters.
            timestamp (int): The timestamp for the request.

        Returns:
            str: The generated signature.
        """
        recv_window = "5000"  # Consistent with headers

        # Step 1: Sort the parameters by key in ascending order
        sorted_params = sorted(params.items()) if params else []

        # Step 2: Concatenate the sorted key-value pairs with '&'
        concatenated_params = "&".join(
            [f"{key}={value}" for key, value in sorted_params]
        )

        # Step 3: Create the prehash string
        prehash_string = f"{timestamp}{self.api_key}{recv_window}{concatenated_params}"

        # Step 4: Generate HMAC SHA256 signature
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            prehash_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        logger.debug(f"Prehash String: {prehash_string}")
        logger.debug(f"Generated Signature: {signature}")

        return signature

    def _send_request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        """
        Sends a request to the Bybit API.

        Args:
            method (str): HTTP method (GET, POST, etc.).
            endpoint (str): API endpoint.
            params (Dict): Query parameters.

        Returns:
            Dict: The API response.

        Raises:
            Exception: If the API request fails.
        """
        timestamp = int(time.time() * 1000)
        params = params or {}

        # Generate signature
        signature = self._generate_signature(params, timestamp)

        # Sort parameters to ensure order consistency
        sorted_params = sorted(params.items()) if params else []

        # Add authentication headers
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-RECV-WINDOW": "5000",
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
        }

        url = f"{self.API_URL}{self.API_VERSION}{endpoint}"

        logger.info(
            f"Sending {method.upper()} request to {url} with params {sorted_params} and headers {headers}"
        )

        try:
            if method.upper() == "GET":
                response = requests.get(
                    url,
                    headers=headers,
                    params=sorted_params if sorted_params else None,
                )
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=params)
            else:
                raise ValueError("Unsupported HTTP method")

            response.raise_for_status()
            data = response.json()

            logger.debug(f"Raw API Response for {endpoint}: {data}")

            if data.get("retCode") != 0:
                ret_code = data.get("retCode")
                ret_msg = data.get("retMsg")
                raise Exception(f"API Error {ret_code}: {ret_msg}")

            return data.get("result", {})
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP ERROR: {http_err}")
            raise
        except Exception as e:
            logger.error(f"ERROR: API request failed: {e}")
            raise

    def get_account_balances(self, account_type: str = "UNIFIED") -> Dict[str, float]:
        """
        Retrieves the account balances from Bybit's specified Trading Account.

        Args:
            account_type (str): The type of account to retrieve balances for.
                                Options: "UNIFIED", "FUNDING", "EARN"

        Returns:
            Dict[str, float]: A dictionary with asset symbols as keys and balances as values.
        """
        account_type_map = {
            "UNIFIED": ("UNIFIED", "/account/wallet-balance"),
            # Uncomment and adjust these lines when handling FUNDING and EARN accounts
            # "FUNDING": ("FUND", "/asset/transfer/query-account-coins-balance"),
            # "EARN": ("INVESTMENT", "/asset/transfer/query-account-coins-balance"),
        }

        mapped_account_type, endpoint = account_type_map.get(
            account_type.upper(), (None, None)
        )
        if not mapped_account_type or not endpoint:
            raise ValueError(f"Invalid account type: {account_type}")

        params = {"accountType": mapped_account_type}

        logger.info(f"Fetching {account_type} account balances.")
        wallet_data = self._send_request("GET", endpoint, params)

        # Log the type and content of wallet_data for debugging
        logger.debug(f"wallet_data type: {type(wallet_data)}, content: {wallet_data}")

        balances = {}

        try:
            if account_type.upper() == "UNIFIED":
                coins_list = wallet_data.get("list", [])[0].get("coin", [])
            else:
                coins_list = wallet_data.get("balance", [])

            for coin in coins_list:
                if isinstance(coin, dict):
                    currency = coin.get("coin")
                    available_balance = float(coin.get("availableToWithdraw", "0"))
                    if available_balance >= 0.001:
                        balances[currency] = available_balance
                else:
                    logger.warning(f"Unexpected coin data format: {coin}")
        except (AttributeError, IndexError) as e:
            logger.error(f"Error processing wallet data for {account_type}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        logger.debug(f"{account_type} Balances: {balances}")

        return balances

    def get_funding_balances(self) -> Dict[str, float]:
        """
        Retrieves the account balances from Bybit's Funding Account.

        Returns:
            Dict[str, float]: A dictionary with asset symbols as keys and balances as values.
        """
        return self.get_account_balances(account_type="FUNDING")

    def get_earn_balances(self) -> Dict[str, float]:
        """
        Retrieves the account balances from Bybit's Earn Account.

        Returns:
            Dict[str, float]: A dictionary with asset symbols as keys and balances as values.
        """
        return self.get_account_balances(account_type="EARN")

    def get_earning_products(self) -> List[Dict]:
        """
        Retrieves all available earning products.

        Returns:
            List[Dict]: List of available earning products.
        """
        endpoint = "/asset/spot-margin-trade/data"
        params = {}  # Add any required parameters if necessary

        logger.info("Fetching earning products.")
        data = self._send_request("GET", endpoint, params)
        earning_products = data.get("spotMarginMode", [])

        logger.debug(f"Earning Products: {earning_products}")

        return earning_products

    def get_earn_positions(self) -> List[Dict]:
        endpoint = "/asset/v3/private/investment-product-position/list"
        params = {}
        
        logger.info("Fetching Earn positions.")
        try:
            data = self._send_request("GET", endpoint, params)
            positions = data.get("result", {}).get("list", [])
            logger.debug(f"Earn Positions: {positions}")
            return positions
        except Exception as e:
            logger.error(f"Error getting Earn positions: {e}")
            return []

    def get_active_earning_positions(self) -> List[Dict]:
        """
        Retrieves active positions from the unified margin account.

        Returns:
            List[Dict]: List of active positions.
        """
        endpoint = "/position/list"
        params = {
            "category": "linear",
            "settleCoin": "USDT",
            "limit": 50,
        }

        logger.info("Fetching active earning positions.")
        try:
            data = self._send_request("GET", endpoint, params)
            positions = data.get("list", [])
            # Filter out positions with zero size
            active_positions = [
                pos for pos in positions if float(pos.get("size", 0)) > 0
            ]
            logger.debug(f"Active Positions: {active_positions}")
            return active_positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []


class BybitFiltered(Bybit):
    """
    Extends Bybit class with additional filtering and data processing capabilities.
    """

    def __init__(self) -> None:
        super().__init__()
        logger.info("Initializing BybitFiltered class.")
        self.unified_balances = self.get_account_balances()
        self.earn_positions = self.get_earn_positions()
        # Uncomment the following lines when handling FUNDING and EARN accounts
        # self.funding_balances = self.get_funding_balances()
        # self.earn_balances = self.get_earn_balances()
        self.earning_positions = self.get_active_earning_positions()

    def get_crypto_balances(self) -> Dict[str, float]:
        """
        Retrieves and filters cryptocurrency balances from Unified, Funding, and Earn accounts, excluding stablecoins.

        Returns:
            Dict[str, float]: Filtered cryptocurrency balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        crypto_balances = {}

        logger.info(
            "Aggregating cryptocurrency balances from Unified, Funding, and Earn accounts."
        )
        for account, balances in [
            ("Unified", self.unified_balances),
            # ("Funding", self.funding_balances),
            # ("Earn", self.earn_balances),
        ]:
            for asset, balance in balances.items():
                if asset not in STABLECOINS and balance >= 0.001:
                    crypto_balances[asset] = crypto_balances.get(asset, 0) + balance

        logger.debug(f"Aggregated Crypto Balances: {crypto_balances}")
        return crypto_balances

    def get_stablecoin_balances(self) -> Dict[str, float]:
        """
        Retrieves balances of stablecoins from Unified, Funding, and Earn accounts.

        Returns:
            Dict[str, float]: Filtered stablecoin balances.
        """
        STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "PAX"}
        stablecoin_balances = {}

        logger.info(
            "Aggregating stablecoin balances from Unified, Funding, and Earn accounts."
        )
        for account, balances in [
            ("Unified", self.unified_balances),
            # ("Funding", self.funding_balances),
            # ("Earn", self.earn_balances),
        ]:
            for asset, balance in balances.items():
                if asset in STABLECOINS and balance >= 1:
                    stablecoin_balances[asset] = (
                        stablecoin_balances.get(asset, 0) + balance
                    )

        logger.debug(f"Aggregated Stablecoin Balances: {stablecoin_balances}")
        return stablecoin_balances

    def get_earning_positions_summary(self) -> Dict[str, Dict]:
        """
        Processes active positions to provide a summary per asset.

        Returns:
            Dict[str, Dict]: A dictionary with assets as keys and position details as values.
        """
        positions_summary = {}

        logger.info("Processing earning positions and savings products for summary.")
        try:
            # Process regular positions
            for position in self.earning_positions:
                symbol = position.get("symbol", "")
                # Extract the base asset (remove USDT suffix)
                asset = symbol.replace("USDT", "")
                size = float(position.get("size", 0))
                position_value = abs(float(position.get("positionValue", 0)))
                unrealized_pnl = float(position.get("unrealisedPnl", 0))
                entry_price = float(position.get("entryPrice", 0))
                mark_price = float(position.get("markPrice", 0))
                leverage = float(position.get("leverage", 0))

                if size <= 0:
                    continue

                if asset not in positions_summary:
                    positions_summary[asset] = {
                        "total_size": 0,
                        "total_value": 0,
                        "total_pnl": 0,
                        "positions": [],
                        "savings": [],
                        "avg_entry_price": 0,
                        "current_price": mark_price,
                    }

                summary = positions_summary[asset]
                summary["total_size"] += size
                summary["total_value"] += position_value
                summary["total_pnl"] += unrealized_pnl

                # Calculate weighted average entry price
                if summary["total_size"] > 0:
                    summary["avg_entry_price"] = (
                        summary["avg_entry_price"] * (summary["total_size"] - size)
                        + entry_price * size
                    ) / summary["total_size"]

                position_info = {
                    "symbol": symbol,
                    "size": size,
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "position_value": position_value,
                    "unrealized_pnl": unrealized_pnl,
                    "leverage": leverage,
                    "pnl_percentage": (
                        (unrealized_pnl / position_value * 100)
                        if position_value > 0
                        else 0
                    ),
                }

                summary["positions"].append(position_info)

            # (No processing of savings positions since it's commented out)

            logger.debug(f"Positions Summary: {positions_summary}")
            return positions_summary

        except Exception as e:
            logger.error(f"Error processing positions: {e}")
            return {}


def main():
    """Main function to demonstrate the Bybit API wrapper functionality."""
    try:
        bybit_filtered = BybitFiltered()

        print("\n=== Account Overview ===")

        print("\nCrypto Balances:")
        crypto_balances = bybit_filtered.get_crypto_balances()
        if crypto_balances:
            for asset, balance in crypto_balances.items():
                print(f"{asset}: {balance:.6f}")
        else:
            print("No crypto balances found.")

        print("\nStablecoin Balances:")
        stablecoin_balances = bybit_filtered.get_stablecoin_balances()
        if stablecoin_balances:
            for asset, balance in stablecoin_balances.items():
                print(f"{asset}: {balance:.2f}")
        else:
            print("No stablecoin balances found.")

        
        print(f"bybit_filtered.earn_positions - {bybit_filtered.earn_positions}")

        print("\n=== Positions Summary ===")
        positions_summary = bybit_filtered.get_earning_positions_summary()
        if positions_summary:
            for asset, summary in positions_summary.items():
                print(f"\n{asset}:")
                print(f"  Total Size: {summary['total_size']:.6f}")
                print(f"  Total Value: {summary['total_value']:.2f}")
                print(f"  Total PnL: {summary['total_pnl']:.2f}")
                print(f"  Average Entry Price: {summary['avg_entry_price']:.2f}")
                print(f"  Current Price: {summary['current_price']:.2f}")
                print(f"  Savings:")
                for saving in summary["savings"]:
                    print(
                        f"    Amount: {saving['amount']:.6f}, APY: {saving['apy']*100:.2f}%"
                    )

                print("\n  Individual Positions:")
                for position in summary["positions"]:
                    print(f"    Symbol: {position['symbol']}")
                    print(f"    Size: {position['size']:.6f}")
                    print(f"    Entry Price: {position['entry_price']:.2f}")
                    print(f"    Mark Price: {position['mark_price']:.2f}")
                    print(f"    Position Value: {position['position_value']:.2f}")
                    print(f"    Unrealized PnL: {position['unrealized_pnl']:.2f}")
                    print(f"    Leverage: {position['leverage']:.2f}x")
                    print(f"    PnL Percentage: {position['pnl_percentage']:.2f}%")
                    print("    ---")
        else:
            print("No positions found.")

    except Exception as e:
        logger.error(f"ERROR: An error occurred: {e}")


if __name__ == "__main__":
    main()
