import logging
import os
import socket
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional

from src.brokers.ib_models import IBPosition

logger = logging.getLogger(__name__)

DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_PORT = 4001
DEFAULT_CLIENT_ID = 1101
DEFAULT_TIMEOUT = 30
DEFAULT_DATA_WAIT_SECONDS = 10


class IBGatewayUnavailable(RuntimeError):
    pass


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _amount_or_text(value: Any) -> Any:
    try:
        if value in (None, ""):
            return value
        return float(value)
    except (TypeError, ValueError):
        return value


def _contract_description(contract: Any) -> str:
    sec_type = getattr(contract, "secType", None)
    con_id = getattr(contract, "conId", None)
    if sec_type in {"BOND", "BILL"} and con_id:
        return f"IBCID{con_id}"

    for attr in ("localSymbol", "symbol", "description"):
        value = getattr(contract, attr, None)
        if value:
            return str(value)
    if con_id:
        return str(con_id)
    return "UNKNOWN"


def _normalize_portfolio_item(item: Any) -> Dict[str, Any]:
    contract = getattr(item, "contract", None)
    realized_pnl = getattr(item, "realizedPNL", None)
    position = IBPosition(
        contractDesc=_contract_description(contract),
        mktValue=_to_float(getattr(item, "marketValue", 0.0)),
        position=_to_float(getattr(item, "position", 0.0)),
        avgPrice=_to_float(getattr(item, "averageCost", 0.0)),
        mktPrice=_to_float(getattr(item, "marketPrice", 0.0)),
        unrealizedPNL=_to_float(getattr(item, "unrealizedPNL", 0.0)),
        realizedPNL=(
            _to_float(realized_pnl) if realized_pnl not in (None, "") else None
        ),
        currency=getattr(contract, "currency", None),
        conId=_to_int(getattr(contract, "conId", None)),
        secType=getattr(contract, "secType", None),
    )
    return position.as_dict()


def _normalize_position_fallback(
    position: Any, portfolio_by_con_id: Dict[int, Any]
) -> Dict[str, Any]:
    contract = getattr(position, "contract", None)
    con_id = _to_int(getattr(contract, "conId", None))
    portfolio_item = portfolio_by_con_id.get(con_id) if con_id is not None else None
    if portfolio_item is not None:
        return _normalize_portfolio_item(portfolio_item)

    normalized = IBPosition(
        contractDesc=_contract_description(contract),
        mktValue=0.0,
        position=_to_float(getattr(position, "position", 0.0)),
        avgPrice=0.0,
        mktPrice=0.0,
        unrealizedPNL=0.0,
        realizedPNL=None,
        currency=getattr(contract, "currency", None),
        conId=con_id,
        secType=getattr(contract, "secType", None),
    )
    return normalized.as_dict()


