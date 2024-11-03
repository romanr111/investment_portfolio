import time
import math
from collections import defaultdict
from typing import Dict, List, Tuple

from binance import Client
from data.api_keys import BINANCE_KEY, BINANCE_SECRET


class Binance:
    """
    Binance API wrapper for retrieving account and savings information.
    """

    # Constants
    STABLECOINS = {"USDT", "USDC", "BUSD", "PAX", "DAI", "EURI"}
    CRYPTO_EXCLUDE = STABLECOINS.union(
        {"QISWAP", "BOBA"}
    )  # Assets to exclude from crypto balances
    MIN_CRYPTO_BALANCE = 0.001  # Exclude balances less than 0.001
    ROUND_DECIMALS = 4

    def __init__(self) -> None:
        """
        Initializes the Binance API client.

        Raises:
            Exception: If the connection to Binance fails.
        """
        try:
            self.client = Client(api_key=BINANCE_KEY, api_secret=BINANCE_SECRET)
            if self.client:
                print("Binance connection is successful!")
            else:
                print("Connection to Binance FAILED!")
                raise Exception("Failed to connect to Binance API.")
        except Exception as e:
            print(f"Exception during Binance client initialization: {e}")
            raise

    def get_earn_total_cash_savings(self) -> int:
        """
        Retrieves the total cash savings in Binance Earn.

        Returns:
            int: Sum of cash savings in Binance Earn, rounded up.

        Raises:
            Exception: If the API call fails.
        """
        try:
            response = self.client.savings_account()
            total_amount = math.ceil(float(response.get("totalAmountInUSDT", 0)))
            print(f"Total Cash Savings in Earn: {total_amount} USDT")
            return total_amount
        except Exception as e:
            print(f"ERROR: Failed to retrieve savings account data: {e}")
            raise

    def _get_spot_account_balances(self) -> Dict[str, float]:
        """
        Retrieves spot account balances, excluding assets containing 'LD' and balances less than 0.001.

        Returns:
            Dict[str, float]: Spot account balances with 'free' balances >= 0.001.

        Raises:
            Exception: If the API call fails.
        """
        try:
            account_info = self.client.get_account()
            balances = account_info.get("balances", [])
            filtered_spot = {
                balance["asset"]: float(balance["free"])
                for balance in balances
                # Filter out not needed tokens;
                if "LD" not in balance["asset"]
                and balance["asset"] != "ETHW"
                and float(balance["free"]) >= self.MIN_CRYPTO_BALANCE
            }
            crypto_balances = {
                token: round(balance, 3) for token, balance in filtered_spot.items()
            }
            print(f"\nFiltered Spot Balances: {crypto_balances}\n")
            return crypto_balances
        except Exception as e:
            print(f"ERROR: Failed to retrieve spot account balances: {e}")
            raise


