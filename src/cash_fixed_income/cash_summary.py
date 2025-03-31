# TODO:
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict

from src.cash_fixed_income import mono
from data.assets_data import CASH, LENDED, DEBT, PRIVAT


@dataclass
class CashPortfolio:
    """
    Represents all cash holdings across different sources.
    """

    # Values passed during initialization (required parameters first)
    ib_cash: float
    crypto_cash: float

    # Static values (with defaults)
    cash: Decimal = Decimal(str(CASH))
    lended: Decimal = Decimal(str(LENDED))
    debt: Decimal = Decimal(str(DEBT))
    private: Decimal = Decimal(str(PRIVAT))

    def __post_init__(self):
        """Initialize dynamic sources (Mono) and convert inputs to Decimal"""
        # Convert input values to Decimal
        self.ib_cash = Decimal(str(self.ib_cash))
        self.crypto_cash = Decimal(str(self.crypto_cash))

        # Get dynamic balances
        self.mono = Decimal(str(mono.Mono().get_total_balance_in_usd()))

        # Wise is no longer used
        self.wise = Decimal("0")

    def as_dict(self) -> Dict[str, Decimal]:
        """Return all balances as a dictionary"""
        return {
            "cash": self.cash,
            "lended": self.lended,
            "debt": self.debt,
            "private": self.private,
            "ib_cash": self.ib_cash,
            "crypto_cash": self.crypto_cash,
            "mono": self.mono,
            "wise": self.wise,
        }

    @property
    def total_cash(self) -> Decimal:
        """Calculate total cash across all sources"""
        return sum(self.as_dict().values())


if __name__ == "__main__":
    portfolio = CashPortfolio(ib_cash=Decimal(100), crypto_cash=Decimal(1))
    print(f"TOTAL FREE CASH = {portfolio.total_cash}")
