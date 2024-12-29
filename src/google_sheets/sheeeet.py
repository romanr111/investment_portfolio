import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from decimal import Decimal

CREDENTIALS_PATH = "data/credentials.json"
SPREADSHEET_NAME = "portfolio_automated"


def get_gspread_client():
    """
    Create an authorized gspread client using service account credentials.
    """
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
    client = gspread.authorize(credentials)
    return client


def create_tab_at_left(spreadsheet, sheet_title):
    """
    Create (or replace) a worksheet named sheet_title at index=1 (second from left).
    """
    # Remove if exists
    try:
        existing = spreadsheet.worksheet(sheet_title)
        spreadsheet.del_worksheet(existing)
    except gspread.exceptions.WorksheetNotFound:
        pass

    # Create new sheet
    worksheet = spreadsheet.add_worksheet(title=sheet_title, rows=200, cols=30)
    spreadsheet.batch_update(
        {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": worksheet.id, "index": 1},
                        "fields": "index",
                    }
                }
            ]
        }
    )
    return worksheet


def row_left(d_val="", e_val=""):
    """
    Helper to create a row that reaches columns D (index=3) & E (index=4).
    We'll fill columns A/B/C as empty, D with d_val, E with e_val.
    """
    return ["", "", "", d_val, e_val]


def parse_ib_data(ib_data):
    """
    Turn IB_DATA into a list of rows for columns D/E.
    Subcategories: e.g. 'Bonds', 'China Stocks', 'Stocks', 'REIT', etc.
    """
    rows = []
    for subcat, contents in ib_data.items():
        if isinstance(contents, dict):
            # Insert subcat label
            rows.append(row_left(subcat))
            # Then each symbol => value
            for sym, val in contents.items():
                rows.append(row_left(sym, str(val)))
            # Blank row
            rows.append(row_left())
        else:
            # Single-value keys like 'Total Stocks Value', 'Net_cash', etc.
            rows.append(row_left(subcat, str(contents)))
            rows.append(row_left())
    return rows


def parse_crypto_data(crypto_data):
    """
    Represent CRYPTO_DATA in a short summary for columns D/E:
      - Show total
      - Show top 5 or so from 'Crypto_Market_Values'
      - Omit detailed token quantities, or show them if you like
    """
    rows = []
    rows.append(row_left("CRYPTO_DATA"))  # Section label
    # 1) total
    total_crypto = crypto_data.get("Total_Crypto_Value", 0)
    rows.append(row_left("Total Crypto Value", str(total_crypto)))
    rows.append(row_left())

    # 2) Market Values
    market_vals = crypto_data.get("Crypto_Market_Values", {})
    if market_vals:
        rows.append(row_left("Market Values"))
        # For readability, let's just show them all or top few
        for sym, val in market_vals.items():
            rows.append(row_left(sym, str(val)))
        rows.append(row_left())

    # 3) If you want to show token quantities
    #    (we skip or you can partially show them)
    # rows.append(row_left("--Token Quantities--"))
    # for sym, qty in crypto_data.get("Token_Quantities", {}).items():
    #     rows.append(row_left(sym, str(qty)))
    # rows.append(row_left())

    return rows


def parse_fixed_income_data(fid_data):
    """
    Summarize the most relevant parts of FIXED_INCOME_DATA in columns D/E:
      - group_weighted_interest
      - monthly_earnings_fixed_income
      - yearly_earnings_fixed_income
      - etc.
    Skip the deeply nested 'fixed_income_full_data' or show briefly.
    """
    rows = []
    rows.append(row_left("FIXED_INCOME_DATA"))

    # group_weighted_interest
    gwi = fid_data.get("group_weighted_interest", {})
    if gwi:
        rows.append(row_left("Group Weighted Interest:"))
        for k, (principal, rate) in gwi.items():
            note = f"{principal} @ {rate}"
            rows.append(row_left(k, note))
        rows.append(row_left())

    # monthly/yearly
    monthly = fid_data.get("monthly_earnings_fixed_income", 0)
    yearly = fid_data.get("yearly_earnings_fixed_income", 0)
    rows.append(row_left("Monthly Income", str(monthly)))
    rows.append(row_left("Yearly Income", str(yearly)))
    rows.append(row_left())

    # Could also show e.g. 'stocks_principal_and_interest'
    # or 'calculated_income', depending on your preference
    # For brevity, let's show just the overall monthly/yearly.
    return rows


def parse_cash_data(cash_data):
    """
    Only show total from CASH_DATA, skipping breakdown.
    """
    rows = []
    total_val = cash_data.get("Total", 0)
    if isinstance(total_val, Decimal):
        total_val = float(total_val)
    rows.append(row_left("CASH_DATA (total)", str(total_val)))
    rows.append(row_left())
    return rows


