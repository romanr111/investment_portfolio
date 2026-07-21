#!/usr/bin/env python3

"""
Portfolio Analysis and Report Generation Module

Analyzes changes in investment portfolios from Interactive Brokers XML exports and generates
reports in text and Markdown formats for Young Investors Club (YIC).

## Usage

### Command Line
```bash
# Generate both text and Markdown reports (default)
python analyze_portfolio_reports.py

# Generate only text report
python analyze_portfolio_reports.py --format text

# Generate only Markdown report
python analyze_portfolio_reports.py --format markdown
```

## Preconditions

1. **Input Files**: Place Interactive Brokers XML exports in the current directory:
   - `stocks_count_trades1.xml` - Initial portfolio state
   - `stocks_count_trades2.xml` - Final portfolio state with transactions included

2. **XML Format**: Files must contain `<FlexStatement>` with `fromDate`/`toDate` and `<OpenPosition>` elements with:
   - `symbol`, `position`, `costBasisPrice`, `positionValue`, `assetCategory`, `markPrice`

3. **Output**: Markdown reports are saved as `portfolio_report_YYYY_qN.md` in the current directory.
"""

# Module for creating Young Investors Club report;
import os
import xml.etree.ElementTree as ET
import glob
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime

# Import bond tickers list
from data.filters_constants import BONDS_VALUES, PRECIOUS_METALS

# Filter out duplicate exchange-specific tickers (e.g., IHYG.L)
BONDS_CORE = [t for t in BONDS_VALUES if "." not in t]
PRECIOUS_METALS_CORE = [t for t in PRECIOUS_METALS if "." not in t]

# Symbols to exclude from main portfolio calculations (displayed separately)
EXCLUDED_SYMBOLS = list(
    dict.fromkeys(
        BONDS_CORE
        + PRECIOUS_METALS_CORE
        + [
            "SGOV",  # Government Money Market Fund
            "COMB",  # Commodity broad ETF
            "SLV",  # Silver ETF
            "BILLS",  # Aggregated Treasury Bills position
        ]
    ).keys()
)

# Special assets to be shown in a separate table (bonds, gold, commodities)
LONG_BONDS_GOLD_COMMODITIES = list(
    dict.fromkeys(
        BONDS_CORE
        + PRECIOUS_METALS_CORE
        + [
            "COMB",  # Commodity broad ETF
            "SLV",  # Silver ETF
            "BILLS",  # Aggregated Treasury Bills position
        ]
    ).keys()
)

# Core symbols for Core/Satellite split (edit to match your rules)
CORE_SYMBOLS = {
    "VOO",
    "QQQ",
    "BRK B",
}

# Chinese equity symbols for China vs. rest split
CHINA_EQUITY_SYMBOLS = {
    "9988",
    "700",
    "KWEB",
    "PDD",
}

HKD_TO_USD_RATE = (
    0.128  # Approximate HKD to USD conversion rate, should be updated with current rate
)
CHINESE_STOCKS = ["9988", "700"]  # Chinese stocks with values in HKD

# Ukrainian translations for portfolio changes
INCREASED = "Збільшив"
DECREASED = "Зменшив"
UNCHANGED = "Без змін"
NEW_POSITION = "Нова позиція"
ELIMINATED = "Закрита позиція"
PORTFOLIO_WEIGHT = "Вага у портфоліо"
AVERAGE_PRICE = "Середня ціна входу"

# Table headers
HEADER_SYMBOL = "Позиція"
HEADER_ACTIVITY = "Остання активність"
HEADER_AVG_PRICE = "Середня ціна входу"
HEADER_WEIGHT = "Вага"

# Activity icons for better readability
ICON_NEW = "🆕"
ICON_INCREASED = "➕"
ICON_DECREASED = "➖"
ICON_UNCHANGED = ""
ICON_ELIMINATED = "✖"


class Stock:
    """Class representing a stock position"""

    def __init__(
        self,
        symbol: str,
        shares: float,
        cost_basis: float,
        position_value: float,
        asset_category: str,
        is_chinese_stock: bool,
        mark_price: float = 0.0,
    ):
        self.symbol = symbol
        self.shares = shares
        self.cost_basis = cost_basis  # Average buy price
        self.position_value = position_value
        self.asset_category = asset_category
        self.is_chinese_stock = is_chinese_stock
        self.mark_price = mark_price  # Current market price
        self.usd_value = self._calculate_usd_value()
        self.weight = 0.0  # Will be calculated later

    def _calculate_usd_value(self) -> float:
        """Calculate position value in USD"""
        return (
            self.position_value * HKD_TO_USD_RATE
            if self.is_chinese_stock
            else self.position_value
        )

    def is_excluded(self) -> bool:
        """Check if stock should be excluded from weight calculations"""
        return self.symbol in EXCLUDED_SYMBOLS or self.asset_category == "BILL"

    def set_weight(self, total_portfolio_value: float) -> None:
        """Set the weight of stock in the portfolio"""
        if total_portfolio_value > 0:
            self.weight = (self.usd_value / total_portfolio_value) * 100
        else:
            self.weight = 0

    def get_price_change_pct(self) -> float:
        """Calculate percentage change between cost basis and current market price"""
        if self.cost_basis > 0 and self.mark_price > 0:
            return ((self.mark_price - self.cost_basis) / self.cost_basis) * 100
        return 0.0


class TradeSummary:
    """Class representing aggregated trade data for a symbol"""

    def __init__(self):
        self.total_quantity = 0.0
        self.weighted_price_sum = 0.0

    def add_trade(self, quantity: float, price: float) -> None:
        """Add a trade to the summary"""
        self.total_quantity += quantity
        self.weighted_price_sum += quantity * price

    def average_price(self) -> float:
        """Return the weighted average price"""
        if self.total_quantity > 0:
            return self.weighted_price_sum / self.total_quantity
        return 0.0


