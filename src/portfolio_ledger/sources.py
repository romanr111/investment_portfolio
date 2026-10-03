from datetime import datetime, timezone
from typing import Any, Optional, Protocol

import requests

from .contract import STABLECOINS


class CryptoActivitySource(Protocol):
    """Activity capability kept separate from balance-only ExchangeBase."""

    source_name: str

    def fetch_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...

    def fetch_lending_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]: ...


def _iso_from_milliseconds(value: Any) -> str:
    return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat()


def normalize_binance_trade(
    trade: dict[str, Any],
    *,
    symbol: str,
    base_asset: str,
    quote_asset: str,
    account: str = "spot",
) -> dict[str, Any]:
    base = base_asset.upper()
    quote = quote_asset.upper()
    quote_quantity = float(trade.get("quoteQty", trade.get("quote_quantity", 0)))
    fee_asset = str(trade.get("commissionAsset", "")).upper() or None
    fee_quantity = float(trade.get("commission", 0))
    return {
        "occurred_at": _iso_from_milliseconds(trade["time"]),
        "source": "binance",
        "account": account,
        "remote_id": f"{symbol}:{trade['id']}",
        "event_type": "buy" if trade.get("isBuyer") else "sell",
        "asset": base,
        "quantity": float(trade["qty"]),
        "quote_asset": quote,
        "quote_quantity": quote_quantity,
        "usd_value": quote_quantity if quote in STABLECOINS else None,
        "fee_asset": fee_asset,
        "fee_quantity": fee_quantity,
        "fee_usd": fee_quantity if fee_asset in STABLECOINS else None,
        "from_location": None,
        "to_location": account,
    }


def normalize_okx_fill(
    fill: dict[str, Any], account: str = "trading"
) -> dict[str, Any]:
    instrument = str(fill["instId"])
    base, quote = instrument.split("-", 2)[:2]
    quantity = float(fill.get("fillSz", fill.get("sz", 0)))
    price = float(fill.get("fillPx", fill.get("px", 0)))
    quote_quantity = quantity * price
    fee_asset = str(fill.get("feeCcy", "")).upper() or None
    fee_quantity = abs(float(fill.get("fee", 0)))
    return {
        "occurred_at": _iso_from_milliseconds(fill["ts"]),
        "source": "okx",
        "account": account,
        "remote_id": f"{instrument}:{fill['tradeId']}",
        "event_type": str(fill["side"]).lower(),
        "asset": base.upper(),
        "quantity": quantity,
        "quote_asset": quote.upper(),
        "quote_quantity": quote_quantity,
        "usd_value": quote_quantity if quote.upper() in STABLECOINS else None,
        "fee_asset": fee_asset,
        "fee_quantity": fee_quantity,
        "fee_usd": fee_quantity if fee_asset in STABLECOINS else None,
        "from_location": account,
        "to_location": account,
    }


def normalize_whitebit_trade(
    trade: dict[str, Any], account: str = "trade"
) -> dict[str, Any]:
    market = str(trade.get("market", trade.get("symbol", "")))
    separator = "_" if "_" in market else "-"
    base, quote = market.split(separator, 1)
    quantity = float(trade.get("amount", trade.get("quantity", 0)))
    price = float(trade.get("price", 0))
    raw_timestamp = float(trade.get("time", trade.get("timestamp", 0)))
    if raw_timestamp < 10_000_000_000:
        raw_timestamp *= 1000
    quote_quantity = quantity * price
    fee_asset = str(trade.get("feeAsset", "")).upper() or None
    fee_quantity = abs(float(trade.get("fee", 0)))
    return {
        "occurred_at": _iso_from_milliseconds(raw_timestamp),
        "source": "whitebit",
        "account": account,
        "remote_id": f"{market}:{trade.get('dealId', trade.get('id'))}",
        "event_type": str(trade["side"]).lower(),
        "asset": base.upper(),
        "quantity": quantity,
        "quote_asset": quote.upper(),
        "quote_quantity": quote_quantity,
        "usd_value": quote_quantity if quote.upper() in STABLECOINS else None,
        "fee_asset": fee_asset,
        "fee_quantity": fee_quantity,
        "fee_usd": fee_quantity if fee_asset in STABLECOINS else None,
        "from_location": account,
        "to_location": account,
    }


