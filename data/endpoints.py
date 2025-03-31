from .config import load_ib_config

BINANCE = "https://api.binance.com"

COINMARKETCAP_API = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"

COINMARKETCAP_HEADERS = {
    "Accepts": "application/json",
    "X-CMC_PRO_API_KEY": "86a14075-ff6e-4a6c-824f-8b7adbfc34f2",
}

# Load IB configuration
IB_CONFIG = load_ib_config()
IB_BASE_URL = f"https://{IB_CONFIG['host']}:{IB_CONFIG['port']}"

SCOPE = ["https://www.googleapis.com/auth/drive"]
SUMMARY_API = f"{IB_BASE_URL}/v1/api/portfolio/U9064529/summary"
POSITIONS_API = f"{IB_BASE_URL}/v1/api/portfolio/U9064529/positions/0"

NASDAQ_API = "https://api.nasdaq.com/api/quote/"

PHYS_GOLD_ENDPOINT = "https://www.goldapi.io/api/"

MONO_API = "https://api.monobank.ua/personal/client-info"

MONO_PERSONAL_TOKEN = {"X-Token": "uHTZA41xA3X_UYLA7IDJ4fW8U2KL9NANONxq4-qhSrzI"}

CELSIUS_KEY = "b5015c33-8f56-4652-a630-8da62fe5189d"

NASDAQ_HEADERS = {
    "referer": "https://www.nasdaq.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 11_2_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.105 Safari/537.36",
}

# https://www.goldapi.io/dashboard
# IEX_API = 'https://cloud.iexapis.com/stable/crypto/'
# TOKEN = '?token=pk_fd6275d9647d425f8d15dfccdc4524ad'
