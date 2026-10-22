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
    args = parser.parse_args()
    try:
        result = enrich_snapshot_file(args.snapshot, args.output, config=load_config(args.config),
                                       cache_dir=args.cache_dir, allow_network=not args.offline)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"Snapshot enrichment failed ({type(error).__name__}). Original data was not changed.\n")
    metric = result.get("data", result)["HOLY_GRAIL_DATA"]
    print(json.dumps({"output": str(args.output.resolve()), "as_of_date": metric["as_of_date"],
                      "status": metric["status"], "effective_streams": metric["effective_streams"],
                      "estimated_progress_pct": metric["estimated_progress_pct"],
                      "target_achieved": metric["target_achieved"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
