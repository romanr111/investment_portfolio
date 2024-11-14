# -------------------------------- DONE --------------------------------
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional


class ExchangeBase(ABC):
    """Base class for cryptocurrency exchange clients with common functionality."""

    # Common constants
    STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "PAX", "EURI"}
    MIN_CRYPTO_BALANCE = 0.001
    ROUND_DECIMALS = 4

    def __init__(self) -> None:
        """Initialize exchange client and validate connection."""
        if not self._validate_connection():
            raise Exception(f"Failed to connect to {self.__class__.__name__} API.")

    @abstractmethod
    def _validate_connection(self) -> bool:
        """Validate API connection."""
        pass

    def _round_amount(self, amount: float, decimals: Optional[int] = None) -> float:
        """Round amount to specified decimal places."""
        decimals = decimals if decimals is not None else self.ROUND_DECIMALS
        return round(amount, decimals)

    def _filter_small_balances(self, balances: Dict[str, float]) -> Dict[str, float]:
        """Filter out balances below minimum threshold."""
        return {
            asset: balance
            for asset, balance in balances.items()
            if balance >= self.MIN_CRYPTO_BALANCE
        }

    def _calculate_weighted_yield(
        self,
        existing_principal: float,
        existing_yield: float,
        new_principal: float,
        new_yield: float,
    ) -> Tuple[float, float]:
        """Calculate weighted yield for combined positions."""
        total_principal = existing_principal + new_principal
        weighted_yield = (
            (existing_principal * existing_yield + new_principal * new_yield)
            / total_principal
            if total_principal > 0
            else 0
        )

        return (self._round_amount(total_principal), self._round_amount(weighted_yield))

    def get_stablecoin_balances(self, balances: Dict[str, float]) -> Dict[str, float]:
        """Filter and return stablecoin balances."""
        stablecoin_balances = {
            asset: balance
            for asset, balance in balances.items()
            if asset in self.STABLECOINS and balance >= 1
        }
        return stablecoin_balances

    def filter_out_crypto_balances(
        self, balances: Dict[str, float]
    ) -> Dict[str, float]:
        """Filter and return crypto balances, excluding stablecoins."""
        crypto_balances = {
            asset: balance
            for asset, balance in balances.items()
            if asset not in self.STABLECOINS and balance >= self.MIN_CRYPTO_BALANCE
        }
        return crypto_balances

    def aggregate_positions(
        self,
        positions: Dict[str, Tuple[float, float]],
        new_position: Tuple[str, float, float],
    ) -> Dict[str, Tuple[float, float]]:
        """Combines MULTIPLE positions of the same asset
        Used when you have several positions in the same asset and need to combine them;
        """
        asset, principal, yield_rate = new_position

        if asset in positions:
            existing_principal, existing_yield = positions[asset]
            total_principal, weighted_yield = self._calculate_weighted_yield(
                existing_principal, existing_yield, principal, yield_rate
            )
            positions[asset] = (total_principal, weighted_yield)
        else:
            positions[asset] = (
                self._round_amount(principal),
                self._round_amount(yield_rate),
            )

        return positions

    @abstractmethod
    def get_account_balances(self) -> Dict[str, float]:
        """Retrieve account balances from exchange."""
        pass

    @abstractmethod
    def get_savings_positions(self) -> Dict[str, Tuple[float, float]]:
        """Retrieve savings/earn positions from exchange."""
        pass
