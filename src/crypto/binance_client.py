import time
import logging
import traceback
import multiprocessing
from functools import wraps
from binance import Client
from data.api_keys import BINANCE_KEY, BINANCE_SECRET
from typing import Dict, Tuple, Callable, Any
from src.crypto.base_exchange_client import ExchangeBase
import requests
import hmac
import hashlib
from urllib.parse import urlencode

# Set up logging
logger = logging.getLogger(__name__)


# Define a timeout exception
class TimeoutError(Exception):
    pass


# Define the timeout function at module level to avoid pickling issues
def run_with_timeout(func, args, kwargs, queue):
    try:
        result = func(*args, **kwargs)
        queue.put((True, result))
    except Exception as e:
        queue.put((False, e))


# Timeout decorator using multiprocessing (works better on macOS)
def timeout(seconds=30):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Use a queue to pass the result or exception
            queue = multiprocessing.Queue()

            # Use the module-level function instead of a local function
            process = multiprocessing.Process(
                target=run_with_timeout, args=(func, args, kwargs, queue)
            )

            # Start the process and wait for it to finish or timeout
            process.start()
            process.join(seconds)

            # If the process is still alive after the timeout, terminate it
            if process.is_alive():
                process.terminate()
                process.join()
                raise TimeoutError(
                    f"Function {func.__name__} timed out after {seconds} seconds"
                )

            # Get the result or re-raise the exception
            success, result = queue.get()
            if success:
                return result
            else:
                raise result

        return wrapper

    return decorator


