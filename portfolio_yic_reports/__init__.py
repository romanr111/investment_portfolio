"""
Portfolio Analysis Module

This module contains tools for analyzing portfolio changes and generating reports.

The legacy ``analyze_portfolio_reports`` module is imported lazily to avoid a
hard dependency on the local-only ``data.filters_constants`` module, which is
not available in clean checkouts. Use ``from portfolio_yic_reports.analyze_portfolio_reports import ...``
directly when the private data files are present.
"""

__all__ = [
    "PortfolioAnalyzer",
    "XMLPortfolioParser",
    "TableFormatter",
    "format_date_with_quarter",
    "generate_report_filename",
]


def __getattr__(name: str):
    if name in __all__:
        from . import analyze_portfolio_reports

        return getattr(analyze_portfolio_reports, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
