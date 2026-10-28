"""Historical quality summaries and dated risk-evidence validation."""
from datetime import date, datetime, timezone

COUNT_VERSION = "risk_equivalent_streams_v1"
POLICY_VERSION = "diversification_policy_v1"
CHECK_IDS = ("family_concentration", "issuer_concentration", "breadth", "stability",
             "recession", "inflation", "liquidity_crypto", "counterparty", "local_fx", "illiquidity")


def reviewed_record(exposure, as_of_date, *, review_cutoff=None):
    record = exposure.get("risk_record", {})
    try:
        valid = (isinstance(record, dict) and isinstance(record.get("source"), str) and bool(record["source"].strip())
                 and date.fromisoformat(record["effective_from"]) <= date.fromisoformat(as_of_date)
                 and (not record.get("effective_to") or date.fromisoformat(as_of_date) <= date.fromisoformat(record["effective_to"]))
                 and datetime.fromisoformat(record["reviewed_at"]).date() <= (date.fromisoformat(review_cutoff) if review_cutoff else datetime.now(timezone.utc).date()))
    except (ValueError, TypeError, KeyError):
        valid = False
    return record if valid else {}


def summarize_checks(checks):
    if len(checks) != 10 or {c["id"] for c in checks} != set(CHECK_IDS):
        raise ValueError("Exactly the ten versioned checks are required")
    counts = {state: sum(c["state"] == state for c in checks) for state in ("pass", "fail", "unknown")}
    if sum(counts.values()) != 10:
        raise ValueError("Invalid check state")
    return dict(score_min=10 * counts["pass"], score_max=10 * (counts["pass"] + counts["unknown"]),
                score=10 * counts["pass"] if not counts["unknown"] else None, check_counts=counts)
