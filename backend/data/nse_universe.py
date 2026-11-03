"""
ATBot — NSE Universe Symbol Lists (dynamic)

Constituents are fetched from NSE's official index CSVs, cached on disk,
and fall back to a hardcoded snapshot if NSE is unreachable.

Resolution order for get_universe(name):
  1. Fresh on-disk cache (younger than CACHE_TTL_SECONDS)
  2. Live fetch from NSE (then written to cache)
  3. Stale on-disk cache (any age)
  4. Hardcoded snapshot below

All symbols are returned in yfinance format (SYMBOL.NS).
"""

import csv
import io
import json
import logging
import time
from pathlib import Path
from typing import Dict, List

import requests

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
# Tried in order; first one that returns a valid CSV wins.
SOURCE_BASE_URLS: List[str] = [
    "https://nsearchives.nseindia.com/content/indices",
    "https://www.niftyindices.com/IndexConstituent",
]
NSE_HOME = "https://www.nseindia.com"
INDEX_FILES: Dict[str, str] = {
    "nifty50": "ind_nifty50list.csv",
    "nifty_next50": "ind_niftynext50list.csv",
    "nifty100": "ind_nifty100list.csv",
    "nifty200": "ind_nifty200list.csv",
}
EXPECTED_SIZE: Dict[str, int] = {
    "nifty50": 50, "nifty_next50": 50, "nifty100": 100, "nifty200": 200,
}

CACHE_DIR = Path(".cache/universe")
CACHE_TTL_SECONDS = 24 * 3600  # refresh daily

# NSE rejects requests without a browser-like User-Agent.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/market-data/live-equity-market",
}


# ── Fetch / cache ─────────────────────────────────────────────────────────────
def _fetch_from_nse(name: str) -> List[str]:
    """Try each source in SOURCE_BASE_URLS until one returns a valid list."""
    errors: List[str] = []
    with requests.Session() as session:
        session.headers.update(HEADERS)
        try:  # warm-up request sets the cookies NSE expects
            session.get(NSE_HOME, timeout=8)
        except requests.RequestException:
            pass  # not fatal; the CSV request may still work

        for base in SOURCE_BASE_URLS:
            url = f"{base}/{INDEX_FILES[name]}"
            try:
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
                return _parse_constituents(name, resp.text)
            except Exception as e:
                errors.append(f"{url}: {e}")
                log.warning("Source failed for %s: %s", name, errors[-1])

    raise RuntimeError(f"All sources failed for {name}: {errors}")


