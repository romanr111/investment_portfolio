# -------------------------------- HARDCODED DONE --------------------------------

import hashlib
import hmac
import time
from typing import Dict, Tuple

import requests

from data.api_keys import BYBIT_API_KEY, BYBIT_API_SECRET
from data.assets_data import BYBIT_SAVINGS
from src.crypto.base_exchange_client import ExchangeBase


class Bybit(ExchangeBase):
    """Bybit API wrapper for retrieving account balances."""

    API_URL = "https://api.bybit.com"
    API_VERSION = "/v5"

    # Reduced stablecoin set to only confirmed valid ones
    STABLECOINS = {"USDT", "USDC", "BUSD", "DAI"}

    def __init__(self) -> None:
        self.api_key = BYBIT_API_KEY
        self.api_secret = BYBIT_API_SECRET

        if not all([self.api_key, self.api_secret]):
            raise ValueError(
                "API key and secret key must be set in environment variables."
            )

        super().__init__()

    def _validate_connection(self) -> bool:
        try:
            self._send_request(
                "GET", "/account/wallet-balance", {"accountType": "UNIFIED"}
            )
            return True
        except Exception as e:
            print(f"Failed to validate Bybit connection: {e}")
            return False

    def _generate_signature(self, params: Dict, timestamp: int) -> str:
        recv_window = "5000"
        sorted_params = sorted(params.items()) if params else []
        concatenated_params = "&".join(
            [f"{key}={value}" for key, value in sorted_params]
        )
        prehash_string = f"{timestamp}{self.api_key}{recv_window}{concatenated_params}"

        return hmac.new(
            self.api_secret.encode("utf-8"),
            prehash_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _send_request(self, method: str, endpoint: str, params: Dict = None) -> Dict:
        timestamp = int(time.time() * 1000)
        params = params or {}
        signature = self._generate_signature(params, timestamp)
        sorted_params = sorted(params.items()) if params else []

        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-RECV-WINDOW": "5000",
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
        }

        url = f"{self.API_URL}{self.API_VERSION}{endpoint}"

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

            if data.get("retCode") != 0:
                raise Exception(
                    f"API Error {data.get('retCode')}: {data.get('retMsg')}"
                )

            return data.get("result", {})
        except Exception as e:
            print(f"API request failed: {e}")
            raise

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """Get combined crypto balances from unified and funding accounts."""
        unified_balances = self.get_spot_account_balances()
        funding_balances = self.get_funding_balances()

        combined_balances = unified_balances.copy()
        for asset, balance in funding_balances.items():
            combined_balances[asset] = combined_balances.get(asset, 0) + balance

        return self.filter_out_crypto_balances(combined_balances)

    def get_spot_account_balances(
        self, account_type: str = "UNIFIED"
    ) -> Dict[str, float]:
        """Get account balances for specified account type."""
        if account_type == "UNIFIED":
            endpoint = "/account/wallet-balance"
            params = {"accountType": "UNIFIED"}
            wallet_data = self._send_request("GET", endpoint, params)

            balances = {}
            try:
                coins_list = wallet_data.get("list", [])[0].get("coin", [])
                for coin in coins_list:
                    if isinstance(coin, dict):
                        currency = coin.get("coin")
                        balance = float(coin.get("availableToWithdraw", "0"))
                        if balance >= self.MIN_CRYPTO_BALANCE:
                            balances[currency] = self._round_amount(balance)
            except (AttributeError, IndexError) as e:
                print(f"Error processing wallet data: {e}")

            return balances

        elif account_type == "FUNDING":
            endpoint = "/asset/transfer/query-account-coin-balance"
            balances = {}

            # Check only valid stablecoins for funding account
            for coin in self.STABLECOINS:
                try:
                    params = {"accountType": "FUND", "coin": coin}
                    coin_data = self._send_request("GET", endpoint, params)
                    if coin_data and "balance" in coin_data:
                        balance = float(
                            coin_data.get("balance", {}).get("walletBalance", "0")
                        )
                        if balance >= self.MIN_CRYPTO_BALANCE:
                            balances[coin] = self._round_amount(balance)
                except Exception as e:
                    print(f"Could not fetch funding balance for {coin}: {e}")

            return balances
        else:
            raise ValueError(f"Invalid account type: {account_type}")

    def get_funding_balances(self) -> Dict[str, float]:
        """Get funding account balances."""
        try:
            return self.get_spot_account_balances(account_type="FUNDING")
        except Exception as e:
            print(f"Error getting funding balances: {e}")
            return {}

    def get_savings_positions(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """Get savings positions. Currently returns empty as endpoint is not available."""
        # TODO:
        return {"bybit": BYBIT_SAVINGS}


class BybitFiltered(Bybit):
    """Enhanced Bybit client with filtering capabilities."""

    def __init__(self) -> None:
        super().__init__()
        self.refresh_balances()

    def refresh_balances(self) -> None:
        """Refresh account balances."""
        self.unified_balances = self.get_spot_account_balances()
        self.funding_balances = self.get_funding_balances()

    def get_cash_balance(self) -> int:
        """Get total stablecoin balance in USD cents."""
        combined_balances = {**self.unified_balances, **self.funding_balances}
        val = self.filter_out_stablecoin_balances(combined_balances)
        return int(sum(val.values()))


def main():
    """Main function demonstrating the Bybit client functionality."""
    try:
        print("\n=== Initializing Bybit Client ===")
        bybit = BybitFiltered()

        print("\n=== Account Balances ===")
        print("\nCrypto Balances:")
        crypto_balances = bybit.get_all_crypto_balances()
        for asset, balance in crypto_balances.items():
            print(f"{asset}: {balance:.8f}")

        print("\nSavings:")
        savings = bybit.get_savings_positions()
        for exchange, positions in savings.items():
            print(f"\n{exchange.capitalize()}:")
            for asset, (principal, apy) in positions.items():
                print(f"{asset}: Principal = {principal}, APY={apy:.1%}")

        print("\nFunding Balances:")
        funding_balances = bybit.get_funding_balances()
        for asset, balance in funding_balances.items():
            print(f"{asset}: {balance:.6f}")

        print(f"\nByBit Free Cash - {bybit.get_cash_balance()}")

    except Exception as e:
        print(f"Error in main: {e}")


if __name__ == "__main__":
    main()
