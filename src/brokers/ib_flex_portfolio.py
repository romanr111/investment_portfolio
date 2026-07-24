"""IB Flex Web Service fetcher for portfolio snapshot query (Open Positions + Trades).

Shared component reusable by both the portfolio sync pipeline and the
quarterly report generator. Mirrors the request/ polling flow of
``src.brokers.ib_flex_performance`` but targets a different Flex Query
(default env var ``IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT``) and returns the
raw XML text instead of a parsed TWR metric.
"""

import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FLEX_SEND_REQUEST_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
)
FLEX_GET_STATEMENT_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
)
FLEX_VERSION = "3"
FLEX_HEADERS = {"User-Agent": "Python/investment_portfolio"}


class IBFlexPortfolioError(RuntimeError):
    pass


def _text_for(root: ET.Element, name: str) -> Optional[str]:
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag == name.lower():
            return element.text
    return None


def parse_flex_error(root: ET.Element) -> Optional[str]:
    error_code = _text_for(root, "ErrorCode")
    error_message = _text_for(root, "ErrorMessage")
    if error_code or error_message:
        return ": ".join(part for part in [error_code, error_message] if part)
    return None


def extract_reference_code(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    error = parse_flex_error(root)
    if error:
        raise IBFlexPortfolioError(error)

    status = _text_for(root, "Status")
    if status and status.lower() != "success":
        raise IBFlexPortfolioError(f"Flex request status={status}")

    reference_code = _text_for(root, "ReferenceCode")
    if not reference_code:
        raise IBFlexPortfolioError("Flex SendRequest did not return ReferenceCode")
    return reference_code


def extract_to_date(xml_text: str) -> Optional[str]:
    """Return the ``toDate`` attribute of the first FlexStatement (YYYYMMDD)."""
    root = ET.fromstring(xml_text)
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "FlexStatement" and "toDate" in element.attrib:
            return element.attrib["toDate"]
    return None


class IBFlexPortfolioFetcher:
    """Fetches a portfolio snapshot or trades XML from the IB Flex Web Service.

    For position snapshots (default): ``IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT``
    must include Open Positions + Trades sections with ``Period = Last Business Day``.

    For quarterly trades: pass ``query_id`` explicitly or set
    ``IB_FLEX_QUERY_ID_QUARTERLY_TRADES``; the query must include Trades
    section with ``Period = Last Quarter``.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        query_id: Optional[str] = None,
        account_id: Optional[str] = None,
        poll_interval_seconds: float = 3.0,
        max_polls: int = 10,
        session: Optional[requests.Session] = None,
    ):
        self.token = token if token is not None else os.getenv("IB_FLEX_TOKEN")
        self.query_id = (
            query_id
            if query_id is not None
            else os.getenv("IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT")
        )
        self.account_id = (
            account_id if account_id is not None else os.getenv("IB_ACCOUNT_ID")
        )
        self.poll_interval_seconds = poll_interval_seconds
        self.max_polls = max_polls
        self.session = session or requests.Session()

    def fetch_snapshot_xml(self) -> str:
        """Request and download the portfolio snapshot XML text."""
        if not self.token:
            raise IBFlexPortfolioError("IB_FLEX_TOKEN is not configured")
        if not self.query_id:
            raise IBFlexPortfolioError(
                "IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT is not configured"
            )

        reference_code = self._send_request()
        return self._download_statement(reference_code)

    def fetch_and_save(
        self,
        snapshots_dir: str = "data/ib_flex_snapshots",
        filename_prefix: str = "stocks_count_trades",
    ) -> Path:
        """Fetch the snapshot XML and persist it under ``snapshots_dir``.

        File name: ``<filename_prefix>_<toDate>_<timestamp>.xml``.
        Returns the path to the saved file.
        """
        xml_text = self.fetch_snapshot_xml()
        to_date = extract_to_date(xml_text) or datetime.now(
            timezone.utc
        ).strftime("%Y%m%d")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        out_dir = Path(snapshots_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"{filename_prefix}_{to_date}_{timestamp}.xml"
        file_path.write_text(xml_text, encoding="utf-8")
        logger.info("Saved IB Flex portfolio snapshot to %s", file_path)
        return file_path

    def _send_request(self) -> str:
        response = self.session.get(
            FLEX_SEND_REQUEST_URL,
            params={"t": self.token, "q": self.query_id, "v": FLEX_VERSION},
            headers=FLEX_HEADERS,
            timeout=30,
        )
        if not response.ok:
            raise IBFlexPortfolioError(
                f"Flex SendRequest HTTP {response.status_code}"
            )
        return extract_reference_code(response.text)

    def _download_statement(self, reference_code: str) -> str:
        last_error: Optional[str] = None
        for attempt in range(self.max_polls):
            response = self.session.get(
                FLEX_GET_STATEMENT_URL,
                params={"t": self.token, "q": reference_code, "v": FLEX_VERSION},
                headers=FLEX_HEADERS,
                timeout=30,
            )
            if not response.ok:
                raise IBFlexPortfolioError(
                    f"Flex GetStatement HTTP {response.status_code}"
                )
            try:
                root = ET.fromstring(response.text)
            except ET.ParseError:
                return response.text

            error = parse_flex_error(root)
            if not error:
                return response.text
            last_error = error
            if (
                "not available" not in error.lower()
                and "being generated" not in error.lower()
                and "in progress" not in error.lower()
            ):
                raise IBFlexPortfolioError(error)
            if attempt < self.max_polls - 1:
                time.sleep(self.poll_interval_seconds)

        raise IBFlexPortfolioError(last_error or "Flex statement was not ready")