def build_left_columns(data):
    """
    Build a list of rows that collectively represent
    IB_DATA, CRYPTO_DATA, FIXED_INCOME_DATA, and a single line for CASH_DATA.
    """
    rows = []

    # 1) IB_DATA
    ib_data = data.get("IB_DATA", {})
    if ib_data:
        rows.append(row_left("IB_DATA"))  # section label
        # parse subcategories
        rows.extend(parse_ib_data(ib_data))

    # 2) CRYPTO_DATA
    crypto_data = data.get("CRYPTO_DATA", {})
    if crypto_data:
        rows.extend(parse_crypto_data(crypto_data))

    # 3) FIXED_INCOME_DATA
    fid_data = data.get("FIXED_INCOME_DATA", {})
    if fid_data:
        rows.extend(parse_fixed_income_data(fid_data))

    # 4) CASH_DATA
    cash_data = data.get("CASH_DATA", {})
    if cash_data:
        rows.extend(parse_cash_data(cash_data))

    return rows


def build_right_columns(data, left_table):
    """
    We want to place data in columns G/H/I for:
      - row 0 => Financial Freedom => FIN_FREEDOM_GOAL_PROGRESS
      - row 1 => Net worth => TOTAL_ASSETS
      - row 2.. => each allocation category => value => pct
      - final => Monthly Dividend (if any from FIXED_INCOME_DATA or other)
    We'll place these in the first few rows, ignoring how big the left_table is.

    We'll define a helper to set a cell in final_table.
    """
    final_table = left_table[:]

    def set_cell(r, c, val):
        """Ensure final_table[r][c] exists, then set it."""
        while len(final_table) <= r:
            final_table.append([])
        while len(final_table[r]) <= c:
            final_table[r].append("")
        final_table[r][c] = val

    # Row 0 => colG=6 => "Financial Freedom", colH=7 => progress
    freedom = data.get("FIN_FREEDOM_GOAL_PROGRESS", "")
    set_cell(0, 6, "Financial Freedom")
    set_cell(0, 7, freedom)

    # Row 1 => colG=6 => "Net worth", colH=7 => total
    total_assets = data.get("TOTAL_ASSETS", 0)
    set_cell(1, 6, "Net worth")
    set_cell(1, 7, str(total_assets))
    # Row 1 => colI=8 => "%" (label)
    set_cell(1, 8, "%")

    # ALLOCATIONS
    # If present, show each category
    alloc_data = data.get("ALLOCATIONS", {}).get("allocation_breakdown", {})
    # We'll convert each category => (value, pct).
    # value = total_assets * (pct / 100)
    row_idx = 2
    for cat, pct in alloc_data.items():
        val = round(total_assets * (pct / 100))
        set_cell(row_idx, 6, cat)
        set_cell(row_idx, 7, str(val))
        set_cell(row_idx, 8, str(pct))
        row_idx += 1

    # Finally, monthly dividend (or monthly income)
    # from e.g. "FIXED_INCOME_DATA['monthly_earnings_fixed_income']"
    monthly_div = 0
    if "FIXED_INCOME_DATA" in data:
        monthly_div = data["FIXED_INCOME_DATA"].get("monthly_earnings_fixed_income", 0)
        # Round if needed
        monthly_div = round(monthly_div, 2)

    set_cell(row_idx, 6, "Monthly Dividend")
    set_cell(row_idx, 7, str(monthly_div))

    return final_table


def single_tab_update(spreadsheet, data):
    """
    Create a new tab named today's date, place it at index=1.
    Build a 'left_table' for columns D/E that includes IB_DATA, CRYPTO_DATA,
    FIXED_INCOME_DATA, and a line for total cash.
    Then overlay the 'right side' with net worth, allocations, etc.
    """
    date_title = datetime.now().strftime("%d %b %Y")
    worksheet = create_tab_at_left(spreadsheet, date_title)

    # 1) Build the left side
    left_table = build_left_columns(data)

    # 2) Add the right side info
    final_table = build_right_columns(data, left_table)

    # Upload
    worksheet.clear()
    worksheet.update("A1", final_table)


def main(data):
    """
    Main entry point.
    """
    client = get_gspread_client()
    spreadsheet = client.open(SPREADSHEET_NAME)

    single_tab_update(spreadsheet, data)


