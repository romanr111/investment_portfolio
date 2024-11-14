import time
from binance import Client
from data.api_keys import BINANCE_KEY, BINANCE_SECRET
from typing import Dict, Tuple
from src.crypto.base_exchange_client import ExchangeBase


class BinanceClient(ExchangeBase):
    """Binance API wrapper with common exchange functionality."""

    CRYPTO_EXCLUDE = ExchangeBase.STABLECOINS.union({"QISWAP", "BOBA"})

    def __init__(self) -> None:
        """Initialize Binance client and validate connection."""
        try:
            self.client = Client(api_key=BINANCE_KEY, api_secret=BINANCE_SECRET)
            super().__init__()
            self.spot_balances = self._get_spot_balances()
            self.flexible_savings = (
                self.client.get_simple_earn_flexible_product_position()
            )
            self.fixed_savings = self.client.get_simple_earn_locked_product_position()
        except Exception as e:
            print(f"ERROR: Binance client initialization failed: {e}")
            raise

    def _validate_connection(self) -> bool:
        """Validate Binance API connection."""
        return bool(self.client)

    def _get_spot_balances(self) -> Dict[str, float]:
        """Get filtered spot account balances."""
        account_info = self.client.get_account()
        balances = {
            balance["asset"]: float(balance["free"])
            for balance in account_info.get("balances", [])
            if "LD" not in balance["asset"]
            and balance["asset"] != "ETHW"
            and float(balance["free"]) >= self.MIN_CRYPTO_BALANCE
        }
        return self._filter_small_balances(balances)

    def _compute_effective_yield(
        self,
        principal: float,
        tier_apr_dict: Dict[str, str],
        latest_apr: float,
        additional_yield: float,
    ) -> float:
        """Calculate effective yield considering tiers and bonus."""
        tiers = []
        for tier_range, apr_str in tier_apr_dict.items():
            try:
                upper_limit_str = tier_range.split("-")[1]
                upper_limit = float(
                    "".join(filter(lambda x: x.isdigit() or x == ".", upper_limit_str))
                )
                apr = float(apr_str)
                tiers.append((upper_limit, apr))
            except (IndexError, ValueError) as e:
                print(f"WARNING: Unable to parse tier range '{tier_range}': {e}")
                continue

        tiers.sort(key=lambda x: x[0])
        remaining_principal = principal
        weighted_yield = 0.0
        last_upper_limit = 0.0

        for upper_limit, tier_apr in tiers:
            tier_amount = min(remaining_principal, upper_limit - last_upper_limit)
            if tier_amount <= 0:
                last_upper_limit = upper_limit
                continue

            combined_apr = tier_apr + latest_apr
            weighted_yield += (tier_amount / principal) * combined_apr
            remaining_principal -= tier_amount
            last_upper_limit = upper_limit

            if remaining_principal <= 0:
                break

        if remaining_principal > 0:
            weighted_yield += (remaining_principal / principal) * latest_apr

        if additional_yield > 0:
            weighted_yield += additional_yield

        return round(
            weighted_yield, 4
        )  # Round to 4 decimal places for percentage accuracy

    def get_spot_account_balances(self) -> Dict[str, float]:
        """Get SPOT account balances."""
        return self.spot_balances

    def get_savings_positions(self) -> Dict[str, Tuple[float, float]]:
        """Get stablecoin savings positions with weighted yields."""
        savings_positions = {}

        # Process flexible savings
        for loan in self.flexible_savings.get("rows", []):
            asset = loan.get("asset", "Unknown")
            if asset not in self.STABLECOINS:
                continue

            principal = round(float(loan.get("totalAmount", 0)))  # Round to integer
            latest_apr = float(loan.get("latestAnnualPercentageRate", 0))
            tier_apr_dict = loan.get("tierAnnualPercentageRate", {})
            additional_yield = float(loan.get("yesterdayAirdropPercentageRate", 0))

            if principal > 0:
                if tier_apr_dict:
                    effective_yield = self._compute_effective_yield(
                        principal, tier_apr_dict, latest_apr, additional_yield
                    )
                else:
                    effective_yield = round(latest_apr + additional_yield, 4)

                savings_positions = self.aggregate_positions(
                    savings_positions, (asset, principal, effective_yield)
                )

        # Process fixed savings
        for loan in self.fixed_savings.get("rows", []):
            asset = loan.get("asset", "Unknown")
            if asset not in self.STABLECOINS:
                continue

            principal = round(float(loan.get("amount", 0)))  # Round to integer
            apy = round(float(loan.get("apy", 0)), 4)  # Round to 4 decimal places

            if principal > 0:
                savings_positions = self.aggregate_positions(
                    savings_positions, (asset, principal, apy)
                )

        return savings_positions if savings_positions else {"None": (0, 0.0)}

    def _get_savings_crypto_balances(self) -> Dict[str, float]:
        """Get crypto balances from flexible and fixed savings products."""
        savings_balances = {}

        # Process flexible savings
        for position in self.flexible_savings.get("rows", []):
            asset = position.get("asset", "Unknown")
            if asset not in self.STABLECOINS and asset not in self.CRYPTO_EXCLUDE:
                amount = float(position.get("totalAmount", 0))
                if amount >= self.MIN_CRYPTO_BALANCE:
                    savings_balances[asset] = savings_balances.get(asset, 0) + amount

        # Process fixed savings
        for position in self.fixed_savings.get("rows", []):
            asset = position.get("asset", "Unknown")
            if asset not in self.STABLECOINS and asset not in self.CRYPTO_EXCLUDE:
                amount = float(position.get("amount", 0))
                if amount >= self.MIN_CRYPTO_BALANCE:
                    savings_balances[asset] = savings_balances.get(asset, 0) + amount

        return savings_balances

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """Get aggregated crypto balances from spot and savings."""
        crypto_spot = self.filter_out_crypto_balances(self.spot_balances)
        crypto_savings = self._get_savings_crypto_balances()

        aggregated = {}
        # Add spot balances
        for asset, balance in crypto_spot.items():
            if asset not in self.CRYPTO_EXCLUDE:
                aggregated[asset] = balance

        # Add savings balances
        for asset, balance in crypto_savings.items():
            if asset in aggregated:
                aggregated[asset] += balance
            else:
                aggregated[asset] = balance

        # Convert WBETH to ETH if WBETH is present
        if "WBETH" in aggregated:
            aggregated["ETH"] = aggregated.get("ETH", 0) + aggregated["WBETH"]
            del aggregated["WBETH"]

        return {asset: balance for asset, balance in aggregated.items() if balance > 0}

    def get_cash_balance(self) -> int:
        """Get total stablecoin balance in spot account."""
        stablecoin_balances = self.filter_out_stablecoin_balances(
            dict(self.spot_balances)
        )
        if not stablecoin_balances:
            return 0
        else:
            return sum(stablecoin_balances.values())

    def get_earn_total_cash_savings(self) -> int:
        """Get total stablecoin savings in Binance Earn."""
        savings_positions = self.get_savings_positions()
        stablecoin_positions = {
            asset: principal
            for asset, (principal, _) in savings_positions.items()
            if asset in self.STABLECOINS
        }
        return sum(stablecoin_positions.values())  # Values are already rounded


def main():
    """Main function demonstrating usage of the refactored classes."""
    try:
        # Binance
        binance_client = BinanceClient()
        print("\n=== Binance ===")
        print("\nAggregated Crypto Balances:")
        crypto = binance_client.get_all_crypto_balances()
        for asset, balance in crypto.items():
            print(f"{asset}: {balance:.6f}")

        cash = binance_client.get_cash_balance()
        print(f"\nStablecoin Balances: {cash}")

        print("\nSavings Positions:")
        binance_savings = binance_client.get_savings_positions()
        for asset, (principal, yield_rate) in binance_savings.items():
            print(f"{asset}: Principal={principal}, APY={yield_rate*100:.2f}%")

    except Exception as e:
        print(f"ERROR inside main(): {e}")


if __name__ == "__main__":
    start_time = time.time()  # Start time
    main()
    end_time = time.time()  # End time
    execution_time = end_time - start_time
    print(f"\nExecution time of main(): {execution_time:.2f} seconds")
