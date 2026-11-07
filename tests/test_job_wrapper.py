"""Focused offline tests for the src.job_control.run_job wrapper."""
import fcntl
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import src.job_control.run_job as run_job


class JobWrapperTests(unittest.TestCase):
    _PING_URL = "http://healthcheck.example/fixed-test-uid"

    def _workspace(self):
        temp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        return Path(temp)

    def _capture_run_paths(self, temp):
        run_dir = temp / "run"
        for name in ("RUN_DIR", "RECEIPTS_FILE"):
            patcher = patch.object(
                run_job, name, run_dir if name == "RUN_DIR" else run_dir / "receipts.jsonl"
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        return run_dir

    def _last_receipt(self, run_dir):
        lines = (run_dir / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines, "one receipt line per run")
        return json.loads(lines[-1])

    def _ping_ok_response(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        return response

    def test_second_run_while_locked_exits_3_and_records_locked(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        lock_path = run_dir / "locktest.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        holder = open(lock_path, "a+", encoding="utf-8")
        self.addCleanup(holder.close)
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        holder.seek(0)
        holder.write(str(os.getpid()))
        holder.flush()

        return_code = run_job.run(
            ["--job", "locktest", "--env-file", "none", "--", "/bin/echo", "never"]
        )
        receipt = self._last_receipt(run_dir)
        self.assertEqual(return_code, 3)
        self.assertEqual(receipt["outcome"], "locked")
        self.assertEqual(receipt["exit_code"], 3)
        self.assertEqual(receipt["attempts"], 1)
        self.assertEqual(receipt["notified"], "skipped")
        self.assertEqual(receipt["command"], ["/bin/echo", "never"])

    def test_successful_run_appends_schema_receipt_after_executing_command(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        return_code = run_job.run(
            ["--job", "receipttest", "--env-file", "none", "--", sys.executable, "-c", "print('ok')"]
        )
        receipt = self._last_receipt(run_dir)
        self.assertEqual(return_code, 0)
        self.assertEqual(receipt["schema"], 1)
        self.assertEqual(receipt["job"], "receipttest")
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(receipt["command"], [sys.executable, "-c", "print('ok')"])
        self.assertEqual(receipt["attempts"], 1)
        self.assertIsInstance(receipt["pid"], int)
        for field in ("start_utc", "end_utc", "duration_s", "retry_delay_s", "notified"):
            self.assertIn(field, receipt)
        self.assertEqual(receipt["notified"], "skipped")

    def test_failure_with_one_retry_records_two_attempts_and_child_exit_code(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        return_code = run_job.run(
            [
                "--job",
                "retrytest",
                "--env-file",
                "none",
                "--retries",
                "1",
                "--retry-delay",
                "0",
                "--",
                sys.executable,
                "-c",
                "import sys; sys.exit(7)",
            ]
        )
        receipt = self._last_receipt(run_dir)
        self.assertEqual(return_code, 7)
        self.assertEqual(receipt["outcome"], "fail")
        self.assertEqual(receipt["attempts"], 2)
        self.assertEqual(receipt["exit_code"], 7)
        self.assertEqual(receipt["notified"], "skipped")

    def test_healthcheck_without_url_is_an_offline_noop(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        with patch.object(run_job.urllib.request, "urlopen") as urlopen:
            return_code = run_job.run(
                [
                    "--job",
                    "pingtest",
                    "--env-file",
                    "none",
                    "--",
                    sys.executable,
                    "-c",
                    "print('ok')",
                ]
            )
        self.assertEqual(return_code, 0)
        urlopen.assert_not_called()
        receipt = self._last_receipt(run_dir)
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(receipt["notified"], "skipped")

    def test_healthcheck_success_pings_start_then_bare_url_and_notifies_ok(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        with patch.object(run_job.urllib.request, "urlopen") as urlopen:
            urlopen.return_value = self._ping_ok_response()
            return_code = run_job.run(
                [
                    "--job",
                    "pingstart",
                    "--env-file",
                    "none",
                    "--healthcheck-url",
                    self._PING_URL,
                    "--",
                    sys.executable,
                    "-c",
                    "print('ok')",
                ]
            )
        self.assertEqual(return_code, 0)
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("/start", urlopen.call_args_list[0].args[0])
        self.assertEqual(urlopen.call_args_list[1].args[0], self._PING_URL)
        receipt = self._last_receipt(run_dir)
        self.assertEqual(receipt["notified"], "ok")

    def test_healthcheck_after_failed_child_pings_url_with_fail_suffix(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        with patch.object(run_job.urllib.request, "urlopen") as urlopen:
            urlopen.return_value = self._ping_ok_response()
            return_code = run_job.run(
                [
                    "--job",
                    "pingfail",
                    "--env-file",
                    "none",
                    "--healthcheck-url",
                    self._PING_URL,
                    "--",
                    sys.executable,
                    "-c",
                    "import sys; sys.exit(7)",
                ]
            )
        self.assertEqual(return_code, 7)
        self.assertEqual(urlopen.call_count, 2)
        self.assertEqual(urlopen.call_args_list[1].args[0], self._PING_URL + "/fail")
        receipt = self._last_receipt(run_dir)
        self.assertEqual(receipt["outcome"], "fail")
        self.assertEqual(receipt["exit_code"], 7)

    def test_healthcheck_ping_failure_records_warning_and_keeps_success_exit(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        with patch.object(run_job.urllib.request, "urlopen") as urlopen:
            urlopen.side_effect = OSError("simulated ping outage")
            return_code = run_job.run(
                [
                    "--job",
                    "pingwarn",
                    "--env-file",
                    "none",
                    "--healthcheck-url",
                    self._PING_URL,
                    "--",
                    sys.executable,
                    "-c",
                    "print('ok')",
                ]
            )
        self.assertEqual(return_code, 0)
        receipt = self._last_receipt(run_dir)
        self.assertEqual(receipt["outcome"], "success")
        self.assertEqual(receipt["notified"], "warning")

    def test_first_try_success_with_retries_records_executed_attempts(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        return_code = run_job.run(
            [
                "--job",
                "executed",
                "--env-file",
                "none",
                "--retries",
                "2",
                "--retry-delay",
                "0",
                "--",
                sys.executable,
                "-c",
                "print('ok')",
            ]
        )
        receipt = self._last_receipt(run_dir)
        self.assertEqual(return_code, 0)
        self.assertEqual(receipt["attempts"], 1)

    def test_negative_retries_clamps_to_a_single_attempt(self):
        temp = self._workspace()
        run_dir = self._capture_run_paths(temp)
        return_code = run_job.run(
            [
                "--job",
                "clamp",
                "--env-file",
                "none",
                "--retries",
                "-3",
                "--retry-delay",
                "0",
                "--",
                sys.executable,
                "-c",
                "import sys; sys.exit(7)",
            ]
        )
        receipt = self._last_receipt(run_dir)
        self.assertEqual(return_code, 7)
        self.assertEqual(receipt["attempts"], 1)
        self.assertEqual(receipt["exit_code"], 7)
        self.assertEqual(receipt["outcome"], "fail")


if __name__ == "__main__":
    unittest.main()