class TreasuryBillsAggregate:
    """Class representing aggregated Treasury Bills position"""

    def __init__(self):
        self.symbol = "BILLS"
        self.total_value = 0.0
        self.weighted_avg_price = 0.0
        self.individual_bills = []  # List of individual BILL positions
        self.asset_category = "BILL"
        self.is_chinese_stock = False
        self.weight = 0.0

    def add_bill(self, stock: Stock) -> None:
        """Add an individual Treasury Bill to the aggregate"""
        if stock.asset_category == "BILL":
            self.individual_bills.append(stock)
            self.total_value += stock.usd_value

    def calculate_weighted_average_price(self) -> None:
        """Calculate weighted average price of all Treasury Bills"""
        total_nominal_value = 0.0
        weighted_price_sum = 0.0

        for bill in self.individual_bills:
            nominal_value = bill.shares
            total_nominal_value += nominal_value
            weighted_price_sum += bill.cost_basis * nominal_value

        if total_nominal_value > 0:
            self.weighted_avg_price = weighted_price_sum / total_nominal_value
        else:
            self.weighted_avg_price = 0.0

    @property
    def usd_value(self) -> float:
        """Get total USD value of all Treasury Bills"""
        return self.total_value

    def set_weight(self, total_portfolio_value: float) -> None:
        """Set the weight of Treasury Bills in the portfolio"""
        if total_portfolio_value > 0:
            self.weight = (self.usd_value / total_portfolio_value) * 100
        else:
            self.weight = 0


class Portfolio:
    """Class representing a portfolio of stocks"""

    def __init__(self, portfolio_date: str):
        self.date = portfolio_date
        self.stocks: Dict[str, Stock] = {}
        self.treasury_bills: Optional[TreasuryBillsAggregate] = None
        self.sell_trades: Dict[str, TradeSummary] = {}

    def add_stock(self, stock: Stock) -> None:
        """Add a stock to the portfolio"""
        if stock.asset_category == "BILL":
            # Aggregate Treasury Bills
            if self.treasury_bills is None:
                self.treasury_bills = TreasuryBillsAggregate()
            self.treasury_bills.add_bill(stock)
        else:
            self.stocks[stock.symbol] = stock

    def get_stock(self, symbol: str) -> Optional[Stock]:
        """Get a stock by symbol"""
        if symbol == "BILLS" and self.treasury_bills:
            return self.treasury_bills
        return self.stocks.get(symbol)

    def add_sell_trade(self, symbol: str, quantity: float, price: float) -> None:
        """Add a sell trade to the portfolio trade summary"""
        if quantity <= 0 or price <= 0:
            return
        summary = self.sell_trades.get(symbol)
        if summary is None:
            summary = TradeSummary()
            self.sell_trades[symbol] = summary
        summary.add_trade(quantity, price)

    def get_avg_sell_price(self, symbol: str) -> float:
        """Get the weighted average sell price for a symbol"""
        summary = self.sell_trades.get(symbol)
        return summary.average_price() if summary else 0.0

    def get_symbols(self) -> Set[str]:
        """Get all stock symbols in portfolio"""
        symbols = set(self.stocks.keys())
        if self.treasury_bills and self.treasury_bills.total_value > 0:
            symbols.add("BILLS")
        return symbols

    def calculate_weights(self) -> None:
        """Calculate weights of all stocks in portfolio"""
        total_value = self.get_total_value()

        for stock in self.stocks.values():
            stock.set_weight(total_value)

        if self.treasury_bills:
            self.treasury_bills.calculate_weighted_average_price()
            self.treasury_bills.set_weight(total_value)

    def get_total_value(self) -> float:
        """Calculate total value of portfolio (excluding certain assets)"""
        total = 0.0
        for stock in self.stocks.values():
            if not stock.is_excluded():
                total += stock.usd_value
        return total


