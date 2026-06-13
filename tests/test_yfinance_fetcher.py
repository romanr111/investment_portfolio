import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.brokers.data_fetchers.yfinance_fetcher import YFinanceFetcher


class YFinanceFetcherTests(unittest.TestCase):
    def _mock_ticker(self, symbol: str):
        ticker = MagicMock()
        ticker.ticker = symbol
        ticker.info = {}
        ticker.dividends = pd.Series(dtype=float)
        return ticker

    @patch("src.brokers.data_fetchers.yfinance_fetcher.forward_dividend")
    @patch("src.brokers.data_fetchers.yfinance_fetcher.yf.Ticker")
    def test_get_dividend_data_uses_forward_dividend_once_for_generic_symbol(
        self, mock_ticker_cls, mock_forward_dividend
    ) -> None:
        mock_ticker_cls.return_value = self._mock_ticker("PDD")
        mock_forward_dividend.return_value = (0.0, 0.0)

        fetcher = YFinanceFetcher()
        data = fetcher.get_dividend_data("PDD")

        self.assertEqual(mock_forward_dividend.call_count, 1)
        self.assertEqual(data["PDD"]["dividend_yield"], 0.0)
        self.assertEqual(data["PDD"]["dividend"], 0.0)

    @patch("src.brokers.data_fetchers.yfinance_fetcher.forward_dividend")
    @patch("src.brokers.data_fetchers.yfinance_fetcher.yf.Ticker")
    def test_get_dividend_data_uses_baba_forward_dividend_once_for_baba(
        self, mock_ticker_cls, mock_forward_dividend
    ) -> None:
        mock_ticker_cls.return_value = self._mock_ticker("BABA")
        mock_forward_dividend.return_value = (0.0094, 1.03)

        fetcher = YFinanceFetcher()
        data = fetcher.get_dividend_data("BABA")

        self.assertEqual(mock_forward_dividend.call_count, 1)
        mock_forward_dividend.assert_called_once_with("BABA")
        self.assertAlmostEqual(data["BABA"]["dividend_yield"], 0.0094)
        self.assertAlmostEqual(data["BABA"]["dividend"], 1.03)


if __name__ == "__main__":
    unittest.main()
