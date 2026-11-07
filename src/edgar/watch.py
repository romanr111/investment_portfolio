"""EDGAR watch CLI: resolve equity positions, poll submissions, alert.

One pass per invocation (launchd owns the cadence). Phase order: resolve
universe -> per-CIK submissions -> new accessions and events -> document
fetches (empty-item 8-K/A re-scan plus Risk Factors on the latest periodic
filing) -> append alerts.jsonl -> commit state -> send digest -> healthcheck
ping. Committing state before the send means a Telegram outage never turns
into duplicate alerts on the next run.

Partial failures commit state only for the CIKs whose submissions were
processed and exit 2; a steady SEC block aborts before the state commit
(no partial idempotency point, no sends) and exits 1.

Exit codes: 0 ok, 1 fatal, 2 partial, 3 busy.
"""
import argparse
import copy
import fcntl
import json
import logging
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.portfolio_sync import _load_local_env_file
from src.edgar import digest as digest_module
from src.edgar import risk_factors
from src.edgar import severity
from src.edgar import state as state_store
from src.edgar import telegram
from src.edgar import universe
from src.edgar.edgar_client import EdgarBlocked, EdgarClient, EdgarRequestError

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = PROJECT_ROOT / "data" / "snapshots" / "combined_data_latest.json"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "edgar"

STATE_FILE_NAME = "state.json"
ALERTS_FILE_NAME = "alerts.jsonl"
LOCK_FILE_NAME = "watch.lock"
CIK_CACHE_NAME = "cik_map.json"
CONFIG_FILE_NAME = "config.json"
FILINGS_DIR_NAME = "filings"
RF_CHECK_DIR_NAME = "rf_check"

HEALTHCHECK_TIMEOUT_S = 5

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_PARTIAL = 2
EXIT_BUSY = 3

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="src.edgar.watch",
        description="EDGAR filing watch for individual equity positions.",
    )
    parser.add_argument(
        "--dry-alert",
        action="store_true",
        help="print the digest to stdout without Telegram or healthcheck (state still commits)",
    )
    parser.add_argument(
        "--limit-tickers", type=int, default=None, metavar="N",
        help="process only the N largest monitored positions",
    )
    parser.add_argument(
        "--backfill-days", type=int, default=None, metavar="N",
        help="first-contact anti-flood window override (default 7)",
    )
    parser.add_argument(
        "--extract-rf", metavar="SYMBOL", default=None,
        help="offline-style Risk Factors check: latest vs previous periodic filing; touches no state",
    )
    parser.add_argument(
        "--snapshot", default=str(DEFAULT_SNAPSHOT), metavar="PATH",
        help="combined_data snapshot (default data/snapshots/combined_data_latest.json)",
    )
    parser.add_argument(
        "--data-dir", default=None, metavar="PATH",
        help="EDGAR data directory (default data/edgar)",
    )
    parser.add_argument(
        "--healthcheck-url", default="", metavar="URL",
        help="healthcheck ping URL (otherwise HEALTHCHECK_EDGAR_URL)",
    )
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    return parser.parse_args(argv)


def run(argv=None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format=_LOG_FORMAT
    )
    _load_local_env_file()
    if args.extract_rf:
        return _run_extract_rf(args, _resolve_data_dir(args.data_dir))

    data_dir = _resolve_data_dir(args.data_dir)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("cannot create data dir %s: %s", data_dir, exc)
        return EXIT_FATAL
    lock_handle = _acquire_lock(data_dir)
    if lock_handle is None:
        print(
            f"edgar-watch: another run holds {data_dir / LOCK_FILE_NAME}",
            file=sys.stderr,
        )
        return EXIT_BUSY
    try:
        return _run_locked(args, data_dir)
    finally:
        # Closing the descriptor releases the advisory lock.
        lock_handle.close()


def main() -> int:
    return run()


