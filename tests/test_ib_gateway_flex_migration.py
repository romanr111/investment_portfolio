"""Tests for IB Gateway + IB Flex migration.

Verifies portfolio item normalization, bond CUSIP→IBCID, account summary
shape, one-connection snapshot, socket-error message, TWR extraction,
polling, and token leak prevention.
"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.brokers.ib_flex_performance import (
    IBFlexPerformanceFetcher,
    extract_reference_code,
    extract_twr_from_activity_statement,
)
from src.brokers.ib_gateway_portfolio import (
    IBGatewayUnavailable,
    IBGatewayPortfolioLoader,
    _normalize_portfolio_item,
)


class TestGatewayPortfolioNormalization(unittest.TestCase):

    def test_gateway_portfolio_item_normalizes_current_ib_shape(self):
        contract = SimpleNamespace(
            localSymbol="AAPL",
            symbol="AAPL",
            conId=265598,
            secType="STK",
            currency="USD",
        )
        item = SimpleNamespace(
            contract=contract,
            marketValue=1234.56,
            position=10,
            averageCost=100.12,
            marketPrice=123.45,
            unrealizedPNL=233.3,
            realizedPNL=4.5,
        )

        self.assertEqual(
            _normalize_portfolio_item(item),
            {
                "contractDesc": "AAPL",
                "mktValue": 1234.56,
                "position": 10.0,
                "avgPrice": 100.12,
                "mktPrice": 123.45,
                "unrealizedPNL": 233.3,
                "realizedPNL": 4.5,
                "currency": "USD",
                "conId": 265598,
                "secType": "STK",
            },
        )

    def test_gateway_bond_contract_uses_ibcid_for_existing_categorizer(self):
        contract = SimpleNamespace(
            localSymbol="",
            symbol="912797LB9",
            conId=12345,
            secType="BOND",
            currency="USD",
        )
        item = SimpleNamespace(
            contract=contract,
            marketValue=999.0,
            position=1,
            averageCost=98.0,
            marketPrice=99.9,
            unrealizedPNL=1.9,
            realizedPNL=0,
        )

        self.assertEqual(
            _normalize_portfolio_item(item)["contractDesc"], "IBCID12345"
        )

    def test_gateway_account_summary_keeps_totalcashvalue_compatible_shape(self):
        values = [
            SimpleNamespace(
                tag="TotalCashValue",
                value="8358.33",
                currency="USD",
                account="DU123",
            ),
            SimpleNamespace(
                tag="NetLiquidation",
                value="111230.75",
                currency="USD",
                account="DU123",
            ),
        ]

        summary = IBGatewayPortfolioLoader._normalize_account_values(values)

        self.assertEqual(summary["totalcashvalue"]["amount"], 8358.33)
        self.assertEqual(summary["netliquidation"]["amount"], 111230.75)


class TestGatewaySnapshot(unittest.TestCase):

    def test_gateway_snapshot_fetches_summary_and_positions_from_one_connection(self):
        contract = SimpleNamespace(
            localSymbol="AAPL",
            symbol="AAPL",
            conId=265598,
            secType="STK",
            currency="USD",
        )
        portfolio_item = SimpleNamespace(
            contract=contract,
            marketValue=1234.56,
            position=10,
            averageCost=100.12,
            marketPrice=123.45,
            unrealizedPNL=233.3,
            realizedPNL=4.5,
        )

        class FakeIB:
            def accountValues(self):
                return [
                    SimpleNamespace(
                        tag="TotalCashValue",
                        value="8358.33",
                        currency="USD",
                        account="DU123",
                    )
                ]

            def portfolio(self):
                return [portfolio_item]

        class FakeConnection:
            def __enter__(self):
                return FakeIB()

            def __exit__(self, *_args):
                return False

        loader = IBGatewayPortfolioLoader()

        with patch.object(loader, "connection", lambda: FakeConnection()):
            summary, positions = loader.fetch_portfolio_snapshot()

        self.assertEqual(summary["totalcashvalue"]["amount"], 8358.33)
        self.assertEqual(positions[0]["contractDesc"], "AAPL")


class TestGatewaySocketError(unittest.TestCase):

    def test_gateway_socket_error_is_explicit(self):
        def raise_os_error(*_args, **_kwargs):
            raise OSError("closed")

        loader = IBGatewayPortfolioLoader(host="127.0.0.1", port=4001)

        with patch("socket.create_connection", side_effect=raise_os_error):
            try:
                loader.check_socket_available()
            except IBGatewayUnavailable as exc:
                message = str(exc)
            else:
                self.fail("Expected IBGatewayUnavailable")

        self.assertIn("IB Gateway API unavailable at 127.0.0.1:4001", message)
        self.assertIn("Client Portal Gateway is no longer supported", message)


class TestFlexPerformance(unittest.TestCase):


    def test_flex_change_in_nav_extracts_ytd_twr(self):
        xml_text = """
        <FlexQueryResponse>
          <FlexStatements>
            <FlexStatement accountId="DU123">
              <ChangeInNAV accountId="DU123" fromDate="2026-01-01" toDate="2026-05-06" twr="12.34567" />
            </FlexStatement>
          </FlexStatements>
        </FlexQueryResponse>
        """
        self.assertEqual(
            extract_twr_from_activity_statement(xml_text, "DU123"), 12.3457
        )

    def test_flex_fetcher_reports_missing_config_as_normalized_error(self):
        fetcher = IBFlexPerformanceFetcher(token="", query_id="", account_id="DU123")

        result = fetcher.fetch_ytd_twr()

        self.assertEqual(result["period"], "YTD")
        self.assertIsNone(result["rate_of_return_pct"])
        self.assertEqual(result["measure"], "TWR")
        self.assertEqual(result["source"], "ib_flex_activity_statement")
        self.assertIn("IB_FLEX_TOKEN", result["error"])

    def test_flex_http_error_does_not_leak_token(self):
        class Response:
            ok = False
            status_code = 403
            text = ""

        class Session:
            def get(self, *_args, **_kwargs):
                return Response()

        fetcher = IBFlexPerformanceFetcher(
            token="secret-token",
            query_id="query-id",
            account_id="DU123",
            session=Session(),
        )

        result = fetcher.fetch_ytd_twr()

        self.assertNotIn("secret-token", result["error"])
        self.assertNotIn("query-id", result["error"])
        self.assertIn("HTTP 403", result["error"])

    def test_flex_get_statement_polls_while_generation_is_in_progress(self):
        class Response:
            ok = True
            status_code = 200

            def __init__(self, text):
                self.text = text

        class Session:
            def __init__(self):
                self.calls = 0

            def get(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return Response(
                        """
                        <FlexStatementResponse>
                          <Status>Success</Status>
                          <ReferenceCode>ABC123</ReferenceCode>
                        </FlexStatementResponse>
                        """
                    )
                if self.calls == 2:
                    return Response(
                        """
                        <FlexStatementResponse>
                          <ErrorCode>1019</ErrorCode>
                          <ErrorMessage>Statement generation in progress. Please try again shortly.</ErrorMessage>
                        </FlexStatementResponse>
                        """
                    )
                return Response(
                    """
                    <FlexQueryResponse>
                      <FlexStatements>
                        <FlexStatement accountId="DU123">
                          <ChangeInNAV accountId="DU123" twr="4.25" />
                        </FlexStatement>
                      </FlexStatements>
                    </FlexQueryResponse>
                    """
                )

        fetcher = IBFlexPerformanceFetcher(
            token="token",
            query_id="query",
            account_id="DU123",
            session=Session(),
            poll_interval_seconds=0,
            max_polls=3,
        )

        with patch("time.sleep"):
            result = fetcher.fetch_ytd_twr()

        self.assertEqual(result["rate_of_return_pct"], 4.25)
        self.assertIsNone(result["error"])


if __name__ == "__main__":
    unittest.main()
