"""Load Dalio risk metrics from ``analytics/output/summary.json``."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def load_dalio_summary(path: Path) -> Dict:
    if not path.exists():
        logger.info("Dalio summary not found at %s; skipping Dalio section", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load Dalio summary %s: %s", path, exc)
        return {}


def extract_dalio_metrics(summary: Dict) -> Dict:
    div = summary.get("diversification_metrics", {}) or {}
    mgmt = summary.get("management_rules", {}) or {}
    return {
        "hhi": div.get("hhi"),
        "effective_bets": div.get("effective_bets"),
        "bucket_count": div.get("bucket_count"),
        "rebalance_due": mgmt.get("quarterly_rebalance_due"),
        "next_rebalance_date": mgmt.get("next_rebalance_date"),
        "corr_breach_count": mgmt.get("corr_breach_count"),
        "weight_drift_breach_count": mgmt.get("weight_drift_breach_count"),
        "max_gross_leverage_observed": mgmt.get("max_gross_leverage_observed"),
        "data_quality_penalty_pct": mgmt.get("data_quality_penalty_pct"),
    }