def _resolve_data_dir(raw) -> Path:
    if not raw:
        return DEFAULT_DATA_DIR
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _acquire_lock(data_dir: Path):
    """Non-blocking flock; None means another run holds the watch."""
    lock_path = data_dir / LOCK_FILE_NAME
    handle = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _load_config(config_path: Path) -> dict:
    config = {
        "version": 1,
        "force_include": {},
        "force_exclude": {},
        "min_market_value_usd": 0,
        "max_backfill_days": 7,
        "digest": {},
    }
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return config
    except (OSError, ValueError) as exc:
        logger.warning("ignoring unreadable EDGAR config %s: %s", config_path, exc)
        return config
    if not isinstance(payload, dict):
        logger.warning("ignoring unexpected EDGAR config content in %s", config_path)
        return config
    for key in ("force_include", "force_exclude", "min_market_value_usd", "max_backfill_days"):
        if payload.get(key) is not None:
            config[key] = payload[key]
    digest_config = payload.get("digest") or {}
    if isinstance(digest_config, dict):
        config["digest"].update(digest_config)
    return config


def _run_locked(args, data_dir: Path) -> int:
    config_path = data_dir / CONFIG_FILE_NAME
    config = _load_config(config_path)
    state_path = data_dir / STATE_FILE_NAME
    alerts_path = data_dir / ALERTS_FILE_NAME
    cik_cache = data_dir / CIK_CACHE_NAME
    filings_dir = data_dir / FILINGS_DIR_NAME
    state = state_store.load(state_path)
    run_state = copy.deepcopy(state)
    run_state.setdefault("ciks", {})
    run_state.setdefault("universe", {})

    session = requests.Session()
    client = EdgarClient(session=session)
    try:
        min_value = float(config.get("min_market_value_usd") or 0)
    except (TypeError, ValueError) as exc:
        logger.error(
            "invalid min_market_value_usd in config %s: %s", config_path, exc
        )
        return EXIT_FATAL
    try:
        rows, value_filtered = universe.load_snapshot_symbols(
            Path(args.snapshot), min_value
        )
    except (OSError, ValueError) as exc:
        logger.error("cannot load snapshot %s: %s", args.snapshot, exc)
        return EXIT_FATAL
    if not rows:
        logger.error(
            "snapshot %s carries no equity positions in %s",
            args.snapshot,
            sorted(universe.EQUITY_CATEGORIES),
        )
        return EXIT_FATAL
    try:
        cik_map, _source = universe.load_cik_map(
            session, cik_cache, ua=os.environ.get("SEC_USER_AGENT")
        )
    except (requests.RequestException, ValueError) as exc:
        logger.error("cannot load CIK map (no usable cache): %s", exc)
        return EXIT_FATAL

    positions = universe.resolve_positions(rows, cik_map, config)
    monitored = [p for p in positions if p.status == universe.STATUS_MONITORED]
    monitored.sort(key=_value_key)
    process_list = monitored
    if args.limit_tickers is not None:
        process_list = monitored[: max(0, int(args.limit_tickers))]
    skipped = {
        "unresolved": [p.ticker for p in positions if p.status == universe.STATUS_SKIPPED_UNRESOLVED],
        "fund": [],
        "excluded": [p.ticker for p in positions if p.status == universe.STATUS_EXCLUDED],
        "value_filtered": value_filtered,
        "hidden_by_limit": max(0, len(monitored) - len(process_list)),
    }

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    backfill_days = config.get("max_backfill_days", 7)
    if args.backfill_days is not None:
        backfill_days = args.backfill_days

    results, alert_rows, failures, blocked, new_total = _per_cik_pass(
        client, process_list, run_state, skipped, now, ts, backfill_days, filings_dir
    )

    if blocked:
        # Abort before the state commit: no partial idempotency point, no sends.
        digest_text = digest_module.build_digest(
            results,
            skipped,
            _digest_ctx(ts, rows, monitored, process_list, new_total, failures, config),
        )
        print(digest_text)
        sys.stdout.flush()
        return EXIT_FATAL

    will_send = (
        not args.dry_alert
        and bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
        and bool(os.environ.get("TELEGRAM_CHAT_ID"))
    )
    for row in alert_rows:
        row["digest_sent"] = will_send
    _append_alerts(alerts_path, alert_rows)

    run_state["updated_at_utc"] = ts
    run_state["last_run_utc"] = ts
    run_state["run_count"] = int(run_state.get("run_count", 0)) + 1
    for position in positions:
        run_state["universe"][position.ticker] = {
            "cik": position.cik,
            "sec_ticker": position.sec_ticker,
            "title": position.title,
            "category": position.category,
            "status": position.status,
            "resolved_at_utc": ts,
            "snapshot_as_of": position.snapshot_as_of,
        }
    try:
        state_store.save(state_path, run_state)
    except OSError as exc:
        # Alerts were appended (plan order); without the state commit the
        # next run re-alerts the same filings, which stays correct.
        logger.error("cannot save state %s: %s", state_path, exc)
        return EXIT_FATAL
    digest_text = digest_module.build_digest(
        results,
        skipped,
        _digest_ctx(ts, rows, monitored, process_list, new_total, failures, config),
    )
    exit_code = EXIT_PARTIAL if failures else EXIT_OK
    if args.dry_alert:
        print(digest_text)
        sys.stdout.flush()
        return exit_code

    if will_send:
        ok, detail = telegram.send(
            session,
            os.environ.get("TELEGRAM_BOT_TOKEN"),
            os.environ.get("TELEGRAM_CHAT_ID"),
            digest_text,
        )
        if ok:
            logger.info("Telegram digest sent (%s)", detail)
        else:
            logger.warning("Telegram digest not delivered (%s)", detail)
            # There is no resend: keep the full digest in the launchd log.
            print(digest_text)
            sys.stdout.flush()
    else:
        logger.info("telegram not configured; digest printed to stdout")
        print(digest_text)
        sys.stdout.flush()

    _ping_healthcheck(args.healthcheck_url, exit_code == EXIT_OK)
    return exit_code


