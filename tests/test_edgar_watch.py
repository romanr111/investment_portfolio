"""Offline integration tests for the EDGAR watch: fake sessions and fixtures.

All network endpoints are fake: no test issues a real HTTP request. Real
holdings never appear here; every fixture symbol (TESTA, TESTB, SAMPLECO,
HKSTOCK, TESTFUND, HKADR) is invented.
"""
import fcntl
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import requests

from src.edgar import digest as digest_module
from src.edgar import risk_factors
from src.edgar import severity
from src.edgar import universe
from src.edgar import watch
from src.edgar.edgar_client import EdgarBlocked, EdgarClient, EdgarRequestError, TICKER_MAP_URL

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edgar"
FIXED_NOW = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

ENV_KEYS = ("SEC_USER_AGENT", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "HEALTHCHECK_EDGAR_URL")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _fixture_json(name: str):
    return json.loads(_fixture(name))


def _day_offset(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _recomputed_rf_diff_counts():
    """Locally recompute the tenk_v1 -> tenk_v2 Risk Factors diff counts."""
    old_section = risk_factors.extract_item_1a(risk_factors.html_to_text(_fixture("tenk_v1.html")))[1]
    new_section = risk_factors.extract_item_1a(risk_factors.html_to_text(_fixture("tenk_v2.html")))[1]
    added, removed, _diff, _headers = risk_factors.diff_text(old_section, new_section)
    return added, removed


def _submissions(cik, rows, entity="operating", sic="3571"):
    accessions = [row[0] for row in rows]
    return {
        "cik": cik,
        "entityType": entity,
        "sic": sic,
        "filings": {
            "recent": {
                "accessionNumber": accessions,
                "filingDate": [row[4] for row in rows],
                "form": [row[1] for row in rows],
                "items": [row[2] for row in rows],
                "primaryDocument": [row[3] for row in rows],
            }
        },
    }


TESTA_V1_ROWS = [
    ("0001010-26-000007", "8-K", "1.03,9.01", "testa-8k-item103.htm", _day_offset(0)),
    ("0001010-26-000006", "10-K", "", "testa-20261031.htm", _day_offset(1)),
    ("0001010-26-000005", "4", "", "testa-form4.xml", _day_offset(2)),
    ("0001010-26-000004", "NPORT-P", "", "nport-20261103.xml", _day_offset(3)),
    ("0001010-25-000001", "10-K", "", "testa-20250930.htm", _day_offset(400)),
]
TESTA_V2_ROWS = [
    ("0001010-26-000008", "10-K", "", "testa-20261106.htm", _day_offset(0))
] + TESTA_V1_ROWS
TESTB_ROWS = [("0002020-26-000001", "10-Q", "", "testb-20260930.htm", _day_offset(1))]
SAMPLECO_ROWS = [("0003030-26-000001", "8-K", "2.02,9.01", "sampleco-8k.htm", _day_offset(0))]
HKADR_ROWS = [("0005050-26-000001", "NPORT-P", "", "nport-20261103.xml", _day_offset(1))]
TESTFUND_ROWS = [("0004040-26-000001", "NPORT-P", "", "nport.xml", _day_offset(0))]


def _default_routes(submissions_by_cik, docs_by_name, ticker_map=None):
    def route(url):
        if url.startswith("https://data.sec.gov/submissions/"):
            cik = url.rsplit("CIK", 1)[-1].replace(".json", "")
            payload = submissions_by_cik.get(cik)
            if isinstance(payload, Exception):
                raise payload
            if payload is None:
                raise AssertionError(f"no submissions fixture routed for CIK {cik}")
            return _FakeResponse(200, text=json.dumps(payload))
        if url.startswith("https://www.sec.gov/Archives/edgar/data/"):
            for fragment, html in docs_by_name.items():
                if fragment in url:
                    return _FakeResponse(200, text=html)
            return _FakeResponse(404, text="missing document")
        if url == TICKER_MAP_URL:
            if ticker_map is None:
                raise AssertionError("ticker map network access was not expected")
            return _FakeResponse(200, text=json.dumps(ticker_map), json_obj=ticker_map)
        raise AssertionError(f"unexpected offline URL routed: {url}")

    return route


class _FakeResponse:
    def __init__(self, status_code=200, text="", json_obj=None):
        self.status_code = status_code
        self.text = text
        self._json = json_obj

    def json(self):
        if self._json is None:
            raise ValueError("body is not json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)
        return None


class _FakeSession:
    def __init__(self, route):
        self.route = route
        self.gets = []
        self.posts = []

    def get(self, url, headers=None, timeout=None, **_kwargs):
        self.gets.append({"url": url, "headers": headers})
        result = self.route(url)
        return result

    def post(self, url, data=None, timeout=None, **_kwargs):
        self.posts.append({"url": url, "data": data})
        return _FakeResponse(200, json_obj={"ok": True, "result": {}})


class _FastEdgarClient(EdgarClient):
    def __init__(self, session=None, **kwargs):
        kwargs.setdefault("min_request_interval", 0.0)
        kwargs.setdefault("retry_backoff_seconds", 0.0)
        super().__init__(session=session, **kwargs)


class _OfflineModuleTestCase(unittest.TestCase):
    """Common environment isolation and fixture wiring for watch runs."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.data_dir = Path(self.temp)
        with (self.data_dir / "cik_map.json").open("w", encoding="utf-8") as handle:
            json.dump(universe.build_cik_map(_fixture_json("company_tickers_fixture.json")), handle)
        self.config_path = self.data_dir / "config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "force_include": {"HKSTOCK": {"via": "HKADR", "note": "sample ADR mapping"}},
                }
            ),
            encoding="utf-8",
        )
        self._saved_env = {}
        self._patch_env_keys()
        patcher = patch.object(watch, "_load_local_env_file", lambda: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self._client_patcher = patch.object(watch, "EdgarClient", _FastEdgarClient)
        self._client_patcher.start()
        self.addCleanup(self._client_patcher.stop)
        self._session_holder = {"session": _FakeSession(_default_routes({}, {}))}
        session_patcher = patch.object(watch.requests, "Session", lambda: self._session_holder["session"])
        session_patcher.start()
        self.addCleanup(session_patcher.stop)

    def _patch_env_keys(self):
        saved = self._saved_env
        for key in ENV_KEYS:
            saved[key] = os.environ.pop(key, None)

        def restore():
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

        self.addCleanup(restore)

    def _run_watch(self, *extra, session=None):
        if session is not None:
            self._session_holder["session"] = session
        arguments = ["--snapshot", str(FIXTURES / "snapshot_fixture.json"), "--data-dir", str(self.data_dir)]
        arguments.extend(extra)
        with redirect_stdout(io.StringIO()) as buffer:
            code = watch.run(arguments)
        return code, buffer.getvalue()

    def _session(self):
        routes = _default_routes(self._submissions_by_cik(), self._docs_by_name())
        return _FakeSession(routes)

    def _submissions_by_cik(self):
        return {
            "0000001010": _submissions("1010", TESTA_V1_ROWS),
            "0000002020": _submissions("2020", TESTB_ROWS),
            "0000003030": _submissions("3030", SAMPLECO_ROWS, sic="3571"),
            "0000005050": _submissions("5050", HKADR_ROWS, entity="other", sic="3571"),
        }

    def _docs_by_name(self):
        return {
            "testa-20261031.htm": _fixture("tenk_v1.html"),
            "testa-20261106.htm": _fixture("tenk_v2.html"),
            "testb-20260930.htm": _fixture("tenk_v1.html"),
        }

    def _read_state(self):
        return json.loads((self.data_dir / "state.json").read_text(encoding="utf-8"))

    def _alerts_lines(self):
        path = self.data_dir / "alerts.jsonl"
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()


class WatchRunTests(_OfflineModuleTestCase):
    def test_first_run_alerts_red_with_url_and_commits_state(self):
        # A private UA string must never leak into the run log (the plan's
        # no-key-logging rule); every later stdout assertion doubles as a check.
        os.environ["SEC_USER_AGENT"] = "OwnerUA/1.0 (contact@owner.example)"
        code, output = self._run_watch("--dry-alert", session=self._session())
        self.assertEqual(code, 0, output)
        self.assertNotIn("OwnerUA", output)
        self.assertEqual(code, 0, output)
        self.assertIn("EDGAR watch ·", output)
        self.assertIn("\U0001F534 [TESTA] 8-K items 1.03,9.01 - Bankruptcy or Receivership", output)
        self.assertIn("Bankruptcy or Receivership", output)
        self.assertIn(
            "https://www.sec.gov/Archives/edgar/data/0000001010/000101026000007/"
            "0001010-26-000007-index.htm",
            output,
        )
        self.assertIn("Risk Factors: +0/-0 (no baseline)", output)
        self.assertIn("1 × Form 4 (insider changes)", output)
        self.assertIn("new 7", output)
        state_payload = self._read_state()
        self.assertEqual(state_payload["run_count"], 1)
        self.assertIn("0000001010", state_payload["ciks"])
        self.assertEqual(
            state_payload["ciks"]["0000001010"]["last_rf_accession"], "0001010-26-000006"
        )
        record = state_payload["ciks"]["0000001010"]
        self.assertTrue(Path(record["last_rf_baseline"]["path"]).exists())
        self.assertEqual(state_payload["universe"]["HKSTOCK"]["status"], "monitored")
        self.assertEqual(state_payload["universe"]["HKSTOCK"]["sec_ticker"], "HKADR")
        filings_dir = self.data_dir / "filings" / "0000001010" / "000101026000006"
        self.assertTrue((filings_dir / "risk_factors.txt").exists())
        metadata = json.loads((filings_dir / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["rf_status"], "extracted")
        self.assertIsNone(metadata["diff_vs"])
        lines = self._alerts_lines()
        self.assertEqual(len(lines), 7)
        red_row = json.loads(lines[0])
        self.assertEqual(red_row["level"], "RED")
        self.assertEqual(red_row["item_code"], "1.03")
        self.assertEqual(red_row["items"], "1.03,9.01")
        self.assertFalse(red_row["digest_sent"])

    def test_second_run_is_heartbeat_without_new_rows(self):
        self._run_watch("--dry-alert", session=self._session())
        alerts_before = self._alerts_lines()
        filings_before = sorted(p.name for p in (self.data_dir / "filings" / "0000001010").iterdir())
        code, output = self._run_watch("--dry-alert", session=self._session())
        self.assertEqual(code, 0, output)
        self.assertIn("✅ EDGAR watch ok · 0 new filings · 4 monitored", output)
        state_payload = self._read_state()
        self.assertEqual(state_payload["run_count"], 2)
        self.assertEqual(self._alerts_lines(), alerts_before)
        filings_after = sorted(p.name for p in (self.data_dir / "filings" / "0000001010").iterdir())
        self.assertEqual(filings_after, filings_before)

    def test_new_periodic_filing_diffs_risk_factors_against_baseline(self):
        self._run_watch("--dry-alert", session=self._session())
        self._run_watch("--dry-alert", session=self._session())
        submissions_v2 = dict(self._submissions_by_cik())
        submissions_v2["0000001010"] = _submissions("1010", TESTA_V2_ROWS)
        routes = _default_routes(submissions_v2, self._docs_by_name())
        code, output = self._run_watch("--dry-alert", session=_FakeSession(routes))
        self.assertEqual(code, 0, output)
        self.assertIn("[TESTA] 10-K filed ", output)
        # The digest counts must equal a locally recomputed v1 -> v2 diff.
        added, removed = _recomputed_rf_diff_counts()
        self.assertIn(f"Risk Factors: +{added}/-{removed}", output)
        state_payload = self._read_state()
        self.assertEqual(
            state_payload["ciks"]["0000001010"]["last_rf_accession"], "0001010-26-000008"
        )
        new_dir = self.data_dir / "filings" / "0000001010" / "000101026000008"
        self.assertTrue((new_dir / "risk_factors.txt").exists())
        self.assertTrue((new_dir / "rf_diff_vs_0001010-26-000006.txt").exists())
        alerts_lines = self._alerts_lines()
        self.assertEqual(len(alerts_lines), 8)
        periodic_row = json.loads(alerts_lines[-1])
        self.assertEqual(periodic_row["form"], "10-K")
        self.assertEqual(periodic_row["headline"], "Periodic filing (Risk Factors check)")

    def test_telegram_digest_sent_once_when_configured(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "TESTTOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "42"
        session = self._session()
        code, output = self._run_watch(session=session)
        self.assertEqual(code, 0, output)
        self.assertEqual(len(session.posts), 1)
        post = session.posts[0]
        self.assertEqual(post["url"], "https://api.telegram.org/botTESTTOKEN/sendMessage")
        self.assertEqual(post["data"]["chat_id"], "42")
        alerts_line = json.loads(self._alerts_lines()[0])
        self.assertTrue(alerts_line["digest_sent"])

    def test_partial_cik_failure_commits_only_successful_state_and_exits_2(self):
        submissions_by_cik = self._submissions_by_cik()
        failing_routes = _default_routes(
            submissions_by_cik,
            self._docs_by_name(),
        )

        def route_with_failure(url):
            if "CIK0000002020" in url:
                return _FakeResponse(503, text="unavailable")
            return failing_routes(url)

        code, output = self._run_watch("--dry-alert", session=_FakeSession(route_with_failure))
        self.assertEqual(code, 2, output)
        self.assertIn("CIK error [TESTB]", output)
        submissions_requests = [g["url"] for g in self._session_holder["session"].gets if "submissions" in g["url"]]
        self.assertEqual(submissions_requests.count(
            "https://data.sec.gov/submissions/CIK0000002020.json"), 3
        )
        state_payload = self._read_state()
        self.assertNotIn("0000002020", state_payload["ciks"])
        self.assertIn("0000001010", state_payload["ciks"])
        self.assertEqual(len(self._alerts_lines()), 6)

    def test_busy_lock_exits_3_without_writing_state(self):
        lock_path = self.data_dir / "watch.lock"
        holder = open(lock_path, "a+", encoding="utf-8")
        self.addCleanup(holder.close)
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        code, _output = self._run_watch("--dry-alert", session=self._session())
        self.assertEqual(code, 3)
        self.assertFalse((self.data_dir / "state.json").exists())
        self.assertFalse((self.data_dir / "alerts.jsonl").exists())

    def test_sec_block_aborts_before_state_commit_and_send(self):
        def blocked_route(url):
            if "submissions" in url:
                return _FakeResponse(403, text="<html>Your Request Originates from an Undeclared Automated Tool</html>")
            raise AssertionError("blocked run must not reach documents")

        session = _FakeSession(blocked_route)
        code, output = self._run_watch(session=session)
        self.assertEqual(code, 1, output)
        self.assertIn("CIK error [TESTA]", output)
        self.assertIn("BLOCKED", output)
        self.assertFalse((self.data_dir / "state.json").exists())
        self.assertFalse((self.data_dir / "alerts.jsonl").exists())
        self.assertEqual(session.posts, [])
        # The identity is reported, never rotated.
        self.assertEqual(len(session.gets), 3)
        for recorded in session.gets:
            self.assertEqual(
                recorded["headers"]["User-Agent"],
                session.gets[0]["headers"]["User-Agent"],
            )

    def test_extract_rf_reports_counts_and_touches_no_state(self):
        # The extract-rf flow fetches the two latest periodics (v2 rows put
        # both the 2026-11-06 and 2026-11-07 filings in the window).
        routes = _default_routes(
            {"0000001010": _submissions("1010", TESTA_V2_ROWS)}, self._docs_by_name()
        )
        code, output = self._run_watch("--extract-rf", "TESTA", session=_FakeSession(routes))
        self.assertEqual(code, 0, output)
        self.assertIn("latest: 10-K 0001010-26-000008", output)
        self.assertIn("previous: 10-K 0001010-26-000006", output)
        added, removed = _recomputed_rf_diff_counts()
        self.assertIn(f"diff: +{added}/-{removed} lines", output)
        self.assertIn('"Supply chain concentration"', output)
        diff_files = list((self.data_dir / "rf_check").glob("TESTA_*.diff"))
        self.assertEqual(len(diff_files), 1)
        self.assertFalse((self.data_dir / "state.json").exists())
        self.assertFalse((self.data_dir / "alerts.jsonl").exists())

    def test_limit_tickers_processes_largest_positions_only(self):
        routes = _default_routes(self._submissions_by_cik(), self._docs_by_name())
        session = _FakeSession(routes)
        code, output = self._run_watch("--dry-alert", "--limit-tickers", "1", session=session)
        self.assertEqual(code, 0, output)
        submissions_urls = [g["url"] for g in session.gets if "submissions" in g["url"]]
        self.assertEqual(
            submissions_urls, ["https://data.sec.gov/submissions/CIK0000001010.json"]
        )
        self.assertIn("--limit-tickers hid 3 of 4 monitored", output)
        self.assertFalse((self.data_dir / "alerts.jsonl").read_text(encoding="utf-8").strip() == "")

    def test_8ka_scan_failure_degrades_to_items_unknown_alert(self):
        # An 8-K/A with empty items needs the one-shot document scan; the
        # primary document is absent from the docs map, so the route returns
        # 404 and the scan fails. The run must degrade, not crash.
        submissions_by_cik = self._submissions_by_cik()
        submissions_by_cik["0000001010"] = _submissions(
            "1010",
            [("0001010-26-000100", "8-K/A", "", "testa-8ka-unscannable.htm", _day_offset(0))],
        )
        routes = _default_routes(submissions_by_cik, self._docs_by_name())
        code, output = self._run_watch("--dry-alert", session=_FakeSession(routes))
        self.assertEqual(code, 0, output)
        self.assertIn("Items unknown (scan failed)", output)
        rows = [json.loads(line) for line in self._alerts_lines()]
        unknown = [row for row in rows if row["headline"] == "Items unknown (scan failed)"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["form"], "8-K/A")
        self.assertIsNone(unknown[0]["item_code"])
        self.assertIsNone(unknown[0]["items"])

    def test_telegram_failure_prints_full_digest(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "TESTTOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "42"

        class _FailingPostSession(_FakeSession):
            def post(self, url, data=None, timeout=None, **_kwargs):
                self.posts.append({"url": url, "data": data})
                raise requests.ConnectionError("telegram unreachable")

        session = _FailingPostSession(
            _default_routes(self._submissions_by_cik(), self._docs_by_name())
        )
        code, output = self._run_watch(session=session)
        self.assertEqual(code, 0, output)
        self.assertEqual(len(session.posts), 1)
        # The full digest survives in the log (launchd stdout redirect).
        self.assertIn("EDGAR watch ·", output)
        self.assertIn("\U0001F534 [TESTA] 8-K items 1.03,9.01", output)

    def test_state_save_failure_exits_fatal_after_alerts_without_send(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "TESTTOKEN"
        os.environ["TELEGRAM_CHAT_ID"] = "42"
        session = self._session()
        with patch.object(watch.state_store, "save", side_effect=OSError("disk full")):
            code, output = self._run_watch(session=session)
        self.assertEqual(code, 1, output)
        # Alerts were appended: the next run re-alerts, which stays correct.
        self.assertTrue(self._alerts_lines())
        self.assertEqual(session.posts, [])
        self.assertFalse((self.data_dir / "state.json").exists())

    def test_healthcheck_pings_bare_url_on_success(self):
        url = "http://healthcheck.example/edgar-uid"
        with patch.object(watch.urllib.request, "urlopen") as ping:
            ping.return_value.__enter__.return_value.status = 200
            code, output = self._run_watch("--healthcheck-url", url, session=self._session())
        self.assertEqual(code, 0, output)
        self.assertEqual(ping.call_count, 1, output)
        self.assertEqual(ping.call_args[0][0], url)

    def test_healthcheck_pings_fail_path_on_partial_run(self):
        url = "http://healthcheck.example/edgar-uid"
        failing_routes = _default_routes(self._submissions_by_cik(), self._docs_by_name())

        def route_with_failure(routed_url):
            if "CIK0000002020" in routed_url:
                return _FakeResponse(503, text="unavailable")
            return failing_routes(routed_url)

        with patch.object(watch.urllib.request, "urlopen") as ping:
            ping.return_value.__enter__.return_value.status = 200
            code, output = self._run_watch(
                "--healthcheck-url", url, session=_FakeSession(route_with_failure)
            )
        self.assertEqual(code, 2, output)
        self.assertEqual(ping.call_count, 1, output)
        self.assertEqual(ping.call_args[0][0], url + "/fail")

    def test_value_floor_hides_positions_and_counts_them(self):
        self.config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "force_include": {"HKSTOCK": {"via": "HKADR", "note": "sample ADR mapping"}},
                    "min_market_value_usd": 600,
                }
            ),
            encoding="utf-8",
        )
        code, output = self._run_watch("--dry-alert", session=self._session())
        self.assertEqual(code, 0, output)
        self.assertIn("Below value floor: 3", output)
        self.assertIn("monitored 1", output)
        self.assertIn("new 4", output)

    def test_invalid_min_market_value_config_is_fatal(self):
        self.config_path.write_text(
            json.dumps({"min_market_value_usd": "lots"}), encoding="utf-8"
        )
        code, output = self._run_watch("--dry-alert", session=self._session())
        self.assertEqual(code, 1, output)
        # The config parse fails before any network access.
        self.assertEqual(self._session_holder["session"].gets, [])


class EdgarClientTests(_OfflineModuleTestCase):
    def _client(self, route, **kwargs):
        kwargs.setdefault("min_request_interval", 0)
        kwargs.setdefault("retry_backoff_seconds", 0)
        return EdgarClient(session=_FakeSession(route), ua="Tester/1.0 (contact@example.com)", **kwargs)

    def test_submissions_json_roundtrip(self):
        client = self._client(_default_routes({"0000001010": {"entityType": "operating"}}, {}))
        payload = client.fetch_submissions("0000001010")
        self.assertEqual(payload["entityType"], "operating")

    def test_submissions_non_json_body_is_blocked_diagnosis(self):
        client = self._client(lambda url: _FakeResponse(200, text="<html>Request Rate Threshold Exceeded</html>"))
        with self.assertRaises(EdgarBlocked):
            client.fetch_submissions("0000001010")

    def test_submissions_non_dict_payload_is_blocked(self):
        client = self._client(lambda url: _FakeResponse(200, text="[1, 2]"))
        with self.assertRaises(EdgarBlocked):
            client.fetch_submissions("0000001010")

    def test_steady_403_raises_blocked_after_retries_and_keeps_identity(self):
        client = self._client(
            lambda url: _FakeResponse(403, text="<html>blocked</html>"), retries=2
        )
        with self.assertRaises(EdgarBlocked):
            client.fetch_submissions("0000001010")
        self.assertEqual(len(client.session.gets), 3)

    def test_steady_429_raises_blocked(self):
        client = self._client(lambda url: _FakeResponse(429, text="slow down"), retries=1)
        with self.assertRaises(EdgarBlocked):
            client.fetch_submissions("0000001010")

    def test_steady_503_raises_request_error(self):
        client = self._client(lambda url: _FakeResponse(503, text="unavailable"), retries=1)
        with self.assertRaises(EdgarRequestError):
            client.fetch_submissions("0000001010")

    def test_document_404_passes_through_without_block(self):
        client = self._client(lambda url: _FakeResponse(404, text="missing"))
        status, body = client.fetch_document("0000001010", "000101026000007", "missing.htm")
        self.assertEqual(status, 404)
        self.assertEqual(body, "missing")

    def test_user_agent_prefers_env_over_default(self):
        os.environ["SEC_USER_AGENT"] = "OwnerUA/1.0 (contact@owner.example)"
        try:
            client = EdgarClient(session=_FakeSession(lambda url: _FakeResponse(200, text="{}")))
            self.assertEqual(client.ua, "OwnerUA/1.0 (contact@owner.example)")
            client.fetch_submissions("0000001010")
            headers = client.session.gets[0]["headers"]
            self.assertEqual(headers["User-Agent"], "OwnerUA/1.0 (contact@owner.example)")
        finally:
            os.environ.pop("SEC_USER_AGENT", None)

    def test_default_user_agent_is_honest_fallback(self):
        os.environ.pop("SEC_USER_AGENT", None)
        client = EdgarClient(session=_FakeSession(lambda url: _FakeResponse(200, text="{}")))
        self.assertIn("investment-portfolio-edgar-watch/1.0", client.ua)

    def test_pacing_space_outs_requests(self):
        client = EdgarClient(
            session=_FakeSession(lambda url: _FakeResponse(200, text="{}")),
            ua="Tester/1.0",
            min_request_interval=0.05,
        )
        started = time.monotonic()
        client.fetch_submissions("0000001010")
        client.fetch_submissions("0000001010")
        self.assertGreaterEqual(time.monotonic() - started, 0.049)

    def test_filing_url_construction(self):
        client = self._client(lambda url: _FakeResponse(200, text="{}"))
        self.assertEqual(
            client.filing_url("0000001010", "0001010-26-000007"),
            "https://www.sec.gov/Archives/edgar/data/0000001010/000101026000007/0001010-26-000007-index.htm",
        )


class UniverseTests(_OfflineModuleTestCase):
    def test_normalize_symbol_maps_spaces_and_dots(self):
        self.assertEqual(universe.normalize_symbol("BRK B"), "BRK-B")
        self.assertEqual(universe.normalize_symbol("bf.b"), "BF-B")
        self.assertEqual(universe.normalize_symbol(" ok "), "OK")

    def test_load_snapshot_symbols_reads_equity_buckets_only(self):
        rows, value_filtered = universe.load_snapshot_symbols(FIXTURES / "snapshot_fixture.json")
        self.assertEqual(value_filtered, 0)
        tickers = [row["ticker"] for row in rows]
        self.assertIn("TESTA", tickers)
        self.assertIn("HKSTOCK", tickers)
        self.assertNotIn("SAMPLENOTE", tickers)
        self.assertNotIn("SAMPLECOIN", tickers)
        test_a = next(row for row in rows if row["ticker"] == "TESTA")
        self.assertEqual(test_a["market_value"], 900.0)

    def test_min_market_value_floor_is_applied_and_counted(self):
        rows, value_filtered = universe.load_snapshot_symbols(
            FIXTURES / "snapshot_fixture.json", min_market_value_usd=350
        )
        self.assertEqual(sorted(row["ticker"] for row in rows), ["TESTA", "TESTB"])
        self.assertEqual(value_filtered, 2)
        # A floor above every position keeps the empty-universe signal.
        rows_all, value_filtered_all = universe.load_snapshot_symbols(
            FIXTURES / "snapshot_fixture.json", min_market_value_usd=10_000
        )
        self.assertEqual(rows_all, [])
        self.assertEqual(value_filtered_all, 4)

    def test_build_cik_map_pads_ciks_and_normalizes(self):
        payload = {"0": {"cik_str": 1067983, "ticker": "BRK B", "title": "Sample Holder"}}
        cik_map = universe.build_cik_map(payload)
        self.assertEqual(cik_map["BRK-B"]["cik"], "0001067983")

    def test_load_cik_map_fetches_caches_and_falls_back(self):
        session = _FakeSession(_default_routes({}, {}, ticker_map=_fixture_json("company_tickers_fixture.json")))
        cache_path = self.data_dir / "cik_map_blank.json"
        cik_map, source = universe.load_cik_map(session, cache_path, ua="UA/1.0 (a@b.example)", now=FIXED_NOW)
        self.assertEqual(source, "fresh")
        self.assertIn("TESTA", cik_map)
        second_map, second_source = universe.load_cik_map(session, cache_path, ua="UA/1.0", now=FIXED_NOW)
        self.assertEqual(second_source, "cache")
        self.assertEqual(second_map, cik_map)
        # Exactly one network fetch: the second load is served from cache.
        self.assertEqual(len(session.gets), 1)
        self.assertEqual(session.gets[0]["url"], TICKER_MAP_URL)

        # Stale cache survives a failing fetch.
        old_stamp = (FIXED_NOW - timedelta(days=60)).timestamp()
        os.utime(cache_path, (old_stamp, old_stamp))

        def failing(url):
            raise requests.ConnectionError("offline")

        stale_map, stale_source = universe.load_cik_map(_FakeSession(failing), cache_path, now=FIXED_NOW)
        self.assertEqual(stale_source, "stale")
        self.assertIn("TESTA", stale_map)

        with self.assertRaises(requests.ConnectionError):
            universe.load_cik_map(_FakeSession(failing), self.data_dir / "absent_cache.json", now=FIXED_NOW)

    def test_resolve_positions_statuses_and_forces(self):
        rows, _value_filtered = universe.load_snapshot_symbols(FIXTURES / "snapshot_fixture.json")
        cik_map = universe.build_cik_map(_fixture_json("company_tickers_fixture.json"))
        positions = universe.resolve_positions(rows, cik_map, {})
        statuses = {p.ticker: p.status for p in positions}
        self.assertEqual(statuses["TESTA"], "monitored")
        self.assertEqual(statuses["HKSTOCK"], "skipped_unresolved")

        positions = universe.resolve_positions(
            rows,
            cik_map,
            {"force_include": {"HKSTOCK": {"via": "HKADR"}}, "force_exclude": {"SAMPLECO": {}}},
        )
        statuses = {p.ticker: (p.status, p.cik, p.sec_ticker, p.forced) for p in positions}
        self.assertEqual(statuses["HKSTOCK"], ("monitored", "0000005050", "HKADR", True))
        self.assertEqual(statuses["SAMPLECO"], ("excluded_config", "", "", True))

    def test_classify_fund_multi_signal(self):
        spy_like = {"entityType": "other", "sic": "6770", "filings": {"recent": {"form": ["NPORT-P"]}}}
        self.assertTrue(universe.classify_fund(spy_like))
        slv_like = {"entityType": "operating", "sic": "6221", "filings": {"recent": {"form": ["8-K"]}}}
        self.assertTrue(universe.classify_fund(slv_like))
        nport_only = {"entityType": "operating", "sic": "3571", "filings": {"recent": {"form": ["NPORT-P"]}}}
        self.assertTrue(universe.classify_fund(nport_only))
        operating = {
            "entityType": "operating",
            "sic": "3571",
            "filings": {"recent": {"form": ["10-K", "8-K", "4"]}},
        }
        self.assertFalse(universe.classify_fund(operating))


class DigestTests(_OfflineModuleTestCase):
    def _red_event(self):
        return {
            "form": "8-K",
            "item_code": "1.03",
            "items": "1.03,9.01",
            "title": "Bankruptcy or Receivership",
            "level": severity.LEVEL_RED,
            "accession": "0001010-26-000007",
            "filed": "2026-11-06",
            "url": "https://www.sec.gov/Archives/edgar/data/0000001010/000101026000007/0001010-26-000007-index.htm",
        }

    def test_red_info_and_form4_sections(self):
        results = [
            {
                "ticker": "TESTA",
                "events": [self._red_event(),
                           dict(self._red_event(), item_code="9.01", title="Financial Statements and Exhibits", level=severity.LEVEL_INFO),
                           {"form": "4", "level": severity.LEVEL_INFO, "item_code": None, "accession": "b", "url": "u4", "filed": "2026-11-05", "title": "Form 4", "items": None}],
                "rf": [{"form": "10-K", "filed": "2026-11-05", "accession": "a", "url": "u", "status": "extracted", "added": 3, "removed": 1, "headers": ["New risk header"], "no_baseline": False}],
            }
        ]
        skipped = {"unresolved": ["HKX"], "fund": ["FND"], "excluded": [], "hidden_by_limit": 0}
        ctx = {
            "ts": "2026-11-07T12:00:00Z", "positions": 4, "monitored": 3, "processed": 3,
            "new": 3, "failures": [], "digest": {"char_budget": 4000},
        }
        text = digest_module.build_digest(results, skipped, ctx)
        self.assertIn("EDGAR watch · 2026-11-07T12:00:00Z · positions 4 · monitored 3 · new 3", text)
        self.assertIn("\U0001F534 [TESTA] 8-K items 1.03,9.01", text)
        self.assertIn("Bankruptcy or Receivership", text)
        self.assertIn("1 × Form 4 (insider changes)", text)
        self.assertIn("Risk Factors: +3/-1", text)
        self.assertIn('new: "New risk header"', text)
        self.assertIn("Skipped: 1 unresolved, 1 fund-like", text)

    def test_heartbeat_for_zero_new_filings(self):
        text = digest_module.build_digest([], {"unresolved": [], "fund": [], "excluded": [], "hidden_by_limit": 0}, {"ts": "t", "positions": 4, "monitored": 3, "processed": 3, "new": 0, "failures": []})
        self.assertEqual(text, "✅ EDGAR watch ok · 0 new filings · 3 monitored")

    def test_failure_lines_render(self):
        ctx = {
            "ts": "t", "positions": 1, "monitored": 1, "processed": 1, "new": 0,
            "failures": [{"ticker": "TESTB", "error": "EDGAR returned 503 after 3 attempts"}],
        }
        text = digest_module.build_digest(
            [{"ticker": "TESTB", "error": "boom", "events": [], "rf": []}],
            {"unresolved": [], "fund": [], "excluded": [], "hidden_by_limit": 0},
            ctx,
        )
        self.assertIn("CIK error [TESTB]", text)
        self.assertIn("EDGAR returned 503", text)

    def test_budget_drops_info_first_and_appends_marker(self):
        results = [
            {"ticker": f"T{i}", "events": [], "rf": [], "error": None} for i in range(6)
        ]
        info_events = []
        for index in range(6):
            results[index]["events"] = [
                {
                    "form": "8-K",
                    "item_code": "2.02",
                    "items": "2.02",
                    "title": f"Info event title {index}",
                    "level": severity.LEVEL_INFO,
                    "accession": f"acc{index}",
                    "filed": "2026-11-06",
                    "url": f"https://u/{index}",
                }
            ]
        red_blocks_results = [
            {"ticker": "RED1", "events": [self._red_event()], "rf": [], "error": None}
        ]
        ctx = {
            "ts": "t", "positions": 9, "monitored": 9, "processed": 9, "new": 9,
            "failures": [], "digest": {"char_budget": 550, "max_info_lines": 20},
        }
        text = digest_module.build_digest(red_blocks_results + results, {"unresolved": [], "fund": [], "excluded": [], "hidden_by_limit": 0}, ctx)
        self.assertIn("\U0001F534 [RED1]", text)
        # The budget fits RED plus four info blocks; the last two info blocks
        # are dropped and marked with the alerts-log pointer.
        self.assertIn("Info event title 0", text)
        self.assertNotIn("Info event title 5", text)
        self.assertIn(f"… (+2 entries in {digest_module.ALERTS_LOG_PATH})", text)

    def _warn_tier_results(self):
        """RED + one large WARN block + several small INFO blocks."""
        warn_url = (
            "https://www.sec.gov/Archives/edgar/data/0000001010/"
            "000101026000009/0001010-26-000009-large-warn-url-padding.htm"
        )
        warn_event = {
            "form": "8-K",
            "item_code": "2.05",
            "items": "2.05",
            "title": "Costs Associated with Exit or Disposal Activities",
            "level": severity.LEVEL_WARN,
            "accession": "0001010-26-000009",
            "filed": "2026-11-06",
            "url": warn_url,
        }
        results = [
            {"ticker": "RED1", "events": [self._red_event()], "rf": [], "error": None},
            {"ticker": "WARN1", "events": [warn_event], "rf": [], "error": None},
        ]
        for index in range(3):
            results.append(
                {
                    "ticker": f"T{index}",
                    "events": [self._info_event(index)],
                    "rf": [],
                    "error": None,
                }
            )
        return results

    def _info_event(self, index):
        return {
            "form": "8-K",
            "item_code": "2.02",
            "items": "2.02",
            "title": f"Info event title {index}",
            "level": severity.LEVEL_INFO,
            "accession": f"acc{index}",
            "filed": "2026-11-06",
            "url": f"https://u/{index}",
        }

    def _segments(self, results, new):
        skipped = {"unresolved": [], "fund": [], "excluded": [], "hidden_by_limit": 0}
        ctx = {
            "ts": "t", "positions": 5, "monitored": 5, "processed": 5,
            "new": new, "failures": [],
            "digest": {"char_budget": 100000, "max_info_lines": 20},
        }
        unrestricted = digest_module.build_digest(results, skipped, ctx)
        segments = [s for s in unrestricted.split("\n\n") if s]
        return segments[0], segments[1:]

    def test_warn_block_kept_and_infos_forfeited_under_tight_budget(self):
        results = self._warn_tier_results()
        # Measure the real rendered sizes with a generous budget, then pin
        # the budget to the exact boundary where WARN still fits.
        header, blocks = self._segments(results, new=5)
        budget = len(header) + 2 + len(blocks[0]) + 2 + len(blocks[1])
        ctx = {
            "ts": "t", "positions": 5, "monitored": 5, "processed": 5,
            "new": 5, "failures": [],
            "digest": {"char_budget": budget, "max_info_lines": 20},
        }
        text = digest_module.build_digest(
            results,
            {"unresolved": [], "fund": [], "excluded": [], "hidden_by_limit": 0},
            ctx,
        )
        self.assertIn("\U0001F534 [RED1]", text)
        self.assertIn("Costs Associated with Exit or Disposal Activities", text)
        # Dropping nothing above INFO is a WARN kept boundary: every INFO is
        # forfeited wholesale, not just the ones that no longer fit.
        self.assertNotIn("Info event title 0", text)
        self.assertNotIn("Info event title 2", text)
        self.assertIn(f"… (+3 entries in {digest_module.ALERTS_LOG_PATH})", text)

    def test_form4_drop_forfeits_infos_under_tight_budget(self):
        form4_event = dict(
            self._red_event(),
            form="4",
            item_code=None,
            items=None,
            title="Form 4",
            level=severity.LEVEL_INFO,
            accession="acc4",
            url="https://u/4",
        )
        results = [
            {"ticker": "RED1", "events": [self._red_event()], "rf": [], "error": None},
            {"ticker": "T4", "events": [form4_event], "rf": [], "error": None},
            {"ticker": "T0", "events": [self._info_event(0)], "rf": [], "error": None},
            {"ticker": "T1", "events": [self._info_event(1)], "rf": [], "error": None},
        ]
        header, blocks = self._segments(results, new=4)
        blocks = [b for b in blocks if "Form 4" not in b]
        # The Form 4 fold line never fits: it is dropped (1) and both INFO
        # blocks are forfeited (2).
        budget = len(header) + 2 + len(blocks[0])
        ctx = {
            "ts": "t", "positions": 5, "monitored": 5, "processed": 5,
            "new": 4, "failures": [],
            "digest": {"char_budget": budget, "max_info_lines": 20},
        }
        text = digest_module.build_digest(
            results,
            {"unresolved": [], "fund": [], "excluded": [], "hidden_by_limit": 0},
            ctx,
        )
        self.assertIn("\U0001F534 [RED1]", text)
        self.assertNotIn("Form 4 (insider changes)", text)
        self.assertNotIn("Info event title 0", text)
        self.assertIn(f"… (+3 entries in {digest_module.ALERTS_LOG_PATH})", text)

    def test_rf_failure_suffixes(self):
        for status, marker in (
            ("document_fetch_failed", "document fetch failed"),
            ("item1a_not_found", "item 1A not found"),
            ("empty", "empty 1A"),
        ):
            results = [
                {"ticker": "T", "events": [], "rf": [{"form": "10-K", "filed": "d", "status": status, "url": "u"}]}
            ]
            text = digest_module.build_digest(
                results,
                {"unresolved": [], "fund": [], "excluded": [], "hidden_by_limit": 0},
                {
                    "ts": "t", "positions": 1, "monitored": 1, "processed": 1, "new": 1,
                    "failures": [], "digest": {},
                },
            )
            self.assertIn(f"Risk Factors unavailable ({marker})", text)


if __name__ == "__main__":
    unittest.main()
