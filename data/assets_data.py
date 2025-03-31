CASH = 350 + 28.5  # Cash in wallet;
LENDED = 1470
DEBT = 0
PRIVAT = 1.5  # TODO To check API docs again

# LANDING
# TODO: to work on hardcoded savings format;
ESTATE_GURU = (3155, 0.08)  # TODO to withdraw 430 EUR
PEER_BERRY = (273, 0.068)  # TODO to withdraw ALL 273 EUR
WHITEBIT_SAVINGS = (
    ("USDC", 11601, 0.1739),
    ("USDC", 2004, 0.1563),
    ("USDT", 2245, 0.1864),
)
BYBIT_SAVINGS = {"USDC": (500, 0.0623), "USDT": (502, 0.06), "DAI": (885, 0.0778)}

# TREZOR + Other Crypto Wallets;
TREZOR = {"BTC": 0.039994, "ETH": 0.50884}
COLD_STORAGE = {**TREZOR, "EOS": 90, "NEO": 5, "SC": 4343}

# COIN_LOAN = (0, 0)
# YOU_HODLER = (0, 0)
# GLD_GRAMS_AVAILABLE = 0
