"""Parser for IB Flex portfolio snapshot XML (OpenPosition + Trade)."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class PositionRecord:
    symbol: str
    shares: float
    cost_basis_price: float
    position_value: float
    asset_category: str
    mark_price: float


@dataclass
class TradeRecord:
    symbol: str
    buy_sell: str
    quantity: float
    trade_price: float
    asset_category: str


@dataclass
class SnapshotData:
    account_id: str
    from_date: str
    to_date: str
    when_generated: str
    positions: Dict[str, PositionRecord]
    trades: List[TradeRecord]

    @property
    def to_date_iso(self) -> Optional[str]:
        if len(self.to_date) == 8:
            return (
                f"{self.to_date[:4]}-{self.to_date[4:6]}-{self.to_date[6:8]}"
            )
        return self.to_date


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_snapshot(file_path: str) -> SnapshotData:
    """Parse a Flex portfolio snapshot XML file."""
    tree = ET.parse(file_path)
    root = tree.getroot()

    flex_statement = None
    for element in root.iter():
        if _strip_ns(element.tag) == "FlexStatement":
            flex_statement = element
            break

    if flex_statement is None:
        raise ValueError(f"No FlexStatement element in {file_path}")

    account_id = flex_statement.attrib.get("accountId", "")
    from_date = flex_statement.attrib.get("fromDate", "")
    to_date = flex_statement.attrib.get("toDate", "")
    when_generated = flex_statement.attrib.get("whenGenerated", "")

    positions: Dict[str, PositionRecord] = {}
    for pos in flex_statement.iter():
        if _strip_ns(pos.tag) != "OpenPosition":
            continue
        symbol = pos.attrib.get("symbol", "")
        if not symbol:
            continue
        positions[symbol] = PositionRecord(
            symbol=symbol,
            shares=float(pos.attrib.get("position", "0") or 0),
            cost_basis_price=float(
                pos.attrib.get("costBasisPrice", "0") or 0
            ),
            position_value=float(
                pos.attrib.get("positionValue", "0") or 0
            ),
            asset_category=pos.attrib.get("assetCategory", ""),
            mark_price=float(pos.attrib.get("markPrice", "0") or 0),
        )

    trades: List[TradeRecord] = []
    for trade in flex_statement.iter():
        if _strip_ns(trade.tag) != "Trade":
            continue
        symbol = trade.attrib.get("symbol", "")
        if not symbol:
            continue
        buy_sell = trade.attrib.get("buySell", "").upper()
        quantity = float(trade.attrib.get("quantity", "0") or 0)
        trade_price = float(trade.attrib.get("tradePrice", "0") or 0)
        asset_category = trade.attrib.get("assetCategory", "")
        trades.append(
            TradeRecord(
                symbol=symbol,
                buy_sell=buy_sell,
                quantity=quantity,
                trade_price=trade_price,
                asset_category=asset_category,
            )
        )

    return SnapshotData(
        account_id=account_id,
        from_date=from_date,
        to_date=to_date,
        when_generated=when_generated,
        positions=positions,
        trades=trades,
    )