def _per_cik_pass(client, process_list, run_state, skipped, now, ts, backfill_days, filings_dir):
    """Collect submissions and events for every monitored CIK.

    Returns (results, alert_rows, failures, blocked, new_total); run_state
    and the fund entries of skipped are updated in place.
    """
    results = []
    alert_rows = []
    failures = []
    blocked = False
    new_total = 0

    for position in process_list:
        entry = {
            "ticker": position.ticker,
            "category": position.category,
            "cik": position.cik,
            "status": position.status,
            "events": [],
            "rf": [],
            "error": None,
        }
        record = dict(run_state["ciks"].get(position.cik) or _default_record(position))
        try:
            submissions = client.fetch_submissions(position.cik)
        except EdgarBlocked as exc:
            blocked = True
            entry["error"] = f"BLOCKED: {digest_module.one_line(exc)}"
            results.append(entry)
            failures.append({"ticker": position.ticker, "error": f"BLOCKED: {digest_module.one_line(exc)}"})
            break
        except (EdgarRequestError, requests.RequestException) as exc:
            entry["error"] = digest_module.one_line(exc)
            results.append(entry)
            failures.append({"ticker": position.ticker, "error": digest_module.one_line(exc)})
            continue

        if not position.forced and universe.classify_fund(submissions):
            position.status = universe.STATUS_SKIPPED_FUND
            skipped["fund"].append(position.ticker)
            continue

        new_filings, updated_record = state_store.new_accessions(
            submissions, record, max_backfill_days=backfill_days, now=now
        )
        new_total += len(new_filings)
        entry["events"].extend(
            _new_filings_flow(
                new_filings, position, client, entries_sink=alert_rows, ts=ts
            )
        )
        entry["rf"].extend(
            _rf_flow(client, position, submissions, updated_record, filings_dir)
        )
        updated_record["last_success_utc"] = ts
        run_state["ciks"][position.cik] = updated_record
        results.append(entry)

    return results, alert_rows, failures, blocked, new_total


def _digest_ctx(ts, rows, monitored, process_list, new_total, failures, config) -> dict:
    return {
        "ts": ts,
        "positions": len(rows),
        "monitored": len(monitored),
        "processed": len(process_list),
        "new": new_total,
        "failures": failures,
        "digest": config.get("digest") or {},
    }


def _value_key(position):
    return -position.market_value


def _default_record(position) -> dict:
    return {
        "ticker": position.ticker,
        "sec_ticker": position.sec_ticker,
        "seen_accessions": [],
        "seen_cap": state_store.DEFAULT_SEEN_CAP,
        "last_rf_accession": None,
        "last_rf_baseline": None,
    }


