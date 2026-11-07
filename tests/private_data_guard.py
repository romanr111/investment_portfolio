"""Skip tests that reach the private local ``data.*`` modules when they are absent.

Fresh clones carry only ``data/README.md``: the real ``data/filters_constants.py``,
``data/assets_data.py``, ``data/api_keys.py`` and ``data/endpoints.py`` hold private
holdings, tokens and account values and are intentionally never committed. Test
modules whose import chain reaches those files fail with collection errors there.
Raising ``unittest.SkipTest`` at module import marks them skipped by
``python -m unittest discover -s tests`` instead of failed, and leaves the owner's
full checkout (where every private module exists) running the complete suite.
"""
import importlib.util
import unittest

PRIVATE_DATA_MODULES = (
    "data.filters_constants",
    "data.assets_data",
    "data.api_keys",
    "data.endpoints",
)


def private_data_available() -> bool:
    """True when every imported-elsewhere private data module is importable."""
    return all(importlib.util.find_spec(name) is not None for name in PRIVATE_DATA_MODULES)


def require_private_data() -> None:
    """Raise ``unittest.SkipTest`` at module import when private data is absent."""
    missing = [name for name in PRIVATE_DATA_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        raise unittest.SkipTest(
            "private local data modules are absent in this checkout: " + ", ".join(missing)
        )
