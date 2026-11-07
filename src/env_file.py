"""Load shell-style env files into os.environ with setdefault semantics.

Shared by the sync entry point and the job wrapper so the default
data/ib_flex_env.sh path is defined in exactly one module.
"""

import os
import shlex
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / "data" / "ib_flex_env.sh"


def _load_local_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value, comments=False, posix=True)
        except ValueError:
            parsed = [value]
        os.environ.setdefault(key, parsed[0] if parsed else "")
