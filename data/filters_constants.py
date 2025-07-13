BONDS_VALUES = [
    # US Treasury
    "SGOV",  # iShares 0-3 Month Treasury Bond ETF
    "TLT",  # iShares 20+ Year Treasury Bond ETF
    "IEF",  # iShares 7-10 Year Treasury Bond ETF
    "SHY",  # iShares 1-3 Year Treasury Bond ETF
    # Investment Grade Corporate Bonds
    "LQD",  # iShares iBoxx $ Investment Grade Corporate Bond ETF
    "VCIT",  # Vanguard Intermediate-Term Corporate Bond ETF
    "VCSH",  # Vanguard Short-Term Corporate Bond ETF
    "IGLB",  # iShares Long-Term Corporate Bond ETF
    # High Yield (Junk) Bonds
    "HYG",  # iShares iBoxx $ High Yield Corporate Bond ETF
    "JNK",  # SPDR Bloomberg High Yield Bond ETF
    "USHY",  # iShares Broad USD High Yield Corporate Bond ETF
    "SHYG",  # iShares 0-5 Year High Yield Corporate Bond ETF
    "ANGL",  # VanEck Fallen Angel High Yield Bond ETF
    "FALN",  # iShares Fallen Angels USD Bond ETF
    "SJNK",  # SPDR Bloomberg Short Term High Yield Bond ETF
    "HYLS",  # First Trust Tactical High Yield ETF
    "HYGV",  # FlexShares High Yield Value-Scored Bond Index Fund
    "HYDB",  # iShares High Yield Bond Factor ETF
    "GHYG",  # iShares Global High Yield Corporate Bond ETF
    "SPHY",  # SPDR Portfolio High Yield Bond ETF
    "IHYG",  # iShares International High Yield Bond ETF
    "IHYG.L",  # iShares EUR High Yield Corporate Bond ETF (LSE)
    # International/Emerging Markets Bonds
    "EMB",  # iShares J.P. Morgan USD Emerging Markets Bond ETF
    "EMLC",  # VanEck J.P. Morgan EM Local Currency Bond ETF
    "PCY",  # Invesco Emerging Markets Sovereign Debt ETF
    # Broad Market/Aggregate Bonds
    "AGG",  # iShares Core U.S. Aggregate Bond ETF
    "BND",  # Vanguard Total Bond Market ETF
    # Municipal Bonds
    "MUB",  # iShares National Muni Bond ETF
    # Inflation-Protected
    "VTIP",  # Vanguard Short-Term Inflation-Protected Securities ETF
]

POPULAR_ETFS = [
    # Broad Market US
    "SPY",  # SPDR S&P 500 ETF Trust - tracks S&P 500
    "VOO",  # Vanguard S&P 500 ETF
    "IVV",  # iShares Core S&P 500 ETF
    "QQQ",  # Invesco QQQ Trust - tracks NASDAQ-100
    "VTI",  # Vanguard Total Stock Market ETF
    # International & Emerging Markets
    "EFA",  # iShares MSCI EAFE ETF - developed markets
    "VEA",  # Vanguard FTSE Developed Markets ETF
    "EEM",  # iShares MSCI Emerging Markets ETF
    "VWO",  # Vanguard FTSE Emerging Markets ETF
    "IEFA",  # iShares Core MSCI EAFE ETF
    "KWEB",  # KraneShares CSI China Internet ETF
    "FXI",  # iShares China Large-Cap ETF
    "MCHI",  # iShares MSCI China ETF
    "EWJ",  # iShares MSCI Japan ETF
    "EWY",  # iShares MSCI South Korea ETF
    "INDA",  # iShares MSCI India ETF
    "ARGT",  # Global X MSCI Argentina ETF
    # Fixed Income
    *BONDS_VALUES,
    # Sectors
    "XLF",  # Financial Select Sector SPDR Fund
    "XLK",  # Technology Select Sector SPDR Fund
    "XLE",  # Energy Select Sector SPDR Fund
    "XLV",  # Health Care Select Sector SPDR Fund
    "XLI",  # Industrial Select Sector SPDR Fund
    "XLC",  # Communication Services Select Sector SPDR Fund
    "XLU",  # Utilities Select Sector SPDR Fund
    "XLP",  # Consumer Staples Select Sector SPDR Fund
    "XLY",  # Consumer Discretionary Select Sector SPDR Fund
    # Factors & Styles
    "IWM",  # iShares Russell 2000 ETF - small cap
    "IWF",  # iShares Russell 1000 Growth ETF
    "IWD",  # iShares Russell 1000 Value ETF
    "VIG",  # Vanguard Dividend Appreciation ETF
    "USMV",  # iShares MSCI USA Min Vol Factor ETF
    "MTUM",  # iShares MSCI USA Momentum Factor ETF
    "QUAL",  # iShares MSCI USA Quality Factor ETF
    "SIZE",  # iShares MSCI USA Size Factor ETF
    # Commodities & Real Estate
    "GLD",  # SPDR Gold Shares
    "IAU",  # iShares Gold Trust
    "SLV",  # iShares Silver Trust
    "VNQ",  # Vanguard Real Estate ETF
    "USO",  # United States Oil Fund
    "DBC",  # Invesco DB Commodity Index Tracking Fund
    "PDBC",  # Invesco Optimum Yield Diversified Commodity Strategy
    # Technology & Innovation
    "ARKK",  # ARK Innovation ETF
    "ARKG",  # ARK Genomic Revolution ETF
    "ICLN",  # iShares Global Clean Energy ETF
    "SMH",  # VanEck Semiconductor ETF
    "SOXX",  # iShares Semiconductor ETF
]


