from decimal import Decimal
from types import SimpleNamespace

from data.assets_data import OTHER_BETS
from src.data_source import DataSource
from src.google_sheets.spreadsheet_structure import PortfolioTableBuilder


def _extract_allocation_rows(table):
    rows = {}
    for row in table:
        if len(row) > 8 and row[6] and str(row[8]).endswith("%"):
            rows[row[6]] = row[7]
    return rows


def test_calculate_total_assets_excludes_ib_cash_from_cash_total():
    data_source = DataSource.__new__(DataSource)
    data_source.ib_data = {"IB_Portfolio_Value": 111230, "Net_cash": 8358}
    data_source.crypto = SimpleNamespace(get_total_crypto_value=lambda: 4627)
    data_source.fi_data = {
        "group_weighted_interest": {
            "Crypto Landing": (18295.1125, 0.0),
            "p2p_lending": (2295, 0.0),
        }
    }
    data_source.cash = SimpleNamespace(
        total_cash=Decimal("8610"),
        ib_cash=Decimal("8358"),
    )

    expected_total = int(
        111230 + 4627 + 18295.1125 + 2295 + float(Decimal("8610") - Decimal("8358")) + float(OTHER_BETS)
    )

    assert data_source.calculate_total_assets() == expected_total


def test_build_central_columns_uses_actual_cash_value_for_allocation_rows():
    data = {
        "FIN_FREEDOM_GOAL_PROGRESS": "0%",
        "TOTAL_ASSETS": 1000,
        "ALLOCATIONS": {
            "allocation_breakdown": {
                "Stocks": 40.0,
                "Bonds": 30.0,
                "Cash": 30.0,
            }
        },
        "IB_DATA": {
            "Total Stocks Value": 400,
            "Bonds": {"BOND": 300},
            "China Stocks": {},
            "Stocks": {},
            "Commodities": {},
            "Precious Metals": {},
            "REIT": {},
        },
        "CRYPTO_DATA": {"Total_Crypto_Value": 0},
        "FIXED_INCOME_DATA": {
            "group_weighted_interest": {
                "Crypto Landing": (0, 0.0),
                "p2p_lending": (0, 0.0),
            }
        },
        "CASH_DATA": {"Total": 50},
        "OTHER_ASSETS": {"Other Bets": 0},
    }

    table = PortfolioTableBuilder(data).build_central_columns([])
    rows = _extract_allocation_rows(table)

    assert rows["Stocks"] == "400"
    assert rows["Bonds"] == "300"
    assert rows["Cash"] == "50"
