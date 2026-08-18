"""
Stock Universe — 1500+ NSE stocks across Small, Mid and Large cap
Fetches live stock lists from NSE India
"""

import requests
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

UNIVERSE_FILE = Path("stock_universe.json")
UNIVERSE_MAX_AGE_HOURS = 24  # Refresh once a day

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}

# NSE index endpoints for each cap
NSE_INDICES = {
    "LARGE_CAP": [
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20NEXT%2050",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20100",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20200",
    ],
    "MID_CAP": [
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20MIDCAP%20150",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20MIDCAP%20100",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20MIDCAP%2050",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20MIDSMALLCAP%20400",
    ],
    "SMALL_CAP": [
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20SMALLCAP%20250",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20SMALLCAP%20100",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20SMALLCAP%2050",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY500%20LARGEMIDSMALL%20EQUAL-CAP%20WEIGHTED",
    ],
}

# Fallback hardcoded lists in case NSE API is unavailable
FALLBACK_LARGE_CAP = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC",
    "KOTAKBANK", "SBIN", "BHARTIARTL", "AXISBANK", "LT", "ASIANPAINT", "MARUTI",
    "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND", "WIPRO", "TECHM",
    "HCLTECH", "BAJFINANCE", "BAJAJFINSV", "ONGC", "NTPC", "POWERGRID",
    "TATAMOTORS", "TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA", "DIVISLAB",
    "DRREDDY", "CIPLA", "APOLLOHOSP", "ADANIENT", "ADANIPORTS", "ADANIGREEN",
    "GRASIM", "EICHERMOT", "HEROMOTOCO", "BAJAJ-AUTO", "BPCL", "IOC",
    "VEDL", "SBILIFE", "HDFCLIFE", "PIDILITIND", "DABUR", "BRITANNIA",
]

FALLBACK_MID_CAP = [
    "ZOMATO", "PAYTM", "NYKAA", "POLICYBZR", "DELHIVERY", "CARTRADE",
    "IRCTC", "INDIAMART", "AFFLE", "HAPPSTMNDS", "LTTS", "COFORGE",
    "PERSISTENT", "MPHASIS", "KPITTECH", "TATAELXSI", "SONACOMS",
    "STARHEALTH", "ICICIGI", "HDFCAMC", "NIPPONLIFE", "UTIAMC",
    "CHOLAFIN", "M&MFIN", "SHRIRAMFIN", "MUTHOOTFIN", "MANAPPURAM",
    "FEDERALBNK", "IDFCFIRSTB", "BANDHANBNK", "RBLBANK", "YESBANK",
    "PNB", "BANKBARODA", "CANBK", "UNIONBANK", "INDIANB",
    "VOLTAS", "HAVELLS", "POLYCAB", "APLAPOLLO", "SUPREMEIND",
    "ASTRAL", "PIIND", "UPL", "COROMANDEL", "RALLIS",
    "WHIRLPOOL", "BLUESTAR", "CROMPTON", "VGUARD", "ORIENTELEC",
]

FALLBACK_SMALL_CAP = [
    "NAZARA", "LATENTVIEW", "EASEMYTRIP", "NUVOCO", "ROUTE",
    "SAPPHIRE", "PENIND", "GLAND", "GLENMARK", "ALKEM",
    "TORNTPHARM", "IPCALAB", "NATCOPHARM", "GRANULES", "LAURUS",
    "SEQUENT", "STRIDES", "SOLARA", "SUVEN", "HIKAL",
    "TANLA", "MASTEK", "ZENSAR", "HEXAWARE", "NIIT",
    "RATEGAIN", "INTELLECT", "DATAMATICS", "SAKSOFT", "NEWGEN",
    "BIKAJI", "DEVYANI", "SAPPHIREFDS", "WESTLIFE", "JUBLFOOD",
    "BURGERKING", "BARBEQUE", "SPECIALITY", "RESTAURANTS", "VAIBHAVGBL",
    "TITAN", "KALYAN", "SENCO", "THANGAMAYIL", "RAJESHEXPO",
    "DOMS", "CAMLIN", "FLAIR", "LINC", "KOKUYO",
]


