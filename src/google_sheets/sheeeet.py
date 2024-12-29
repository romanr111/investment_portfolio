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
    try:
        existing = spreadsheet.worksheet(sheet_title)
        spreadsheet.del_worksheet(existing)
    except gspread.exceptions.WorksheetNotFound:
        pass

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
    Turn IB_DATA into a list of rows for columns D/E, but do NOT print
    the 'IB_DATA' label itself. We only skip subcategories if they are empty.
    """
    rows = []
    # (We skip printing "IB_DATA" as a label.)

    for subcat, contents in ib_data.items():
        if isinstance(contents, dict) and not contents:
            # Skip if subcategory is an empty dict
            continue

        if isinstance(contents, dict):
            # Subcategory header
            rows.append(row_left(subcat))
            for sym, val in contents.items():
                rows.append(row_left(sym, str(val)))
            rows.append(row_left())  # blank row
        else:
            # Single-value (e.g. "Total Stocks Value")
            rows.append(row_left(subcat, str(contents)))
            rows.append(row_left())  # blank row

    return rows


def parse_crypto_data(crypto_data):
    """
    Represent CRYPTO_DATA in columns D/E:
      - Show total
      - Show market values
    """
    rows = []
    rows.append(row_left("CRYPTO_DATA"))  # Section label

    total_crypto = crypto_data.get("Total_Crypto_Value", 0)
    rows.append(row_left("Total Crypto Value", str(total_crypto)))
    rows.append(row_left())

    market_vals = crypto_data.get("Crypto_Market_Values", {})
    if market_vals:
        rows.append(row_left("Market Values"))
        for sym, val in market_vals.items():
            rows.append(row_left(sym, str(val)))
        rows.append(row_left())

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
    Build a list of rows that collectively represent:
      - IB_DATA (Bonds, Stocks, etc., skipping only if subcat is empty)
      - CRYPTO_DATA
      - single line for CASH_DATA
    """
    rows = []

    ib_data = data.get("IB_DATA", {})
    if ib_data:
        rows.extend(parse_ib_data(ib_data))

    crypto_data = data.get("CRYPTO_DATA", {})
    if crypto_data:
        rows.extend(parse_crypto_data(crypto_data))

    cash_data = data.get("CASH_DATA", {})
    if cash_data:
        rows.extend(parse_cash_data(cash_data))

    return rows


def build_right_columns(data, left_table):
    """
    Place data in columns G/H/I for:
      - row 0 => "Financial Freedom" => FIN_FREEDOM_GOAL_PROGRESS
      - row 1 => blank row
      - row 2 => "Net worth" => TOTAL_ASSETS  (col I => '%' label)
      - row 3.. => each allocation => value => pct

    Then in columns K (10) / L (11) we show FIXED_INCOME_DATA:
      - Single row for "Total" with e.g. "86483 @ 6.4%" from fixed_inc_principal_and_interest
      - group_weighted_interest lines (Bonds, Crypto Landing, p2p_lending),
        each e.g. "57720 @ 4.4%"
      - after p2p_lending, one blank row, then monthly/yearly dividends.
    """
    final_table = left_table[:]

    def set_cell(r, c, val):
        """Ensure final_table[r][c] exists, then set it."""
        while len(final_table) <= r:
            final_table.append([])
        while len(final_table[r]) <= c:
            final_table[r].append("")
        final_table[r][c] = val

    #
    # ============ Columns G/H/I (Net Worth & Allocations) ============
    #
    # Row 0 => "Financial Freedom"
    freedom = data.get("FIN_FREEDOM_GOAL_PROGRESS", "")
    set_cell(0, 6, "Financial Freedom")
    set_cell(0, 7, freedom)

    # Row 1 => blank
    set_cell(1, 6, "")
    set_cell(1, 7, "")

    # Row 2 => Net worth
    total_assets = data.get("TOTAL_ASSETS", 0)
    set_cell(2, 6, "Net worth")
    set_cell(2, 7, str(total_assets))
    set_cell(2, 8, "%")  # column I => label

    # Allocations (row 3..)
    alloc_data = data.get("ALLOCATIONS", {}).get("allocation_breakdown", {})
    row_idx = 3
    for cat, pct in alloc_data.items():
        val = round(total_assets * (pct / 100))
        set_cell(row_idx, 6, cat)
        set_cell(row_idx, 7, str(val))
        set_cell(row_idx, 8, f"{pct}")  # show raw % or formatted
        row_idx += 1

    #
    # ============ Columns K/L (FIXED_INCOME_DATA) ============
    #
    fid = data.get("FIXED_INCOME_DATA", {})
    gwi = fid.get("group_weighted_interest", {})
    fipi = fid.get("fixed_inc_principal_and_interest", {})

    # We'll place everything starting near row=2 => col=K=10
    # Label "FIXED_INCOME_DATA"
    set_cell(2, 10, "FIXED_INCOME_DATA")
    row_gwi = 3

    #
    # 1) Combine principal & interest into a single row labeled "Total"
    #    e.g. "86483 @ 6.4%"
    #
    if fipi:
        principal = fipi.get("principal", 0)
        interest_raw = fipi.get("interest", 0)  # e.g. 0.064 => "6.4%"
        interest_str = f"{interest_raw * 100:.1f}%"
        combined_val = f"{principal} @ {interest_str}"
        # Single row
        set_cell(row_gwi, 10, "Total")
        set_cell(row_gwi, 11, combined_val)
        row_gwi += 1

    #
    # 2) group_weighted_interest lines
    #
    if gwi:
        for label, (principal, rate) in gwi.items():
            rate_pct = f"{rate * 100:.1f}%"
            text_val = f"{principal} @ {rate_pct}"
            set_cell(row_gwi, 10, label)  # e.g. "Bonds"
            set_cell(row_gwi, 11, text_val)  # e.g. "57720 @ 4.4%"
            row_gwi += 1

            # If label == "p2p_lending", we do the blank row + monthly/yearly
            if label == "p2p_lending":
                # one blank row
                row_gwi += 1

                # Monthly / Yearly Dividend
                monthly_div = fid.get("total_monthly", 0)
                yearly_div = fid.get("total_yearly", 0)

                set_cell(row_gwi, 10, "Monthly Dividend")
                set_cell(row_gwi, 11, str(monthly_div))
                row_gwi += 1

                set_cell(row_gwi, 10, "Yearly Dividend")
                set_cell(row_gwi, 11, str(yearly_div))
                row_gwi += 1

    return final_table


