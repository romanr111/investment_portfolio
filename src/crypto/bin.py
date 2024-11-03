import math
from collections import defaultdict
from typing import Dict, List

from binance import Client
from data.crypto_data import BINANCE_LOCKED_STACKING
from data.api_keys import BINANCE_KEY, BINANCE_SECRET


class Binance:
    # Needs to be updated manually every time staking changes;

    def __init__(self) -> None:
        self.__binance_connection = Client(
            api_key=BINANCE_KEY, api_secret=BINANCE_SECRET
        )

        if self.__binance_connection:
            print("Binance connection is successful!")
        else:
            raise Exception("Connection to Binance FAILED!")

    def get_earn_total_cash_savings(self) -> int:
        """
        Returns:
            int: Sum of cash savings in Binance Earn
        """
        try:
            response = self.__binance_connection.savings_account()
            return math.ceil(float(response["totalAmountInUSDT"]))
        except Exception as e:
            print(f"ERROR: Failed to retrieve savings account data: {e}")
            raise

    def _get_flexible_savings_info(self) -> List[Dict]:
        try:
            response = (
                self.__binance_connection.get_simple_earn_flexible_product_position()
            )
            print("Flexible Savings Response:", response)  # Debugging line
            return response
        except Exception as e:
            print(f"ERROR: Failed to retrieve flexible savings info: {e}")
            raise

    def _get_fixed_savings_info(self) -> List[Dict]:
        try:
            response = (
                self.__binance_connection.get_simple_earn_locked_product_position()
            )
            print("Fixed Savings Response:", response)  # Debugging line
            return response
        except Exception as e:
            print(f"ERROR: Failed to retrieve fixed savings info: {e}")
            raise

    def _get_spot_account_balances(self) -> Dict[str, str]:
        """
        Returns:
            dict: Spot account balance without zero values.
        """
        try:
            balances = self.__binance_connection.get_account()["balances"]
            filtered_spot = {}

            for balance in balances:
                if "LD" in balance["asset"]:
                    continue
                elif float(balance["free"]) > 0.0:
                    filtered_spot[balance["asset"]] = balance["free"]

            return filtered_spot
        except Exception as e:
            print(f"ERROR: Failed to retrieve spot account balances: {e}")
            raise


