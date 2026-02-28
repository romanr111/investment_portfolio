import argparse
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import main


class MainDalioOnlyModeTests(unittest.TestCase):
    @staticmethod
    def _mock_parser(namespace: argparse.Namespace) -> MagicMock:
        parser = MagicMock()
        parser.parse_args.return_value = namespace
        return parser

    @staticmethod
    def _build_args(**overrides: object) -> argparse.Namespace:
        base = {
            "dalio_only": True,
            "skip_dalio_analysis": False,
            "dalio_input_csv": "/tmp/dalio-input.csv",
            "history_csv_path": "data/portfolio_history.csv",
            "history_jsonl_path": "data/portfolio_history.jsonl",
            "skip_history_sync": False,
            "credentials_path": "data/credentials.json",
            "spreadsheet_name": "portfolio_automated",
            "history_currency": "USD",
            "history_return_source": "blank",
            "history_strict_required_buckets": False,
            "history_include_zero_positions": False,
            "history_frequency": "monthly",
            "history_start_date": None,
            "history_end_date": None,
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_dalio_only_mode_runs_without_full_pipeline_imports(self) -> None:
        args = self._build_args()
        parser = self._mock_parser(args)
        original_import = __import__

        def guard_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
            if name == "src.data_source" or name.startswith("src.data_source."):
                raise AssertionError(
                    "src.data_source must not be imported in --dalio-only mode."
                )
            return original_import(name, globals, locals, fromlist, level)

        with patch("main._build_cli", return_value=parser):
            with patch("main._run_dalio_analysis") as run_dalio:
                with patch("builtins.__import__", side_effect=guard_import):
                    exit_code = main.main()

        self.assertEqual(exit_code, 0)
        run_dalio.assert_called_once_with(args)

    def test_dalio_only_conflicts_with_skip_flag(self) -> None:
        args = self._build_args(skip_dalio_analysis=True)
        parser = self._mock_parser(args)

        with patch("main._build_cli", return_value=parser):
            with patch("main._run_dalio_analysis") as run_dalio:
                exit_code = main.main()

        self.assertEqual(exit_code, 1)
        run_dalio.assert_not_called()

    def test_dalio_only_auto_syncs_history_when_default_input_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_history_path = f"{tmp_dir}/portfolio_history.csv"
            args = self._build_args(
                dalio_input_csv=None,
                history_csv_path=missing_history_path,
                history_jsonl_path=f"{tmp_dir}/portfolio_history.jsonl",
                skip_history_sync=False,
            )
            parser = self._mock_parser(args)

            with patch("main._build_cli", return_value=parser):
                with patch("main._run_history_sync_only") as run_history_sync:
                    with patch("main._run_dalio_analysis") as run_dalio:
                        exit_code = main.main()

            self.assertEqual(exit_code, 0)
            run_history_sync.assert_called_once_with(args)
            run_dalio.assert_called_once_with(args)

    def test_dalio_only_missing_default_input_fails_when_history_sync_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_history_path = f"{tmp_dir}/portfolio_history.csv"
            args = self._build_args(
                dalio_input_csv=None,
                history_csv_path=missing_history_path,
                history_jsonl_path=f"{tmp_dir}/portfolio_history.jsonl",
                skip_history_sync=True,
            )
            parser = self._mock_parser(args)

            with patch("main._build_cli", return_value=parser):
                with patch("main._run_history_sync_only") as run_history_sync:
                    with patch("main._run_dalio_analysis") as run_dalio:
                        exit_code = main.main()

            self.assertEqual(exit_code, 1)
            run_history_sync.assert_not_called()
            run_dalio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
