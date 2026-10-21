import unittest
from typing import Dict, Tuple
from unittest.mock import patch

from src.crypto.base_exchange_client import ExchangeBase
from src.crypto.crypto_tokens import CryptoData


class FakeBrokerBase(ExchangeBase):
    """ExchangeBase stand-in that never touches a live API."""

    def __init__(self) -> None:
        pass

    def _validate_connection(self) -> bool:
        return True

    def get_cash_balance(self) -> int:
        return 0

    def get_savings_positions(self) -> Dict[str, Tuple[float, float]]:
        return {}


class FakeHealthyBroker(FakeBrokerBase):
    def get_all_crypto_balances(self) -> Dict[str, float]:
        return {"BTC": 1.0}


class FakeBrokenBroker(FakeBrokerBase):
    def get_all_crypto_balances(self) -> Dict[str, float]:
        raise RuntimeError("exchange unavailable")


class CryptoSourceStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        # get_all_crypto_quantity also merges COLD_STORAGE constants; test
        # results must be deterministic on broker data only.
        patcher = patch("src.crypto.crypto_tokens.COLD_STORAGE", {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_healthy_broker_is_marked_ok(self) -> None:
        source_status: Dict[str, str] = {}

        CryptoData.get_all_crypto_quantity([FakeHealthyBroker()], source_status)

        self.assertEqual(source_status, {"FakeHealthyBroker": "ok"})

    def test_failed_broker_is_marked_failed_and_others_still_collected(self) -> None:
        source_status: Dict[str, str] = {}

        quantities = CryptoData.get_all_crypto_quantity(
            [FakeBrokenBroker(), FakeHealthyBroker()],
            source_status,
        )

        self.assertEqual(quantities, {"BTC": 1.0})
        self.assertEqual(
            source_status,
            {"FakeBrokenBroker": "failed", "FakeHealthyBroker": "ok"},
        )

    def test_collecting_without_status_param_unchanged(self) -> None:
        quantities = CryptoData.get_all_crypto_quantity([FakeHealthyBroker()])

        self.assertEqual(quantities, {"BTC": 1.0})


if __name__ == "__main__":
    unittest.main()