import logging
from datetime import datetime, timezone
from typing import Iterable

from .sources import (
    BinanceActivitySource,
    CryptoActivitySource,
    OKXActivitySource,
    WhiteBitActivitySource,
)
from .storage import PortfolioLedger


logger = logging.getLogger(__name__)


def build_activity_sources(brokers: Iterable, config: dict | None = None) -> list:
    config = config or {}
    sources = []
    for broker in brokers:
        class_name = broker.__class__.__name__
        if class_name == "BinanceClient":
            symbols = config.get("binance", {}).get("symbols", [])
            sources.append(BinanceActivitySource(broker, symbols=symbols))
        elif class_name in {"OKXClient", "OKXFiltered"}:
            sources.append(OKXActivitySource(broker))
        elif class_name == "WhiteBit":
            sources.append(WhiteBitActivitySource(broker))
    return sources


def sync_crypto_sources(
    ledger: PortfolioLedger,
    sources: Iterable[CryptoActivitySource],
    start_at: datetime,
    end_at: datetime,
    *,
    dry_run: bool = False,
) -> dict[str, dict]:
    state = ledger.load_import_state()
    results: dict[str, dict] = {}

    for source in sources:
        source_name = source.source_name
        source_state = state.get(source_name, {})
        events = []
        lending_events = []
        event_cursor = source_state.get("events", {})
        lending_cursor = source_state.get("lending", {})
        failures = {}

        try:
            events, event_cursor = source.fetch_events(
                start_at, end_at, source_state.get("events")
            )
        except Exception as error:
            failures["events"] = type(error).__name__
            logger.warning(
                "Crypto event sync failed for %s (%s)", source_name, type(error).__name__
            )

        try:
            lending_events, lending_cursor = source.fetch_lending_events(
                start_at, end_at, source_state.get("lending")
            )
        except Exception as error:
            failures["lending"] = type(error).__name__
            logger.warning(
                "Crypto lending sync failed for %s (%s)",
                source_name,
                type(error).__name__,
            )

        combined_events = list(events) + list(lending_events)
        successful_capabilities = 2 - len(failures)
        coverage_complete = (
            not failures
            and event_cursor.get("coverage") == "complete"
            and lending_cursor.get("coverage") == "complete"
        )
        if dry_run:
            imported_count = len(combined_events)
            duplicate_count = 0
        else:
            import_result = ledger.import_events(combined_events)
            imported_count = import_result.imported_count
            duplicate_count = import_result.duplicate_count
            now = datetime.now(timezone.utc).isoformat()
            next_state = {
                "events": event_cursor,
                "lending": lending_cursor,
                "coverage": "complete" if coverage_complete else "partial",
                "last_attempt_at": now,
                "coverage_start": start_at.isoformat(),
                "coverage_end": end_at.isoformat(),
            }
            if successful_capabilities:
                next_state["last_success_at"] = now
            elif source_state.get("last_success_at"):
                next_state["last_success_at"] = source_state["last_success_at"]
            if failures:
                next_state["errors"] = failures
            state[source_name] = next_state
            ledger.save_import_state(state)

        if failures and not successful_capabilities:
            status = "error"
        elif failures or not coverage_complete:
            status = "partial"
        else:
            status = "dry_run" if dry_run else "complete"
        results[source_name] = {
            "status": status,
            "fetched_count": len(combined_events),
            "imported_count": imported_count,
            "duplicate_count": duplicate_count,
        }
        if failures:
            results[source_name]["failed_capabilities"] = sorted(failures)
    return results
