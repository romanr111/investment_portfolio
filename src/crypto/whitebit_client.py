# -------------------------------- HARDCODED DONE --------------------------------

import base64
import hashlib
import hmac
import json
import time
from typing import Dict, Tuple, Any, Optional
import requests

from data.api_keys import WHITEBIT_API_KEY, WHITEBIT_API_SECRET
from data.assets_data import WHITEBIT_SAVINGS
from src.crypto.base_exchange_client import ExchangeBase


class WhiteBit(ExchangeBase):
    """WhiteBit API client inheriting from ExchangeBase."""

    def __init__(
        self,
        api_key: str = WHITEBIT_API_KEY,
        secret_key: str = WHITEBIT_API_SECRET,
        base_url: str = "https://whitebit.com",
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")

        # Initialize parent class after setting up API credentials
        super().__init__()

    def _validate_connection(self) -> bool:
        """Implement connection validation by attempting to fetch USDT balance."""
        try:
            self.get_trade_balance("USDT")
            return True
        except Exception as e:
            return False

    def _generate_auth_headers(
        self, endpoint: str, data: Dict[str, Any]
    ) -> Tuple[Dict[str, str], str]:
        """Generate authentication headers for WhiteBit API requests."""
        data["request"] = endpoint
        data["nonce"] = time.time_ns() // 1_000_000
        data["nonceWindow"] = True

        data_json = json.dumps(data, separators=(",", ":"))
        payload = base64.b64encode(data_json.encode("ascii"))
        signature = hmac.new(
            self.secret_key.encode("ascii"), payload, hashlib.sha512
        ).hexdigest()

        headers = {
            "Content-type": "application/json",
            "X-TXC-APIKEY": self.api_key,
            "X-TXC-PAYLOAD": payload,
            "X-TXC-SIGNATURE": signature,
        }
        return headers, data_json

    def get_trade_balance(self, ticker: Optional[str] = None) -> Dict[str, Any]:
        """Get trading account balance for specific ticker or all tickers."""
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

    def get_cash_balance(self) -> int:
        """Implement ExchangeBase method to get stablecoin balance in cents."""
        total = 0
        for stablecoin in self.STABLECOINS:
            try:
                balance = self.get_trade_balance(stablecoin)
                available = float(balance.get("available", "0"))
                total += available
            except Exception:
                continue
        return int(total * 100)  # Convert to cents

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """Implement ExchangeBase method to get all crypto balances."""
        try:
            all_balances = self.get_trade_balance()
            balances = {}
            for ticker, data in all_balances.items():
                available = float(data.get("available", "0"))
                if available >= self.MIN_CRYPTO_BALANCE:
                    balances[ticker] = self._round_amount(available)

            # Ensure tokens from WHITEBIT_SAVINGS are present based on rules:
            core_tokens = {"BTC", "ETH", "SOL", "BNB"}
            excluded_stablecoins = {"USDT", "USDC"}
            for position in WHITEBIT_SAVINGS:
                ticker = position[0]
                if ticker in core_tokens or ticker not in excluded_stablecoins:
                    if ticker not in balances:
                        try:
                            principal = float(position[1])
                        except Exception:
                            principal = 0.0
                        balances[ticker] = self._round_amount(principal)
            return balances
        except Exception as e:
            return {}

    def get_savings_positions(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """
        Implement ExchangeBase method to get savings positions.
        Uses aggregate_positions to combine multiple positions per asset.
        Returns positions wrapped in a dictionary with exchange name as key.
        """
        positions = {}
        for position in WHITEBIT_SAVINGS:
            positions = self.aggregate_positions(positions, position)

        return {"whitebit": positions}


class WhiteBitFallback(WhiteBit):
    """WhiteBit fallback client that provides hardcoded data when API connection fails."""

    def __init__(self):
        """Initialize fallback client without API validation."""
        self.api_key = WHITEBIT_API_KEY
        self.secret_key = WHITEBIT_API_SECRET
        self.base_url = "https://whitebit.com"
        # Skip parent __init__ to avoid API validation

    def _validate_connection(self) -> bool:
        """Always return True for fallback client."""
        return True

    def get_cash_balance(self) -> int:
        """Return 0 for fallback since we can't access live cash data."""
        return 0

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """Return hardcoded crypto balances from WHITEBIT_SAVINGS."""
        balances = {}
        core_tokens = {"BTC", "ETH", "SOL", "BNB"}
        excluded_stablecoins = {"USDT", "USDC"}

        for position in WHITEBIT_SAVINGS:
            ticker = position[0]
            if ticker in core_tokens or ticker not in excluded_stablecoins:
                try:
                    principal = float(position[1])
                    if principal >= self.MIN_CRYPTO_BALANCE:
                        balances[ticker] = self._round_amount(principal)
                except Exception:
                    continue
        return balances


def main():
    """Main function demonstrating WhiteBit client functionality."""
    try:
        whitebit = WhiteBit()

        print("\n=== Account Overview ===")

        print("\nCrypto Balances:")
        crypto_balances = whitebit.get_all_crypto_balances()
        crypto_balances = whitebit.filter_out_crypto_balances(crypto_balances)
        for asset, balance in crypto_balances.items():
            print(f"{asset}: {balance:.8f}")

        print("\nStablecoin Balances:")
        all_balances = whitebit.get_all_crypto_balances()
        stablecoin_balances = whitebit.filter_out_stablecoin_balances(all_balances)
        for asset, balance in stablecoin_balances.items():
            print(f"{asset}: {balance:.2f}")

        total_cash_usd = whitebit.get_cash_balance() / 100  # Convert cents to USD
        print(f"\nTotal Cash: ${total_cash_usd:.2f}")

        print("\nSavings:")
        savings = whitebit.get_savings_positions()
        for exchange, positions in savings.items():
            for asset, (principal, apy) in positions.items():
                print(f"{asset}: Principal = ${principal:.2f}, APY={apy * 100:.1f}%")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
