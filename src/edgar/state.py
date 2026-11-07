"""Atomic local state store and seen-filing bookkeeping for the EDGAR watch.

``state.json`` is the only written state a run depends on; it is loaded from
and saved to ``data/edgar/state.json`` atomically (temp file + fsync +
``os.replace``). A missing or corrupted file starts from an empty state, so
the local layout is safe to delete (the first reseeded run marks everything
inside the backfill window and alerts only on the last few days).
"""
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_VERSION = 1
DEFAULT_SEEN_CAP = 500


def empty_state() -> dict:
    return {
        "$version": STATE_VERSION,
        "updated_at_utc": "",
        "last_run_utc": "",
        "run_count": 0,
        "universe": {},
        "ciks": {},
    }


def load(path) -> dict:
    """Load the state file; any missing or corrupted file yields a fresh state."""
    path = Path(path)
    state = empty_state()
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return state
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable EDGAR state file %s: %s", path, exc)
        return state
    if not isinstance(payload, dict):
        logger.warning("Ignoring unexpected EDGAR state file content in %s", path)
        return state
    for key, value in empty_state().items():
        payload.setdefault(key, value)
    return payload


def save(path, state: dict) -> None:
    """Write the state atomically (temp file, fsync, os.replace)."""
    path = Path(path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=directory)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise


def recent_filings(submissions: dict) -> list:
    """Flatten the parallel columns of ``filings.recent`` into ordered filing dicts."""
    recent = submissions.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict):
        return []
    accessions = recent.get("accessionNumber", []) or []
    forms = recent.get("form", []) or []
    filed = recent.get("filingDate", []) or []
    items = recent.get("items", []) or []
    documents = recent.get("primaryDocument", []) or []
    filings = []
    for index, accession in enumerate(accessions):
        filings.append(
            {
                "accession": accession,
                "form": forms[index] if index < len(forms) else "",
                "filing_date": filed[index] if index < len(filed) else "",
                "items": items[index] if index < len(items) else "",
                "primary_document": documents[index] if index < len(documents) else "",
            }
        )
    return filings


def new_accessions(submissions, cik_record, max_backfill_days=7, now=None, seen_cap=DEFAULT_SEEN_CAP):
    """Return (new_filings, updated_record) for one CIK's submissions JSON.

    EDGAR's ``recent`` list is newest-first. The first contact with a CIK
    records the whole observed window as seen and alerts only on filings
    inside ``max_backfill_days`` (anti-flood: a first run must not turn
    hundreds of old Form 4 rows into alerts). Later runs alert on anything
    not in ``seen_accessions``.

    ``seen_accessions`` is a FIFO store capped at ``seen_cap`` (1000-row
    recent window means a stale filing can resurface after cap churn; that
    trade-off is documented in data/README.md).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    record = dict(cik_record or {})
    known = set(record.get("seen_accessions", []) or [])
    filings = recent_filings(submissions)
    first_contact = not record.get("seen_accessions") and not record.get("last_accession")

    cutoff = (now - timedelta(days=max(0, int(max_backfill_days)))).date().isoformat()
    new_filings = []
    if first_contact:
        for filing in filings:
            if filing["filing_date"] >= cutoff and filing["accession"] not in known:
                new_filings.append(filing)
    else:
        for filing in filings:
            if filing["accession"] not in known:
                new_filings.append(filing)

    marked = [filing["accession"] for filing in filings]
    kept = list(record.get("seen_accessions", []) or [])
    merged = []
    seen_added = set()
    for accession in marked + kept:
        if accession not in seen_added:
            merged.append(accession)
            seen_added.add(accession)
    record["seen_accessions"] = merged[:seen_cap]
    record["seen_cap"] = seen_cap
    record["last_filing_date"] = filings[0]["filing_date"] if filings else record.get("last_filing_date", "")
    if new_filings or first_contact:
        record["last_accession"] = new_filings[0]["accession"] if new_filings else (
            filings[0]["accession"] if filings else record.get("last_accession", "")
        )
    return new_filings, record
