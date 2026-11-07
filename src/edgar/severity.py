"""8-K item severity table and filing classification for the EDGAR watch.

Owner decision (2026-11-07): two alert levels on top of plain INFO.

- RED: 1.03, 1.05, 2.03, 2.04, 3.01, 4.01, 4.02, 5.01, 6.04
- WARN: 2.05, 2.06, 5.05, 5.06, 6.03
- everything else is INFO

Titles follow the official SEC Form 8-K item list (1.05 and 6.04 verified
live on 2026-11-07). Item codes missing from this table classify as INFO
with a warning log, so a newly added official item never creates a silent
RED/WARN hole.

Forms outside the monitored set (NPORT-P, S-8, DEF 14A and similar fund,
proxy and registration noise) are recorded as seen without events.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

LEVEL_RED = "RED"
LEVEL_WARN = "WARN"
LEVEL_INFO = "INFO"

# Item code -> (official title, alert level).
ITEM_TABLE = {
    "1.01": ("Entry into a Material Definitive Agreement", LEVEL_INFO),
    "1.02": ("Termination of a Material Definitive Agreement", LEVEL_INFO),
    "1.03": ("Bankruptcy or Receivership", LEVEL_RED),
    "1.05": ("Material Cybersecurity Incidents", LEVEL_RED),
    "2.01": ("Completion of Acquisition or Disposition of Assets", LEVEL_INFO),
    "2.02": ("Results of Operations and Financial Condition", LEVEL_INFO),
    "2.03": (
        "Creation of a Direct Financial Obligation or an Obligation under an "
        "Off-Balance Sheet Arrangement of a Registrant",
        LEVEL_RED,
    ),
    "2.04": (
        "Triggering Events That Accelerate or Increase a Direct Financial "
        "Obligation or under an Off-Balance Sheet Arrangement of a Registrant",
        LEVEL_RED,
    ),
    "2.05": ("Costs Associated with Exit or Disposal Activities", LEVEL_WARN),
    "2.06": ("Material Impairments", LEVEL_WARN),
    "3.01": (
        "Notice of Delisting or Failure to Satisfy a Continued Listing Rule "
        "or Standard; Transfer of Listing",
        LEVEL_RED,
    ),
    "3.03": ("Material Modification to Rights of Security Holders", LEVEL_INFO),
    "4.01": ("Changes in Registrant's Certifying Accountant", LEVEL_RED),
    "4.02": (
        "Non-Reliance on Previously Issued Financial Statements or a Related "
        "Audit Report or Completed Interim Review",
        LEVEL_RED,
    ),
    "5.01": ("Changes in Control of Registrant", LEVEL_RED),
    "5.02": (
        "Departure of Directors or Certain Officers; Election of Directors; "
        "Appointment of Certain Officers; Compensatory Arrangements of "
        "Certain Officers",
        LEVEL_INFO,
    ),
    "5.03": (
        "Amendments to Articles of Incorporation or Bylaws; "
        "Change in Fiscal Year",
        LEVEL_INFO,
    ),
    "5.05": (
        "Amendments to the Registrant's Code of Ethics, or Waiver of a "
        "Provision of the Code of Ethics",
        LEVEL_WARN,
    ),
    "5.06": ("Change in Shell Company Status", LEVEL_WARN),
    "6.03": ("Suspension or Termination of Duty to File Reports; Notification", LEVEL_WARN),
    "6.04": ("Failure to Make a Required Distribution", LEVEL_RED),
    "9.01": ("Financial Statements and Exhibits", LEVEL_INFO),
}

# What the digest does with each level.
TREATMENTS = {
    LEVEL_RED: "immediate alert (digest RED section)",
    LEVEL_WARN: "digest WARN section",
    LEVEL_INFO: "digest INFO section (Form 4 folded per ticker)",
}

# Forms that produce events or risk-factor work. Everything else is recorded
# as seen with zero events.
MONITORED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "4"})
PERIODIC_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A"})
FORM_4 = "4"
FORM_8K = "8-K"
FORM_8K_A = "8-K/A"

# Sentinel returned by classify() when an 8-K/A carries no item codes; the
# caller does one primary-document fetch and re-classifies from a document
# scan. Scan failure degrades to an INFO "(items:unknown)" event.
NEEDS_DOC_SCAN = "NEEDS_DOC_SCAN"

FORM_4_TITLE = "Statement of changes in beneficial ownership"


@dataclass
class FilingClassification:
    """Result of classifying one monitored filing."""

    form: str
    monitored: bool
    level: str = ""
    events: list = field(default_factory=list)
    needs_doc_scan: bool = False


def parse_items(raw) -> list:
    """Normalize an EDGAR items string ("2.02,9.01") into ordered unique codes."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        parts = [str(item) for item in raw]
    else:
        parts = str(raw).split(",")
    normalized = []
    for part in parts:
        code = part.strip()
        if code and code not in normalized:
            normalized.append(code)
    return normalized


def classify(form, items_raw) -> FilingClassification:
    """Classify one filing into alert events.

    Forms outside the monitored set yield a classification with zero events
    (recorded as seen). Monitored forms yield per-item events; the overall
    level is the most severe event level present. A 10-K/10-Q carries no
    item events here: its Risk Factors diff is handled by the caller.
    """
    if form not in MONITORED_FORMS:
        return FilingClassification(form=form, monitored=False)

    if form in PERIODIC_FORMS:
        return FilingClassification(form=form, monitored=True)

    if form == FORM_4:
        return FilingClassification(
            form=form,
            monitored=True,
            level=LEVEL_INFO,
            events=[_event(FORM_4, None, FORM_4_TITLE, LEVEL_INFO, [])],
        )

    parsed = parse_items(items_raw)
    if not parsed:
        if form == FORM_8K_A:
            return FilingClassification(form=form, monitored=True, needs_doc_scan=True)
        # A plain 8-K with no item codes carries nothing classifiable.
        return FilingClassification(form=form, monitored=True)

    events = []
    for code in parsed:
        title, level = ITEM_TABLE.get(code, (None, LEVEL_INFO))
        if code not in ITEM_TABLE:
            logger.warning("Unknown 8-K item code %r classifies as INFO", code)
        events.append(_event(form, code, title, level, parsed))

    worst = LEVEL_INFO
    if any(event["level"] == LEVEL_RED for event in events):
        worst = LEVEL_RED
    elif any(event["level"] == LEVEL_WARN for event in events):
        worst = LEVEL_WARN
    return FilingClassification(form=form, monitored=True, level=worst, events=events)


def _event(form, item_code, title, level, all_codes) -> dict:
    return {
        "form": form,
        "item_code": item_code,
        "items": ",".join(all_codes) if all_codes else None,
        "title": title,
        "level": level,
    }
