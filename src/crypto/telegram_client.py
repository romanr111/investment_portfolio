# -------------------------------- HARDCODED DONE --------------------------------

import time
from typing import Dict, Tuple, Any
from data.assets_data import TELEGRAM_WALLET_SAVINGS
from src.crypto.base_exchange_client import ExchangeBase


class TelegramClient(ExchangeBase):
    """Telegram Wallet API client inheriting from ExchangeBase."""

    def __init__(self):
        """Initialize TelegramClient."""
        super().__init__()

    def _validate_connection(self) -> bool:
        """Implement connection validation for Telegram Wallet."""
        # For now, return True since we're using hardcoded data
        # In the future, this could validate against Telegram's API
        return True

    def get_cash_balance(self) -> int:
        """Implement ExchangeBase method to get stablecoin balance in cents."""
        # Telegram Wallet doesn't provide cash balance through API
        # Return 0 for now, could be updated if API becomes available
        return 0

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """Implement ExchangeBase method to get all crypto balances."""
        # Telegram Wallet doesn't provide crypto balances through API
        # Return empty dict for now, could be updated if API becomes available
        return {}

    def get_savings_positions(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """
        Implement ExchangeBase method to get savings positions.
        Returns hardcoded Telegram Wallet savings data.
        """
        principal, interest_rate = TELEGRAM_WALLET_SAVINGS
        positions = {"USDT": (principal, interest_rate)}

        return {"telegram": positions}


def main():
    """Main function demonstrating Telegram client functionality."""
    try:
        telegram = TelegramClient()

        print("\n=== Telegram Wallet Overview ===")

        print("\nSavings:")
        savings = telegram.get_savings_positions()
        for exchange, positions in savings.items():
            for asset, (principal, apy) in positions.items():
                print(f"{asset}: Principal = ${principal:.2f}, APY={apy * 100:.1f}%")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
