#!/usr/bin/env python3
"""Parallel unittest runner using concurrent.futures.

Splits test files across N workers (default 3) and runs them in parallel.
Reports combined results. Exit code is non-zero if any worker fails.

Usage:
    python tests/parallel_runner.py [--workers N] [--pattern P]
"""

import argparse
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"
PYTHON = sys.executable


def discover_test_files(pattern: str) -> list[str]:
    return sorted(p.name for p in TESTS_DIR.glob(pattern))


def get_test_methods(filename: str) -> list[str]:
    """Parse a test file to extract test method names (test_*)."""
    methods: list[str] = []
    for line in (TESTS_DIR / filename).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("def test_"):
            name = stripped.split("(")[0].replace("def ", "")
            methods.append(name)
    return methods


def run_one_file(filename: str) -> dict:
    start = time.time()
    result = subprocess.run(
        [PYTHON, "-m", "unittest", "discover", "-s", "tests", "-p", filename, "-v"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    elapsed = time.time() - start
    stderr = result.stderr or ""
    ran_line = ""
    for line in stderr.splitlines():
        if line.startswith("Ran ") or line.startswith("OK") or "FAILED" in line:
            ran_line = line
            break
    return {
        "file": filename,
        "returncode": result.returncode,
        "elapsed": elapsed,
        "ran_line": ran_line,
        "stderr_tail": stderr[-500:] if stderr else "",
    }


def run_one_test(filename: str, test_name: str) -> dict:
    """Run a single test method from a file via unittest -k pattern."""
    start = time.time()
    result = subprocess.run(
        [PYTHON, "-m", "unittest", "discover", "-s", "tests", "-p", filename,
         "-k", test_name],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = time.time() - start
    stderr = result.stderr or ""
    ran_line = ""
    for line in stderr.splitlines():
        if line.startswith("Ran ") or line.startswith("OK") or "FAILED" in line:
            ran_line = line
            break
    return {
        "file": f"{filename}::{test_name}",
        "returncode": result.returncode,
        "elapsed": elapsed,
        "ran_line": ran_line,
        "stderr_tail": stderr[-500:] if stderr else "",
    }


def run_test_group(filename: str, test_names: list[str]) -> dict:
    """Run a group of test methods from a file using a temporary loader script."""
    start = time.time()
    # Build a small Python script that loads only the named tests.
    loader_code = (
        "import sys, unittest, importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('m', 'tests/{filename}')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        f"names = {test_names!r}\n"
        "suite = unittest.TestSuite()\n"
        "for cls_name in dir(mod):\n"
        "    cls = getattr(mod, cls_name)\n"
        "    if isinstance(cls, type) and issubclass(cls, unittest.TestCase):\n"
        "        for name in names:\n"
        "            if hasattr(cls, name):\n"
        "                suite.addTest(cls(name))\n"
        "runner = unittest.TextTestRunner(verbosity=0)\n"
        "result = runner.run(suite)\n"
        "sys.exit(0 if result.wasSuccessful() else 1)\n"
    )
    result = subprocess.run(
        [PYTHON, "-c", loader_code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    elapsed = time.time() - start
    stderr = result.stderr or ""
    ran_line = ""
    for line in stderr.splitlines():
        if line.startswith("Ran ") or line.startswith("OK") or "FAILED" in line:
            ran_line = line
            break
    label = f"{filename}::group[{len(test_names)}]"
    return {
        "file": label,
        "returncode": result.returncode,
        "elapsed": elapsed,
        "ran_line": ran_line,
        "stderr_tail": stderr[-500:] if stderr else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel unittest runner")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel workers")
    parser.add_argument("--pattern", default="test_*.py", help="Test file glob pattern")
    args = parser.parse_args()

    files = discover_test_files(args.pattern)
    if not files:
        print("No test files found.", file=sys.stderr)
        return 1

    print(f"Running {len(files)} test files across {args.workers} workers...")
    print()
    total_start = time.time()
    results = []

    # Split large files with setUpClass caching into GROUPS of tests rather
    # than individual tests. Each group runs in its own subprocess and
    # benefits from the class-level cache. This parallelizes the remaining
    # per-test work (which the cache doesn't eliminate) without forcing
    # each subprocess to re-do the cached setup for every single test.
    SPLIT_THRESHOLD = 20
    GROUP_SIZE = 14  # ~4 groups for a 54-test file, fits 8 workers
    jobs: list[tuple[str, str | None]] = []
    for f in files:
        methods = get_test_methods(f)
        source = (TESTS_DIR / f).read_text(encoding="utf-8")
        has_setup_class = "setUpClass" in source
        is_heavy = "import numpy" in source or "import pandas" in source
        if len(methods) > SPLIT_THRESHOLD and is_heavy:
            if has_setup_class:
                # Split into groups; each group shares the cached setUpClass.
                for i in range(0, len(methods), GROUP_SIZE):
                    group = methods[i : i + GROUP_SIZE]
                    # Encode group as pipe-separated test names.
                    pattern = "|".join(group)
                    jobs.append((f, pattern))
            else:
                # No cache — split per-test for maximum parallelism.
                for m in methods:
                    jobs.append((f, m))
        else:
            jobs.append((f, None))

    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for job in jobs:
            filename, test_spec = job
            if test_spec is None:
                fut = executor.submit(run_one_file, filename)
            elif "|" in test_spec:
                # Group of tests (pipe-separated names).
                group_names = test_spec.split("|")
                fut = executor.submit(run_test_group, filename, group_names)
            else:
                fut = executor.submit(run_one_test, filename, test_spec)
            futures[fut] = job
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            status = "OK" if res["returncode"] == 0 else "FAIL"
            print(f"  [{status}] {res['file']:55s} {res['elapsed']:6.1f}s  {res['ran_line']}")

    total_elapsed = time.time() - total_start
    results.sort(key=lambda r: r["file"])
    failures = [r for r in results if r["returncode"] != 0]

    print()
    print(f"Total: {len(results)} jobs, {len(failures)} failed, wall time {total_elapsed:.1f}s")
    if failures:
        print()
        for r in failures:
            print(f"=== {r['file']} (FAILED) ===")
            print(r["stderr_tail"][-800:])
            print()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())