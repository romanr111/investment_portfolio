"""EDGAR HTTP client: UA contract, pacing, retries and block detection.

SEC blocks undeclared automated clients (verified live 2026-11-07: an
undeclared User-Agent gets 403 HTML, a burst page returns HTML with a
200-like status). Only submissions bodies are validated: a non-JSON 200
from ``fetch_submissions`` is classified as ``EdgarBlocked``
(submissions must be JSON). Documents are legitimately HTML and their
bodies are never validated: a steady 403/429 still raises
``EdgarBlocked`` after retries inside ``_get``, while a 200-status HTML
block page for a document passes through and consumers degrade via a
``risk_factors.scan_item_codes`` miss. The block is a stop: the identity
is reported, never rotated for a workaround.

The honest default identity is a fallback for OSS checkouts and offline
tests without ``SEC_USER_AGENT``; live runs are expected to configure a
real contact in the env file (owner action, documented in data/README.md).
"""
import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

SEC_DEFAULT_UA = (
    "investment-portfolio-edgar-watch/1.0 "
    "(github.com/romanr111/investment_portfolio; contact: repo owner)"
)
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

RETRY_STATUSES = frozenset({429, 403, 500, 502, 503, 504})
DEFAULT_MIN_REQUEST_INTERVAL = 0.4
DEFAULT_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 30


class EdgarBlocked(Exception):
    """SEC returned a block or rate-limit response after retries; the run stops."""


class EdgarRequestError(Exception):
    """EDGAR request failed after retries for a non-block reason."""


def resolve_user_agent(explicit=None) -> str:
    """Explicit value wins, then ``SEC_USER_AGENT``, then the honest default."""
    if explicit:
        return explicit
    from_env = os.environ.get("SEC_USER_AGENT", "").strip()
    return from_env or SEC_DEFAULT_UA


class EdgarClient:
    def __init__(
        self,
        session=None,
        ua=None,
        min_request_interval=DEFAULT_MIN_REQUEST_INTERVAL,
        retries=DEFAULT_RETRIES,
        retry_backoff_seconds=DEFAULT_RETRY_BACKOFF_SECONDS,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    ):
        self.session = session if session is not None else requests.Session()
        self.ua = resolve_user_agent(ua)
        self.min_request_interval = max(0.0, float(min_request_interval))
        self.retries = max(0, int(retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.timeout = timeout
        self._last_request_ts = None

    def _headers(self) -> dict:
        return {"User-Agent": self.ua, "Accept-Encoding": "gzip, deflate"}

    def _pace(self) -> None:
        if self._last_request_ts is None or self.min_request_interval <= 0:
            self._last_request_ts = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_ts
        remaining = self.min_request_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_ts = time.monotonic()

    def _get(self, url):
        """GET with pacing and retries; returns (status, body_text)."""
        attempts = self.retries + 1
        status = None
        body = ""
        for attempt in range(attempts):
            self._pace()
            try:
                response = self.session.get(url, headers=self._headers(), timeout=self.timeout)
            except requests.RequestException as exc:
                raise EdgarRequestError(f"network error fetching {url}: {exc}") from exc
            status = response.status_code
            body = response.text
            if status == 200 or status == 404 or status not in RETRY_STATUSES:
                return status, body
            if attempt + 1 < attempts:
                logger.warning(
                    "EDGAR returned %s for %s (attempt %s/%s); retrying",
                    status,
                    url,
                    attempt + 1,
                    attempts,
                )
                time.sleep(self.retry_backoff_seconds * (attempt + 1))
        if status in (403, 429):
            raise EdgarBlocked(
                f"SEC returned {status} after {attempts} attempts for {url}; "
                "stop and report, never rotate the identity"
            )
        raise EdgarRequestError(f"EDGAR returned {status} after {attempts} attempts for {url}")

    def fetch_submissions(self, cik10: str) -> dict:
        """Fetch and parse a CIK's submissions JSON; HTML block pages raise EdgarBlocked."""
        status, body = self._get(SUBMISSIONS_URL.format(cik=cik10))
        if status != 200:
            raise EdgarRequestError(f"submissions {cik10}: HTTP {status}")
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise EdgarBlocked(
                f"non-JSON response for submissions {cik10} "
                "(SEC block or rate-limit page): "
                + str(exc)
            ) from exc
        if not isinstance(payload, dict):
            raise EdgarBlocked(f"unexpected submissions payload for {cik10}")
        return payload

    def fetch_document(self, cik10: str, nodash: str, primary_document: str):
        """Fetch one filing primary document; returns (status, body_text).

        The body is not validated (documents are legitimately HTML): a
        steady 403/429 raises ``EdgarBlocked`` after retries, but a burst
        page served as 200 HTML passes through; consumers degrade via
        ``risk_factors.scan_item_codes``.
        """
        url = f"{ARCHIVES_BASE}/{cik10}/{nodash}/{primary_document}"
        return self._get(url)

    def filing_url(self, cik10: str, accession_dashes: str) -> str:
        nodash = accession_dashes.replace("-", "")
        return f"{ARCHIVES_BASE}/{cik10}/{nodash}/{accession_dashes}-index.htm"