class PortfolioAnalyzer:
    """Class for analyzing portfolio changes"""

    def __init__(self, initial_portfolio: Portfolio, final_portfolio: Portfolio):
        self.initial_portfolio = initial_portfolio
        self.final_portfolio = final_portfolio
        self.activity_counts = {
            "increased": 0,
            "decreased": 0,
            "unchanged": 0,
            "new": 0,
            "eliminated": 0,
        }

        # Special cases - hardcoded values
        self.hardcoded_prices = {
            "9988": 152.7,  # Hardcoded average buying price for 9988
        }

    def get_all_symbols(self) -> Set[str]:
        """Get all symbols from both portfolios"""
        return self.initial_portfolio.get_symbols().union(
            self.final_portfolio.get_symbols()
        )

    def analyze_change(self, symbol: str) -> Tuple[str, float, float, float]:
        """Analyze change for a specific stock"""
        initial_stock = self.initial_portfolio.get_stock(symbol)
        final_stock = self.final_portfolio.get_stock(symbol)

        activity = ""
        avg_price = 0.0
        weight = 0.0
        price_change_pct = 0.0

        # Special handling for Treasury Bills aggregate
        if symbol == "BILLS":
            return self._analyze_treasury_bills_change()

        # Both initial and final
        if initial_stock and final_stock:
            pct_change = (
                (final_stock.shares - initial_stock.shares) / initial_stock.shares * 100
                if initial_stock.shares > 0
                else 0
            )

            if pct_change > 0:
                activity = (
                    f"{ICON_INCREASED} {INCREASED} (+{int(round(abs(pct_change)))}%)"
                )
                self.activity_counts["increased"] += 1
            elif pct_change < 0:
                activity = (
                    f"{ICON_DECREASED} {DECREASED} (-{int(round(abs(pct_change)))}%)"
                )
                self.activity_counts["decreased"] += 1
            else:
                activity = f"{ICON_UNCHANGED} {UNCHANGED}"
                self.activity_counts["unchanged"] += 1

            # Handle special case for 9988
            if symbol in self.hardcoded_prices:
                avg_price = self.hardcoded_prices[symbol]
                # Calculate P&L with hardcoded price and current mark price
                if final_stock.mark_price > 0:
                    price_change_pct = (
                        (final_stock.mark_price - avg_price) / avg_price
                    ) * 100
            else:
                avg_price = final_stock.cost_basis
                price_change_pct = final_stock.get_price_change_pct()

            weight = final_stock.weight

        # Eliminated position
        elif initial_stock and not final_stock:
            activity = f"{ICON_ELIMINATED} {ELIMINATED}"

            # Handle special case for 9988
            if symbol in self.hardcoded_prices:
                avg_price = self.hardcoded_prices[symbol]
            else:
                avg_price = initial_stock.cost_basis

            sell_avg_price = self.final_portfolio.get_avg_sell_price(symbol)
            if avg_price > 0 and sell_avg_price > 0:
                price_change_pct = ((sell_avg_price - avg_price) / avg_price) * 100

            self.activity_counts["eliminated"] += 1

        # New position
        elif final_stock and not initial_stock:
            activity = f"{ICON_NEW} {NEW_POSITION}"

            # Handle special case for 9988
            if symbol in self.hardcoded_prices:
                avg_price = self.hardcoded_prices[symbol]
                # Calculate P&L with hardcoded price and current mark price
                if final_stock.mark_price > 0:
                    price_change_pct = (
                        (final_stock.mark_price - avg_price) / avg_price
                    ) * 100
            else:
                avg_price = final_stock.cost_basis
                price_change_pct = final_stock.get_price_change_pct()

            weight = final_stock.weight
            self.activity_counts["new"] += 1

        return activity, avg_price, weight, price_change_pct

    def _analyze_treasury_bills_change(self) -> Tuple[str, float, float, float]:
        """Analyze change for aggregated Treasury Bills positions"""
        initial_bills = self.initial_portfolio.treasury_bills
        final_bills = self.final_portfolio.treasury_bills

        activity = ""
        avg_price = 0.0
        weight = 0.0
        price_change_pct = 0.0

        # Both periods have Treasury Bills
        if initial_bills and final_bills:
            # Compare total values
            value_change_pct = (
                (final_bills.total_value - initial_bills.total_value)
                / initial_bills.total_value
                * 100
                if initial_bills.total_value > 0
                else 0
            )

            if value_change_pct > 5:  # Threshold for significant change
                activity = f"{ICON_INCREASED} {INCREASED} (+{int(round(abs(value_change_pct)))}%)"
                self.activity_counts["increased"] += 1
            elif value_change_pct < -5:
                activity = f"{ICON_DECREASED} {DECREASED} (-{int(round(abs(value_change_pct)))}%)"
                self.activity_counts["decreased"] += 1
            else:
                activity = f"{ICON_UNCHANGED} {UNCHANGED}"
                self.activity_counts["unchanged"] += 1

            avg_price = final_bills.weighted_avg_price
            weight = final_bills.weight

        # Treasury Bills eliminated
        elif initial_bills and not final_bills:
            activity = f"{ICON_ELIMINATED} {ELIMINATED}"
            avg_price = initial_bills.weighted_avg_price
            self.activity_counts["eliminated"] += 1

        # New Treasury Bills position
        elif final_bills and not initial_bills:
            activity = f"{ICON_NEW} {NEW_POSITION}"
            avg_price = final_bills.weighted_avg_price
            weight = final_bills.weight
            self.activity_counts["new"] += 1

        return activity, avg_price, weight, price_change_pct


class XMLPortfolioParser:
    """Class for parsing portfolio data from XML files"""

    @staticmethod
    def parse(file_path: str) -> Tuple[Portfolio, str, str]:
        """Parse XML file and create a Portfolio"""
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Extract date information
        flex_statement = root.find(".//FlexStatement")
        from_date = flex_statement.attrib.get("fromDate", "")
        to_date = flex_statement.attrib.get("toDate", "")

        # Use the to_date as the portfolio date
        portfolio = Portfolio(to_date)

        for position in root.findall(".//OpenPosition"):
            symbol = position.attrib.get("symbol", "")
            shares = float(position.attrib.get("position", "0"))
            cost_basis = float(position.attrib.get("costBasisPrice", "0"))
            position_value = float(position.attrib.get("positionValue", "0"))
            asset_category = position.attrib.get("assetCategory", "")
            mark_price = float(position.attrib.get("markPrice", "0"))

            is_chinese_stock = symbol in CHINESE_STOCKS

            stock = Stock(
                symbol=symbol,
                shares=shares,
                cost_basis=cost_basis,
                position_value=position_value,
                asset_category=asset_category,
                is_chinese_stock=is_chinese_stock,
                mark_price=mark_price,
            )

            portfolio.add_stock(stock)

        for trade in root.findall(".//Trade"):
            symbol = trade.attrib.get("symbol", "")
            if not symbol:
                continue

            buy_sell = trade.attrib.get("buySell", "").upper()
            quantity = float(trade.attrib.get("quantity", "0"))
            trade_price = float(trade.attrib.get("tradePrice", "0"))

            is_sell = buy_sell == "SELL" or quantity < 0
            if not is_sell:
                continue

            sell_quantity = abs(quantity)
            portfolio.add_sell_trade(symbol, sell_quantity, trade_price)

        return portfolio, from_date, to_date

    @staticmethod
    def _merge_trades_into(file_path: str, portfolio: Portfolio) -> None:
        """Parse a supplemental trades-only Flex export and add sell trades."""
        tree = ET.parse(file_path)
        root = tree.getroot()

        for trade in root.findall(".//Trade"):
            symbol = trade.attrib.get("symbol", "")
            if not symbol:
                continue

            buy_sell = trade.attrib.get("buySell", "").upper()
            quantity = float(trade.attrib.get("quantity", "0"))
            trade_price = float(trade.attrib.get("tradePrice", "0"))

            is_sell = buy_sell == "SELL" or quantity < 0
            if not is_sell:
                continue

            sell_quantity = abs(quantity)
            portfolio.add_sell_trade(symbol, sell_quantity, trade_price)