def single_tab_update(spreadsheet, data):
    """
    Create a new tab named today's date, place it at index=1.
    Build a 'left_table' for columns D/E (IB_DATA, CRYPTO_DATA, CASH_DATA).
    Then in columns G/H/I, show Net worth & Allocations.

    In columns K/L, show:
      - single row for "Total" => e.g. "86483 @ 6.4%"
      - group_weighted_interest lines => e.g. "57720 @ 4.4%"
      - after 'p2p_lending', one blank row => monthly/yearly dividends
    """
    date_title = datetime.now().strftime("%d %b %Y")
    worksheet = create_tab_at_left(spreadsheet, date_title)

    # 1) Build the left side (D/E)
    left_table = build_left_columns(data)

    # 2) Add right side (G/H/I) + FIXED_INCOME lines in columns K/L
    final_table = build_right_columns(data, left_table)

    worksheet.clear()
    worksheet.update("A1", final_table)


import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime


def update_net_worth_timeline(spreadsheet, total_assets):
    """
    Appends a new row at the bottom of the 'net_worth_timeline' worksheet.
    The new row will contain:
    - total_assets (e.g., 140271) in column A
    - current date in column B (e.g., "29 Dec 2024")
    """

    # 1) Open or create the 'net_worth_timeline' worksheet
    try:
        worksheet = spreadsheet.worksheet("net_worth_timeline")
    except gspread.exceptions.WorksheetNotFound:
        # If not found, create it (2 columns: "Net Worth" and "Date")
        worksheet = spreadsheet.add_worksheet(
            title="net_worth_timeline", rows=200, cols=2
        )
        # Optionally, you could insert headers in row 1:
        # worksheet.update("A1", [["Net Worth", "Date"]])

    # 2) Determine the next empty row
    #    We can read all values and see how many rows we have
    existing_values = worksheet.get_all_values()
    last_row = len(existing_values)  # e.g. if we have 18 rows, last_row=18
    next_row = last_row + 1  # the row index we want to update

    # 3) Format the date, e.g., "29 Dec 2024"
    date_str = datetime.now().strftime("%d %b %Y")

    # 4) Write the new entry
    #    Column A => total_assets, Column B => date_str
    worksheet.update_cell(next_row, 1, str(total_assets))
    worksheet.update_cell(next_row, 2, date_str)


def main(data):
    """
    Main entry point.
    """
    client = get_gspread_client()
    spreadsheet = client.open(SPREADSHEET_NAME)

    single_tab_update(spreadsheet, data)
    total_assets = data.get("TOTAL_ASSETS", 0)
    update_net_worth_timeline(spreadsheet, total_assets)


if __name__ == "__main__":
    # Example usage
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
            "Total_Crypto_Value": 6245,
            "Crypto_Market_Values": {
                "BTC": 3748,
                "ETH": 2057,
                "TON": 102,
                "ADA": 90,
                "BNB": 83,
                "EOS": 71,
                "NEO": 70,
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
            "monthly_earnings_fixed_income": 462,
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
        "TOTAL_ASSETS": 140271,
        "FIN_FREEDOM_GOAL_PROGRESS": "28.05%",
        "ALLOCATIONS": {
            "allocation_breakdown": {
                "Bonds": 41.26,
                "Stocks": 30.69,
                "Crypto Lending": 18.0,
                "Crypto Coins": 4.45,
                "P2P Lending": 2.5,
                "Commodities": 1.83,
                "Cash": 0.88,
                "Gold": 0.39,
                "REIT": 0.0,
            },
            "total_fixed_income_pct": 61.65,
        },
    }

    main(data_structure)