def fetch_nse_index_stocks(url: str, session: requests.Session) -> list:
    """Fetch stock symbols from NSE index API."""
    symbols = []
    try:
        r = session.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("data", []):
                symbol = item.get("symbol", "")
                if symbol and symbol != "Symbol":
                    symbols.append(symbol)
    except Exception as e:
        log.warning(f"Failed to fetch from {url}: {e}")
    return symbols


def symbol_to_instrument_key(symbol: str) -> str:
    """Convert NSE symbol to Upstox instrument key format."""
    return f"NSE_EQ|{symbol}"


def build_universe() -> dict:
    """Build complete stock universe from NSE."""
    log.info("Building stock universe from NSE...")

    session = requests.Session()
    # Need to set cookies first
    try:
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
    except Exception:
        pass

    universe = {"LARGE_CAP": set(), "MID_CAP": set(), "SMALL_CAP": set()}

    for cap, urls in NSE_INDICES.items():
        for url in urls:
            symbols = fetch_nse_index_stocks(url, session)
            universe[cap].update(symbols)
            if symbols:
                log.info(f"{cap}: fetched {len(symbols)} stocks from NSE")

    # Add fallbacks if NSE API failed
    if len(universe["LARGE_CAP"]) < 10:
        log.info("Using fallback large cap list")
        universe["LARGE_CAP"].update(FALLBACK_LARGE_CAP)
    if len(universe["MID_CAP"]) < 10:
        log.info("Using fallback mid cap list")
        universe["MID_CAP"].update(FALLBACK_MID_CAP)
    if len(universe["SMALL_CAP"]) < 10:
        log.info("Using fallback small cap list")
        universe["SMALL_CAP"].update(FALLBACK_SMALL_CAP)

    result = {
        "LARGE_CAP": sorted(list(universe["LARGE_CAP"])),
        "MID_CAP":   sorted(list(universe["MID_CAP"])),
        "SMALL_CAP": sorted(list(universe["SMALL_CAP"])),
        "updated_at": str(datetime.now()),
    }

    total = len(result["LARGE_CAP"]) + len(result["MID_CAP"]) + len(result["SMALL_CAP"])
    log.info(f"Universe built: {len(result['LARGE_CAP'])} large + {len(result['MID_CAP'])} mid + {len(result['SMALL_CAP'])} small = {total} total stocks")

    UNIVERSE_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def get_universe(force_refresh: bool = False) -> dict:
    """Get stock universe, refreshing if older than 24 hours."""
    if not force_refresh and UNIVERSE_FILE.exists():
        data = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
        updated_at = datetime.fromisoformat(data.get("updated_at", "2000-01-01"))
        if datetime.now() - updated_at < timedelta(hours=UNIVERSE_MAX_AGE_HOURS):
            total = len(data["LARGE_CAP"]) + len(data["MID_CAP"]) + len(data["SMALL_CAP"])
            log.info(f"Using cached universe: {total} stocks")
            return data

    return build_universe()


def get_all_symbols(cap_filter: list = None) -> list:
    """
    Get all symbols as Upstox instrument keys.
    cap_filter: ['LARGE_CAP', 'MID_CAP', 'SMALL_CAP'] or None for all
    """
    universe = get_universe()
    symbols = []
    caps = cap_filter or ["LARGE_CAP", "MID_CAP", "SMALL_CAP"]
    for cap in caps:
        for symbol in universe.get(cap, []):
            symbols.append(f"NSE_EQ|{symbol}")
    return symbols


def get_plain_symbols(cap_filter: list = None) -> list:
    """Get plain symbols without instrument key prefix."""
    universe = get_universe()
    symbols = []
    caps = cap_filter or ["LARGE_CAP", "MID_CAP", "SMALL_CAP"]
    for cap in caps:
        symbols.extend(universe.get(cap, []))
    return symbols


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    u = build_universe()
    print(f"\nLarge Cap: {len(u['LARGE_CAP'])} stocks")
    print(f"Mid Cap:   {len(u['MID_CAP'])} stocks")
    print(f"Small Cap: {len(u['SMALL_CAP'])} stocks")
    total = len(u['LARGE_CAP']) + len(u['MID_CAP']) + len(u['SMALL_CAP'])
    print(f"Total:     {total} stocks")