def _milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _thirty_day_windows(start_ms: int, end_ms: int):
    max_span_ms = 30 * 24 * 60 * 60 * 1000
    window_start = start_ms
    while window_start <= end_ms:
        window_end = min(window_start + max_span_ms - 1, end_ms)
        yield window_start, window_end
        window_start = window_end + 1


def _transfer_timestamp(record: dict[str, Any]) -> str:
    value = record.get("insertTime", record.get("applyTime", record.get("time")))
    if isinstance(value, (int, float)) or str(value).isdigit():
        numeric = float(value)
        if numeric < 10_000_000_000:
            numeric *= 1000
        return _iso_from_milliseconds(numeric)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


class BinanceActivitySource:
    source_name = "binance"

    def __init__(self, client: Any, symbols: Optional[list[str]] = None) -> None:
        self.client = client
        self.symbols = [symbol.upper() for symbol in (symbols or [])]

    def fetch_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        api = self.client.client
        cursor = cursor or {}
        symbols = self.symbols or [
            str(symbol).upper() for symbol in cursor.get("symbols", [])
        ]
        start_ms = _milliseconds(start_at)
        if cursor.get("last_end_ms") is not None:
            start_ms = max(start_ms, int(cursor["last_end_ms"]) + 1)
        end_ms = _milliseconds(end_at)
        if start_ms > end_ms:
            return [], {
                "symbols": symbols,
                "last_end_ms": end_ms,
                "coverage": cursor.get("coverage", "complete" if symbols else "partial"),
            }
        events = []
        coverage_complete = bool(symbols)

        for symbol in symbols:
            symbol_info = api.get_symbol_info(symbol)
            if not symbol_info:
                continue
            trades = api.get_my_trades(
                symbol=symbol,
                startTime=start_ms,
                endTime=end_ms,
                limit=1000,
            )
            if len(trades) >= 1000:
                coverage_complete = False
            events.extend(
                normalize_binance_trade(
                    trade,
                    symbol=symbol,
                    base_asset=symbol_info["baseAsset"],
                    quote_asset=symbol_info["quoteAsset"],
                )
                for trade in trades
            )

        for deposit in api.get_deposit_history(startTime=start_ms, endTime=end_ms):
            asset = str(deposit.get("coin", deposit.get("asset"))).upper()
            quantity = float(deposit.get("amount", 0))
            events.append(
                {
                    "occurred_at": _transfer_timestamp(deposit),
                    "source": "binance",
                    "account": "spot",
                    "remote_id": f"deposit:{deposit.get('txId', deposit.get('id'))}",
                    "transfer_id": deposit.get("txId") or None,
                    "event_type": "deposit",
                    "asset": asset,
                    "quantity": quantity,
                    "quote_asset": None,
                    "quote_quantity": None,
                    "usd_value": quantity if asset in STABLECOINS else None,
                    "fee_asset": None,
                    "fee_quantity": 0.0,
                    "from_location": "external",
                    "to_location": "binance",
                }
            )
        for withdrawal in api.get_withdraw_history(startTime=start_ms, endTime=end_ms):
            asset = str(withdrawal.get("coin", withdrawal.get("asset"))).upper()
            quantity = float(withdrawal.get("amount", 0))
            events.append(
                {
                    "occurred_at": _transfer_timestamp(withdrawal),
                    "source": "binance",
                    "account": "spot",
                    "remote_id": f"withdrawal:{withdrawal.get('id', withdrawal.get('txId'))}",
                    "transfer_id": withdrawal.get("txId") or None,
                    "event_type": "withdrawal",
                    "asset": asset,
                    "quantity": quantity,
                    "quote_asset": None,
                    "quote_quantity": None,
                    "usd_value": quantity if asset in STABLECOINS else None,
                    "fee_asset": asset,
                    "fee_quantity": abs(float(withdrawal.get("transactionFee", 0))),
                    "fee_usd": (
                        abs(float(withdrawal.get("transactionFee", 0)))
                        if asset in STABLECOINS
                        else None
                    ),
                    "from_location": "binance",
                    "to_location": "external",
                }
            )

        return events, {
            "symbols": symbols,
            "last_end_ms": end_ms,
            "coverage": "complete" if coverage_complete else "partial",
        }

    def fetch_lending_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not hasattr(self.client, "_binance_signed_request"):
            return [], {"last_end_ms": _milliseconds(end_at), "coverage": "partial"}

        events = []
        start_ms = _milliseconds(start_at)
        cursor = cursor or {}
        if cursor.get("last_end_ms") is not None:
            start_ms = max(start_ms, int(cursor["last_end_ms"]) + 1)
        end_ms = _milliseconds(end_at)
        if start_ms > end_ms:
            return [], {
                "last_end_ms": end_ms,
                "coverage": cursor.get("coverage", "complete"),
            }
        endpoint_types = {
            "/sapi/v1/simple-earn/flexible/history/rewardsRecord": "reward",
            "/sapi/v1/simple-earn/flexible/history/subscriptionRecord": "lending_subscription",
            "/sapi/v1/simple-earn/flexible/history/redemptionRecord": "lending_redemption",
        }
        for endpoint, event_type in endpoint_types.items():
            for window_start, window_end in _thirty_day_windows(start_ms, end_ms):
                page = 1
                previous_page_signature = None
                while True:
                    params = {
                        "startTime": window_start,
                        "endTime": window_end,
                        "current": page,
                        "size": 100,
                    }
                    if event_type == "reward":
                        params["type"] = "ALL"
                    response = self.client._binance_signed_request(
                        "GET", endpoint, params=params
                    )
                    rows = response.get("rows", [])
                    signature = tuple(
                        (
                            row.get("id"),
                            row.get("purchaseId"),
                            row.get("redeemId"),
                            row.get("time", row.get("createTime")),
                        )
                        for row in rows
                    )
                    if page > 1 and signature == previous_page_signature:
                        break
                    previous_page_signature = signature
                    for row in rows:
                        asset = str(row.get("asset", "")).upper()
                        quantity = float(
                            row.get(
                                "amount",
                                row.get("rewards", row.get("totalAmount", 0)),
                            )
                        )
                        row_time = row.get("time", row.get("createTime", window_end))
                        remote_key = row.get(
                            "id",
                            row.get(
                                "purchaseId",
                                row.get("redeemId", row.get("productId")),
                            ),
                        )
                        if event_type == "lending_redemption":
                            from_location, to_location = "simple_earn", "spot"
                        elif event_type == "lending_subscription":
                            from_location, to_location = "spot", "simple_earn"
                        else:
                            from_location = to_location = "simple_earn"
                        events.append(
                            {
                                "occurred_at": _iso_from_milliseconds(row_time),
                                "source": "binance",
                                "account": "simple_earn",
                                "remote_id": (
                                    f"{event_type}:{remote_key}:{asset}:"
                                    f"{row_time}:{quantity}"
                                ),
                                "event_type": event_type,
                                "asset": asset,
                                "quantity": quantity,
                                "usd_value": (
                                    quantity if asset in STABLECOINS else None
                                ),
                                "from_location": from_location,
                                "to_location": to_location,
                            }
                        )
                    if len(rows) < 100:
                        break
                    page += 1
        return events, {"last_end_ms": end_ms, "coverage": "complete"}