class BinanceClient(ExchangeBase):
    """Binance API wrapper with common exchange functionality."""

    CRYPTO_EXCLUDE = ExchangeBase.STABLECOINS.union({"QISWAP", "BOBA"})
    API_TIMEOUT = 20  # seconds

    def __init__(self) -> None:
        """Initialize Binance client and validate connection."""
        logger.debug("Initializing BinanceClient")
        try:
            logger.debug("Creating Binance Client instance")
            # Add timeout to API calls
            self.client = Client(
                api_key=BINANCE_KEY,
                api_secret=BINANCE_SECRET,
                requests_params={"timeout": self.API_TIMEOUT},
            )
            super().__init__()

            logger.debug("Validating connection with timeout")
            if not self._safe_validate_connection():
                logger.error("Binance connection validation failed")
                raise Exception("Binance connection validation failed")

            logger.debug("Getting spot balances with timeout")
            self.spot_balances = self._safe_get_spot_balances()

            logger.debug("Getting flexible savings positions with timeout")
            self.flexible_savings = self._safe_get_flexible_savings()

            logger.debug("Getting fixed savings positions with timeout")
            self.fixed_savings = self._safe_get_fixed_savings()

            logger.debug("BinanceClient initialization completed")
        except TimeoutError as e:
            logger.error(f"Timeout during BinanceClient initialization: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            # Initialize with empty values to allow the program to continue
            self.spot_balances = {}
            self.flexible_savings = {"rows": []}
            self.fixed_savings = {"rows": []}
        except Exception as e:
            logger.error(f"ERROR: Binance client initialization failed: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            # Initialize with empty values to allow the program to continue
            self.spot_balances = {}
            self.flexible_savings = {"rows": []}
            self.fixed_savings = {"rows": []}

    def _validate_connection(self) -> bool:
        """
        Abstract method implementation required by ExchangeBase.
        Validate connection to the Binance API.
        """
        try:
            logger.debug("Validating Binance API connection")
            system_status = self.client.get_system_status()
            return system_status.get("status") == 0  # 0 means normal
        except Exception as e:
            logger.error(f"Failed to validate Binance connection: {str(e)}")
            return False

    def _safe_validate_connection(self) -> bool:
        """Validate Binance API connection with timeout safety."""
        try:
            start_time = time.time()
            status = self.client.get_system_status()
            logger.debug(
                f"System status check took {time.time() - start_time:.2f} seconds: {status}"
            )
            return bool(self.client and status)
        except Exception as e:
            logger.error(f"Failed to validate connection: {str(e)}")
            return False

    def _safe_get_spot_balances(self) -> Dict[str, float]:
        """Get spot balances with timeout safety."""
        try:
            start_time = time.time()
            balances = self._get_spot_balances()
            logger.debug(
                f"Spot balances retrieved in {time.time() - start_time:.2f} seconds"
            )
            return balances
        except Exception as e:
            logger.error(f"Error getting spot balances: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return {}

    def _get_all_rows(self, endpoint):
        page, collected = 1, []
        while True:
            resp = self._binance_signed_request(
                "GET", endpoint, params={"current": page, "size": 100}
            )
            rows = resp.get("rows", [])
            collected.extend(rows)

            # stop when we've fetched everything
            if len(collected) >= resp.get("total", len(collected)):
                break
            page += 1
            time.sleep(0.1)  # polite‑ish throttle

        return collected

    def _binance_signed_request(self, method, endpoint, params=None):
        if params is None:
            params = {}
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        # Get API key/secret from the Client instance
        api_key = (
            self.client.API_KEY
            if hasattr(self.client, "API_KEY")
            else self.client.api_key
        )
        api_secret = (
            self.client.API_SECRET
            if hasattr(self.client, "API_SECRET")
            else self.client.api_secret
        )
        signature = hmac.new(
            api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers = {"X-MBX-APIKEY": api_key}
        url = f"https://api.binance.com{endpoint}?{query_string}&signature={signature}"
        response = requests.request(method, url, headers=headers)
        logger.debug(f"Binance API response for {endpoint}: {response.text}")
        response.raise_for_status()
        return response.json()

    def _safe_get_flexible_savings(self) -> Dict:
        try:
            logger.debug("Fetching *all* flexible Simple Earn positions")
            rows = self._get_all_rows("/sapi/v1/simple-earn/flexible/position")

            parsed = []
            for pos in rows:
                asset = pos["asset"]
                principal = float(pos["totalAmount"])
                apy = float(pos.get("latestAnnualPercentageRate", 0))

                if principal > 0:
                    parsed.append(
                        {
                            "asset": asset,
                            "totalAmount": principal,
                            "latestAnnualPercentageRate": apy,
                            "tierAnnualPercentageRate": pos.get(
                                "tierAnnualPercentageRate", {}
                            ),
                            "yesterdayAirdropPercentageRate": pos.get(
                                "yesterdayAirdropPercentageRate", 0
                            ),
                        }
                    )
            return {"rows": parsed}
        except Exception as e:
            logger.error("Error getting flexible savings: %s", e, exc_info=True)
            return {"rows": []}

    def _safe_get_fixed_savings(self) -> Dict:
        """Get locked savings with timeout safety using Simple Earn API."""
        try:
            start_time = time.time()
            logger.debug(
                "Getting locked savings positions via Simple Earn API (requests)"
            )
            response = self._binance_signed_request(
                "GET", "/sapi/v1/simple-earn/locked/position"
            )
            positions = response.get("rows", response.get("data", []))  # <‑‑ fixed
            rows = []

            for pos in positions:
                asset = pos.get("asset")
                principal = float(
                    pos.get("amount", pos.get("totalAmount", 0))
                )  # <‑‑ fixed
                apy = float(pos.get("apy", pos.get("interestRate", 0)))  # <‑‑ fixed

                if asset and principal > 0:
                    rows.append({"asset": asset, "amount": principal, "apy": apy})

            return {"rows": rows}
        except Exception as e:
            logger.error(f"Error getting locked savings positions: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return {"rows": []}

    def _get_spot_balances(self) -> Dict[str, float]:
        """Get filtered spot account balances."""
        logger.debug("Getting spot account information")
        try:
            start_time = time.time()
            account_info = self.client.get_account()
            logger.debug(
                f"get_account API call took {time.time() - start_time:.2f} seconds"
            )
            logger.debug(
                f"Retrieved account info with {len(account_info.get('balances', []))} balances"
            )

            balances = {
                balance["asset"]: float(balance["free"])
                for balance in account_info.get("balances", [])
                if "LD" not in balance["asset"]
                and balance["asset"] != "ETHW"
                and float(balance["free"]) >= self.MIN_CRYPTO_BALANCE
            }

            logger.debug(f"Filtered to {len(balances)} non-zero balances")
            return self._filter_small_balances(balances)
        except Exception as e:
            logger.error(f"Error getting spot balances: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            # Return empty dict to allow the program to continue
            return {}

    def get_spot_account_balances(self) -> Dict[str, float]:
        """Get SPOT account balances."""
        logger.debug("Getting spot account balances")
        return self.spot_balances

    def get_savings_positions(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        """Get stablecoin savings positions with weighted yields."""
        logger.debug("Getting savings positions")
        # Removed the timeout decorator to avoid pickling issues

        try:
            # Use a timeout-safe approach inside the method
            start_time = time.time()
            savings_positions = {}

            # Process flexible savings
            logger.debug(
                f"Processing {len(self.flexible_savings.get('rows', []))} flexible savings positions"
            )
            for loan in self.flexible_savings.get("rows", []):
                asset = str(loan.get("asset", "Unknown"))
                if asset not in self.STABLECOINS:
                    continue

                principal = round(float(loan.get("totalAmount", 0)))
                latest_apr = float(loan.get("latestAnnualPercentageRate", 0))
                tier_apr_dict = loan.get("tierAnnualPercentageRate", {})
                additional_yield = float(loan.get("yesterdayAirdropPercentageRate", 0))

                if principal > 0:
                    logger.debug(
                        f"Processing {asset} flexible savings with principal {principal}"
                    )
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
            logger.debug(
                f"Processing {len(self.fixed_savings.get('rows', []))} fixed savings positions"
            )
            for loan in self.fixed_savings.get("rows", []):
                asset = str(loan.get("asset", "Unknown"))
                if asset not in self.STABLECOINS:
                    continue

                principal = round(float(loan.get("amount", 0)))
                apy = round(float(loan.get("apy", 0)), 4)

                if principal > 0:
                    logger.debug(
                        f"Processing {asset} fixed savings with principal {principal}"
                    )
                    savings_positions = self.aggregate_positions(
                        savings_positions, (asset, principal, apy)
                    )

            result = (
                {"binance": savings_positions}
                if savings_positions
                else {"binance": {"None": (0, 0.0)}}
            )
            logger.debug(f"Found {len(savings_positions)} savings positions")
            logger.debug(
                f"Savings positions retrieved in {time.time() - start_time:.2f} seconds"
            )
            return result

        except Exception as e:
            logger.error(f"Error getting savings positions: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return {"binance": {"None": (0, 0.0)}}

    def _compute_effective_yield(
        self,
        principal: float,
        tier_apr_dict: Dict[str, str],
        latest_apr: float,
        additional_yield: float,
    ) -> float:
        """Calculate effective yield considering tiers and bonus."""
        logger.debug(
            f"Computing effective yield for principal {principal}, latest APR {latest_apr}, additional yield {additional_yield}"
        )
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
                logger.warning(f"Unable to parse tier range '{tier_range}': {str(e)}")
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

        final_yield = round(weighted_yield, 4)
        logger.debug(f"Computed effective yield: {final_yield}")
        return final_yield

    def _get_savings_crypto_balances(self) -> Dict[str, float]:
        """Get crypto balances from flexible and fixed savings products."""
        logger.debug("Getting savings crypto balances")
        savings_balances = {}

        # Process flexible savings
        logger.debug("Processing flexible savings for crypto balances")
        for position in self.flexible_savings.get("rows", []):
            asset = position.get("asset", "Unknown")
            if asset not in self.STABLECOINS and asset not in self.CRYPTO_EXCLUDE:
                amount = float(position.get("totalAmount", 0))
                if amount >= self.MIN_CRYPTO_BALANCE:
                    savings_balances[asset] = savings_balances.get(asset, 0) + amount
                    logger.debug(
                        f"Added {asset} balance {amount} from flexible savings"
                    )

        # Process fixed savings
        logger.debug("Processing fixed savings for crypto balances")
        for position in self.fixed_savings.get("rows", []):
            asset = position.get("asset", "Unknown")
            if asset not in self.STABLECOINS and asset not in self.CRYPTO_EXCLUDE:
                amount = float(position.get("amount", 0))
                if amount >= self.MIN_CRYPTO_BALANCE:
                    savings_balances[asset] = savings_balances.get(asset, 0) + amount
                    logger.debug(f"Added {asset} balance {amount} from fixed savings")

        logger.debug(f"Found {len(savings_balances)} crypto tokens in savings")
        return savings_balances

    def get_all_crypto_balances(self) -> Dict[str, float]:
        """Get aggregated crypto balances from spot and savings."""
        logger.debug("Getting all crypto balances")
        crypto_spot = self.filter_out_crypto_balances(self.spot_balances)
        crypto_savings = self._get_savings_crypto_balances()

        logger.debug(
            f"Found {len(crypto_spot)} spot crypto tokens and {len(crypto_savings)} savings crypto tokens"
        )

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
            logger.debug(f"Converting WBETH ({aggregated['WBETH']}) to ETH")
            aggregated["ETH"] = aggregated.get("ETH", 0) + aggregated["WBETH"]
            del aggregated["WBETH"]

        result = {
            asset: balance for asset, balance in aggregated.items() if balance > 0
        }
        logger.debug(f"Total aggregated crypto tokens: {len(result)}")
        return result

    def get_funding_wallet_balance(self) -> Dict[str, float]:
        """Get balances from Funding wallet."""
        logger.debug("Getting funding wallet balances")
        try:
            params = {
                "timestamp": int(
                    time.time() * 1000
                ),  # Current timestamp in milliseconds
                "needBtcValuation": "false",  # We don't need BTC valuation
            }
            logger.debug("Requesting funding wallet data from API")
            funding_wallet = self.client._request_margin_api(
                "post", "asset/get-funding-asset", signed=True, data=params
            )

            if not funding_wallet:
                logger.debug("No funding wallet data returned")
                return {}

            logger.debug(f"Processing {len(funding_wallet)} funding wallet assets")
            balances = {}
            for asset in funding_wallet:
                try:
                    free_balance = float(asset.get("free", "0"))
                    if free_balance > 0:
                        balances[asset["asset"]] = free_balance
                        logger.debug(
                            f"Added {asset['asset']} balance {free_balance} from funding wallet"
                        )
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Error processing funding wallet asset: {str(e)}")
                    continue

            filtered = self._filter_small_balances(balances)
            logger.debug(f"Found {len(filtered)} non-zero balances in funding wallet")
            return filtered
        except Exception as e:
            logger.warning(
                f"Unable to fetch funding wallet balance: {str(e)}", exc_info=True
            )
            return {}

    def get_cash_balance(self) -> int:
        """Get total stablecoin balance in spot and funding accounts."""
        logger.debug("Getting cash balance")
        funding_balances = self.get_funding_wallet_balance()
        funding_stablecoins = self.filter_out_stablecoin_balances(funding_balances)
        spot_stablecoins = self.filter_out_stablecoin_balances(dict(self.spot_balances))

        logger.debug(
            f"Found {len(spot_stablecoins)} spot stablecoins and {len(funding_stablecoins)} funding stablecoins"
        )

        total_stablecoins = sum(spot_stablecoins.values()) + sum(
            funding_stablecoins.values()
        )
        logger.debug(f"Total stablecoin balance: {int(total_stablecoins)}")
        return int(total_stablecoins)

    def get_earn_total_cash_savings(self) -> int:
        """Get total stablecoin savings in Binance Earn."""
        logger.debug("Getting earn total cash savings")
        savings_positions = self.get_savings_positions()
        stablecoin_positions = {
            asset: principal
            for asset, (principal, _) in savings_positions.items()
            if asset in self.STABLECOINS
        }
        total = sum(stablecoin_positions.values())
        logger.debug(f"Total stablecoin savings: {total}")
        return total  # Values are already rounded


def main():
    """Main function demonstrating usage of the refactored classes."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting BinanceClient test run")
    try:
        binance_client = BinanceClient()
        print("\n=== Binance ===")
        print("\nAggregated Crypto Balances:")
        crypto = binance_client.get_all_crypto_balances()
        for asset, balance in crypto.items():
            print(f"{asset}: {balance:.6f}")
        # Now print your Flexible & Locked savings
        print("\nSavings Positions (Binance Simple Earn):")
        savings = binance_client.get_savings_positions().get("binance", {})
        # If there's no real data, “None” key will show up; skip it
        for asset, (principal, apr) in savings.items():
            if asset == "None":
                continue
            # APR is a decimal like 0.0412 → format as percentage
            print(f"{asset}: {principal} @ {apr * 100:.2f}% APR")
        logger.info("BinanceClient test run completed successfully")
    except Exception as e:
        logger.error(f"Error in BinanceClient test: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    start_time = time.time()
    main()
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"\nExecution time of main(): {execution_time:.2f} seconds")
