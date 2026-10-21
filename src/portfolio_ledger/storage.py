import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CRYPTO_EVENT_TYPES = {
    "buy",
    "sell",
    "reward",
    "fee",
    "deposit",
    "withdrawal",
    "internal_transfer",
    "lending_subscription",
    "lending_redemption",
}


@dataclass(frozen=True)
class ImportResult:
    imported_count: int
    duplicate_count: int


class PortfolioLedger:
    """File-backed local ledger. Raw records never leave ``data/``."""

    def __init__(self, root: Path | str = "data/portfolio_ledger") -> None:
        self.root = Path(root)
        self.crypto_dir = self.root / "crypto"
        self.imported_events_path = self.crypto_dir / "imported_events.jsonl"
        self.manual_events_path = self.crypto_dir / "manual_events.csv"
        self.import_state_path = self.crypto_dir / "import_state.json"
        self.sources_config_path = self.crypto_dir / "sources.json"
        self.other_assets_dir = self.root / "other_assets"
        self.assets_path = self.other_assets_dir / "assets.csv"
        self.asset_events_path = self.other_assets_dir / "events.csv"
        self.asset_valuations_path = self.other_assets_dir / "valuations.csv"
        self.p2p_dir = self.root / "p2p"
        self.p2p_positions_path = self.p2p_dir / "positions.csv"

    @staticmethod
    def _canonical_event(raw_event: dict[str, Any]) -> dict[str, Any]:
        source = str(raw_event.get("source", "")).strip().lower()
        account = str(raw_event.get("account", "")).strip().lower()
        remote_id = str(raw_event.get("remote_id", "")).strip()
        event_id = str(raw_event.get("event_id", "")).strip()
        if not event_id and source and account and remote_id:
            event_id = f"{source}:{account}:{remote_id}"
        if not event_id:
            raise ValueError(
                "Crypto events require event_id or source + account + remote_id."
            )

        required = ("occurred_at", "event_type", "asset")
        missing = [name for name in required if not raw_event.get(name)]
        if missing:
            raise ValueError(f"Crypto event missing required fields: {', '.join(missing)}")
        event_type = str(raw_event["event_type"]).strip().lower()
        if event_type not in CRYPTO_EVENT_TYPES:
            raise ValueError(f"Unsupported crypto event_type: {event_type}")

        event = dict(raw_event)
        event.update(
            {
                "event_id": event_id,
                "source": source,
                "account": account,
                "remote_id": remote_id or None,
                "event_type": event_type,
                "asset": str(raw_event["asset"]).strip().upper(),
                "quote_asset": (
                    str(raw_event["quote_asset"]).strip().upper()
                    if raw_event.get("quote_asset")
                    else None
                ),
                "ingested_at": raw_event.get("ingested_at")
                or datetime.now(timezone.utc).isoformat(),
            }
        )
        if event.get("usd_value") in (None, "") and event.get("amount_usd") not in (
            None,
            "",
        ):
            event["usd_value"] = float(event["amount_usd"])
        return event

    def _load_imported_events(self) -> list[dict[str, Any]]:
        if not self.imported_events_path.exists():
            return []
        events = []
        with self.imported_events_path.open(encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Invalid JSONL at {self.imported_events_path}:{line_number}"
                    ) from error
        return events

    @staticmethod
    def _csv_value(name: str, raw_value: Any) -> Any:
        if raw_value is None:
            return None
        value = str(raw_value).strip()
        if not value:
            return None
        if name in {
            "quantity",
            "quote_quantity",
            "usd_value",
            "fee_quantity",
            "fee_usd",
            "fx_rate_to_usd",
            "amount",
            "amount_usd",
        }:
            return float(value)
        return value

    def _load_manual_events(self) -> list[dict[str, Any]]:
        if not self.manual_events_path.exists():
            return []
        events = []
        with self.manual_events_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                parsed = {
                    name: self._csv_value(name, raw_value)
                    for name, raw_value in row.items()
                }
                events.append(self._canonical_event(parsed))
        return events

    def load_crypto_events(self) -> list[dict[str, Any]]:
        events = self._load_imported_events() + self._load_manual_events()
        by_event_id: dict[str, dict[str, Any]] = {}
        for event in events:
            event_id = str(event["event_id"])
            if event_id in by_event_id:
                raise ValueError(f"Duplicate crypto event_id in ledger: {event_id}")
            by_event_id[event_id] = event
        return sorted(by_event_id.values(), key=lambda event: event["occurred_at"])

    def import_events(self, events: Iterable[dict[str, Any]]) -> ImportResult:
        existing = self.load_crypto_events()
        known_ids = {str(event.get("event_id")) for event in existing}
        imported: list[dict[str, Any]] = []
        duplicate_count = 0

        for raw_event in events:
            event = self._canonical_event(raw_event)
            if event["event_id"] in known_ids:
                duplicate_count += 1
                continue
            known_ids.add(event["event_id"])
            imported.append(event)

        if imported:
            self.crypto_dir.mkdir(parents=True, exist_ok=True)
            with self.imported_events_path.open("a", encoding="utf-8") as handle:
                for event in imported:
                    handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True))
                    handle.write("\n")

        return ImportResult(len(imported), duplicate_count)

    def load_import_state(self) -> dict[str, Any]:
        if not self.import_state_path.exists():
            return {}
        with self.import_state_path.open(encoding="utf-8") as handle:
            state = json.load(handle)
        if not isinstance(state, dict):
            raise ValueError("Crypto import state must be a JSON object.")
        return state

    def load_sources_config(self) -> dict[str, Any]:
        if not self.sources_config_path.exists():
            return {}
        with self.sources_config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)
        if not isinstance(config, dict):
            raise ValueError("Crypto sources config must be a JSON object.")
        return config

    def save_import_state(self, state: dict[str, Any]) -> None:
        self.crypto_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self.import_state_path.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=True, indent=2, sort_keys=True)
        temporary_path.replace(self.import_state_path)

    @staticmethod
    def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8", newline="") as handle:
            return [
                {
                    name: (str(value).strip() if value is not None else "")
                    for name, value in row.items()
                }
                for row in csv.DictReader(handle)
            ]

    def load_car_assets(self) -> list[dict[str, Any]]:
        return self._load_csv_rows(self.assets_path)

    def load_car_events(self) -> list[dict[str, Any]]:
        return self._load_csv_rows(self.asset_events_path)

    def load_car_valuations(self) -> list[dict[str, Any]]:
        return self._load_csv_rows(self.asset_valuations_path)

    def load_p2p_positions(self) -> list[dict[str, Any]]:
        return self._load_csv_rows(self.p2p_positions_path)
