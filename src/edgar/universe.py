"""Snapshot-to-EDGAR position resolution and fund classification.

The equity universe comes from the saved ``combined_data`` snapshot
(``data.IB_DATA``) restricted to the equity buckets. ``EQUITY_CATEGORIES``
is a copied set mirroring ``UNPROFILED_EQUITY_CATEGORIES``
(analytics/holy_grail/concentration_v1.py:150): copied on purpose, this
package must not import analytics or data.

Individual-share filtering is by name-only resolution plus the multi-signal
fund classifier (ETF and commodity-trust shells resolve in the ticker map
the same way operating companies do, so resolution alone is not a filter).
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.edgar.edgar_client import TICKER_MAP_URL, resolve_user_agent

logger = logging.getLogger(__name__)

# Mirrors analytics/holy_grail/concentration_v1.py:150 (UNPROFILED_EQUITY_CATEGORIES);
# copied, never imported, to keep src/edgar self-contained.
EQUITY_CATEGORIES = frozenset({"Stocks", "China Stocks", "REIT"})
_EQUITY_CATEGORY_ORDER = ("Stocks", "China Stocks", "REIT")

TICKER_MAP_TTL_DAYS = 30
STATUS_MONITORED = "monitored"
STATUS_SKIPPED_UNRESOLVED = "skipped_unresolved"
STATUS_SKIPPED_FUND = "skipped_fund"
STATUS_EXCLUDED = "excluded_config"

_FUND_ENTITY_TYPES = frozenset({"other", "funds"})
_FUND_SIC_PREFIX = "6221"
# Fund-detection signal forms: deliberately wider than severity.PERIODIC_FORMS
# (an 8-K stream also indicates an operating filer); Risk Factors work stays
# periodic-only.
_FUND_SIGNAL_FORM_SET = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"})


@dataclass
class Position:
    ticker: str  # snapshot symbol as written in IB_DATA
    category: str
    market_value: float
    snapshot_as_of: str
    sec_ticker: str = ""
    cik: str = ""
    title: str = ""
    status: str = STATUS_SKIPPED_UNRESOLVED
    forced: bool = False  # came from force_include / force_exclude config


def normalize_symbol(symbol: str) -> str:
    """Upper-case; spaces and dots become dashes ("BRK B" -> "BRK-B")."""
    return (symbol or "").strip().upper().replace(" ", "-").replace(".", "-")


def load_snapshot_symbols(snapshot_path, min_market_value_usd=0.0) -> tuple:
    """Equity rows and the below-floor count from the saved snapshot.

    Returns (rows, value_filtered): rows carry the equity positions at or
    above the floor; value_filtered counts the rows skipped by it.
    """
    payload = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    ib_data = (payload.get("data") or {}).get("IB_DATA") or {}
    as_of = payload.get("as_of_date", "")
    if not isinstance(ib_data, dict):
        raise ValueError(f"snapshot {snapshot_path} carries no data.IB_DATA object")
    rows = []
    value_filtered = 0
    for category in _EQUITY_CATEGORY_ORDER:
        category_positions = ib_data.get(category) or {}
        if not isinstance(category_positions, dict):
            continue
        for ticker, value in category_positions.items():
            try:
                market_value = float(value)
            except (TypeError, ValueError):
                logger.warning("Ignoring unparseable value for %s in %s", ticker, category)
                continue
            if market_value < min_market_value_usd:
                value_filtered += 1
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "category": category,
                    "market_value": market_value,
                    "snapshot_as_of": as_of,
                }
            )
    return rows, value_filtered


def build_cik_map(payload: dict) -> dict:
    """Normalize the company_tickers.json map: normalized ticker -> {cik, ticker, title}."""
    if not isinstance(payload, dict):
        raise ValueError("company tickers payload is not a JSON object")
    cik_map = {}
    for entry in payload.values():
        try:
            cik_str = int(entry.get("cik_str"))
        except (AttributeError, TypeError, ValueError):
            continue
        ticker = normalize_symbol(str(entry.get("ticker", "")))
        if not ticker or ticker in cik_map:
            continue
        cik_map[ticker] = {
            "cik": f"{cik_str:010d}",
            "ticker": ticker,
            "title": str(entry.get("title", "")),
        }
    return cik_map


def load_cik_map(session, cache_path, ua=None, ttl_days=TICKER_MAP_TTL_DAYS, now=None):
    """Load the ticker-to-CIK map from cache or network; returns (map, source).

    source is "fresh" (fetched now), "cache" (within TTL) or "stale" (network
    failed but an older cache still exists). With no cache and a failed fetch
    the underlying error propagates to the caller.
    """
    cache_path = Path(cache_path)
    if now is None:
        now = datetime.now(timezone.utc)
    if cache_path.exists():
        try:
            age_days = (now.timestamp() - cache_path.stat().st_mtime) / 86400.0
            if age_days <= ttl_days:
                return json.loads(cache_path.read_text(encoding="utf-8")), "cache"
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable CIK map cache %s: %s", cache_path, exc)

    user_agent = resolve_user_agent(ua)
    try:
        response = session.get(
            TICKER_MAP_URL,
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=30,
        )
        response.raise_for_status()
        cik_map = build_cik_map(response.json())
    except (requests.RequestException, ValueError, AttributeError) as exc:
        if cache_path.exists():
            try:
                logger.warning("CIK map fetch failed (%s); using stale cache", exc)
                return json.loads(cache_path.read_text(encoding="utf-8")), "stale"
            except (OSError, ValueError):
                pass
        raise
    _save_cache(cache_path, cik_map)
    return cik_map, "fresh"


def _save_cache(cache_path: Path, cik_map: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        temp_path = cache_path.with_name(cache_path.name + ".tmp")
        temp_path.write_text(json.dumps(cik_map, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(cache_path)
    except OSError:  # cache is best-effort; resolution continues with the live map
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def _string_keys(mapping) -> dict:
    """Normalize config include/exclude keys: exact snapshot name and normalized form."""
    normalized = {}
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            normalized[str(key)] = value if isinstance(value, dict) else {}
            normalized[normalize_symbol(str(key))] = value if isinstance(value, dict) else {}
    return normalized


def resolve_positions(rows, cik_map, config) -> list:
    """Resolve snapshot rows into Position records with static statuses.

    Statuses set here: monitored, skipped_unresolved, excluded_config. The
    fund status is applied later by the caller, per-CIK, using
    classify_fund() on the submissions JSON.
    """
    force_include = _string_keys(config.get("force_include") or {})
    force_exclude = _string_keys(config.get("force_exclude") or {})
    positions = []
    for row in rows:
        ticker = row["ticker"]
        position = Position(
            ticker=ticker,
            category=row["category"],
            market_value=row["market_value"],
            snapshot_as_of=row.get("snapshot_as_of", ""),
        )
        if ticker in force_exclude or normalize_symbol(ticker) in force_exclude:
            position.status = STATUS_EXCLUDED
            position.forced = True
            positions.append(position)
            continue
        forced = force_include.get(ticker) or force_include.get(normalize_symbol(ticker))
        resolved = _resolve_one(position, cik_map, forced)
        positions.append(resolved)
    return positions


def _resolve_one(position: Position, cik_map, forced) -> Position:
    if forced and forced.get("via"):
        entry = cik_map.get(normalize_symbol(str(forced.get("via"))))
        if entry:
            position.cik = entry["cik"]
            position.sec_ticker = entry["ticker"]
            position.title = entry["title"]
            position.status = STATUS_MONITORED
            position.forced = True
            return position
    entry = cik_map.get(normalize_symbol(position.ticker))
    if entry:
        position.cik = entry["cik"]
        position.sec_ticker = entry["ticker"]
        position.title = entry["title"]
        position.status = STATUS_MONITORED
        return position
    if forced:
        logger.warning(
            "force_include for %s has no resolvable %r; kept unresolved",
            position.ticker,
            forced.get("via"),
        )
    position.status = STATUS_SKIPPED_UNRESOLVED
    return position


def classify_fund(submissions: dict) -> bool:
    """Multi-signal fund detection from a submissions JSON.

    True when entityType is a fund shell ('other', 'funds'), the SIC code is
    a commodity-trust code (6221, verified for an iShares-style trust
    ticker), or the recent window carries no 10-K/10-Q/8-K at all
    (NPORT-P-only filers: broad index ETF shells with no periodic forms).
    """
    entity_type = str(submissions.get("entityType", "")).strip().lower()
    sic = str(submissions.get("sic", "")).strip()
    forms = set(
        ((submissions.get("filings") or {}).get("recent") or {}).get("form") or []
    )
    has_fund_signal_forms = bool(forms & _FUND_SIGNAL_FORM_SET)
    return (
        entity_type in _FUND_ENTITY_TYPES
        or sic.startswith(_FUND_SIC_PREFIX)
        or not has_fund_signal_forms
    )
