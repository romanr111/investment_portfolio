import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd


DATE_TAB_FORMAT = "%d %b %Y"
CORE_BUCKETS = (
    "Stocks",
    "Bonds",
    "Other Bets",
    "Crypto Lending",
    "Precious Metals",
    "Crypto Coins",
    "Commodities",
    "Cash",
    "P2P Lending",
)

SHEET_CATEGORY_TO_BUCKET = {
    "Stocks": "Stocks",
    "Bonds": "Bonds",
    "Other Bets": "Other Bets",
    # Legacy portfolio tabs (pre-2025) used broad labels.
    "Mining": "Other Bets",
    "Crypto Lending": "Crypto Lending",
    "Crypto Landing": "Crypto Lending",
    "Crypto": "Crypto Coins",
    "Precious Metals": "Precious Metals",
    "Gold": "Precious Metals",
    "Crypto Coins": "Crypto Coins",
    "Commodities": "Commodities",
    "Cash": "Cash",
    "Cash & Equivalents": "Cash",
    "P2P Lending": "P2P Lending",
    "REIT": "Stocks",
}


def _to_plain_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _to_plain_json(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _sum_numeric(values: Iterable[Any]) -> float:
    total = 0.0
    for value in values:
        number = _parse_number(value)
        if number is None:
            continue
        total += number
    return total


def _parse_number(raw_value: Any) -> Optional[float]:
    if raw_value is None:
        return None

    if isinstance(raw_value, (int, float)):
        if isinstance(raw_value, float) and (math.isnan(raw_value) or math.isinf(raw_value)):
            return None
        return float(raw_value)

    if isinstance(raw_value, Decimal):
        return float(raw_value)

    text = str(raw_value).strip()
    if not text:
        return None

    text = text.replace(",", "")
    text = text.replace("$", "")
    text = text.replace("€", "")
    text = text.replace("%", "")
    text = re.sub(r"\s+", "", text)

    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"

    try:
        return float(text)
    except ValueError:
        return None


def _parse_tab_date(title: str) -> Optional[pd.Timestamp]:
    normalized_title = str(title).strip()
    if not normalized_title:
        return None
    try:
        return pd.Timestamp(datetime.strptime(normalized_title, DATE_TAB_FORMAT).date())
    except ValueError:
        parsed = pd.to_datetime(normalized_title, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed.date())


def _safe_bucket_value(combined_data: dict, bucket: str) -> float:
    ib_data = combined_data.get("IB_DATA", {})
    if bucket == "Stocks":
        total_stocks = _parse_number(ib_data.get("Total Stocks Value"))
        if total_stocks is not None:
            return total_stocks
        return _sum_numeric(ib_data.get("Stocks", {}).values()) + _sum_numeric(
            ib_data.get("China Stocks", {}).values()
        )
    if bucket == "Bonds":
        return _sum_numeric(ib_data.get("Bonds", {}).values())
    if bucket == "Precious Metals":
        direct = _sum_numeric(ib_data.get("Precious Metals", {}).values())
        if direct > 0:
            return direct
        return _sum_numeric(ib_data.get("Gold", {}).values())
    if bucket == "Commodities":
        return _sum_numeric(ib_data.get("Commodities", {}).values())
    if bucket == "Crypto Coins":
        return _parse_number(combined_data.get("CRYPTO_DATA", {}).get("Total_Crypto_Value")) or 0.0
    if bucket == "Crypto Lending":
        group_interest = combined_data.get("FIXED_INCOME_DATA", {}).get("group_weighted_interest", {})
        value_tuple = group_interest.get("Crypto Landing", (0, 0))
        if isinstance(value_tuple, (list, tuple)) and value_tuple:
            return _parse_number(value_tuple[0]) or 0.0
        return _parse_number(value_tuple) or 0.0
    if bucket == "P2P Lending":
        group_interest = combined_data.get("FIXED_INCOME_DATA", {}).get("group_weighted_interest", {})
        value_tuple = group_interest.get("p2p_lending", (0, 0))
        if isinstance(value_tuple, (list, tuple)) and value_tuple:
            return _parse_number(value_tuple[0]) or 0.0
        return _parse_number(value_tuple) or 0.0
    if bucket == "Cash":
        return _parse_number(combined_data.get("CASH_DATA", {}).get("Total")) or 0.0
    if bucket == "Other Bets":
        return _sum_numeric(combined_data.get("OTHER_ASSETS", {}).values())
    return 0.0


def combined_data_to_unified_snapshot_rows(
    combined_data: dict,
    as_of_date: str,
    currency: str = "USD",
) -> list[dict[str, Any]]:
    rows = []
    for bucket in CORE_BUCKETS:
        rows.append(
            {
                "date": as_of_date,
                "asset_bucket": bucket,
                "market_value": _safe_bucket_value(combined_data, bucket),
                "return_pct": pd.NA,
                "currency": currency.upper(),
                "source_type": "combined_data",
                "source_ref": "DataSource.get_combined_data",
            }
        )
    return rows


def save_combined_data_snapshot_json(
    combined_data: dict,
    output_dir: str,
    as_of_date: Optional[str] = None,
) -> Path:
    snapshot_dir = Path(output_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc)
    date_value = as_of_date or now_utc.date().isoformat()
    timestamp_label = now_utc.strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "as_of_date": date_value,
        "saved_at_utc": now_utc.isoformat(),
        "source": "DataSource.get_combined_data",
        "data": _to_plain_json(combined_data),
    }

    dated_file = snapshot_dir / f"combined_data_{date_value}_{timestamp_label}.json"
    latest_file = snapshot_dir / "combined_data_latest.json"

    with dated_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    with latest_file.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)

    return dated_file