# Hong Kong Listed Chinese Stocks
CHINA_TICKERS = [
    # Tech Giants
    "9988",  # Alibaba
    "700",  # Tencent
    "3690",  # Meituan
    "9618",  # JD.com
    "2359",  # WuXi AppTec
    "9999",  # NetEase
    "9888",  # Baidu
    "1024",  # Kuaishou
    # Biotech/Healthcare
    "2269",  # WuXi Biologics
    "3759",  # Pharmaron
    "6160",  # BeiGene
    # Consumer/Tech Hardware
    "1810",  # Xiaomi
    "175",  # Geely Auto
    "2333",  # Great Wall Motor
    "2015",  # Li Auto
    # Financial Services
    "2318",  # Ping An Insurance
    "941",  # China Mobile
    "939",  # China Construction Bank
    "1398",  # ICBC
    "3968",  # China Merchants Bank
    "2388",  # BOC Hong Kong
]

# Chinese ADRs and ETFs Listed on NYSE/NASDAQ
CHINA_ADR = [
    # Individual ADRs
    "BABA",  # Alibaba
    "PDD",  # PDD Holdings (Pinduoduo)
    "JD",  # JD.com
    "BIDU",  # Baidu
    "NIO",  # NIO Inc
    "XPEV",  # XPeng
    "LI",  # Li Auto
    "NTES",  # NetEase
    "TCOM",  # Trip.com
    "BILI",  # Bilibili
    "TME",  # Tencent Music
    "EDU",  # New Oriental Education
    "TAL",  # TAL Education
    "YUMC",  # Yum China
    "HTHT",  # H World Group (Huazhu)
    "ZTO",  # ZTO Express
    "DIDI",  # DiDi Global
    # China ETFs
    "KWEB",  # KraneShares CSI China Internet ETF
    "FXI",  # iShares China Large-Cap ETF
    "MCHI",  # iShares MSCI China ETF
    "ASHR",  # Xtrackers Harvest CSI 300 China A-Shares ETF
    "CQQQ",  # Invesco China Technology ETF
    "CHIQ",  # Global X MSCI China Consumer Discretionary ETF
    "CHIX",  # Global X MSCI China Financials ETF
    "GXC",  # SPDR S&P China ETF
    "KBA",  # KraneShares Bosera MSCI China A Share ETF
    "RAYC",  # Rayliant Quantamental China Equity ETF
]

HK_TO_ADR_MAP = {
    "9988": "BABA",  # Alibaba
    "700": "TCEHY",  # Tencent
    "9618": "JD",  # JD.com
    "9888": "BIDU",  # Baidu
    "9999": "NTES",  # NetEase
    "2015": "LI",  # Li Auto
    "3690": "MPNGY",  # Meituan
    "1024": "KUASF",  # Kuaishou
    "1810": "XIACY",  # Xiaomi
    "2318": "PNGAY",  # Ping An Insurance
    "941": "CHL",  # China Mobile
    "939": "CICHY",  # China Construction Bank
    "1398": "IDCBY",  # ICBC
    "3968": "CIHKY",  # China Merchants Bank
    "2388": "BHKLY",  # BOC Hong Kong
}