class TableFormatter:
    """Class for formatting portfolio data as a table"""

    def __init__(self, analyzer: PortfolioAnalyzer, format_type="text"):
        self.analyzer = analyzer
        self.format_type = format_type  # "text" or "markdown"
        # Fixed column widths
        self.symbol_width = 8
        self.activity_width = 24
        self.price_width = 32
        self.weight_width = 14

    def _display_symbol(self, symbol: str) -> str:
        """Return the user-facing label for a given ticker."""
        return "T Bills" if symbol == "BILLS" else symbol

    def _format_price_cell(self, symbol: str, avg_price: float) -> str:
        """Format entry/exit prices with P&L percentage."""
        if avg_price <= 0:
            return "-"

        final_stock = self.analyzer.final_portfolio.get_stock(symbol)
        if final_stock:
            target_price = float(getattr(final_stock, "mark_price", 0.0))
            if target_price <= 0:
                return f"{avg_price:.2f}$"
            pct_change = ((target_price - avg_price) / avg_price) * 100
            sign = "+" if pct_change > 0 else ""
            if abs(pct_change) < 1:
                pct_str = f"{sign}{pct_change:.1f}%"
            else:
                pct_str = f"{sign}{pct_change:.0f}%"
            return f"{avg_price:.2f}$ ({pct_str})"

        target_price = self.analyzer.final_portfolio.get_avg_sell_price(symbol)
        if target_price > 0:
            pct_change = ((target_price - avg_price) / avg_price) * 100
            sign = "+" if pct_change > 0 else ""
            if abs(pct_change) < 1:
                pct_str = f"{sign}{pct_change:.1f}%"
            else:
                pct_str = f"{sign}{pct_change:.0f}%"
            return f"{avg_price:.2f}$ → {target_price:.2f}$ (Exit) ({pct_str})"

        return f"{avg_price:.2f}$"

    def _format_weight_cell(self, symbol: str) -> Tuple[str, float]:
        """Format weight for open and closed positions."""
        initial_stock = self.analyzer.initial_portfolio.get_stock(symbol)
        final_stock = self.analyzer.final_portfolio.get_stock(symbol)

        if final_stock:
            weight = final_stock.weight
            return (f"{weight:.2f}%" if weight > 0 else "-"), weight

        if initial_stock:
            weight = initial_stock.weight
            if weight > 0:
                return f"{weight:.2f}% → 0%", 0.0

        return "-", 0.0

    def _calculate_core_satellite_ratio(self) -> Tuple[float, float]:
        """Calculate Core/Satellite split for equity positions."""
        core_value = 0.0
        total_value = 0.0

        for stock in self.analyzer.final_portfolio.stocks.values():
            if stock.is_excluded():
                continue
            total_value += stock.usd_value
            if stock.symbol in CORE_SYMBOLS:
                core_value += stock.usd_value

        if total_value <= 0:
            return 0.0, 0.0

        core_pct = (core_value / total_value) * 100
        satellite_pct = 100 - core_pct
        return core_pct, satellite_pct

    def _calculate_china_ratio(self) -> Tuple[float, float]:
        """Calculate China vs. rest split for equity positions."""
        china_value = 0.0
        total_value = 0.0

        for stock in self.analyzer.final_portfolio.stocks.values():
            if stock.is_excluded():
                continue
            total_value += stock.usd_value
            if stock.symbol in CHINA_EQUITY_SYMBOLS:
                china_value += stock.usd_value

        if total_value <= 0:
            return 0.0, 0.0

        china_pct = (china_value / total_value) * 100
        rest_pct = 100 - china_pct
        return china_pct, rest_pct

    def format_as_table(self) -> str:
        """Format portfolio analysis as a table based on format_type"""
        if self.format_type == "markdown":
            return self._format_as_markdown_table()
        else:
            return self._format_as_text_table()

    def _format_as_text_table(self) -> str:
        """Format portfolio analysis as a simple text table without box characters"""
        output_data = []
        all_symbols = self.analyzer.get_all_symbols()

        # Create table header with simple ASCII
        header = f"{HEADER_SYMBOL.ljust(self.symbol_width)}  {HEADER_ACTIVITY.ljust(self.activity_width)}  {HEADER_AVG_PRICE.ljust(self.price_width)}  {HEADER_WEIGHT.ljust(self.weight_width)}"
        separator = f"{'-' * self.symbol_width}  {'-' * self.activity_width}  {'-' * self.price_width}  {'-' * self.weight_width}"

        table_lines = [header, separator]

        for symbol in all_symbols:
            if self._should_skip(symbol):
                continue

            activity, avg_price, _, _ = self.analyzer.analyze_change(symbol)

            # Format values with fixed width
            symbol_display = self._display_symbol(symbol)
            symbol_str = symbol_display[: self.symbol_width].ljust(self.symbol_width)
            activity_str = activity[: self.activity_width].ljust(self.activity_width)

            price_str = self._format_price_cell(symbol, avg_price).ljust(
                self.price_width
            )

            weight_str, weight_sort = self._format_weight_cell(symbol)
            weight_str = weight_str.ljust(self.weight_width)

            # Create row
            row = f"{symbol_str}  {activity_str}  {price_str}  {weight_str}"
            output_data.append((weight_sort, row))

        # Sort by weight in descending order
        output_data.sort(reverse=True)

        # Add sorted rows to table
        table_lines.extend([data[1] for data in output_data])

        # Add separator before summary
        table_lines.append(separator)

        # Format activity summary
        activity_summary = (
            f"↑{self.analyzer.activity_counts['increased']} "
            f"↓{self.analyzer.activity_counts['decreased']} "
            f"={self.analyzer.activity_counts['unchanged']} "
            f"+{self.analyzer.activity_counts['new']} "
            f"-{self.analyzer.activity_counts['eliminated']}"
        )

        # Add summary row
        summary = f"{'Підсумок'.ljust(self.symbol_width)}  {activity_summary.ljust(self.activity_width)}  {''.ljust(self.price_width)}  {'100.00%'.ljust(self.weight_width)}"
        table_lines.append(summary)

        # Add legend
        table_lines.append("Примітка: комісії, дивіденди та FX не враховані.")
        table_lines.append("")
        table_lines.append("Для закритих позицій друга ціна — середня ціна виходу.")
        table_lines.append("")
        core_pct, satellite_pct = self._calculate_core_satellite_ratio()
        table_lines.append(
            f"Співвідношення Core/Satellite (акції): {core_pct:.2f}% / {satellite_pct:.2f}%."
        )
        table_lines.append("")
        china_pct, rest_pct = self._calculate_china_ratio()
        table_lines.append(
            f"Співвідношення Китай/Інші (акції): {china_pct:.2f}% / {rest_pct:.2f}%."
        )
        table_lines.append("")

        # Add total value
        total_value = self.analyzer.final_portfolio.get_total_value()
        total_line = (
            "Загальна вартість всіх акцій (в USD, без облігацій, золота та "
            f"товарних активів): {total_value:,.2f}$"
        )
        table_lines.append(total_line)

        # Add special assets table
        special_assets_table = self._format_special_assets_table_text()
        if special_assets_table:
            table_lines.append("")
            table_lines.append("")
            table_lines.append("Облігації, золото та товарні активи")
            table_lines.append("")
            table_lines.append(special_assets_table)

        return "\n".join(table_lines)

    def _format_special_assets_table_text(self) -> str:
        """Format a separate table for special asset categories with changes only in text format"""
        special_data = []

        # Create table header
        header = f"{HEADER_SYMBOL.ljust(self.symbol_width)}  {HEADER_ACTIVITY.ljust(self.activity_width)}  {HEADER_AVG_PRICE.ljust(self.price_width)}  {'Вага (IBKR активи)'.ljust(self.weight_width)}"
        separator = f"{'-' * self.symbol_width}  {'-' * self.activity_width}  {'-' * self.price_width}  {'-' * self.weight_width}"

        table_lines = [header, separator]

        # Get all symbols that actually exist in either portfolio
        all_existing_symbols = self.analyzer.initial_portfolio.get_symbols().union(
            self.analyzer.final_portfolio.get_symbols()
        )

        # Calculate weight base for special assets once
        stocks_total = self.analyzer.final_portfolio.get_total_value()
        special_assets_value = 0
        for special_symbol in LONG_BONDS_GOLD_COMMODITIES:
            special_stock = self.analyzer.final_portfolio.get_stock(
                special_symbol
            ) or self.analyzer.initial_portfolio.get_stock(special_symbol)
            if special_stock:
                special_assets_value += special_stock.usd_value
        total_portfolio_value = stocks_total + special_assets_value

        # Check each special asset
        for symbol in LONG_BONDS_GOLD_COMMODITIES:
            # Skip if symbol doesn't exist in either portfolio
            if symbol not in all_existing_symbols:
                continue

            activity, avg_price, _, _ = self.analyzer.analyze_change(symbol)

            # Format values for the table
            symbol_display = self._display_symbol(symbol)
            symbol_str = symbol_display.ljust(self.symbol_width)
            activity_str = activity.ljust(self.activity_width)

            price_str = self._format_price_cell(symbol, avg_price).ljust(
                self.price_width
            )

            initial_stock = self.analyzer.initial_portfolio.get_stock(symbol)
            final_stock = self.analyzer.final_portfolio.get_stock(symbol)
            weight_sort = 0.0

            if final_stock and total_portfolio_value > 0:
                weight = (final_stock.usd_value / total_portfolio_value) * 100
                weight_str = f"{weight:.2f}%" if weight > 0 else "-"
                weight_sort = weight
            elif initial_stock and total_portfolio_value > 0:
                weight = (initial_stock.usd_value / total_portfolio_value) * 100
                weight_str = f"{weight:.2f}% → 0%" if weight > 0 else "-"
                weight_sort = 0.0
            else:
                weight_str = "-"

            weight_str = weight_str.ljust(self.weight_width)

            # Create row
            row = f"{symbol_str}  {activity_str}  {price_str}  {weight_str}"
            special_data.append((weight_sort, row))

        # Sort by weight in descending order
        special_data.sort(reverse=True)

        # Only show the table if there are assets with changes
        if not special_data:
            return ""

        # Add sorted rows to table
        table_lines.extend([data[1] for data in special_data])

        return "\n".join(table_lines)

    def _format_as_markdown_table(self) -> str:
        """Format portfolio analysis as a Markdown table for better compatibility"""
        output_data = []
        all_symbols = self.analyzer.get_all_symbols()

        # Create Markdown table header
        header = f"| {HEADER_SYMBOL} | {HEADER_ACTIVITY} | {HEADER_AVG_PRICE} | {HEADER_WEIGHT} |"
        separator = f"|{'-' * (self.symbol_width + 2)}|{'-' * (self.activity_width + 2)}|{'-' * (self.price_width + 2)}|{'-' * (self.weight_width + 2)}|"

        table_lines = [header, separator]

        for symbol in all_symbols:
            if self._should_skip(symbol):
                continue

            activity, avg_price, _, _ = self.analyzer.analyze_change(symbol)

            # Format values for markdown table
            price_str = self._format_price_cell(symbol, avg_price)

            weight_str, weight_sort = self._format_weight_cell(symbol)

            # Create markdown row
            symbol_display = self._display_symbol(symbol)
            row = f"| {symbol_display} | {activity} | {price_str} | {weight_str} |"
            output_data.append((weight_sort, row))

        # Sort by weight in descending order
        output_data.sort(reverse=True)

        # Add sorted rows to table
        table_lines.extend([data[1] for data in output_data])

        # Format activity summary - use the same counts as in text formatter
        activity_summary = (
            f"↑{self.analyzer.activity_counts['increased']} "
            f"↓{self.analyzer.activity_counts['decreased']} "
            f"={self.analyzer.activity_counts['unchanged']} "
            f"+{self.analyzer.activity_counts['new']} "
            f"-{self.analyzer.activity_counts['eliminated']}"
        )

        # Add summary row without separator after it
        summary = f"| **Підсумок** | {activity_summary} | | **100.00%** |"
        table_lines.append(summary)

        # Add legend
        table_lines.append("")
        table_lines.append("Примітка: комісії, дивіденди та FX не враховані.")
        table_lines.append("")
        table_lines.append("Для закритих позицій друга ціна — середня ціна виходу.")
        table_lines.append("")
        core_pct, satellite_pct = self._calculate_core_satellite_ratio()
        table_lines.append(
            f"Співвідношення Core/Satellite (акції): {core_pct:.2f}% / {satellite_pct:.2f}%."
        )
        table_lines.append("")
        china_pct, rest_pct = self._calculate_china_ratio()
        table_lines.append(
            f"Співвідношення Китай/Інші (акції): {china_pct:.2f}% / {rest_pct:.2f}%."
        )
        table_lines.append("")

        # Add total value
        total_value = self.analyzer.final_portfolio.get_total_value()
        total_line = (
            "**Загальна вартість всіх акцій (в USD, без облігацій, золота та "
            f"товарних активів): {total_value:,.2f}$**"
        )
        table_lines.append(total_line)

        # Add special assets table
        special_assets_table = self._format_special_assets_table()
        if special_assets_table:
            table_lines.append("")
            table_lines.append("")
            table_lines.append("## Облігації, золото та товарні активи")
            table_lines.append("")
            table_lines.append(special_assets_table)

        return "\n".join(table_lines)

    def _format_special_assets_table(self) -> str:
        """Format a separate table for special asset categories with changes only"""
        special_data = []

        # Create Markdown table header for special assets
        header = f"| {HEADER_SYMBOL} | {HEADER_ACTIVITY} | {HEADER_AVG_PRICE} | Вага (IBKR активи) |"
        separator = f"|{'-' * (self.symbol_width + 2)}|{'-' * (self.activity_width + 2)}|{'-' * (self.price_width + 2)}|{'-' * (self.weight_width + 2)}|"

        table_lines = [header, separator]

        # Get all symbols that actually exist in either portfolio
        all_existing_symbols = self.analyzer.initial_portfolio.get_symbols().union(
            self.analyzer.final_portfolio.get_symbols()
        )

        # Calculate weight base for special assets once
        stocks_total = self.analyzer.final_portfolio.get_total_value()
        special_assets_value = 0
        for special_symbol in LONG_BONDS_GOLD_COMMODITIES:
            special_stock = self.analyzer.final_portfolio.get_stock(
                special_symbol
            ) or self.analyzer.initial_portfolio.get_stock(special_symbol)
            if special_stock:
                special_assets_value += special_stock.usd_value
        total_portfolio_value = stocks_total + special_assets_value

        # Check each special asset
        for symbol in LONG_BONDS_GOLD_COMMODITIES:
            # Skip if symbol doesn't exist in either portfolio
            if symbol not in all_existing_symbols:
                continue

            activity, avg_price, _, _ = self.analyzer.analyze_change(symbol)

            # Skip if no meaningful data (empty activity and zero price means position doesn't exist)
            if not activity.strip() and avg_price == 0.0:
                continue

            # Format values for the table
            price_str = self._format_price_cell(symbol, avg_price)

            initial_stock = self.analyzer.initial_portfolio.get_stock(symbol)
            final_stock = self.analyzer.final_portfolio.get_stock(symbol)
            weight_sort = 0.0

            if final_stock and total_portfolio_value > 0:
                weight = (final_stock.usd_value / total_portfolio_value) * 100
                weight_str = f"{weight:.2f}%" if weight > 0 else "-"
                weight_sort = weight
            elif initial_stock and total_portfolio_value > 0:
                weight = (initial_stock.usd_value / total_portfolio_value) * 100
                weight_str = f"{weight:.2f}% → 0%" if weight > 0 else "-"
                weight_sort = 0.0
            else:
                weight_str = "-"

            # Create row
            symbol_display = self._display_symbol(symbol)
            row = f"| {symbol_display} | {activity} | {price_str} | {weight_str} |"
            special_data.append((weight_sort, row))

        # Sort by weight in descending order
        special_data.sort(reverse=True)

        # Only show the table if there are assets with changes
        if not special_data:
            return ""

        # Add sorted rows to table
        table_lines.extend([data[1] for data in special_data])

        return "\n".join(table_lines)

    def _should_skip(self, symbol: str) -> bool:
        """Check if symbol should be skipped in output"""
        initial_stock = self.analyzer.initial_portfolio.get_stock(symbol)
        final_stock = self.analyzer.final_portfolio.get_stock(symbol)

        # Special assets are shown in their own table,
        # but we don't want to skip them completely
        if symbol in LONG_BONDS_GOLD_COMMODITIES:
            # We want these symbols to be processed for the special assets table,
            # but still skip them in the main table
            return True

        # Check if it's an excluded symbol (other than special assets)
        if symbol in EXCLUDED_SYMBOLS:
            return True

        # Check if it's a BILL in either portfolio
        is_bill = (initial_stock and initial_stock.asset_category == "BILL") or (
            final_stock and final_stock.asset_category == "BILL"
        )

        return is_bill


