"""Frozen ten-check quality summary (risk_equivalent_streams_v1 / diversification_policy_v1)."""

COUNT_VERSION = "risk_equivalent_streams_v1"
POLICY_VERSION = "diversification_policy_v1"
CHECK_IDS = ("family_concentration", "issuer_concentration", "breadth", "stability",
             "recession", "inflation", "liquidity_crypto", "counterparty", "local_fx", "illiquidity")


def summarize_checks(checks):
    if len(checks) != 10 or {c["id"] for c in checks} != set(CHECK_IDS):
        raise ValueError("Exactly the ten versioned checks are required")
    counts = {state: sum(c["state"] == state for c in checks) for state in ("pass", "fail", "unknown")}
    if sum(counts.values()) != 10:
        raise ValueError("Invalid check state")
    return dict(score_min=10 * counts["pass"], score_max=10 * (counts["pass"] + counts["unknown"]),
                score=10 * counts["pass"] if not counts["unknown"] else None, check_counts=counts)