class OKXActivitySource:
    source_name = "okx"

    def __init__(self, client: Any) -> None:
        self.client = client

    def fetch_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        start_ms = _milliseconds(start_at)
        if cursor and cursor.get("last_end_ms") is not None:
            start_ms = max(start_ms, int(cursor["last_end_ms"]) + 1)
        end_ms = _milliseconds(end_at)
        if start_ms > end_ms:
            return [], {
                "last_end_ms": end_ms,
                "coverage": (cursor or {}).get("coverage", "complete"),
            }
        params = {"begin": str(start_ms), "end": str(end_ms), "limit": "100"}
        fill_params = dict(params, instType="SPOT")
        fills = self.client._send_request(
            "GET", "/trade/fills-history", params=fill_params
        )
        coverage_complete = len(fills) < 100
        events = [normalize_okx_fill(fill) for fill in fills]

        for endpoint, event_type in (
            ("/asset/deposit-history", "deposit"),
            ("/asset/withdrawal-history", "withdrawal"),
        ):
            rows = self.client._send_request("GET", endpoint, params=params)
            if len(rows) >= 100:
                coverage_complete = False
            for row in rows:
                asset = str(row.get("ccy", "")).upper()
                quantity = abs(float(row.get("amt", 0)))
                fee_quantity = abs(float(row.get("fee", 0)))
                events.append(
                    {
                        "occurred_at": _iso_from_milliseconds(row.get("ts", end_ms)),
                        "source": "okx",
                        "account": "funding",
                        "remote_id": f"{event_type}:{row.get('txId', row.get('wdId', row.get('depId')))}",
                        "transfer_id": row.get("txId") or None,
                        "event_type": event_type,
                        "asset": asset,
                        "quantity": quantity,
                        "usd_value": quantity if asset in STABLECOINS else None,
                        "fee_asset": asset if event_type == "withdrawal" else None,
                        "fee_quantity": fee_quantity,
                        "fee_usd": (
                            fee_quantity if asset in STABLECOINS else None
                        ),
                        "from_location": "okx" if event_type == "withdrawal" else "external",
                        "to_location": "external" if event_type == "withdrawal" else "okx",
                    }
                )
        return events, {
            "last_end_ms": end_ms,
            "coverage": "complete" if coverage_complete else "partial",
        }

    def fetch_lending_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        start_ms = _milliseconds(start_at)
        cursor = cursor or {}
        if cursor.get("last_end_ms") is not None:
            start_ms = max(start_ms, int(cursor["last_end_ms"]) + 1)
        end_ms = _milliseconds(end_at)
        if start_ms > end_ms:
            return [], {
                "last_end_ms": end_ms,
                "coverage": cursor.get("coverage", "complete"),
            }
        try:
            rows = self.client._send_request(
                "GET",
                "/finance/savings/lending-history",
                params={"begin": str(start_ms), "end": str(end_ms), "limit": "100"},
            )
        except Exception:
            return [], {"last_end_ms": end_ms, "coverage": "partial"}
        events = []
        for row in rows:
            asset = str(row.get("ccy", "")).upper()
            quantity = abs(float(row.get("earnings", row.get("amt", 0))))
            events.append(
                {
                    "occurred_at": _iso_from_milliseconds(row.get("ts", end_ms)),
                    "source": "okx",
                    "account": "simple_earn",
                    "remote_id": f"reward:{row.get('ordId', row.get('id'))}:{row.get('ts')}",
                    "event_type": "reward",
                    "asset": asset,
                    "quantity": quantity,
                    "usd_value": quantity if asset in STABLECOINS else None,
                    "from_location": "simple_earn",
                    "to_location": "simple_earn",
                }
            )
        cursor_result = {
            "last_end_ms": end_ms,
            "coverage": "partial" if len(rows) >= 100 else "complete",
        }
        if len(rows) >= 100:
            cursor_result["reason"] = "page_limit_reached"
        return events, cursor_result