def format_date_with_quarter(date_str: str) -> str:
    """
    Format date string YYYYMMDD to display with quarter and year
    Example: "20250101" -> "1-й квартал 2025 року"
    """
    if not date_str or len(date_str) != 8:
        return date_str

    try:
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        year = date_obj.year
        month = date_obj.month

        # Determine quarter
        quarter = (month - 1) // 3 + 1

        # Use correct ukrainian suffix for the quarter number
        suffix = "-й"
        if quarter == 3:
            suffix = "-ій"

        return f"{quarter}{suffix} квартал {year} року"
    except ValueError:
        # If date format is not as expected, return original
        return date_str


def generate_report_filename(date_str: str) -> str:
    """
    Generate a filename for the markdown report based on the date
    Example: "20250101" -> "portfolio_report_2025_q1.md"
    """
    if not date_str or len(date_str) != 8:
        return "portfolio_report.md"

    try:
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        year = date_obj.year
        quarter = (date_obj.month - 1) // 3 + 1
        return f"portfolio_report_{year}_q{quarter}.md"
    except ValueError:
        return "portfolio_report.md"


class PortfolioReportGenerator:
    """Generates portfolio comparison reports in text or Markdown format."""

    def __init__(
        self,
        initial_portfolio: Portfolio,
        final_portfolio: Portfolio,
        format_type: str = "text",
    ) -> None:
        self.analyzer = PortfolioAnalyzer(initial_portfolio, final_portfolio)
        self.formatter = TableFormatter(self.analyzer, format_type=format_type)
        self.format_type = format_type

    def generate(self) -> str:
        """Generate the report as a string."""
        return self.formatter.format_as_table()

    def save_markdown(self, output_path: Path, title: str) -> None:
        """Save the Markdown report to the given path with a title."""
        report = self.generate()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"\n # {title}\n\n")
            f.write(report)


