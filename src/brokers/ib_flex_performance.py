import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

import requests

from src.brokers.ib_models import IBPerformanceYTD

logger = logging.getLogger(__name__)

FLEX_SEND_REQUEST_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
)
FLEX_GET_STATEMENT_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
)
FLEX_VERSION = "3"
FLEX_HEADERS = {"User-Agent": "Python/investment_portfolio"}


class IBFlexError(RuntimeError):
    pass


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _text_for(root: ET.Element, name: str) -> Optional[str]:
    for element in root.iter():
        if _strip_namespace(element.tag).lower() == name.lower():
            return element.text
    return None


def parse_flex_error(root: ET.Element) -> Optional[str]:
    error_code = _text_for(root, "ErrorCode")
    error_message = _text_for(root, "ErrorMessage")
    if error_code or error_message:
        return ": ".join(part for part in [error_code, error_message] if part)
    return None


def _raise_for_status_without_query(response: requests.Response, action: str) -> None:
    if response.ok:
        return
    raise IBFlexError(f"Flex {action} HTTP {response.status_code}")


def extract_reference_code(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    error = parse_flex_error(root)
    if error:
        raise IBFlexError(error)

    status = _text_for(root, "Status")
    if status and status.lower() != "success":
        raise IBFlexError(f"Flex request status={status}")

    reference_code = _text_for(root, "ReferenceCode")
    if not reference_code:
        raise IBFlexError("Flex SendRequest did not return ReferenceCode")
    return reference_code


def extract_twr_from_activity_statement(
    xml_text: str, account_id: Optional[str] = None
) -> float:
    root = ET.fromstring(xml_text)
    error = parse_flex_error(root)
    if error:
        raise IBFlexError(error)

    candidates = []
    for element in root.iter():
        tag = _strip_namespace(element.tag).lower()
        if tag not in {"changeinnav", "changeinnavs"}:
            continue
        attrs = {str(k).lower(): v for k, v in element.attrib.items()}
        if account_id and attrs.get("accountid") not in {None, "", account_id}:
            continue
        for key in ("twr", "timeweightedreturn", "timeweightedrateofreturn"):
            value = _to_float(attrs.get(key))
            if value is not None:
                candidates.append(value)

    if candidates:
        return round(candidates[-1], 4)

    for element in root.iter():
        attrs = {str(k).lower(): v for k, v in element.attrib.items()}
        if account_id and attrs.get("accountid") not in {None, "", account_id}:
            continue
        for key, value in attrs.items():
            if "twr" in key or "timeweighted" in key:
                parsed = _to_float(value)
                if parsed is not None:
                    return round(parsed, 4)

    raise IBFlexError("Flex Activity Statement did not include YTD TWR")


class IBFlexPerformanceFetcher:
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
            else os.getenv("IB_FLEX_QUERY_ID_YTD_PERFORMANCE")
        )
        self.account_id = (
            account_id if account_id is not None else os.getenv("IB_ACCOUNT_ID")
        )
        self.poll_interval_seconds = poll_interval_seconds
        self.max_polls = max_polls
        self.session = session or requests.Session()

    def fetch_ytd_twr(self) -> Dict[str, Any]:
        try:
            if not self.token:
                raise IBFlexError("IB_FLEX_TOKEN is not configured")
            if not self.query_id:
                raise IBFlexError("IB_FLEX_QUERY_ID_YTD_PERFORMANCE is not configured")

            reference_code = self._send_request()
            xml_text = self._download_statement(reference_code)
            twr = extract_twr_from_activity_statement(xml_text, self.account_id)
            return IBPerformanceYTD(rate_of_return_pct=twr).as_dict()
        except Exception as exc:
            error = f"YTD performance unavailable from IBKR Flex: {exc}"
            logger.warning(error)
            return IBPerformanceYTD(error=error).as_dict()

    def _send_request(self) -> str:
        response = self.session.get(
            FLEX_SEND_REQUEST_URL,
            params={"t": self.token, "q": self.query_id, "v": FLEX_VERSION},
            headers=FLEX_HEADERS,
            timeout=30,
        )
        _raise_for_status_without_query(response, "SendRequest")
        return extract_reference_code(response.text)

    def _download_statement(self, reference_code: str) -> str:
        last_error = None
        for attempt in range(self.max_polls):
            response = self.session.get(
                FLEX_GET_STATEMENT_URL,
                params={"t": self.token, "q": reference_code, "v": FLEX_VERSION},
                headers=FLEX_HEADERS,
                timeout=30,
            )
            _raise_for_status_without_query(response, "GetStatement")
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
                raise IBFlexError(error)
            if attempt < self.max_polls - 1:
                time.sleep(self.poll_interval_seconds)

        raise IBFlexError(last_error or "Flex statement was not ready")
