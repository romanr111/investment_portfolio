"""Quarter labels and activity must belong to the closing export quarter."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestQuarterlyReportPeriod(unittest.TestCase):
    def test_q3_reports_use_closing_quarter_with_june_baseline(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reports = root / "portfolio_yic_reports"
            reports.mkdir()
            for name in ("analyze_portfolio_reports.py", "generate_quarterly_report.py",
                         "quarterly_report_html.py"):
                shutil.copy2(source / "portfolio_yic_reports" / name, reports / name)
            exports = root / "data" / "ib_flex_snapshots"
            snapshots = root / "data" / "snapshots"
            exports.mkdir(parents=True)
            snapshots.mkdir()
            for day in ("20260630", "20260930"):
                (exports / f"stocks_count_trades_{day}_fixture.xml").write_text(
                    f'<FlexQueryResponse><FlexStatement fromDate="{day}" toDate="{day}">'
                    '<OpenPosition symbol="AAPL" position="10" costBasisPrice="100" '
                    'positionValue="1100" assetCategory="STK" markPrice="110"/>'
                    '</FlexStatement></FlexQueryResponse>'
                )
            for day in ("2026-06-30", "2026-09-30"):
                (snapshots / f"combined_data_{day}_fixture.json").write_text(json.dumps({
                    "ASSET_ALLOCATION": {"net_worth": 1100, "allocations": {
                        "Stocks": {"percentage": 100, "value_usd": 1100}}},
                    "IB_PERFORMANCE": {"rate_of_return_pct": 5},
                    "INDEX_PERFORMANCE": {"SP500": {"rate_of_return_pct": 10}},
                    "ACTIVITY_DATA": {"quarters": {
                        "2026-Q2": {"crypto": [{"asset": "Q2_ASSET", "coverage": "partial"}]},
                        "2026-Q3": {"crypto": [{"asset": "Q3_ASSET", "coverage": "partial"}]}}},
                }))
            env = dict(os.environ, PYTHONPATH=str(source))
            commands = [
                ("analyze_portfolio_reports.py", ["--format", "markdown"]),
                ("generate_quarterly_report.py", []),
            ]
            for script, extra in commands:
                result = subprocess.run(
                    [sys.executable, str(reports / script), "--year", "2026",
                     "--quarter", "3", *extra], cwd=root, env=env,
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            markdown = (reports / "portfolio_report_2026_q3.md").read_text()
            html = (reports / "portfolio_report_q3_2026.html").read_text()
            with self.subTest(format="markdown"):
                self.assertIn("3-ій квартал 2026 року", markdown)
            with self.subTest(format="html"):
                self.assertIn("Q3 2026", html)
                self.assertIn("Липень – Вересень 2026 року", html)
                self.assertIn("Q3_ASSET", html)
                self.assertNotIn("Q2_ASSET", html)