def load_portfolios(
    base_dir: Path,
) -> Optional[Tuple[Portfolio, Portfolio, str, str]]:
    """
    Discover the Flex XML exports in base_dir, parse them, apply hardcoded
    one-off adjustments, and return weighted portfolios with period dates.

    Shared by the Markdown report (main) and the quarterly HTML generator so
    the one-off adjustments live in exactly one place.

    Returns (initial_portfolio, final_portfolio, initial_to_date,
    final_to_date) or None when the input files are missing.

    If a `stocks_trades_quarterly_YYYY_qN.xml` file is present, its `<Trade>`
    elements are merged into the final portfolio so closed positions can show
    realized P/L.
    """
    matching_files = list(base_dir.glob("stocks_count*.xml"))

    initial_file = None
    final_file = None
    for path in matching_files:
        name = path.name
        if name.endswith("1.xml"):
            initial_file = path
        elif name.endswith("2.xml"):
            final_file = path

    if not initial_file or not final_file:
        print("Error: Could not find required files in", base_dir)
        print("Expected: stocks_count1.xml (initial) and stocks_count2.xml (final)")
        return None

    print(f"Analyzing positions from {initial_file.name} to {final_file.name}...")

    # Parse portfolio data
    parser = XMLPortfolioParser()
    initial_portfolio, initial_from_date, initial_to_date = parser.parse(
        str(initial_file)
    )
    final_portfolio, final_from_date, final_to_date = parser.parse(str(final_file))

    # Merge supplemental quarterly trades if available
    for trades_path in sorted(base_dir.glob("stocks_trades_quarterly_*.xml")):
        parser._merge_trades_into(str(trades_path), final_portfolio)
        print(f"Merged trades from {trades_path.name}")

    # Calculate portfolio weights
    initial_portfolio.calculate_weights()
    final_portfolio.calculate_weights()

    return initial_portfolio, final_portfolio, initial_to_date, final_to_date