class IBGatewayPortfolioLoader:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        self.host = host or os.getenv("IB_GATEWAY_HOST", DEFAULT_GATEWAY_HOST)
        self.port = int(port or os.getenv("IB_GATEWAY_PORT", DEFAULT_GATEWAY_PORT))
        self.client_id = int(
            client_id or os.getenv("IB_GATEWAY_CLIENT_ID", DEFAULT_CLIENT_ID)
        )
        self.timeout = int(timeout or os.getenv("IB_GATEWAY_TIMEOUT", DEFAULT_TIMEOUT))
        self.data_wait_seconds = int(
            os.getenv("IB_GATEWAY_DATA_WAIT_SECONDS", DEFAULT_DATA_WAIT_SECONDS)
        )

    def check_socket_available(self) -> None:
        try:
            with socket.create_connection((self.host, self.port), timeout=3):
                return
        except OSError as exc:
            raise IBGatewayUnavailable(
                f"IB Gateway API unavailable at {self.host}:{self.port}. "
                "Start IB Gateway or enable auto-start service. "
                "Client Portal Gateway is no longer supported."
            ) from exc

    @contextmanager
    def connection(self):
        self.check_socket_available()
        try:
            from ib_insync import IB
        except ImportError as exc:
            raise IBGatewayUnavailable(
                "ib_insync is required for IB Gateway access. "
                "Install project dependencies before running portfolio sync."
            ) from exc

        ib = IB()
        try:
            self._connect_for_account_data(ib)
            if not ib.isConnected():
                raise IBGatewayUnavailable(
                    f"IB Gateway API unavailable at {self.host}:{self.port}. "
                    "Start IB Gateway or enable auto-start service. "
                    "Client Portal Gateway is no longer supported."
                )
            yield ib
        except IBGatewayUnavailable:
            raise
        except Exception as exc:
            raise IBGatewayUnavailable(
                f"IB Gateway API unavailable at {self.host}:{self.port}. "
                "Start IB Gateway or enable auto-start service. "
                "Client Portal Gateway is no longer supported."
            ) from exc
        finally:
            if ib.isConnected():
                self._cancel_account_data(ib)
                ib.disconnect()

    def _connect_for_account_data(self, ib: Any) -> None:
        if os.getenv("IB_GATEWAY_SYNC_CONNECT") == "1":
            ib.connect(
                self.host,
                self.port,
                clientId=self.client_id,
                readonly=True,
                timeout=self.timeout,
            )
            return

        ib.wrapper.clientId = self.client_id
        ib.client.connect(self.host, self.port, self.client_id, timeout=self.timeout)
        account_id = os.getenv("IB_ACCOUNT_ID", "")
        ib.client.reqAccountUpdates(True, account_id)
        ib.client.reqPositions()
        ib.sleep(self.data_wait_seconds)

    @staticmethod
    def _cancel_account_data(ib: Any) -> None:
        try:
            account_id = os.getenv("IB_ACCOUNT_ID", "")
            ib.client.reqAccountUpdates(False, account_id)
        except Exception:
            logger.debug("Unable to cancel IB account updates", exc_info=True)
        try:
            ib.client.cancelPositions()
        except Exception:
            logger.debug("Unable to cancel IB positions request", exc_info=True)

    def fetch_positions(self) -> List[Dict[str, Any]]:
        with self.connection() as ib:
            return self._fetch_positions_from_connection(ib)

    def fetch_account_summary(self) -> Dict[str, Dict[str, Any]]:
        with self.connection() as ib:
            return self._fetch_account_summary_from_connection(ib)

    def fetch_portfolio_snapshot(self) -> tuple:
        with self.connection() as ib:
            summary = self._fetch_account_summary_from_connection(ib)
            positions = self._fetch_positions_from_connection(ib)
            return summary, positions

    def _fetch_positions_from_connection(self, ib: Any) -> List[Dict[str, Any]]:
        portfolio_items = []
        for _ in range(10):
            portfolio_items = list(ib.portfolio())
            if portfolio_items:
                break
            ib.sleep(1)
        if portfolio_items:
            return [_normalize_portfolio_item(item) for item in portfolio_items]

        logger.warning(
            "IB Gateway portfolio rows were empty; falling back to positions. "
            "Market value and P&L may be missing."
        )
        positions = list(self._request_positions(ib))
        portfolio_by_con_id = {
            _to_int(getattr(getattr(item, "contract", None), "conId", None)): item
            for item in list(ib.portfolio())
            if _to_int(getattr(getattr(item, "contract", None), "conId", None))
            is not None
        }
        return [
            _normalize_position_fallback(position, portfolio_by_con_id)
            for position in positions
        ]

    def _request_positions(self, ib: Any) -> Iterable[Any]:
        cached_positions = list(ib.positions())
        if cached_positions:
            return cached_positions
        if os.getenv("IB_GATEWAY_USE_REQ_POSITIONS_FALLBACK") == "1":
            req_positions = getattr(ib, "reqPositions", None)
            if callable(req_positions):
                result = req_positions()
                if result:
                    return result
        return []

    def _fetch_account_summary_from_connection(
        self, ib: Any
    ) -> Dict[str, Dict[str, Any]]:
        for _ in range(10):
            summary = self._normalize_account_values(ib.accountValues())
            if "totalcashvalue" in summary:
                return summary
            ib.sleep(1)

        raise IBGatewayUnavailable(
            "IB Gateway account values did not include TotalCashValue. "
            "Confirm the account is connected and API account updates are enabled."
        )

    @staticmethod
    def _normalize_account_values(values: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        for item in values:
            tag = getattr(item, "tag", None)
            if not tag:
                continue
            value = getattr(item, "value", None)
            key = str(tag).lower()
            normalized[key] = {
                "amount": _amount_or_text(value),
                "currency": getattr(item, "currency", None),
                "account": getattr(item, "account", None),
            }
        return normalized
