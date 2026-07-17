"""Tests for the Telegram notification helper."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / ".github" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import notify_telegram  # noqa: E402


class TestNotifyTelegram(unittest.TestCase):
    def test_skip_when_no_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            result = notify_telegram.notify()
            self.assertEqual(result, 0)

    def test_sends_message_on_success(self):
        with mock.patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_CHAT_ID": "12345",
            "JOB_STATUS": "success",
            "GITHUB_RUN_URL": "https://github.com/test/repo/runs/1",
        }), mock.patch("notify_telegram.requests.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True, status_code=200, text="ok")
            result = notify_telegram.notify()
            self.assertEqual(result, 0)
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertIn("sendMessage", args[0])
            self.assertEqual(kwargs["json"]["chat_id"], "12345")
            self.assertIn("✅", kwargs["json"]["text"])

    def test_sends_message_on_failure(self):
        with mock.patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_CHAT_ID": "12345",
            "JOB_STATUS": "failure",
            "GITHUB_RUN_URL": "https://github.com/test/repo/runs/1",
        }), mock.patch("notify_telegram.requests.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=True, status_code=200, text="ok")
            result = notify_telegram.notify()
            self.assertEqual(result, 0)
            kwargs = mock_post.call_args.kwargs
            self.assertIn("❌", kwargs["json"]["text"])

    def test_returns_error_on_api_failure(self):
        with mock.patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_CHAT_ID": "12345",
            "JOB_STATUS": "success",
            "GITHUB_RUN_URL": "",
        }), mock.patch("notify_telegram.requests.post") as mock_post:
            mock_post.return_value = mock.Mock(ok=False, status_code=401, text="Unauthorized")
            result = notify_telegram.notify()
            self.assertEqual(result, 1)

    def test_returns_error_on_exception(self):
        import requests as req
        with mock.patch.dict(os.environ, {
            "TELEGRAM_BOT_TOKEN": "fake-token",
            "TELEGRAM_CHAT_ID": "12345",
            "JOB_STATUS": "success",
            "GITHUB_RUN_URL": "",
        }), mock.patch("notify_telegram.requests.post", side_effect=req.RequestException("timeout")):
            result = notify_telegram.notify()
            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()