def _activity_kind(activity: str) -> Tuple[str, str]:
    """Map an activity string with icon prefix to (kind, text without icon)."""
    for icon, kind in (
        (ICON_NEW, "new"),
        (ICON_INCREASED, "increased"),
        (ICON_DECREASED, "decreased"),
        (ICON_ELIMINATED, "closed"),
    ):
        if icon and activity.startswith(icon):
            return kind, activity[len(icon):].strip()
    return "unchanged", activity.strip()


def collect_stock_rows(analyzer: PortfolioAnalyzer) -> List[Dict]:
    """
    Structured stock rows for the HTML report: open positions sorted by
    weight descending, then closed positions, price and P/L as separate
    fields. Mirrors the row logic of the Markdown table.
    """
    formatter = TableFormatter(analyzer)
    open_rows = []
    closed_rows = []

    for symbol in analyzer.get_all_symbols():
        if formatter._should_skip(symbol):
            continue

        activity, avg_price, _, pl_pct = analyzer.analyze_change(symbol)
        kind, activity_text = _activity_kind(activity)
        symbol_display = formatter._display_symbol(symbol)

        if kind == "closed":
            weight_text, _ = formatter._format_weight_cell(symbol)
            sell_price = analyzer.final_portfolio.get_avg_sell_price(symbol)
            if avg_price > 0 and sell_price > 0:
                price_text = f"{avg_price:.2f}$ → {sell_price:.2f}$"
            elif avg_price > 0:
                price_text = f"{avg_price:.2f}$"
            else:
                price_text = "-"
            initial_stock = analyzer.initial_portfolio.get_stock(symbol)
            closed_rows.append(
                (
                    initial_stock.weight if initial_stock else 0.0,
                    {
                        "symbol": symbol_display,
                        "kind": kind,
                        "activity_text": activity_text,
                        "weight_text": weight_text,
                        "price_text": price_text,
                        "pl_pct": pl_pct if avg_price > 0 and sell_price > 0 else None,
                    },
                )
            )
        else:
            final_stock = analyzer.final_portfolio.get_stock(symbol)
            weight = final_stock.weight if final_stock else 0.0
            open_rows.append(
                (
                    weight,
                    {
                        "symbol": symbol_display,
                        "kind": kind,
                        "activity_text": activity_text,
                        "weight_pct": weight,
                        "price_text": f"{avg_price:.2f}$" if avg_price > 0 else "-",
                        "pl_pct": pl_pct if avg_price > 0 else None,
                    },
                )
            )

    open_rows.sort(key=lambda item: item[0], reverse=True)
    closed_rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in open_rows] + [row for _, row in closed_rows]