class WhiteBitActivitySource:
    source_name = "whitebit"

    def __init__(self, client: Any) -> None:
        self.client = client

    def _request_private(self, endpoint: str, data: dict[str, Any]) -> Any:
        if hasattr(self.client, "request_private"):
            return self.client.request_private(endpoint, data)
        headers, data_json = self.client._generate_auth_headers(endpoint, data)
        response = requests.post(
            f"{self.client.base_url}{endpoint}",
            headers=headers,
            data=data_json,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def fetch_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        start_seconds = int(start_at.timestamp())
        if cursor and cursor.get("last_end_seconds") is not None:
            start_seconds = max(start_seconds, int(cursor["last_end_seconds"]) + 1)
        end_seconds = int(end_at.timestamp())
        response = self._request_private(
            "/api/v4/trade-account/executed-history",
            {"startDate": start_seconds, "endDate": end_seconds, "limit": 100},
        )
        rows = response.get("records", response.get("data", [])) if isinstance(response, dict) else response
        events = [normalize_whitebit_trade(row) for row in rows]
        return events, {
            "last_end_seconds": end_seconds,
            "coverage": "partial",
            "reason": "trade_history_only_manual_transfers_required",
        }

    def fetch_lending_events(
        self,
        start_at: datetime,
        end_at: datetime,
        cursor: Optional[dict[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return [], {
            "last_end_seconds": int(end_at.timestamp()),
            "coverage": "partial",
            "reason": "manual_lending_history_required",
        }