if __name__ == "__main__":
    # Example data structure (the one you provided).
    # In reality, you'll pass your actual data.
    from decimal import Decimal

    data_structure = {
        "IB_DATA": {
            "Bonds": {
                "IBCID746579811": 29655,
                "IBCID722427489": 22879,
                "TLT": 3481,
                "SGOV": 1705,
            },
            "China Stocks": {"700": 5378, "9988": 5304, "KWEB": 3950, "PDD": 975},
            "Stocks": {
                "C": 3834,
                "GOOG": 3688,
                "NKE": 3513,
                "BN": 2230,
                "CVS": 2001,
                "COP": 1842,
                "COF": 1802,
                "HUM": 1778,
                "CVX": 1733,
                "INTC": 1459,
                "IBKR": 1112,
                "ADBE": 894,
                "CP": 798,
                "UPS": 756,
            },
            "Short Selling": {},
            "REIT": {},
            "Gold": {"IAU": 544},
            "Commodities": {"COMB": 2572},
            "Total Stocks Value": 43047,
            "Net_cash": 139,
            "IB_Portfolio_Value": 104022,
        },
        "CRYPTO_DATA": {
            "Total_Crypto_Value": 6280,
            "Crypto_Market_Values": {
                "BTC": 3773,
                "ETH": 2062,
                "TON": 103,
                "ADA": 92,
                "BNB": 84,
                "EOS": 71,
                "NEO": 71,
                "SC": 24,
            },
            "Token_Quantities": {
                "BTC": 0.04,
                "ETH": 0.6129,
                "BNB": 0.1183,
                "ADA": 103.5215,
                "LUNA": 0.2025,
                "TON": 17.9381,
                "BANANA": 0.0062,
                "DOGS": 101.87,
                "HMSTR": 15.96,
                "CATI": 0.4943,
                "SCR": 0.2952,
                "USUAL": 1.622,
                "THE": 0.1729,
                "MOVE": 1.6477,
                "VANA": 0.0271,
                "PENGU": 20.4154,
                "1000CAT": 8.7506,
                "COMP": 0.0398,
                "UAH": 0.2925,
                "EOS": 90,
                "NEO": 5,
                "SC": 4343,
            },
        },
        "FIXED_INCOME_DATA": {
            "group_weighted_interest": {
                "Bonds": (57720, 0.044),
                "Crypto Landing": (25255, 0.108),
                "p2p_lending": (3508, 0.079),
            },
            "calculated_income": {
                "Bonds": 2540,
                "Crypto Landing": 2728,
                "p2p_lending": 277,
            },
            "fixed_inc_principal_and_interest": {"principal": 86483, "interest": 0.064},
            "monthly_earnings_fixed_income": 462.0833333333333,
            "yearly_earnings_fixed_income": 5545,
            "fixed_income_full_data": {
                "Bonds": {
                    "IBCID746579811": (29655, 0.044),
                    "IBCID722427489": (22879, 0.044),
                    "TLT": (3481, 0.048),
                    "SGOV": (1705, 0.045),
                },
                "Crypto Landing": {
                    "binance": {
                        "EURI": (503, 0.085),
                        "USDC": (1003, 0.079),
                        "USDT": (4815, 0.051),
                    },
                    "okx": {"USDT": (3051, 0.044), "USDC": (3569, 0.097)},
                    "bybit": {"USDC": (503, 0.138), "USDT": (543, 0.107)},
                    "whitebit": {"USDT": (3864, 0.156), "USDC": (7404, 0.156)},
                },
                "p2p_lending": {"EstateGuru": (3224, 0.08), "PeerBerry": (284, 0.068)},
            },
            "stocks_principal_and_interest": {
                "total_principal": 43047,
                "weighted_interest": 2.15,
            },
            "stocks_monthly": 77,
            "stocks_yearly": 925,
            "total_monthly": 539,
            "total_yearly": 6470,
        },
        "CASH_DATA": {
            "Total": Decimal("1241"),
            "Breakdown": {
                "cash": Decimal("500"),
                "lended": Decimal("924"),
                "debt": Decimal("0"),
                "private": Decimal("-738"),
                "ib_cash": Decimal("139"),
                "crypto_cash": Decimal("2"),
                "mono": Decimal("414"),
                "wise": Decimal("0"),
            },
        },
        "TOTAL_ASSETS": 140306,
        "FIN_FREEDOM_GOAL_PROGRESS": "28.06%",
        "ALLOCATIONS": {
            "allocation_breakdown": {
                "Bonds": 41.24,
                "Stocks": 30.68,
                "Crypto Lending": 18.0,
                "Crypto Coins": 4.48,
                "P2P Lending": 2.5,
                "Commodities": 2.22,
                "Cash": 0.88,
                "REIT": 0.0,
            },
            "total_fixed_income_pct": 61.64,
        },
    }

    main(data_structure)