def collect_special_asset_rows(analyzer: PortfolioAnalyzer) -> List[Dict]:
    """
    Structured bond/gold/commodity rows for the HTML report. Weights use the
    same base as the Markdown special-assets table: stocks total plus special
    assets total (IBKR subset). Price and P/L columns mirror collect_stock_rows
    so both IBKR tables share the same column format.
    """
    formatter = TableFormatter(analyzer)

    all_existing_symbols = analyzer.initial_portfolio.get_symbols().union(
        analyzer.final_portfolio.get_symbols()
    )

    stocks_total = analyzer.final_portfolio.get_total_value()
    special_assets_value = 0
    for special_symbol in LONG_BONDS_GOLD_COMMODITIES:
        special_stock = analyzer.final_portfolio.get_stock(
            special_symbol
        ) or analyzer.initial_portfolio.get_stock(special_symbol)
        if special_stock:
            special_assets_value += special_stock.usd_value
    total_portfolio_value = stocks_total + special_assets_value

    rows = []
    for symbol in LONG_BONDS_GOLD_COMMODITIES:
        if symbol not in all_existing_symbols:
            continue

        activity, avg_price, _, pl_pct = analyzer.analyze_change(symbol)
        if not activity.strip() and avg_price == 0.0:
            continue

        kind, activity_text = _activity_kind(activity)

        initial_stock = analyzer.initial_portfolio.get_stock(symbol)
        final_stock = analyzer.final_portfolio.get_stock(symbol)

        if kind == "closed":
            sell_price = analyzer.final_portfolio.get_avg_sell_price(symbol)
            if avg_price > 0 and sell_price > 0:
                price_text = f"{avg_price:.2f}$ → {sell_price:.2f}$"
            elif avg_price > 0:
                price_text = f"{avg_price:.2f}$"
            else:
                price_text = "-"
            row_pl_pct = pl_pct if avg_price > 0 and sell_price > 0 else None
        else:
            price_text = f"{avg_price:.2f}$" if avg_price > 0 else "-"
            row_pl_pct = pl_pct if avg_price > 0 else None

        row = {
            "symbol": formatter._display_symbol(symbol),
            "kind": kind,
            "activity_text": activity_text,
            "price_text": price_text,
            "pl_pct": row_pl_pct,
        }
        weight_sort = 0.0
        if final_stock and total_portfolio_value > 0:
            weight = (final_stock.usd_value / total_portfolio_value) * 100
            row["weight_pct"] = weight
            weight_sort = weight
        elif initial_stock and total_portfolio_value > 0:
            weight = (initial_stock.usd_value / total_portfolio_value) * 100
            row["weight_text"] = f"{weight:.2f}% → 0%" if weight > 0 else "-"
        else:
            row["weight_text"] = "-"

        rows.append((weight_sort, row))

    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows]


def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Analyze stock portfolio changes.")
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "both"],
        default="both",
        help="Output format: text, markdown, or both (default: both)",
    )
    args = parser.parse_args()

    # Determine base directory (directory where this script resides)
    base_dir = Path(__file__).resolve().parent

    loaded = load_portfolios(base_dir)
    if loaded is None:
        return
    initial_portfolio, final_portfolio, initial_to_date, final_to_date = loaded

    # Format date for report header - use initial_to_date as the period
    period_formatted = format_date_with_quarter(initial_to_date)

    # Generate and print output
    print(f"Зміни в портфелі акцій за {period_formatted}:")
    print("-" * 80)

    # Output based on the specified format
    if args.format in ["text", "both"]:
        text_generator = PortfolioReportGenerator(
            initial_portfolio, final_portfolio, format_type="text"
        )
        text_output = text_generator.generate()
        print(text_output)

    if args.format in ["markdown", "both"]:
        markdown_generator = PortfolioReportGenerator(
            initial_portfolio, final_portfolio, format_type="markdown"
        )
        report_filename = generate_report_filename(initial_to_date)
        output_path = base_dir / report_filename
        markdown_generator.save_markdown(
            output_path, f"Зміни в портфелі акцій за {period_formatted}"
        )
        print(f"\nMarkdown звіт збережено у файл: {output_path}")


if __name__ == "__main__":
    main()
