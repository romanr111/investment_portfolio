"""Enrich an existing dated snapshot; never fetch broker positions or write Sheets."""
import argparse
import json
from pathlib import Path

from analytics.holy_grail_data import CACHE_DIR, CONFIG_PATH, enrich_snapshot_file, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--offline", action="store_true", help="Use cached public history only")
    parser.add_argument("--previous-snapshot", type=Path, help="Optional previous v2 snapshot for attribution")
    args = parser.parse_args()
    try:
        previous = json.loads(args.previous_snapshot.read_text()) if args.previous_snapshot else None
        result = enrich_snapshot_file(args.snapshot, args.output, config=load_config(args.config),
                                       cache_dir=args.cache_dir, allow_network=not args.offline,
                                       previous_combined_data=previous)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"Snapshot enrichment failed ({type(error).__name__}). Original data was not changed.\n")
    data = result.get("data", result)
    metric = data.get("HOLY_GRAIL_DATA") or {}
    quality = data.get("DIVERSIFICATION_DATA") or {}
    v2 = quality.get("allocation_score_v2") or {}
    print(json.dumps({"output": str(args.output.resolve()),
                      "as_of_date": metric.get("as_of_date") or v2.get("as_of_date") or result.get("as_of_date"),
                      "status": metric.get("status"), "effective_streams": metric.get("effective_streams"),
                      "estimated_progress_pct": metric.get("estimated_progress_pct"),
                      "indicator": quality.get("indicator"),
                      "allocation_score": quality.get("allocation_score"),
                      "allocation_score_v2": quality.get("allocation_score_v2"),
                      "target_achieved": metric.get("target_achieved"),
                      "diversification": {key: quality.get(key) for key in (
                          "status", "count_version", "effective_streams", "score_min", "score_max", "confidence")}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
