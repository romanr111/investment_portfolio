import unittest

from src.crypto.okx_client import OKXFiltered


class OKXFilteredBalanceTests(unittest.TestCase):
    def test_simple_earn_preserves_fractional_principal(self) -> None:
        client = OKXFiltered.__new__(OKXFiltered)
        client.simple_earn_data = [{"ccy": "BTC", "amt": "0.25", "rate": "0.05"}]

        positions = client.get_simple_earn_positions()

        self.assertEqual(positions["BTC"][0], 0.25)

    def test_all_crypto_balances_include_volatile_earn_principal(self) -> None:
        client = OKXFiltered.__new__(OKXFiltered)
        client.get_crypto_balances = lambda: {"BTC": 0.5, "ETH": 2.0}
        client.get_savings_positions = lambda: {
            "okx": {"BTC": (0.25, 0.05), "USDT": (1000.0, 0.04)}
        }

        balances = client.get_all_crypto_balances()

        self.assertEqual(balances, {"BTC": 0.75, "ETH": 2.0})


if __name__ == "__main__":
    unittest.main()
