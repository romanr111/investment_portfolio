"""Synthetic combined_data examples for spreadsheet insight tests."""

from copy import deepcopy


def current_snapshot():
    return {
        "as_of_date": "2026-10-04",
        "TOTAL_ASSETS": 900.003,
        "FINANCIAL_FREEDOM_GOAL_TARGET": 1000.0,
        "IB_DATA": {
            "Total Stocks Value": 200.003,
            "Stocks": {"AAA": 100.0, "TINY": 0.003},
            "China Stocks": {"BBB": 100.0},
            "Bonds": {"SIM-BOND": 200.0},
            "Precious Metals": {"SIM-GOLD": 50.0},
            "Commodities": {"SIM-COM": 25.0},
            "REIT": {},
            "IB_Portfolio_Value": 450.003,
        },
        "ENHANCED_STOCKS": {
            "Stocks": {
                "AAA": {
                    "market_value": 100.0,
                    "unrealized_pnl": 7.05,
                    "unrealized_pnl_percentage": 7.05,
                    "avg_price": 93.4336,
                    "current_price": 100.0,
                    "currency": "USD",
                    "account_label": "IB",
                    "name": "Synthetic Alpha",
                }
            },
            "China Stocks": {
                "BBB": {
                    "market_value": 100.0,
                    "unrealized_pnl": 10.0,
                    "unrealized_pnl_percentage": 10.0,
                    "avg_price": 90.0,
                    "current_price": 100.0,
                    "currency": "HKD",
                    "account_label": "IB",
                    "name": "Synthetic Beta",
                }
            },
        },
        "CRYPTO_DATA": {
            "Total_Crypto_Value": 50.0,
            "Crypto_Market_Values": {"BTC": 50.0},
        },
        "FIXED_INCOME_DATA": {
            "group_weighted_interest": {
                "Bonds": (200.0, 0.04),
                "Crypto Landing": (100.0, 0.08),
                "p2p_lending": (100.0, 0.06),
            },
            "stocks_principal_and_interest": {
                "total_principal": 200.0,
                "weighted_interest": 2.5,
            },
            "stocks_yearly": 5.0,
            "stocks_monthly": 5.0 / 12,
        },
        "CASH_DATA": {"Total": 75.0, "Breakdown": {"SIM-CASH": 75.0}},
        "OTHER_ASSETS": {"Other Bets": 100.0},
        "IB_PERFORMANCE": {"rate_of_return_pct": 7.05, "measure": "TWR"},
        "DATA_METADATA": {
            "timestamp": 1791115200,
            "age_seconds": 60,
            "source": "live_api_calls",
            "last_updated": "2026-10-04T12:00:00",
        },
    }


def previous_snapshot():
    data = current_snapshot()
    data["as_of_date"] = "2026-09-30"
    data["TOTAL_ASSETS"] = 795.0
    data["IB_DATA"]["Total Stocks Value"] = 250.0
    data["IB_DATA"]["Stocks"] = {"AAA": 250.0}
    data["IB_DATA"]["China Stocks"] = {}
    data["IB_DATA"]["Bonds"] = {"SIM-BOND": 220.0}
    data["IB_DATA"]["Commodities"] = {"SIM-COM": 25.0}
    data["IB_DATA"]["Precious Metals"] = {"SIM-GOLD": 50.0}
    data["CRYPTO_DATA"]["Total_Crypto_Value"] = 0.0
    data["CRYPTO_DATA"]["Crypto_Market_Values"] = {}
    data["FIXED_INCOME_DATA"]["group_weighted_interest"]["Crypto Landing"] = (
        50.0,
        0.08,
    )
    data["FIXED_INCOME_DATA"]["group_weighted_interest"]["p2p_lending"] = (0.0, 0.06)
    data["CASH_DATA"]["Total"] = 100.0
    data["OTHER_ASSETS"]["Other Bets"] = 100.0
    return data


def cloned_snapshot(data):
    return deepcopy(data)