class BinanceFiltered(Binance):
    def _get_spot_account_crypto_balances(self) -> defaultdict:
        """Filters out Crypto from Crypto-Dollars in Spot account.

        Returns:
            defaultdict: Spot crypto balances.
        """
        crypto = defaultdict(int)
        try:
            balances = self._get_spot_account_balances()

            for token, balance in balances.items():
                if token not in [
                    "USDT",
                    "USDC",
                    "BUSD",
                    "PAX",
                    "DAI",
                    "QISWAP",
                    "BOBA",
                ]:
                    if float(balance) > 0.0001:
                        crypto[token] = round(float(balance), 3)
        except Exception as e:
            print(f"ERROR: Failed to filter spot account crypto balances: {e}")
            raise

        return crypto

    def collect_savings_interest_data(self) -> dict:
        """
        Retrieves both flexible and fixed savings information and calculates the effective yield
        for each asset, considering tiered rates and additional yield components where applicable.

        Returns:
            dict: If there are savings data, returns a dictionary with the format
                {
                    "Asset1": (principal1, effective_yield1),
                    "Asset2": (principal2, effective_yield2),
                    ...
                }
                Yields are rounded to four decimal places.
                Otherwise, returns {"None": (0, 0)} indicating no data.
        """
        EMPTY_DATA = {"None": (0, 0)}

        savings_data = {}

        try:
            flexible_info = self._get_flexible_savings_info()
            # Access the 'rows' key
            flexible_rows = flexible_info.get("rows", [])
            for loan in flexible_rows:
                asset = loan.get("asset", "Unknown")
                principal = float(loan.get("totalAmount", 0))
                latest_apr = float(loan.get("latestAnnualPercentageRate", 0))
                tier_apr_dict = loan.get("tierAnnualPercentageRate", {})
                additional_yield = 0.0

                # Check for additional yield components (e.g., airdrop rates)
                if "yesterdayAirdropPercentageRate" in loan:
                    additional_yield += float(
                        loan.get("yesterdayAirdropPercentageRate", 0)
                    )

                if tier_apr_dict:
                    # Parse tiers and compute effective yield
                    effective_yield = self._compute_effective_yield(
                        principal, tier_apr_dict, latest_apr, additional_yield
                    )
                else:
                    # No tiered rates, sum latest APR with any additional yield
                    effective_yield = latest_apr + additional_yield

                # Round the yield to four decimal places
                effective_yield = round(effective_yield, 4)

                savings_data[asset] = (round(principal, 4), effective_yield)
        except Exception as e:
            print(f"ERROR: Failed to collect flexible savings data: {e}")

        try:
            fixed_info = self._get_fixed_savings_info()
            # Access the 'rows' key
            fixed_rows = fixed_info.get("rows", [])
            for loan in fixed_rows:
                asset = loan.get("asset", "Unknown")
                principal = float(loan.get("amount", 0))
                apy = float(loan.get("apy", 0))

                # For fixed savings, the APY is used directly as the yield
                effective_yield = round(apy, 4)

                savings_data[asset] = (round(principal, 4), effective_yield)
        except Exception as e:
            print(f"ERROR: Failed to collect fixed savings data: {e}")

        return savings_data if savings_data else EMPTY_DATA

    def _compute_effective_yield(
        self,
        principal: float,
        tier_apr_dict: dict,
        latest_apr: float,
        additional_yield: float,
    ) -> float:
        """
        Computes the effective yield for a flexible savings asset considering tiered APRs
        and additional yield components.

        Args:
            principal (float): The total amount invested in the asset.
            tier_apr_dict (dict): A dictionary with tier ranges as keys and APRs as values.
                                Example: {'0-500EURI': '0.07000000'}
            latest_apr (float): The APR to apply to any amount beyond the highest tier.
            additional_yield (float): Any additional yield components (e.g., airdrop rates).

        Returns:
            float: The effective APR for the invested amount.
        """
        # Parse tiers and sort them based on the upper limit
        tiers = []
        for tier_range, apr_str in tier_apr_dict.items():
            # Extract the upper limit from the tier range string
            try:
                upper_limit_str = tier_range.split("-")[1]
                # Remove any non-numeric characters (e.g., 'EURI')
                upper_limit = float(
                    "".join(filter(lambda x: x.isdigit() or x == ".", upper_limit_str))
                )
            except (IndexError, ValueError):
                print(
                    f"WARNING: Unable to parse tier range '{tier_range}'. Skipping this tier."
                )
                continue
            apr = float(apr_str)
            tiers.append((upper_limit, apr))

        # Sort tiers by upper limit in ascending order
        tiers.sort(key=lambda x: x[0])

        remaining_principal = principal
        weighted_yield = 0.0
        last_upper_limit = 0.0

        for upper_limit, tier_apr in tiers:
            applicable_amount = min(remaining_principal, upper_limit - last_upper_limit)
            if applicable_amount <= 0:
                last_upper_limit = upper_limit
                continue
            # Sum tier APR and latest APR for the applicable amount
            combined_apr = tier_apr + latest_apr
            weighted_yield += (applicable_amount / principal) * combined_apr
            remaining_principal -= applicable_amount
            last_upper_limit = upper_limit
            if remaining_principal <= 0:
                break

        if remaining_principal > 0:
            # Apply the latest APR to the remaining amount
            weighted_yield += (remaining_principal / principal) * latest_apr

        # Add any additional yield components uniformly across the entire principal
        if additional_yield > 0:
            weighted_yield += additional_yield

        return weighted_yield

    def get_spot_account_cash_balance(self) -> int:
        """Filters out USDT/USDC/BUSD/PAX/DAI from all tokens.

        Returns:
            int: Total amount of uninvested cash account balance.
        """
        crypto_cash = 0
        try:
            balances = self._get_spot_account_balances()

            for token, balance in balances.items():
                if token in ["USDT", "USDC", "BUSD", "PAX", "DAI"]:
                    crypto_cash += round(float(balance))
        except Exception as e:
            print(f"ERROR: Failed to calculate spot account cash balance: {e}")
            raise

        return crypto_cash

    def sum_up_all_stablecoins(self) -> int:
        # TODO
        return self.get_spot_account_cash_balance()

    def get_all_crypto_balances(self) -> defaultdict:
        """Sums up all crypto in different wallets (Spot + Earn).

        Returns:
            defaultdict: Name + Amount
        """
        crypto = self._get_spot_account_crypto_balances()

        try:
            for token, amount in BINANCE_LOCKED_STACKING.items():
                crypto[token] += amount
        except Exception as e:
            print(f"ERROR: Failed to add BINANCE_LOCKED_STACKING amounts: {e}")
            raise

        return crypto


if __name__ == "__main__":
    try:
        bin = BinanceFiltered()
        print(
            f"get_spot_account_cash_balance - {bin.get_spot_account_cash_balance()}\n"
        )
        print(f"get_all_crypto_balances - {bin.get_all_crypto_balances()}\n")
        print(
            f"collect_savings_interest_data - {bin.collect_savings_interest_data()}\n"
        )
    except Exception as e:
        print(f"ERROR: {e}")