def _new_filings_flow(new_filings, position, client, entries_sink, ts) -> list:
    """Turn new filings of one CIK into alert events; skip non-monitored forms."""
    events = []
    for filing in new_filings:
        form = str(filing.get("form", ""))
        if form not in severity.MONITORED_FORMS:
            continue  # recorded as seen with zero events
        url = client.filing_url(position.cik, filing["accession"])
        if form in severity.PERIODIC_FORMS:
            entries_sink.append(
                _alert_row(
                    ts, position, filing, None,
                    headline="Periodic filing (Risk Factors check)", url=url, sent=False,
                )
            )
            continue
        classification = severity.classify(form, filing.get("items"))
        doc_scan_needed = classification.needs_doc_scan
        if doc_scan_needed:
            classification = _rescan_8ka(client, position, filing)
            if classification is None:
                # Scan failure degrades to an INFO "(items:unknown)" event;
                # it must not crash the run on the missing classification.
                event = {
                    "form": form,
                    "item_code": None,
                    "items": None,
                    "title": "Items unknown (scan failed)",
                    "level": severity.LEVEL_INFO,
                    "accession": filing["accession"],
                    "filed": filing.get("filing_date", ""),
                    "url": url,
                }
                events.append(event)
                entries_sink.append(_alert_row(ts, position, filing, event, url=url, sent=False))
                continue
        if not classification.events:
            # A plain 8-K with no item codes carries nothing classifiable.
            continue
        for event in classification.events:
            events.append(_full_event(event, filing, url))
            entries_sink.append(_alert_row(ts, position, filing, event, url=url, sent=False))
    return events


def _full_event(event, filing, url, title=None) -> dict:
    merged = dict(event)
    if title is not None:
        merged["title"] = title
    merged["accession"] = filing["accession"]
    merged["filed"] = filing.get("filing_date", "")
    merged["url"] = url
    return merged


def _rescan_8ka(client, position, filing):
    """One primary-document scan for an 8-K/A without item codes; None on failure."""
    nodash = filing["accession"].replace("-", "")
    try:
        status, body = client.fetch_document(
            position.cik, nodash, filing.get("primary_document", "")
        )
    except (EdgarRequestError, requests.RequestException, EdgarBlocked) as exc:
        logger.warning(
            "8-K/A item scan failed for %s (%s): %s",
            position.ticker,
            filing["accession"],
            exc,
        )
        return None
    if status != 200:
        logger.warning("8-K/A item scan got HTTP %s for %s", status, position.ticker)
        return None
    codes = risk_factors.scan_item_codes(body)
    if codes:
        updated = severity.classify(severity.FORM_8K_A, ",".join(codes))
        return updated
    return None


def _rf_flow(client, position, submissions, record, filings_dir) -> list:
    """Risk Factors work for one CIK: the latest periodic filing not yet processed."""
    filings_list = state_store.recent_filings(submissions)
    periodic = [
        filing
        for filing in filings_list
        if str(filing.get("form", "")) in severity.PERIODIC_FORMS
    ]
    if not periodic:
        return []
    latest = periodic[0]
    if latest["accession"] == record.get("last_rf_accession"):
        return []
    # One periodic per run: an older unprocessed periodic is handled on a
    # later run (the baseline progression never skips the diff reference).
    return [_process_risk_factors(client, position, latest, record, filings_dir)]


def _process_risk_factors(client, position, filing, record, filings_dir) -> dict:
    """Fetch, extract Item 1A, diff against the stored baseline; return the digest entry."""
    entry = {
        "form": filing["form"],
        "accession": filing["accession"],
        "filed": filing.get("filing_date", ""),
        "url": client.filing_url(position.cik, filing["accession"]),
        "status": "extracted",
        "added": 0,
        "removed": 0,
        "headers": [],
        "no_baseline": False,
    }
    body, failure = _fetch_rf_document(client, position, filing["accession"], filing)
    if failure is not None:
        entry["status"] = "document_fetch_failed"
        entry["detail"] = failure
        return entry
    return _extract_and_write_rf(body, position, filing, record, filings_dir, entry)


def _fetch_rf_document(client, position, accession, filing):
    """Fetch one periodic filing's primary document for the Item 1A pass.

    Returns (body, None) on HTTP 200 or (None, failure_detail); the failure
    detail becomes the digest entry's "document_fetch_failed" marker.
    """
    nodash = accession.replace("-", "")
    try:
        status, body = client.fetch_document(
            position.cik, nodash, filing.get("primary_document", "")
        )
    except (EdgarRequestError, requests.RequestException, EdgarBlocked) as exc:
        logger.warning(
            "risk factors fetch failed for %s (%s): %s", position.ticker, accession, exc
        )
        return None, digest_module.one_line(exc)
    if status != 200:
        return None, f"HTTP {status}"
    return body, None