class BinanceFiltered(Binance):
    """
    Extends Binance class with additional filtering and data processing capabilities.
    """

    def __init__(self) -> None:
        """
        Initializes the BinanceFiltered object by pre-fetching and caching necessary data.

        Raises:
            Exception: If any API call during initialization fails.
        """
        super().__init__()
        try:
            start_init_time = time.time()
            self.spot_balances = self._get_spot_account_balances()
            self.flexible_savings_info = (
                self.client.get_simple_earn_flexible_product_position()
            )
            self.fixed_savings_info = (
                self.client.get_simple_earn_locked_product_position()
            )
            end_init_time = time.time()
            duration = end_init_time - start_init_time
            print(
                f"Initialization: Data pre-fetched and cached in {duration:.4f} seconds."
            )
        except Exception as e:
            print(f"ERROR: Failed during BinanceFiltered initialization: {e}")
            raise

    def _collect_savings_interest_data(self) -> Dict[str, Tuple[float, float]]:
        """
        Processes cached flexible and fixed savings information to calculate effective yields.

        Returns:
            Dict[str, Tuple[float, float]]: A dictionary with assets as keys and a tuple of
            (principal, effective_yield) as values, with yields rounded to four decimal places.
            Returns {"None": (0.0, 0.0)} if no data is available.
        """
        EMPTY_DATA = {"None": (0.0, 0.0)}
        savings_data: Dict[str, Tuple[float, float]] = {}

        # Process flexible savings
        try:
            flexible_info = self.flexible_savings_info
            flexible_rows = flexible_info.get("rows", [])
            for loan in flexible_rows:
                asset = loan.get("asset", "Unknown")
                principal = float(loan.get("totalAmount", 0.0))
                latest_apr = float(loan.get("latestAnnualPercentageRate", 0.0))
                tier_apr_dict = loan.get("tierAnnualPercentageRate", {})
                additional_yield = float(
                    loan.get("yesterdayAirdropPercentageRate", 0.0)
                )

                if tier_apr_dict:
                    effective_yield = self._compute_effective_yield(
                        principal, tier_apr_dict, latest_apr, additional_yield
                    )
                else:
                    effective_yield = latest_apr + additional_yield

                effective_yield = round(effective_yield, self.ROUND_DECIMALS)
                principal = round(principal, self.ROUND_DECIMALS)

                if asset in savings_data:
                    # Aggregate if asset already exists
                    existing_principal, existing_yield = savings_data[asset]
                    total_principal = existing_principal + principal
                    weighted_yield = (
                        existing_principal * existing_yield
                        + principal * effective_yield
                    ) / total_principal
                    savings_data[asset] = (
                        round(total_principal, self.ROUND_DECIMALS),
                        round(weighted_yield, self.ROUND_DECIMALS),
                    )
                else:
                    savings_data[asset] = (principal, effective_yield)
        except Exception as e:
            print(f"ERROR: Failed to collect flexible savings data: {e}")

        # Process fixed savings
        try:
            fixed_info = self.fixed_savings_info
            fixed_rows = fixed_info.get("rows", [])
            for loan in fixed_rows:
                asset = loan.get("asset", "Unknown")
                principal = float(loan.get("amount", 0.0))
                apy = float(loan.get("apy", 0.0))

                effective_yield = round(apy, self.ROUND_DECIMALS)
                principal = round(principal, self.ROUND_DECIMALS)

                if asset in savings_data:
                    existing_principal, existing_yield = savings_data[asset]
                    total_principal = existing_principal + principal
                    weighted_yield = (
                        existing_principal * existing_yield
                        + principal * effective_yield
                    ) / total_principal
                    savings_data[asset] = (
                        round(total_principal, self.ROUND_DECIMALS),
                        round(weighted_yield, self.ROUND_DECIMALS),
                    )
                else:
                    savings_data[asset] = (principal, effective_yield)
        except Exception as e:
            print(f"ERROR: Failed to collect fixed savings data: {e}")

        return savings_data if savings_data else EMPTY_DATA

    def get_stablecoin_savings(self) -> Dict[str, Tuple[float, float]]:
        """
        Filters the savings interest data to include only stablecoins.

        Returns:
            Dict[str, Tuple[float, float]]: Stablecoin savings with (principal, effective_yield).
        """
        savings = self._collect_savings_interest_data()
        stablecoin_savings = {k: v for k, v in savings.items() if k in self.STABLECOINS}
        return stablecoin_savings

    def get_spot_cash_balance(self) -> int:
        """
        Retrieves the total uninvested cash balance in the spot account, considering only stablecoins.

        Returns:
            int: Total amount of uninvested cash in stablecoins, rounded.

        Raises:
            Exception: If the calculation fails.
        """
        try:
            balances = self.spot_balances
            crypto_cash = sum(
                round(float(balance))
                for token, balance in balances.items()
                if token in self.STABLECOINS
            )
            return crypto_cash
        except Exception as e:
            print(f"ERROR: Failed to calculate spot account cash balance: {e}")
            raise

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """
        Retrieves and sums up all crypto balances across Spot and Earn accounts, excluding stablecoins.

        Returns:
            Dict[str, float]: Aggregated crypto balances.

        Raises:
            Exception: If the aggregation fails.
        """
        try:
            # Exclude stablecoins from spot balances
            crypto_spot = {
                token: balance
                for token, balance in self.spot_balances.items()
                if token not in self.STABLECOINS
            }

            savings_interest_data = self._collect_savings_interest_data()

            aggregated_crypto = defaultdict(float, crypto_spot)

            for asset, (principal, _) in savings_interest_data.items():
                if asset not in self.STABLECOINS and asset != "None":
                    aggregated_crypto[asset] += principal

            # Remove assets with zero balance if any
            aggregated_crypto = {
                asset: balance
                for asset, balance in aggregated_crypto.items()
                if balance > 0
            }

            return aggregated_crypto
        except Exception as e:
            print(f"ERROR: Failed to get all crypto balances: {e}")
            raise

    def _compute_effective_yield(
        self,
        principal: float,
        tier_apr_dict: Dict[str, str],
        latest_apr: float,
        additional_yield: float,
    ) -> float:
        """
        Computes the effective yield for a flexible savings asset considering tiered APRs
        and additional yield components.

        Args:
            principal (float): The total amount invested in the asset.
            tier_apr_dict (Dict[str, str]): Tier ranges and their APRs.
            latest_apr (float): The APR to apply beyond the highest tier.
            additional_yield (float): Additional yield components (e.g., airdrop rates).

        Returns:
            float: The effective APR for the invested amount.
        """
        tiers: List[Tuple[float, float]] = []

        for tier_range, apr_str in tier_apr_dict.items():
            try:
                # Example tier_range: '0-500EURI', extract '500'
                upper_limit_str = tier_range.split("-")[1]
                upper_limit = float(
                    "".join(filter(lambda x: x.isdigit() or x == ".", upper_limit_str))
                )
                apr = float(apr_str)
                tiers.append((upper_limit, apr))
            except (IndexError, ValueError) as e:
                print(
                    f"WARNING: Unable to parse tier range '{tier_range}': {e}. Skipping this tier."
                )
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

        return weighted_yield


if __name__ == "__main__":
    try:
        overall_start_time = time.time()
        binance_filtered = BinanceFiltered()

        cash_balance = binance_filtered.get_spot_cash_balance()
        print(f"Spot Account Cash Balance: {cash_balance} USDT\n")

        crypto_balances = binance_filtered.get_all_crypto_balances()
        print(f"All Crypto Balances (aggregated): {crypto_balances}\n")

        savings_interest_data = binance_filtered.get_stablecoin_savings()
        print(f"Savings Interest Data: {savings_interest_data}\n")

        overall_end_time = time.time()
        overall_duration = overall_end_time - overall_start_time
        print(f"Overall Execution Time: {overall_duration:.4f} seconds")
    except Exception as e:
        print(f"ERROR: {e}")
