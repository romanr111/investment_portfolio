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

### Programmatic Usage
```python
from analyze_portfolio_reports import XMLPortfolioParser, PortfolioAnalyzer, TableFormatter

# Parse portfolio data
parser = XMLPortfolioParser()
initial_portfolio, _, _ = parser.parse("reporting/stocks_count.xml")
final_portfolio, _, _ = parser.parse("reporting/stocks_count (1).xml")

# Analyze and format
initial_portfolio.calculate_weights()
final_portfolio.calculate_weights()
analyzer = PortfolioAnalyzer(initial_portfolio, final_portfolio)
formatter = TableFormatter(analyzer, format_type="markdown")
report = formatter.format_as_table()
```

## Preconditions

1. **Input Files**: Place Interactive Brokers XML exports in the current directory:
   - `stocks_count1.xml` - Initial portfolio state
   - `stocks_count2.xml` - Final portfolio state

2. **XML Format**: Files must contain `<FlexStatement>` with `fromDate`/`toDate` and `<OpenPosition>` elements with:
   - `symbol`, `position`, `costBasisPrice`, `positionValue`, `assetCategory`, `markPrice`

3. **Output**: Markdown reports are saved as `portfolio_report_YYYY_qN.md` in the current directory.
"""

# Module for creating Young Investors Club report;
import os
import xml.etree.ElementTree as ET
import glob
import argparse
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
AVERAGE_PRICE = "Cередня ціна"

# Table headers
HEADER_SYMBOL = "Позиція"
HEADER_ACTIVITY = "Остання активність"
HEADER_AVG_PRICE = "Середня ціна"
HEADER_WEIGHT = "Вага"


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
                activity = f"{INCREASED} (+{int(round(abs(pct_change)))}%)"
                self.activity_counts["increased"] += 1
            elif pct_change < 0:
                activity = f"{DECREASED} (-{int(round(abs(pct_change)))}%)"
                self.activity_counts["decreased"] += 1
            else:
                activity = UNCHANGED
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
            activity = ELIMINATED

            # Handle special case for 9988
            if symbol in self.hardcoded_prices:
                avg_price = self.hardcoded_prices[symbol]
            else:
                avg_price = initial_stock.cost_basis

            self.activity_counts["eliminated"] += 1

        # New position
        elif final_stock and not initial_stock:
            activity = NEW_POSITION

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
                activity = f"{INCREASED} (+{int(round(abs(value_change_pct)))}%)"
                self.activity_counts["increased"] += 1
            elif value_change_pct < -5:
                activity = f"{DECREASED} (-{int(round(abs(value_change_pct)))}%)"
                self.activity_counts["decreased"] += 1
            else:
                activity = UNCHANGED
                self.activity_counts["unchanged"] += 1

            avg_price = final_bills.weighted_avg_price
            weight = final_bills.weight

        # Treasury Bills eliminated
        elif initial_bills and not final_bills:
            activity = ELIMINATED
            avg_price = initial_bills.weighted_avg_price
            self.activity_counts["eliminated"] += 1

        # New Treasury Bills position
        elif final_bills and not initial_bills:
            activity = NEW_POSITION
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

        return portfolio, from_date, to_date


class TableFormatter:
    """Class for formatting portfolio data as a table"""

    def __init__(self, analyzer: PortfolioAnalyzer, format_type="text"):
        self.analyzer = analyzer
        self.format_type = format_type  # "text" or "markdown"
        # Fixed column widths
        self.symbol_width = 8
        self.activity_width = 20
        self.price_width = 15
        self.weight_width = 10

    def _display_symbol(self, symbol: str) -> str:
        """Return the user-facing label for a given ticker."""
        return "T Bills" if symbol == "BILLS" else symbol

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

            activity, avg_price, weight, price_change_pct = (
                self.analyzer.analyze_change(symbol)
            )

            # Format values with fixed width
            symbol_display = self._display_symbol(symbol)
            symbol_str = symbol_display[: self.symbol_width].ljust(self.symbol_width)
            activity_str = activity[: self.activity_width].ljust(self.activity_width)

            # Format price with change percentage
            price_str = f"{avg_price:.2f}$"
            if price_change_pct != 0:
                sign = "+" if price_change_pct > 0 else ""
                # Show decimal for small changes, integers for larger ones
                if abs(price_change_pct) < 1:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.1f}%)"
                else:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.0f}%)"

                # Remove special case for COMB here - not needed in main table
            price_str = price_str.ljust(self.price_width)

            weight_str = f"{weight:.2f}%" if weight > 0 else "-"
            weight_str = weight_str.ljust(self.weight_width)

            # Create row
            row = f"{symbol_str}  {activity_str}  {price_str}  {weight_str}"
            output_data.append((weight, row))

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

        # Add total value
        total_value = self.analyzer.final_portfolio.get_total_value()
        total_line = f"\nЗагальна вартість всіх акцій (в USD, без облігацій, золота та товарних активів): {total_value:,.2f}$"
        table_lines.append(total_line)

        # Add special assets table
        special_assets_table = self._format_special_assets_table_text()
        if special_assets_table:
            table_lines.append("\n\nОблігації, золото та товарні активи\n")
            table_lines.append(special_assets_table)

        return "\n".join(table_lines)

    def _format_special_assets_table_text(self) -> str:
        """Format a separate table for special asset categories with changes only in text format"""
        special_data = []

        # Create table header
        header = f"{HEADER_SYMBOL.ljust(self.symbol_width)}  {HEADER_ACTIVITY.ljust(self.activity_width)}  {HEADER_AVG_PRICE.ljust(self.price_width)}  {'Вага (від загальної вартості)'.ljust(self.weight_width)}"
        separator = f"{'-' * self.symbol_width}  {'-' * self.activity_width}  {'-' * self.price_width}  {'-' * self.weight_width}"

        table_lines = [header, separator]

        # Get all symbols that actually exist in either portfolio
        all_existing_symbols = self.analyzer.initial_portfolio.get_symbols().union(
            self.analyzer.final_portfolio.get_symbols()
        )

        # Check each special asset
        for symbol in LONG_BONDS_GOLD_COMMODITIES:
            # Skip if symbol doesn't exist in either portfolio
            if symbol not in all_existing_symbols:
                continue

            activity, avg_price, _, price_change_pct = self.analyzer.analyze_change(
                symbol
            )

            # Show unchanged positions as well
            if activity == UNCHANGED:
                activity = "Без змін"

            # Format values for the table
            symbol_display = self._display_symbol(symbol)
            symbol_str = symbol_display.ljust(self.symbol_width)
            activity_str = activity.ljust(self.activity_width)

            # Format price with change percentage
            price_str = f"{avg_price:.2f}$"
            if price_change_pct != 0:
                sign = "+" if price_change_pct > 0 else ""
                # Show decimal for small changes, integers for larger ones
                if abs(price_change_pct) < 1:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.1f}%)"
                else:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.0f}%)"

                # Special case for COMB to add dividend note
                if symbol == "COMB" and price_change_pct < 0:
                    if abs(price_change_pct) < 1:
                        price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.1f}% дивіденди)"
                    else:
                        price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.0f}% дивіденди)"
            price_str = price_str.ljust(self.price_width)

            # Calculate weight for the special assets table based on total portfolio value
            # Use stocks value + estimate of special assets value as total portfolio
            stocks_total = self.analyzer.final_portfolio.get_total_value()

            # Get all special assets value to add to stocks total
            special_assets_value = 0
            for special_symbol in LONG_BONDS_GOLD_COMMODITIES:
                special_stock = self.analyzer.final_portfolio.get_stock(
                    special_symbol
                ) or self.analyzer.initial_portfolio.get_stock(special_symbol)
                if special_stock:
                    special_assets_value += special_stock.usd_value

            total_portfolio_value = stocks_total + special_assets_value

            # Get the stock data from appropriate portfolio (prefer final, fallback to initial)
            stock_data = self.analyzer.final_portfolio.get_stock(
                symbol
            ) or self.analyzer.initial_portfolio.get_stock(symbol)

            if stock_data and total_portfolio_value > 0:
                weight = (stock_data.usd_value / total_portfolio_value) * 100
            else:
                weight = 0

            weight_str = f"{weight:.2f}%" if weight > 0 else "-"
            weight_str = weight_str.ljust(self.weight_width)

            # Create row
            row = f"{symbol_str}  {activity_str}  {price_str}  {weight_str}"
            special_data.append((weight, row))

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

            activity, avg_price, weight, price_change_pct = (
                self.analyzer.analyze_change(symbol)
            )

            # Format values for markdown table
            price_str = f"{avg_price:.2f}$"
            if price_change_pct != 0:
                sign = "+" if price_change_pct > 0 else ""
                # Show decimal for small changes, integers for larger ones
                if abs(price_change_pct) < 1:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.1f}%)"
                else:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.0f}%)"

                # Remove special case for COMB here - not needed in main table

            weight_str = f"{weight:.2f}%" if weight > 0 else "-"

            # Create markdown row
            symbol_display = self._display_symbol(symbol)
            row = f"| {symbol_display} | {activity} | {price_str} | {weight_str} |"
            output_data.append((weight, row))

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

        # Add total value
        total_value = self.analyzer.final_portfolio.get_total_value()
        total_line = f"\n**Загальна вартість всіх акцій (в USD, без облігацій, золота та товарних активів): {total_value:,.2f}$**"
        table_lines.append(total_line)

        # Add special assets table
        special_assets_table = self._format_special_assets_table()
        if special_assets_table:
            table_lines.append("\n\n## Облігації, золото та товарні активи\n")
            table_lines.append(special_assets_table)

        return "\n".join(table_lines)

    def _format_special_assets_table(self) -> str:
        """Format a separate table for special asset categories with changes only"""
        special_data = []

        # Create Markdown table header for special assets
        header = f"| {HEADER_SYMBOL} | {HEADER_ACTIVITY} | {HEADER_AVG_PRICE} | Вага (від загальної вартості) |"
        separator = f"|{'-' * (self.symbol_width + 2)}|{'-' * (self.activity_width + 2)}|{'-' * (self.price_width + 2)}|{'-' * (self.weight_width + 2)}|"

        table_lines = [header, separator]

        # Get all symbols that actually exist in either portfolio
        all_existing_symbols = self.analyzer.initial_portfolio.get_symbols().union(
            self.analyzer.final_portfolio.get_symbols()
        )

        # Check each special asset
        for symbol in LONG_BONDS_GOLD_COMMODITIES:
            # Skip if symbol doesn't exist in either portfolio
            if symbol not in all_existing_symbols:
                continue

            activity, avg_price, _, price_change_pct = self.analyzer.analyze_change(
                symbol
            )

            # Skip if no meaningful data (empty activity and zero price means position doesn't exist)
            if not activity.strip() and avg_price == 0.0:
                continue

            # Format values for the table
            price_str = f"{avg_price:.2f}$"
            if price_change_pct != 0:
                sign = "+" if price_change_pct > 0 else ""
                # Show decimal for small changes, integers for larger ones
                if abs(price_change_pct) < 1:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.1f}%)"
                else:
                    price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.0f}%)"

                # Special case for COMB to add dividend note
                if symbol == "COMB" and price_change_pct < 0:
                    if abs(price_change_pct) < 1:
                        price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.1f}% дивіденди)"
                    else:
                        price_str = f"{avg_price:.2f}$ ({sign}{price_change_pct:.0f}% дивіденди)"

            # Calculate weight for the special assets table based on total portfolio value
            # Use stocks value + estimate of special assets value as total portfolio
            stocks_total = self.analyzer.final_portfolio.get_total_value()

            # Get all special assets value to add to stocks total
            special_assets_value = 0
            for special_symbol in LONG_BONDS_GOLD_COMMODITIES:
                special_stock = self.analyzer.final_portfolio.get_stock(
                    special_symbol
                ) or self.analyzer.initial_portfolio.get_stock(special_symbol)
                if special_stock:
                    special_assets_value += special_stock.usd_value

            total_portfolio_value = stocks_total + special_assets_value

            # Get the stock data from appropriate portfolio (prefer final, fallback to initial)
            stock_data = self.analyzer.final_portfolio.get_stock(
                symbol
            ) or self.analyzer.initial_portfolio.get_stock(symbol)

            if stock_data and total_portfolio_value > 0:
                weight = (stock_data.usd_value / total_portfolio_value) * 100
            else:
                weight = 0

            weight_str = f"{weight:.2f}%" if weight > 0 else "-"
            weight_str = weight_str.ljust(self.weight_width)

            # Create row
            symbol_display = self._display_symbol(symbol)
            row = f"| {symbol_display} | {activity} | {price_str} | {weight_str} |"
            special_data.append((weight, row))

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
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent

    # Find all files matching pattern in base directory
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
        return

    print(f"Analyzing positions from {initial_file.name} to {final_file.name}...")

    # Parse portfolio data
    parser = XMLPortfolioParser()
    initial_portfolio, initial_from_date, initial_to_date = parser.parse(
        str(initial_file)
    )
    final_portfolio, final_from_date, final_to_date = parser.parse(str(final_file))

    # Calculate portfolio weights
    initial_portfolio.calculate_weights()
    final_portfolio.calculate_weights()

    # Format date for report header - use initial_to_date as the period
    period_formatted = format_date_with_quarter(initial_to_date)

    # Generate and print output
    print(f"Зміни в портфелі акцій за {period_formatted}:")
    print("-" * 80)

    # Output based on the specified format
    if args.format in ["text", "both"]:
        # Create analyzer for text output
        text_analyzer = PortfolioAnalyzer(initial_portfolio, final_portfolio)
        text_formatter = TableFormatter(text_analyzer, format_type="text")
        text_output = text_formatter.format_as_table()
        print(text_output)

    if args.format in ["markdown", "both"]:
        # Create a separate analyzer instance for markdown to prevent double counting
        markdown_analyzer = PortfolioAnalyzer(initial_portfolio, final_portfolio)
        markdown_formatter = TableFormatter(markdown_analyzer, format_type="markdown")
        markdown_output = markdown_formatter.format_as_table()

        # Save markdown output to a file without printing to console
        report_filename = generate_report_filename(initial_to_date)
        # Save to script directory (where XML files are located)
        output_path = base_dir / report_filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"\n # Зміни в портфелі акцій за {period_formatted}\n\n")
            f.write(markdown_output)
        print(f"\nMarkdown звіт збережено у файл: {output_path}")


if __name__ == "__main__":
    main()
