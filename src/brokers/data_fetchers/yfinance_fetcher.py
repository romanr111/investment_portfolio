"""
YFinance data fetcher for bond ETFs and other securities.
Fetches live data directly from Yahoo Finance.
"""

import logging
from typing import Any, Dict, List, Union, Tuple
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

from .yahoo_forward import forward_dividend

logger = logging.getLogger(__name__)


class YFinanceFetcher:
    """Fetches financial data directly from yfinance library."""

    def __init__(self):
        """Initialize the fetcher."""
        self.adr_map = {}  # Initialize empty ADR map since we don't need it for BRK-B

    def _get_yfinance_symbol(self, symbol: str) -> str:
        """Maps a symbol to its yfinance equivalent.

        Special cases:
        - Maps Hong Kong stocks to ADR equivalents
        - Maps 9988 to BABA (Alibaba ADR)
        - Maps IHYG to IHYG.L (iShares High Yield Corporate Bond ETF)
        - Maps BRK B to BRK-B (Berkshire Hathaway Class B)
        - Returns original symbol for other cases
        """
        # Special case for Alibaba Hong Kong listing
        if symbol == "9988":
            return "BABA"

        # Special case for iShares High Yield Corporate Bond ETF
        if symbol == "IHYG":
            return "IHYG.L"

        # Special case for Berkshire Hathaway Class B
        if symbol == "BRK B":
            return "BRK-B"

        # Use ADR mapping for Hong Kong stocks
        return self.adr_map.get(symbol, symbol)

    def _get_etf_info(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """
        Extract dividend information from yfinance Ticker object with fallback to
        forward dividend data from Yahoo Finance API.

        Args:
            ticker: yfinance Ticker object

        Returns:
            Dictionary containing dividend information
        """
        try:
            info = ticker.info or {}

            # First try to get from yfinance info
            dividend_yield = info.get("yield")  # Some APIs use 'yield' as a key
            dividend_rate = info.get("dividendRate")

            # If we don't have yield, try alternative keys
            if not dividend_yield:
                dividend_yield = info.get("trailingAnnualDividendYield")
                if isinstance(dividend_yield, dict):
                    dividend_yield = dividend_yield.get("raw")

            if not dividend_rate:
                dividend_rate = info.get("trailingAnnualDividendRate")
                if isinstance(dividend_rate, dict):
                    dividend_rate = dividend_rate.get("raw")

            # Get current price for yield calculation
            current_price = info.get(
                "currentPrice", info.get("regularMarketPrice", 0.0)
            )

            # If we don't have yield, try to calculate from dividend and price
            if not dividend_yield and dividend_rate and current_price > 0:
                dividend_yield = float(dividend_rate) / current_price

            # Get historical dividend data
            latest_dividend = 0.0
            latest_dividend_date = None
            annual_dividend = 0.0

            try:
                # Get historical dividends
                dividends = ticker.dividends
                if not dividends.empty:
                    # Get the most recent dividend
                    latest_dividend = float(dividends.iloc[-1])
                    # Get the most recent dividend date as a date object
                    latest_dividend_date = (
                        pd.to_datetime(dividends.index[-1]).date()
                        if not isinstance(dividends.index[-1], pd.Timestamp)
                        else dividends.index[-1].date()
                    )

                    # Calculate annual dividend from the last 12 months
                    end_date = datetime.now()
                    start_date = end_date - timedelta(
                        days=370
                    )  # Slightly more than 12 months

                    # Convert timezone-naive timestamps to timezone-aware for comparison
                    if (
                        hasattr(dividends.index, "tz")
                        and dividends.index.tz is not None
                    ):
                        tz = dividends.index.tz
                        start_ts = pd.Timestamp(start_date).tz_localize(tz)
                        end_ts = pd.Timestamp(end_date).tz_localize(tz)
                    else:
                        start_ts = pd.Timestamp(start_date)
                        end_ts = pd.Timestamp(end_date)

                    # Filter for the last 12 months
                    mask = (dividends.index >= start_ts) & (dividends.index <= end_ts)
                    last_year = dividends.loc[mask]

                    if not last_year.empty:
                        annual_dividend = float(last_year.sum())
            except Exception as e:
                logger.debug(f"Error getting historical dividends: {str(e)}")

            # Special handling for BABA/9988 to ensure we get the correct forward yield
            # These tickers should always use the forward dividend data
            if ticker.ticker in ["BABA", "9988", "9988.HK"]:
                logger.debug(f"Processing BABA/9988 ticker: {ticker.ticker}")
                fwd_yield, fwd_rate = forward_dividend(
                    "BABA"
                )  # Always use BABA for the API call
                if fwd_yield > 0:
                    dividend_yield = fwd_yield
                    dividend_rate = fwd_rate
                    logger.info(
                        f"Using forward dividend data for {ticker.ticker}: yield={fwd_yield*100:.2f}%, rate={fwd_rate}"
                    )
                else:
                    logger.warning(
                        f"Could not get forward dividend for {ticker.ticker}, using hardcoded values"
                    )
                    dividend_yield = 0.0094  # 0.94%
                    dividend_rate = 1.03
            # For other tickers, only try forward dividend if we don't have yield yet
            elif not dividend_yield:
                try:
                    logger.debug(f"Trying forward dividend API for {ticker.ticker}")
                    fwd_yield, fwd_rate = forward_dividend(ticker.ticker)
                    if fwd_yield > 0:
                        dividend_yield = fwd_yield
                        dividend_rate = fwd_rate
                        logger.debug(
                            f"Using forward data for {ticker.ticker}: yield={fwd_yield*100:.2f}%, rate={fwd_rate}"
                        )
                except Exception as e:
                    logger.debug(
                        f"Error getting forward dividend for {ticker.ticker}: {e}"
                    )

            # If we still don't have a yield but have a dividend rate and price, calculate it
            if not dividend_yield and dividend_rate and current_price > 0:
                dividend_yield = float(dividend_rate) / current_price

            return {
                "success": True,
                "symbol": ticker.ticker,
                "dividend_yield": float(dividend_yield or 0),
                "dividend": float(dividend_rate or 0),
                "latest_dividend": latest_dividend,
                "latest_dividend_date": latest_dividend_date,
                "annual_dividend": annual_dividend,
                "source": "yfinance",
                "currency": info.get("currency", "USD"),
            }

        except Exception as e:
            logger.error(f"Error getting ETF info: {str(e)}")
            return {"error": str(e), "success": False, "source": "yfinance"}
            if not dividend_yield and current_price and annual_dividend:
                # Calculate yield as a decimal (e.g., 0.0768 for 7.68%)
                dividend_yield = annual_dividend / current_price

            return {
                "dividend_yield": dividend_yield,
                "annual_dividend": annual_dividend,
                "latest_dividend": latest_dividend,
                "latest_dividend_date": latest_dividend_date,
                "current_price": current_price,
                "name": info.get("shortName", info.get("symbol", "")),
                "category": info.get("quoteType", "ETF"),
                "success": True,
                "source": "yfinance",
            }

        except Exception as e:
            logger.error(f"Error getting ETF info: {str(e)}")
            return {"error": str(e), "success": False, "source": "yfinance"}

    def get_dividend_data(
        self, symbols: Union[str, List[str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get comprehensive dividend data for given symbols.

        Args:
            symbols: Single symbol or list of symbols to fetch data for

        Returns:
            Dictionary with symbol as key and dividend data as value
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        results = {}

        for symbol in symbols:
            symbol_upper = symbol.upper()
            try:
                ticker = yf.Ticker(symbol_upper)
                data = self._get_etf_info(ticker)

                if data.get("success", False):
                    results[symbol_upper] = data
                else:
                    error_msg = data.get("error", "Unknown error")
                    results[symbol_upper] = {
                        "dividend_yield": 0.0,
                        "annual_dividend": 0.0,
                        "ex_dividend_date": None,
                        "latest_dividend": 0.0,
                        "latest_dividend_date": None,
                        "payout_ratio": 0.0,
                        "current_price": None,
                        "name": symbol_upper,
                        "category": "Bond ETF",
                        "error": error_msg,
                        "success": False,
                        "source": "yfinance",
                    }
                    logger.warning(
                        f"Failed to fetch data for {symbol_upper}: {error_msg}"
                    )

            except Exception as e:
                logger.error(f"Error processing {symbol_upper}: {str(e)}")
                results[symbol_upper] = {
                    "dividend_yield": 0.0,
                    "annual_dividend": 0.0,
                    "ex_dividend_date": None,
                    "latest_dividend": 0.0,
                    "latest_dividend_date": None,
                    "payout_ratio": 0.0,
                    "current_price": None,
                    "name": symbol_upper,
                    "category": "Bond ETF",
                    "error": str(e),
                    "success": False,
                    "source": "yfinance",
                }

        return results

    def get_bond_etf_yield(self, symbol: str) -> float:
        """Get the current yield for a bond ETF.

        Note: This method is kept for backward compatibility but is deprecated.
        Use get_dividend_data() instead which provides more comprehensive data.

        Args:
            symbol: The ETF symbol

        Returns:
            The current yield as a percentage (e.g., 5.5 for 5.5%)
        """
        # Get data from the more reliable get_dividend_data method
        data = self.get_dividend_data(symbol)
        symbol_data = data.get(symbol.upper(), {})
        return symbol_data.get("dividend_yield", 0.0)
