"""Where the Holy Grail stack finds local data and the shared economic profiles.

Every location derives from REPO_ROOT, so moving a module never changes what it reads.
`analytics/models/economic_profiles_v1.json` stays where the quarterly report also resolves it.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
CONFIG_PATH = DATA_DIR / "holy_grail_config.json"
CACHE_DIR = DATA_DIR / "holy_grail_history"
CAR_CATEGORY_BLOCK = DATA_DIR / "car_category" / "block_latest.json"
CAR_PROXIES_BLOCK = DATA_DIR / "car_category" / "proxies_latest.json"
PROFILE_PATH = REPO_ROOT / "analytics" / "models" / "economic_profiles_v1.json"
