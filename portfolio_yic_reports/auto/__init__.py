"""Automated quarterly portfolio report generator.

Generates ``REPORT_YYYY_qN.md`` from IB Flex Query 1188471 snapshots plus
``portfolio_history.csv`` (allocation diff) and ``combined_data_*.json``
(Section 3 metrics: YTD TWR, dividends, freedom progress) and
``analytics/output/summary.json`` (Dalio risk metrics).
"""