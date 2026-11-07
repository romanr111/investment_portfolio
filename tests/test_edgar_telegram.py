"""Offline tests for the Telegram digest delivery helper."""
import unittest

from src.edgar import telegram


class FakeResponse:
    def __init__(self, status_code=200, json_obj=None, text=""):
        self.status_code = status_code
        self._json = json_obj
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("body is not json")
        return self._json


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.posts = []

    def post(self, url, data=None, timeout=None, **_kwargs):
        self.posts.append({"url": url, "data": data, "timeout": timeout})
        if self.exc is not None:
            raise self.exc
        if self.response is None:
            response = FakeResponse(200, {"ok": True, "result": {}})
        else:
            response = self.response
        return response


class TelegramSendTests(unittest.TestCase):
    def _send(self, session, token="TOKEN", chat_id="42", text="digest"):
        return telegram.send(session, token, chat_id, text)

    def test_ok_delivery_posts_to_send_message(self):
        session = FakeSession()
        ok, detail = self._send(session)
        self.assertTrue(ok)
        self.assertEqual(detail, "ok")
        self.assertEqual(len(session.posts), 1)
        post = session.posts[0]
        self.assertIn("/sendMessage", post["url"])
        self.assertEqual(post["data"]["chat_id"], "42")
        self.assertEqual(post["data"]["text"], "digest")
        self.assertEqual(post["timeout"], telegram.DEFAULT_TIMEOUT_SECONDS)

    def test_absent_credentials_skip_without_error(self):
        session = FakeSession()
        ok, detail = telegram.send(session, "", "42", "digest")
        self.assertFalse(ok)
        self.assertEqual(detail, "telegram not configured")
        self.assertEqual(session.posts, [])
        ok, _detail = telegram.send(session, "TOKEN", "", "digest")
        self.assertFalse(ok)

    def test_http_400_reports_description(self):
        session = FakeSession(response=FakeResponse(400, {"ok": False, "description": "chat not found"}))
        ok, detail = self._send(session)
        self.assertFalse(ok)
        self.assertEqual(detail, "chat not found")

    def test_non_json_error_body_reports_status(self):
        session = FakeSession(response=FakeResponse(502, text="bad gateway"))
        ok, detail = self._send(session)
        self.assertFalse(ok)
        self.assertEqual(detail, "HTTP 502")

    def test_exception_never_raises(self):
        session = FakeSession(exc=RuntimeError("network down"))
        ok, detail = self._send(session)
        self.assertFalse(ok)
        self.assertIn("RuntimeError", detail)

    def test_transport_exception_detail_redacts_bot_token(self):
        token = "SECRET123"
        exc = RuntimeError(f"cannot post to https://api.telegram.org/bot{token}/sendMessage")
        ok, detail = self._send(FakeSession(exc=exc), token=token)
        self.assertFalse(ok)
        self.assertNotIn(token, detail)
        self.assertIn("***", detail)
        self.assertIn("sendMessage", detail)

    def test_message_truncated_to_telegram_limit(self):
        session = FakeSession()
        self._send(session, text="x" * 9000)
        self.assertEqual(len(session.posts[0]["data"]["text"]), telegram.MAX_MESSAGE_CHARS)


if __name__ == "__main__":
    unittest.main()