def _parse_constituents(name: str, text: str) -> List[str]:
    reader = csv.DictReader(io.StringIO(text))
    symbols: List[str] = []
    for row in reader:
        sym = (row.get("Symbol") or "").strip()
        # NSE files occasionally contain placeholder rows (e.g. DUMMY...)
        if not sym or sym.upper().startswith("DUMMY"):
            continue
        symbols.append(f"{sym}.NS")

    symbols = list(dict.fromkeys(symbols))  # de-dupe, keep order

    # Sanity check: reject truncated / malformed responses
    if len(symbols) < 0.9 * EXPECTED_SIZE[name]:
        raise ValueError(
            f"{name}: got {len(symbols)} symbols, expected ~{EXPECTED_SIZE[name]}"
        )
    return symbols


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def _read_cache(name: str, max_age: float | None) -> List[str] | None:
    path = _cache_path(name)
    if not path.exists():
        return None
    if max_age is not None and (time.time() - path.stat().st_mtime) > max_age:
        return None
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) and data else None
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(name: str, symbols: List[str]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(name).write_text(json.dumps(symbols))
    except OSError as e:
        log.warning("Could not write universe cache for %s: %s", name, e)


# ── Hardcoded fallback snapshot (used only if NSE + cache both fail) ──────────
_FALLBACK_NIFTY50: List[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
    "INFY.NS", "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "KOTAKBANK.NS",
    "LT.NS", "HCLTECH.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "NESTLEIND.NS", "WIPRO.NS",
    "ULTRACEMCO.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "ADANIENT.NS",
    "M&M.NS", "BAJAJFINSV.NS", "JSWSTEEL.NS", "TATACONSUM.NS", "TMPV.NS",
    "HDFCLIFE.NS", "SBILIFE.NS", "TECHM.NS", "GRASIM.NS", "INDUSINDBK.NS",
    "BRITANNIA.NS", "APOLLOHOSP.NS", "COALINDIA.NS", "CIPLA.NS", "EICHERMOT.NS",
    "DRREDDY.NS", "ADANIPORTS.NS", "BPCL.NS", "TATASTEEL.NS", "HEROMOTOCO.NS",
    "DIVISLAB.NS", "HINDALCO.NS", "BAJAJ-AUTO.NS", "SHRIRAMFIN.NS", "BEL.NS",
]

_FALLBACK_NEXT50: List[str] = [
    "ADANIGREEN.NS", "ADANIPOWER.NS", "AMBUJACEM.NS", "BERGEPAINT.NS", "BIOCON.NS",
    "BOSCHLTD.NS", "CANBK.NS", "CHOLAFIN.NS", "COLPAL.NS", "DABUR.NS",
    "DLF.NS", "GODREJCP.NS", "HAVELLS.NS", "HDFCAMC.NS", "ICICIPRULI.NS",
    "ICICIGI.NS", "INDIGO.NS", "INDUSTOWER.NS", "IRCTC.NS", "JIOFIN.NS",
    "LICI.NS", "MARICO.NS", "MUTHOOTFIN.NS", "OFSS.NS", "PIDILITIND.NS",
    "RECLTD.NS", "SIEMENS.NS", "TORNTPHARM.NS", "LTM.NS", "VEDL.NS",
    "VOLTAS.NS", "ETERNAL.NS", "ZYDUSLIFE.NS", "PNB.NS", "BANKBARODA.NS",
    "AUROPHARMA.NS", "ALKEM.NS", "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS",
    "TATAPOWER.NS", "TATACHEM.NS", "PIIND.NS", "DMART.NS", "FEDERALBNK.NS",
    "IDFCFIRSTB.NS", "BANDHANBNK.NS", "ABCAPITAL.NS", "LTF.NS", "NYKAA.NS",
]

_FALLBACK_MIDCAP: List[str] = [
    "AUBANK.NS", "CANFINHOME.NS", "LICHSGFIN.NS", "M&MFIN.NS", "MANAPPURAM.NS",
    "PFC.NS", "POONAWALLA.NS", "MCX.NS", "IRFC.NS", "STARHEALTH.NS",
    "KPITTECH.NS", "LTTS.NS", "TATAELXSI.NS", "SONATSOFTW.NS", "HAPPSTMNDS.NS",
    "CYIENT.NS", "MASTEK.NS", "ROUTE.NS", "RAILTEL.NS", "BSE.NS",
    "LUPIN.NS", "IPCALAB.NS", "APLLTD.NS", "GLAND.NS", "GRANULES.NS",
    "METROPOLIS.NS", "FORTIS.NS", "MAXHEALTH.NS", "LALPATHLAB.NS", "AJANTPHARM.NS",
    "BALKRISIND.NS", "EXIDEIND.NS", "CEATLTD.NS", "MOTHERSON.NS", "ESCORTS.NS",
    "TIINDIA.NS", "SUNDRMFAST.NS", "APOLLOTYRE.NS", "MRF.NS", "BHARATFORG.NS",
    "EMAMILTD.NS", "VBL.NS", "BATAINDIA.NS", "PAGEIND.NS", "RELAXO.NS",
    "RADICO.NS", "UNITDSPR.NS", "VSTIND.NS", "JUBLFOOD.NS", "DEVYANI.NS",
    "BHEL.NS", "CONCOR.NS", "CUMMINSIND.NS", "GRINDWELL.NS", "ABB.NS",
    "THERMAX.NS", "KEC.NS", "KEI.NS", "POLYCAB.NS", "CGPOWER.NS",
    "NATIONALUM.NS", "NMDC.NS", "SAIL.NS", "JINDALSTEL.NS", "WELCORP.NS",
    "RATNAMANI.NS", "HINDCOPPER.NS", "APLAPOLLO.NS", "JSWENERGY.NS", "HINDZINC.NS",
    "ACC.NS", "RAMCOCEM.NS", "JKCEMENT.NS", "SOBHA.NS", "GODREJPROP.NS",
    "OBEROIRLTY.NS", "PRESTIGE.NS", "BRIGADE.NS", "PHOENIXLTD.NS", "NUVOCO.NS",
    "DEEPAKNTR.NS", "NAVINFLUOR.NS", "AARTIIND.NS", "SRF.NS", "CLEAN.NS",
    "CHEMPLASTS.NS", "FINEORG.NS", "GNFC.NS", "CHAMBLFERT.NS", "GSFC.NS",
    "GAIL.NS", "IGL.NS", "MGL.NS", "PETRONET.NS", "NHPC.NS",
    "SJVN.NS", "TORNTPOWER.NS", "CESC.NS", "HINDPETRO.NS", "MRPL.NS",
]

_FALLBACK_NIFTY100 = _FALLBACK_NIFTY50 + _FALLBACK_NEXT50
_FALLBACKS: Dict[str, List[str]] = {
    "nifty50": _FALLBACK_NIFTY50,
    "nifty_next50": _FALLBACK_NEXT50,
    "nifty100": _FALLBACK_NIFTY100,
    "nifty200": list(dict.fromkeys(_FALLBACK_NIFTY100 + _FALLBACK_MIDCAP))[:200],
}


# ── Public API ────────────────────────────────────────────────────────────────
def get_universe(name: str, force_refresh: bool = False) -> List[str]:
    """Return yfinance symbols for a named universe. Falls back to Nifty 50."""
    key = name.lower()
    if key not in INDEX_FILES:
        log.warning("Unknown universe %r, falling back to nifty50", name)
        key = "nifty50"

    # 1. Fresh cache
    if not force_refresh:
        cached = _read_cache(key, max_age=CACHE_TTL_SECONDS)
        if cached:
            return cached

    # 2. Live fetch
    try:
        symbols = _fetch_from_nse(key)
        _write_cache(key, symbols)
        log.info("Loaded %d symbols for %s from NSE", len(symbols), key)
        return symbols
    except Exception as e:
        log.warning("NSE fetch failed for %s: %s", key, e)

    # 3. Stale cache
    stale = _read_cache(key, max_age=None)
    if stale:
        log.warning("Using stale cache for %s (%d symbols)", key, len(stale))
        return stale

    # 4. Hardcoded snapshot
    log.error("Using hardcoded fallback for %s", key)
    return list(_FALLBACKS[key])


# ── Backwards-compatible module-level constants ───────────────────────────────
# Lazy so that importing this module doesn't trigger network calls.
def __getattr__(attr: str):
    mapping = {
        "NIFTY50": "nifty50",
        "NIFTY_NEXT50": "nifty_next50",
        "NIFTY100": "nifty100",
        "NIFTY200": "nifty200",
    }
    if attr in mapping:
        return get_universe(mapping[attr])
    raise AttributeError(attr)


class _UniverseMap(dict):
    def __missing__(self, key):
        return get_universe(key)

    def get(self, key, default=None):
        return get_universe(key)


UNIVERSE_MAP = _UniverseMap()