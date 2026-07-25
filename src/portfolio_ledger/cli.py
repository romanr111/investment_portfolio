import argparse
import sys
from datetime import date, datetime, time, timezone
from typing import Optional

from .storage import PortfolioLedger
from .sync import build_activity_sources, sync_crypto_sources


def _normalize_key_value_args(argv: list[str]) -> list[str]:
    normalized = []
    for argument in argv:
        if argument.startswith("from="):
            normalized.extend(["--from", argument.split("=", 1)[1]])
        elif argument.startswith("to="):
            normalized.extend(["--to", argument.split("=", 1)[1]])
        else:
            normalized.append(argument)
    return normalized


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import private crypto activity ledger events.")
    parser.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--source",
        action="append",
        choices=("binance", "okx", "whitebit"),
        help="Import only the selected source. Repeat to select multiple.",
    )
    parser.add_argument("--dry-run", action="store_true")
    raw_args = list(sys.argv[1:] if argv is None else argv)
    return parser.parse_args(_normalize_key_value_args(raw_args))


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    start_date = date.fromisoformat(args.from_date)
    end_date = date.fromisoformat(args.to_date)
    if end_date < start_date:
        raise ValueError("--to must be on or after --from.")

    ledger = PortfolioLedger()
    from src.crypto.crypto_tokens import CryptoEndpoint

    endpoint = CryptoEndpoint()
    sources = build_activity_sources(endpoint.brokers, ledger.load_sources_config())
    if args.source:
        selected = set(args.source)
        sources = [source for source in sources if source.source_name in selected]
    if not sources:
        print("No matching API activity sources are available.")
        return 2

    results = sync_crypto_sources(
        ledger,
        sources,
        datetime.combine(start_date, time.min, timezone.utc),
        datetime.combine(end_date, time.max, timezone.utc),
        dry_run=args.dry_run,
    )
    for source_name, result in results.items():
        print(
            f"{source_name}: {result['status']}, fetched={result['fetched_count']}, "
            f"imported={result['imported_count']}, duplicates={result['duplicate_count']}"
        )
    return 1 if any(result["status"] == "error" for result in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