def _extract_and_write_rf(body, position, filing, record, filings_dir, entry) -> dict:
    """Extract Item 1A from the fetched document, diff it against the stored
    baseline and write the artifacts; updates record, returns the entry."""
    cik = position.cik
    accession = filing["accession"]
    nodash = accession.replace("-", "")
    url = entry["url"]
    directory = filings_dir / cik / nodash
    text = risk_factors.html_to_text(body)
    extract_status, section = risk_factors.extract_item_1a(text)
    metadata = {
        "accession": accession,
        "cik": cik,
        "form": filing["form"],
        "filed": filing.get("filing_date", ""),
        "primary_doc": filing.get("primary_document", ""),
        "url": url,
    }
    directory.mkdir(parents=True, exist_ok=True)
    if extract_status != risk_factors.STATUS_EXTRACTED:
        entry["status"] = extract_status
        metadata.update(
            {
                "rf_status": extract_status,
                "rf_chars": 0,
                "rf_lines": 0,
                "diff_vs": None,
                "diff_added": 0,
                "diff_removed": 0,
                "diff_headers_added": [],
            }
        )
        _save_metadata(directory / "metadata.json", metadata)
        # Mark processed to avoid refetching a filing that has no Item 1A;
        # the stored baseline stays untouched for the next periodic filing.
        record["last_rf_accession"] = accession
        record["last_error"] = f"risk_factors: {extract_status}"
        record["last_error_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return entry

    baseline = record.get("last_rf_baseline") or {}
    baseline_path = Path(baseline.get("path")) if baseline.get("path") else None
    baseline_text = ""
    if baseline_path is not None:
        try:
            if baseline_path.exists():
                baseline_text = baseline_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("baseline unreadable at %s: %s", baseline_path, exc)

    added = removed = 0
    headers = []
    diff_vs = None
    if baseline_text:
        diff_vs = baseline.get("accession")
        added, removed, diff_text, headers = risk_factors.diff_text(baseline_text, section)
        if diff_text:
            _write_text(directory / f"rf_diff_vs_{diff_vs}.txt", diff_text)

    rf_path = directory / "risk_factors.txt"
    _write_text(rf_path, section)
    metadata.update(
        {
            "rf_status": "extracted",
            "rf_chars": len(section),
            "rf_lines": len(section.splitlines()),
            "diff_vs": diff_vs,
            "diff_added": added,
            "diff_removed": removed,
            "diff_headers_added": headers,
        }
    )
    _save_metadata(directory / "metadata.json", metadata)
    record["last_rf_accession"] = accession
    record["last_rf_baseline"] = {"path": str(rf_path), "accession": accession}
    record.pop("last_error", None)
    record.pop("last_error_utc", None)
    entry.update(
        {
            "added": added,
            "removed": removed,
            "headers": headers,
            "no_baseline": not baseline_text,
            "rf_path": str(rf_path),
        }
    )
    return entry


def _write_text(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.warning("cannot write %s: %s", path, exc)


def _save_metadata(metadata_path: Path, metadata: dict) -> None:
    try:
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("cannot write metadata %s: %s", metadata_path, exc)


def _alert_row(ts_utc, position, filing, event, headline=None, url=None, sent=False) -> dict:
    if event is None:
        return {
            "ts_utc": ts_utc,
            "cik": position.cik,
            "ticker": position.ticker,
            "form": filing["form"],
            "accession": filing["accession"],
            "items": None,
            "level": "INFO",
            "item_code": None,
            "headline": headline or "Periodic filing",
            "url": url or "",
            "digest_sent": sent,
        }
    return {
        "ts_utc": ts_utc,
        "cik": position.cik,
        "ticker": position.ticker,
        "form": filing["form"],
        "accession": filing["accession"],
        "items": event.get("items"),
        "level": event.get("level", "INFO"),
        "item_code": event.get("item_code"),
        "headline": headline or event.get("title") or "8-K item",
        "url": url or "",
        "digest_sent": sent,
    }


def _append_alerts(alerts_path: Path, rows) -> None:
    if not rows:
        return
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    with alerts_path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _ping_healthcheck(explicit_url: str, success: bool) -> None:
    """One healthcheck ping; failures are warnings and never change the exit code."""
    url = explicit_url or os.environ.get("HEALTHCHECK_EDGAR_URL", "")
    if not url:
        return
    target = url if success else url + "/fail"
    try:
        with urllib.request.urlopen(target, timeout=HEALTHCHECK_TIMEOUT_S) as response:
            status = getattr(response, "status", 200)
            if not 200 <= status < 300:
                logger.warning("healthcheck ping returned HTTP %s", status)
    except Exception as exc:  # ping failures stay warnings
        logger.warning("healthcheck ping failed: %s", exc)


def _run_extract_rf(args, data_dir: Path) -> int:
    """--extract-rf SYMBOL: latest vs previous periodic Item 1A diff; no state."""
    symbol = universe.normalize_symbol(args.extract_rf)
    session = requests.Session()
    client = EdgarClient(session=session)
    try:
        cik_map, _source = universe.load_cik_map(
            session, data_dir / CIK_CACHE_NAME, ua=os.environ.get("SEC_USER_AGENT")
        )
    except (requests.RequestException, ValueError) as exc:
        print(f"edgar-watch: cannot load CIK map: {exc}")
        return EXIT_FATAL
    entry = cik_map.get(symbol)
    if not entry:
        print(f"edgar-watch: symbol {symbol} does not resolve in the CIK map")
        return EXIT_FATAL
    try:
        submissions = client.fetch_submissions(entry["cik"])
    except EdgarBlocked as exc:
        print(f"edgar-watch: BLOCKED: {digest_module.one_line(exc)}")
        return EXIT_FATAL
    except (EdgarRequestError, requests.RequestException) as exc:
        print(f"edgar-watch: {digest_module.one_line(exc)}")
        return EXIT_FATAL

    filings_list = state_store.recent_filings(submissions)
    periodic = [
        filing
        for filing in filings_list
        if str(filing.get("form", "")) in severity.PERIODIC_FORMS
    ]
    if len(periodic) < 2:
        print(
            f"edgar-watch: {symbol} has fewer than two periodic filings in the recent window;"
            " cannot diff"
        )
        return EXIT_FATAL
    latest, previous = periodic[0], periodic[1]

    extracted = {}
    for label, filing in (("latest", latest), ("previous", previous)):
        section, failure = _fetch_and_extract(client, entry, filing)
        if failure:
            print(f"edgar-watch: {label} ({filing['accession']}): {failure}")
            return EXIT_FATAL
        extracted[label] = section
        print(
            f"{label}: {filing['form']} {filing['accession']} filed "
            f"{filing.get('filing_date', '')} -> extracted ({len(section.splitlines())} lines)"
        )

    added, removed, diff_text, headers = risk_factors.diff_text(extracted["previous"], extracted["latest"])
    out_dir = data_dir / RF_CHECK_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    diff_path = out_dir / f"{symbol}_{latest['accession'].replace('-', '')}.diff"
    diff_path.write_text(diff_text, encoding="utf-8")

    print(f"diff: +{added}/-{removed} lines")
    if headers:
        print("new headers: " + ", ".join(f'"{header}"' for header in headers))
    print(f"full diff: {diff_path}")
    return EXIT_OK


def _fetch_and_extract(client, map_entry, filing):
    """Return (section_text, None) or (None, failure_message) for one periodic filing."""
    accession = filing["accession"]
    try:
        status, body = client.fetch_document(
            map_entry["cik"],
            accession.replace("-", ""),
            filing.get("primary_document", ""),
        )
    except EdgarBlocked as exc:
        return None, f"BLOCKED: {digest_module.one_line(exc)}"
    except (EdgarRequestError, requests.RequestException) as exc:
        return None, digest_module.one_line(exc)
    if status != 200:
        return None, f"HTTP {status}"
    text = risk_factors.html_to_text(body)
    extract_status, section = risk_factors.extract_item_1a(text)
    if extract_status != risk_factors.STATUS_EXTRACTED:
        return None, extract_status
    return section, None


if __name__ == "__main__":
    raise SystemExit(run())