def sheet_tab_values_to_unified_rows(
    values: list[list[str]],
    tab_title: str,
    currency: str = "USD",
    include_zero_positions: bool = False,
) -> list[dict[str, Any]]:
    tab_date = _parse_tab_date(tab_title)
    if tab_date is None:
        return []

    rows = []
    for row in values:
        # New tab layout stores category/value in G/H, older layout in H/I.
        candidate_pairs = ((6, 7), (7, 8))
        for category_idx, value_idx in candidate_pairs:
            if len(row) <= max(category_idx, value_idx):
                continue
            raw_category = str(row[category_idx]).strip()
            bucket = SHEET_CATEGORY_TO_BUCKET.get(raw_category)
            if not bucket:
                continue
            market_value = _parse_number(row[value_idx])
            if market_value is None:
                continue
            if not include_zero_positions and abs(market_value) < 1e-12:
                continue
            rows.append(
                {
                    "date": tab_date.strftime("%Y-%m-%d"),
                    "asset_bucket": bucket,
                    "market_value": market_value,
                    "return_pct": pd.NA,
                    "currency": currency.upper(),
                    "source_type": "google_sheets",
                    "source_ref": tab_title,
                }
            )
            break
    return rows


def build_unified_history_frame(
    rows: list[dict[str, Any]],
    return_source: str = "blank",
    history_frequency: str = "monthly",
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "asset_bucket",
                "market_value",
                "return_pct",
                "currency",
                "source_type",
                "source_ref",
                "ingested_at_utc",
            ]
        )

    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("History rows contain unparsable date values.")

    if history_frequency == "monthly":
        frame["month"] = frame["date"].dt.to_period("M")
        month_last_dates = frame.groupby("month")["date"].transform("max")
        frame = frame.loc[frame["date"] == month_last_dates].copy()
        frame["date"] = frame["month"].dt.to_timestamp(how="end").dt.normalize()
        frame = frame.drop(columns=["month"])
    elif history_frequency != "raw":
        raise ValueError("history_frequency must be one of: monthly, raw.")

    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame = (
        frame.groupby(["date", "asset_bucket", "currency"], as_index=False)
        .agg(
            {
                "market_value": "sum",
                "source_type": "last",
                "source_ref": "last",
            }
        )
        .sort_values(["asset_bucket", "date"])
        .reset_index(drop=True)
    )

    if return_source == "pct-change":
        frame["return_pct"] = frame.groupby("asset_bucket")["market_value"].pct_change()
    elif return_source == "blank":
        frame["return_pct"] = pd.NA
    else:
        raise ValueError("return_source must be one of: blank, pct-change.")

    frame = frame.sort_values(["date", "asset_bucket"]).reset_index(drop=True)
    frame["ingested_at_utc"] = datetime.now(timezone.utc).isoformat()
    return frame[
        [
            "date",
            "asset_bucket",
            "market_value",
            "return_pct",
            "currency",
            "source_type",
            "source_ref",
            "ingested_at_utc",
        ]
    ]


def validate_required_buckets(
    history_frame: pd.DataFrame,
    required_buckets: Iterable[str] = CORE_BUCKETS,
) -> None:
    if history_frame.empty:
        raise ValueError("History frame is empty.")

    required = set(required_buckets)
    coverage = history_frame.groupby("date")["asset_bucket"].apply(set)
    missing_by_date = {
        date: sorted(required.difference(found))
        for date, found in coverage.items()
        if required.difference(found)
    }
    if missing_by_date:
        preview = "; ".join(
            f"{date}: {', '.join(missing)}"
            for date, missing in list(missing_by_date.items())[:5]
        )
        raise ValueError(
            "Required bucket coverage failed for some dates. "
            f"Examples: {preview}"
        )


def save_unified_history(
    history_frame: pd.DataFrame,
    csv_path: str,
    jsonl_path: Optional[str] = None,
) -> tuple[Path, Optional[Path]]:
    csv_output = Path(csv_path)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    history_frame.to_csv(csv_output, index=False)

    jsonl_output: Optional[Path] = None
    if jsonl_path:
        jsonl_output = Path(jsonl_path)
        jsonl_output.parent.mkdir(parents=True, exist_ok=True)
        history_frame.to_json(
            jsonl_output,
            orient="records",
            lines=True,
            force_ascii=True,
        )

    return csv_output, jsonl_output


def sync_unified_history_from_google_sheets(
    credentials_path: str,
    spreadsheet_name: str,
    output_csv_path: str,
    output_jsonl_path: Optional[str] = None,
    currency: str = "USD",
    return_source: str = "blank",
    strict_required_buckets: bool = False,
    include_zero_positions: bool = False,
    history_frequency: str = "monthly",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    from src.google_sheets.spreadsheet_structure import GoogleSheetsClient

    client = GoogleSheetsClient(credentials_path)
    spreadsheet = client.open_spreadsheet(spreadsheet_name)
    start_ts = pd.Timestamp(start_date) if start_date else None
    end_ts = pd.Timestamp(end_date) if end_date else None

    rows: list[dict[str, Any]] = []
    for worksheet in spreadsheet.worksheets():
        tab_date = _parse_tab_date(worksheet.title)
        if tab_date is None:
            continue
        if start_ts is not None and tab_date < start_ts:
            continue
        if end_ts is not None and tab_date > end_ts:
            continue
        rows.extend(
            sheet_tab_values_to_unified_rows(
                values=worksheet.get_all_values(),
                tab_title=worksheet.title,
                currency=currency,
                include_zero_positions=include_zero_positions,
            )
        )

    frame = build_unified_history_frame(
        rows,
        return_source=return_source,
        history_frequency=history_frequency,
    )
    if strict_required_buckets:
        validate_required_buckets(frame)

    save_unified_history(frame, output_csv_path, output_jsonl_path)
    return frame
