"""
Index performance fetcher for major market indices.
Fetches YTD performance data for S&P 500, NASDAQ, Euro Stoxx 50, and Hang Seng.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """Configuration for a market index."""

    symbol: str
    name: str
    currency: str
    description: str


class IndexPerformanceFetcher:
    """Fetches YTD performance data for major market indices."""

    def __init__(self):
        """Initialize the fetcher with index configurations."""
        self.indices: Dict[str, IndexConfig] = {
            "SP500": IndexConfig(
                symbol="^GSPC",
                name="S&P 500",
                currency="USD",
                description="S&P 500 Index - US large-cap stocks",
            ),
            "NASDAQ": IndexConfig(
                symbol="^IXIC",
                name="NASDAQ Composite",
                currency="USD",
                description="NASDAQ Composite Index - US tech stocks",
            ),
            "EURO_STOXX_50": IndexConfig(
                symbol="^STOXX50E",
                name="Euro Stoxx 50",
                currency="EUR",
                description="Euro Stoxx 50 Index - Eurozone blue-chip stocks",
            ),
            "HANG_SENG": IndexConfig(
                symbol="^HSI",
                name="Hang Seng Index",
                currency="HKD",
                description="Hang Seng Index - Hong Kong stocks",
            ),
        }

    def _get_ytd_start_date(self) -> datetime:
        """Get the start date for Year-to-Date calculations."""
        today = datetime.now()
        return datetime(today.year, 1, 1)

    def _calculate_ytd_return(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """
        Calculate YTD performance for a given ticker.

        Args:
            ticker: yfinance Ticker object

        Returns:
            Dictionary containing YTD performance data
        """
        try:
            # Get YTD start date
            ytd_start = self._get_ytd_start_date()

            # Get historical data for YTD period
            hist = ticker.history(start=ytd_start, end=datetime.now())

            if hist.empty:
                return {
                    "success": False,
                    "error": "No historical data available",
                    "ytd_return_pct": None,
                }

            # Get first and last closing prices
            first_close = hist["Close"].iloc[0]
            last_close = hist["Close"].iloc[-1]

            if first_close <= 0:
                return {
                    "success": False,
                    "error": "Invalid starting price",
                    "ytd_return_pct": None,
                }

            # Calculate YTD return
            ytd_return = (last_close - first_close) / first_close
            ytd_return_pct = round(ytd_return * 100, 4)

            return {
                "success": True,
                "ytd_return_pct": ytd_return_pct,
                "period": "YTD",
                "start_date": ytd_start.strftime("%Y-%m-%d"),
                "end_date": datetime.now().strftime("%Y-%m-%d"),
                "start_price": round(first_close, 4),
                "end_price": round(last_close, 4),
                "currency": ticker.info.get("currency", "USD"),
            }

        except Exception as e:
            logger.error(f"Error calculating YTD return: {str(e)}")
            return {"success": False, "error": str(e), "ytd_return_pct": None}

    def _get_index_info(self, ticker: yf.Ticker, config: IndexConfig) -> Dict[str, Any]:
        """
        Get comprehensive index information including YTD performance.

        Args:
            ticker: yfinance Ticker object
            config: Index configuration object

        Returns:
            Dictionary containing index performance data
        """
        try:
            # Calculate YTD performance
            ytd_data = self._calculate_ytd_return(ticker)

            # Get basic info
            info = ticker.info or {}

            # Combine data
            result: Dict[str, Any] = {
                "symbol": config.symbol,
                "name": config.name,
                "currency": config.currency,
                "description": config.description,
                "success": ytd_data["success"],
                "error": ytd_data.get("error"),
                "period": "YTD",
                "rate_of_return_pct": ytd_data.get("ytd_return_pct"),
                "start_date": ytd_data.get("start_date"),
                "end_date": ytd_data.get("end_date"),
                "start_price": ytd_data.get("start_price"),
                "end_price": ytd_data.get("end_price"),
                "current_price": info.get(
                    "regularMarketPrice", info.get("currentPrice")
                ),
                "market_change": info.get("regularMarketChange"),
                "market_change_pct": info.get("regularMarketChangePercent"),
                "source": "yfinance",
            }

            return result

        except Exception as e:
            logger.error(f"Error getting index info for {config.symbol}: {str(e)}")
            return {
                "symbol": config.symbol,
                "name": config.name,
                "currency": config.currency,
                "description": config.description,
                "success": False,
                "error": str(e),
                "rate_of_return_pct": None,
                "period": "YTD",
                "source": "yfinance",
            }

    def get_all_indices_performance(self) -> Dict[str, Dict[str, Any]]:
        """
        Get YTD performance for all configured indices.

        Returns:
            Dictionary with index keys and performance data as values
        """
        results = {}

        for index_key, config in self.indices.items():
            try:
                logger.info(f"Fetching performance for {config.symbol} ({config.name})")

                ticker = yf.Ticker(config.symbol)
                performance_data = self._get_index_info(ticker, config)

                if performance_data["success"]:
                    logger.info(
                        f"{config.name} YTD return: {performance_data['rate_of_return_pct']}%"
                    )
                else:
                    logger.warning(
                        f"Failed to fetch {config.name} performance: {performance_data.get('error')}"
                    )

                results[index_key] = performance_data

            except Exception as e:
                logger.error(f"Error processing {index_key}: {str(e)}")
                results[index_key] = {
                    "symbol": config.symbol,
                    "name": config.name,
                    "currency": config.currency,
                    "description": config.description,
                    "success": False,
                    "error": str(e),
                    "rate_of_return_pct": None,
                    "period": "YTD",
                    "source": "yfinance",
                }

        return results

    def get_index_performance(self, index_key: str) -> Dict[str, Any]:
        """
        Get YTD performance for a specific index.

        Args:
            index_key: Key of the index (e.g., 'SP500', 'NASDAQ')

        Returns:
            Dictionary containing index performance data
        """
        if index_key not in self.indices:
            return {
                "success": False,
                "error": f"Unknown index: {index_key}",
                "rate_of_return_pct": None,
            }

        config = self.indices[index_key]

        try:
            ticker = yf.Ticker(config.symbol)
            return self._get_index_info(ticker, config)

        except Exception as e:
            logger.error(f"Error getting performance for {index_key}: {str(e)}")
            return {
                "symbol": config.symbol,
                "name": config.name,
                "currency": config.currency,
                "description": config.description,
                "success": False,
                "error": str(e),
                "rate_of_return_pct": None,
                "period": "YTD",
                "source": "yfinance",
            }

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all index performances for easy comparison.

        Returns:
            Dictionary containing comparison data
        """
        all_data = self.get_all_indices_performance()

        summary = {
            "timestamp": datetime.now().isoformat(),
            "period": "YTD",
            "indices": {},
            "best_performer": None,
            "worst_performer": None,
            "successful_fetches": 0,
            "failed_fetches": 0,
        }

        valid_returns = []

        for index_key, data in all_data.items():
            summary["indices"][index_key] = {
                "name": data["name"],
                "rate_of_return_pct": data["rate_of_return_pct"],
                "success": data["success"],
                "error": data.get("error"),
            }

            if data["success"] and data["rate_of_return_pct"] is not None:
                summary["successful_fetches"] += 1
                valid_returns.append((index_key, data["rate_of_return_pct"]))
            else:
                summary["failed_fetches"] += 1

        # Find best and worst performers
        if valid_returns:
            valid_returns.sort(key=lambda x: x[1], reverse=True)
            summary["best_performer"] = {
                "index": valid_returns[0][0],
                "return_pct": valid_returns[0][1],
            }
            summary["worst_performer"] = {
                "index": valid_returns[-1][0],
                "return_pct": valid_returns[-1][1],
            }

        return summary


def main():
    """Test the index performance fetcher."""
    fetcher = IndexPerformanceFetcher()

    print("=== Index Performance Test ===")

    # Get all indices performance
    all_performance = fetcher.get_all_indices_performance()

    for index_key, data in all_performance.items():
        print(f"\n{data['name']} ({data['symbol']}):")
        if data["success"]:
            print(f"  YTD Return: {data['rate_of_return_pct']}%")
            print(f"  Start Price: {data['start_price']}")
            print(f"  End Price: {data['end_price']}")
        else:
            print(f"  Error: {data.get('error')}")

    # Get summary
    summary = fetcher.get_performance_summary()
    print(f"\n=== Summary ===")
    print(f"Successful fetches: {summary['successful_fetches']}")
    print(f"Failed fetches: {summary['failed_fetches']}")

    if summary["best_performer"]:
        print(
            f"Best performer: {summary['best_performer']['index']} ({summary['best_performer']['return_pct']}%)"
        )
    if summary["worst_performer"]:
        print(
            f"Worst performer: {summary['worst_performer']['index']} ({summary['worst_performer']['return_pct']}%)"
        )


if __name__ == "__main__":
    main()
