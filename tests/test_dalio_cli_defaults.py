import importlib
import sys
import types
import unittest
from unittest.mock import patch

from analytics import dalio_holy_grail as dalio_module


def _build_stub_module(module_name: str, **attributes: object) -> types.ModuleType:
    module = types.ModuleType(module_name)
    for attr_name, attr_value in attributes.items():
        setattr(module, attr_name, attr_value)
    return module


class DalioCliDefaultsTest(unittest.TestCase):
    def test_analytics_cli_new_defaults(self) -> None:
        parser = dalio_module._build_cli()
        args = parser.parse_args(["--input", "data/portfolio_history.csv"])

        self.assertEqual(args.covariance_method, "ledoit-wolf")
        self.assertEqual(args.return_type, "simple")
        self.assertEqual(args.analysis_frequency, "auto")
        self.assertAlmostEqual(float(args.min_asset_coverage_pct), 80.0, places=8)
        self.assertIsNone(args.covariance_window)

    def test_main_cli_new_defaults(self) -> None:
        stub_modules = {
            "src.google_sheets.spreadsheet_structure": _build_stub_module(
                "src.google_sheets.spreadsheet_structure",
                update_portfolio_spreadsheet=lambda *args, **kwargs: {},
            ),
            "src.logging.portfolio_logger": _build_stub_module(
                "src.logging.portfolio_logger",
                log_portfolio_data=lambda *args, **kwargs: None,
                log_portfolio_metadata=lambda *args, **kwargs: None,
            ),
            "src.data_source": _build_stub_module(
                "src.data_source",
                DataSource=type("DataSource", (), {"__init__": lambda self: None}),
            ),
            "src.allocation_calculator": _build_stub_module(
                "src.allocation_calculator",
                AllocationCalculator=type(
                    "AllocationCalculator",
                    (),
                    {
                        "__init__": lambda self, *args, **kwargs: None,
                        "prepare_data_for_sheet": lambda self, *args, **kwargs: ({}, []),
                    },
                ),
            ),
            "src.portfolio_history.unified_history": _build_stub_module(
                "src.portfolio_history.unified_history",
                save_combined_data_snapshot_json=lambda *args, **kwargs: None,
                sync_unified_history_from_google_sheets=lambda *args, **kwargs: None,
            ),
        }
        original_main = sys.modules.get("main")
        sys.modules.pop("main", None)
        try:
            with patch.dict(sys.modules, stub_modules):
                main_module = importlib.import_module("main")
                parser = main_module._build_cli()
                args = parser.parse_args([])
        finally:
            sys.modules.pop("main", None)
            if original_main is not None:
                sys.modules["main"] = original_main

        self.assertEqual(args.dalio_covariance_method, "ledoit-wolf")
        self.assertEqual(args.dalio_return_type, "simple")
        self.assertEqual(args.dalio_analysis_frequency, "auto")
        self.assertAlmostEqual(float(args.dalio_min_asset_coverage_pct), 80.0, places=8)
        self.assertIsNone(args.dalio_covariance_window)


if __name__ == "__main__":
    unittest.main()