# Banks
BANKS = [
    # US Banks
    "JPM",  # JPMorgan Chase
    "BAC",  # Bank of America
    "WFC",  # Wells Fargo
    "C",  # Citigroup
    "GS",  # Goldman Sachs
    "MS",  # Morgan Stanley
    "USB",  # U.S. Bancorp
    "PNC",  # PNC Financial
    "TFC",  # Truist Financial
    "SCHW",  # Charles Schwab
    # Canadian Banks
    "TD",  # Toronto-Dominion Bank
    "RY",  # Royal Bank of Canada
    "BNS",  # Bank of Nova Scotia
    "BMO",  # Bank of Montreal
    "CM",  # Canadian Imperial Bank of Commerce
    # Regional/Other Banks
    "EWBC",  # East West Bancorp
    "COF",  # Capital One Financial
    "FITB",  # Fifth Third Bancorp
    "KEY",  # KeyCorp
    "RF",  # Regions Financial
]

# REITs
REITS = [
    # Broad Market REIT ETFs
    "VNQ",  # Vanguard Real Estate ETF
    "VNQI",  # Vanguard Global ex-U.S. Real Estate ETF
    "FREL",  # Fidelity MSCI Real Estate ETF
    "SCHH",  # Schwab U.S. REIT ETF
    "RWR",  # SPDR Dow Jones REIT ETF
    # Individual REITs
    "HHC",  # Howard Hughes Corporation
    "PHM",  # PulteGroup
    "AMT",  # American Tower
    "PLD",  # Prologis
    "CCI",  # Crown Castle
    "EQIX",  # Equinix
    "AVB",  # AvalonBay Communities
    "SPG",  # Simon Property Group
    "WELL",  # Welltower
    "DLR",  # Digital Realty Trust
]

# Commodities
COMM = [
    # Precious Metals (except Gold)
    "SLV",  # iShares Silver Trust
    "PSLV",  # Sprott Physical Silver Trust
    "PPLT",  # Aberdeen Standard Physical Platinum Shares ETF
    # Industrial Metals
    "CPER",  # United States Copper ETF
    "JJC",  # iPath Bloomberg Copper Total Return ETN
    # Broad Commodity ETFs
    "DBC",  # Invesco DB Commodity Index Tracking Fund
    "PDBC",  # Invesco Optimum Yield Diversified Commodity Strategy
    "COMB",  # GraniteShares Bloomberg Commodity Broad Strategy No K-1 ETF
    "BCI",  # Aberdeen Standard Bloomberg All Commodity Strategy K-1 Free ETF
    "GSG",  # iShares S&P GSCI Commodity-Indexed Trust
    "DJP",  # iPath Bloomberg Commodity Index Total Return ETN
    # Agriculture
    "DBA",  # Invesco DB Agriculture Fund
    "TAGS",  # Teucrium Agricultural Fund
    "WEAT",  # Teucrium Wheat Fund
]

# Gold
PRECIOUS_METALS = [
    # Gold ETFs
    "GLD",  # SPDR Gold Shares
    "IAU",  # iShares Gold Trust
    "SGOL",  # Aberdeen Standard Physical Gold Shares ETF
    "PHYS",  # Sprott Physical Gold Trust
    "BAR",  # GraniteShares Gold Trust
    "GLDM",  # SPDR Gold MiniShares Trust
    # Gold Miners ETFs
    "GDX",  # VanEck Gold Miners ETF
    "GDXJ",  # VanEck Junior Gold Miners ETF
    "RING",  # iShares MSCI Global Gold Miners ETF
    # Silver ETFs
    "SLV",  # iShares Silver Trust
    "PSLV",  # Sprott Physical Silver Trust
    # Add more silver/precious metals ETFs as needed
]

PRECIOUS_METALS_KEY = "Precious Metals"
BONDS_KEY = "Bonds"
STOCKS_KEY = "Stocks"
CRYPTO_LENDING_KEY = "Crypto Landing"
P2P_LENDING_KEY = "p2p_lending"
OTHER_KEY = "other"

CHINA_STOCKS_KEY = "China Stocks"
REIT_KEY = "REIT"
GOLD_KEY = "Gold"
IB_STOCKS_KEY = "Stocks"
IB_BONDS_KEY = "Bonds"
COMMODITIES_KEY = "Commodities"
SHORT_SELLING_KEY = "Short Selling"
IB_STOCKS_VALUE = "Total Stocks Value"

PLATFORM_GROUPING = {
    BONDS_KEY: BONDS_VALUES,
    CRYPTO_LENDING_KEY: ["binance", "okx", "bybit", "whitebit", "telegram"],
    P2P_LENDING_KEY: ["EstateGuru", "PeerBerry", "TelegramSavings"],
}
