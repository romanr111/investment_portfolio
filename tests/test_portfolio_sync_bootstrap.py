"""Tests for portfolio_sync bootstrap: env file parsing."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src import portfolio_sync


class TestPortfolioSyncBootstrap(unittest.TestCase):

    def test_load_local_env_file_reads_export_lines_without_overriding(self):
        with TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "ib_flex_env.sh"
            env_file.write_text(
                "\n".join(
                    [
                        "# local config",
                        "export IB_FLEX_TOKEN='secret-token'",
                        'export IB_ACCOUNT_ID="DU123"',
                        "export EXISTING_VALUE=from-file",
                    ]
                )
            )
            # Clean env vars before the test.
            for key in ("IB_FLEX_TOKEN", "IB_ACCOUNT_ID"):
                os.environ.pop(key, None)
            os.environ["EXISTING_VALUE"] = "from-env"

            portfolio_sync._load_local_env_file(env_file)

            self.assertEqual(os.environ["IB_FLEX_TOKEN"], "secret-token")
            self.assertEqual(os.environ["IB_ACCOUNT_ID"], "DU123")
            self.assertEqual(os.environ["EXISTING_VALUE"], "from-env")

            # Cleanup
            for key in ("IB_FLEX_TOKEN", "IB_ACCOUNT_ID", "EXISTING_VALUE"):
                os.environ.pop(key, None)


if __name__ == "__main__":
    unittest.main()