"""Single-instance job wrapper with retry, receipt and healthcheck support.

POSIX only (fcntl advisory locks); Windows is not supported.

Usage: python -m src.job_control.run_job --job NAME [--retries N]
    [--retry-delay S] [--retry-max-delay S] [--env-file PATH|none]
    [--healthcheck-url URL] -- <command>...

Everything after the first ``--`` is executed verbatim as the command. The
wrapper refuses to start the command twice in parallel for the same job: an
advisory ``flock`` on ``data/run/<job>.lock`` makes a second run exit with
code 3 and record ``outcome:"locked"`` without healthcheck pings. One newline
separated JSON receipt per run is appended to ``data/run/receipts.jsonl``
(fields: schema, job, start_utc, end_utc, duration_s, attempts, exit_code,
outcome, command, pid, retry_delay_s, notified).

Healthcheck: with ``--healthcheck-url`` or ``HEALTHCHECK_<JOB>_URL`` set, one
``/start`` ping is sent before the first attempt, the bare URL on success and
``/fail`` after the last failed attempt. Pings are best-effort GETs with a 5s
timeout; their failures are warnings on stderr and never change the exit code.
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.env_file import _load_local_env_file, DEFAULT_ENV_FILE

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_DIR = PROJECT_ROOT / "data" / "run"
RECEIPTS_FILE = RUN_DIR / "receipts.jsonl"
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 60.0
HEALTHCHECK_TIMEOUT_S = 5
RECEIPT_SCHEMA = 1

OUTCOME_FAILURE_EXIT = 1
OUTCOME_USAGE_EXIT = 2
OUTCOME_LOCKED_EXIT = 3


def _healthcheck_env_name(job: str) -> str:
    chars = [ch.upper() if ch.isalnum() else "_" for ch in job]
    return "HEALTHCHECK_" + "".join(chars) + "_URL"


def _healthcheck_url(job: str, explicit_url: str) -> str:
    if explicit_url:
        return explicit_url
    return os.environ.get(_healthcheck_env_name(job), "")


def _ping(url: str) -> bool:
    """Best-effort healthcheck GET; failures are warnings, never errors."""
    try:
        with urllib.request.urlopen(url, timeout=HEALTHCHECK_TIMEOUT_S) as response:
            return 200 <= getattr(response, "status", 200) < 300
    except Exception as exc:  # any failure stays a warning on stderr
        print(f"run_job: healthcheck ping failed: {exc}", file=sys.stderr)
        return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _acquire_lock(job: str):
    """Return (handle, holder_pid); handle None means another run holds it."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = RUN_DIR / f"{job}.lock"
    handle = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.seek(0)
        holder = handle.read(64).strip()
        handle.close()
        return None, holder or "unknown"
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle, None


def _write_receipt(receipt: dict) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(receipt, ensure_ascii=False) + "\n"
    descriptor = os.open(RECEIPTS_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
    finally:
        os.close(descriptor)


def _record(outcome: dict) -> None:
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "job": outcome["job"],
        "start_utc": outcome["start_utc"],
        "end_utc": outcome["end_utc"],
        "duration_s": outcome["duration_s"],
        "attempts": outcome["attempts"],
        "exit_code": outcome["exit_code"],
        "outcome": outcome["outcome"],
        "command": outcome["command"],
        "pid": os.getpid(),
        "retry_delay_s": outcome["retry_delay_s"],
        "notified": outcome["notified"],
    }
    _write_receipt(receipt)


def _parse_args(argv):
    """Split argv on the first ``--``; strict argparse on the left side only."""
    left, right = argv, []
    if "--" in argv:
        separator = argv.index("--")
        left, right = argv[:separator], argv[separator + 1 :]
    parser = argparse.ArgumentParser(
        prog="src.job_control.run_job",
        description=(
            "Run a command under an advisory lock with retries, a receipt "
            "and healthcheck pings."
        ),
    )
    parser.add_argument(
        "--job", required=True, help="job name used for the lock, receipt and env suffix"
    )
    parser.add_argument(
        "--retries", type=int, default=0, help="extra attempts after the first one (default 0)"
    )
    parser.add_argument(
        "--retry-delay", type=float, default=DEFAULT_RETRY_DELAY, help="first backoff delay in seconds"
    )
    parser.add_argument(
        "--retry-max-delay", type=float, default=DEFAULT_RETRY_MAX_DELAY, help="backoff cap in seconds"
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        metavar="PATH|none",
        help="env file loaded with setdefault semantics (default data/ib_flex_env.sh)",
    )
    parser.add_argument(
        "--healthcheck-url", default="", help="ping URL (otherwise HEALTHCHECK_<JOB>_URL)"
    )
    namespace = parser.parse_args(left)
    return namespace, right


def run(argv=None) -> int:
    opts, command = _parse_args(sys.argv[1:] if argv is None else argv)
    if not command:
        raise SystemExit(OUTCOME_USAGE_EXIT)

    if opts.env_file.strip().lower() != "none":
        _load_local_env_file(Path(opts.env_file))

    url = _healthcheck_url(opts.job, opts.healthcheck_url)
    retry_delay = max(0.0, opts.retry_delay)
    handle, holder = _acquire_lock(opts.job)
    start = datetime.now(timezone.utc)

    if handle is None:
        print(f"{opts.job}: already running (pid {holder})", file=sys.stderr)
        _record(
            {
                "job": opts.job,
                "start_utc": _utc_now(),
                "end_utc": _utc_now(),
                "duration_s": 0.0,
                "attempts": 1,
                "exit_code": OUTCOME_LOCKED_EXIT,
                "outcome": "locked",
                "command": command,
                "retry_delay_s": retry_delay,
                "notified": "skipped",
            }
        )
        return OUTCOME_LOCKED_EXIT

    pings = []
    if url:
        pings.append(_ping(url + "/start"))

    try:
        planned_attempts = max(0, opts.retries) + 1
        executed = 0
        exit_code = None
        for index in range(planned_attempts):
            executed += 1
            try:
                exit_code = subprocess.run(command, check=False).returncode
            except OSError as exc:
                exit_code = None
                print(f"run_job: failed to run command: {exc}", file=sys.stderr)
            if exit_code == 0:
                break
            if index + 1 < planned_attempts:
                time.sleep(min(retry_delay * (2**index), max(0.0, opts.retry_max_delay)))

        end = datetime.now(timezone.utc)
        if exit_code == 0:
            outcome = "success"
            suffix = ""
        else:
            outcome = "fail"
            suffix = "/fail"
        if url:
            pings.append(_ping(url + suffix))
        notified = "skipped" if not url else ("ok" if all(pings) else "warning")
        _record(
            {
                "job": opts.job,
                "start_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duration_s": round((end - start).total_seconds(), 3),
                "attempts": executed,
                "exit_code": exit_code,
                "outcome": outcome,
                "command": command,
                "retry_delay_s": retry_delay,
                "notified": notified,
            }
        )
    finally:
        # Releasing the file descriptor releases the advisory lock.
        handle.close()

    return 0 if exit_code == 0 else (exit_code if exit_code is not None else OUTCOME_FAILURE_EXIT)


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(run())
