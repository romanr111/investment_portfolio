import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from src.env_file import _load_local_env_file, DEFAULT_ENV_FILE as LOCAL_ENV_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = PROJECT_ROOT / ".venv"
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
RUNTIME_IMPORTS = ("pandas", "yaml", "ib_async", "gspread", "requests")


def _running_inside_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix) or hasattr(
        sys, "real_prefix"
    )


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _missing_runtime_imports() -> list:
    return [name for name in RUNTIME_IMPORTS if importlib.util.find_spec(name) is None]


def _ensure_venv() -> None:
    python_path = _venv_python()
    if not python_path.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])

    check = subprocess.run(
        [
            str(python_path),
            "-c",
            "import importlib.util, sys; "
            f"missing=[m for m in {RUNTIME_IMPORTS!r} if importlib.util.find_spec(m) is None]; "
            "sys.exit(1 if missing else 0)",
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if check.returncode != 0:
        subprocess.check_call(
            [str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)],
            cwd=PROJECT_ROOT,
        )


def _reexec_in_venv() -> None:
    python_path = _venv_python()
    os.execv(
        str(python_path),
        [str(python_path), "-m", "src.portfolio_sync", *sys.argv[1:]],
    )


def main() -> int:
    os.chdir(PROJECT_ROOT)
    _load_local_env_file()

    if not _running_inside_venv():
        _ensure_venv()
        _reexec_in_venv()

    if _missing_runtime_imports():
        _ensure_venv()

    from main import main as run_portfolio_sync

    return run_portfolio_sync()


if __name__ == "__main__":
    raise SystemExit(main())
