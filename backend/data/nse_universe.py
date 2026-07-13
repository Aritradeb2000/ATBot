"""
ATBot — NSE Universe Symbol Lists
Curated, liquid stock lists for batch scanning.

All symbols are in yfinance format (symbol.NS).
Lists are approximate constituents — exact index weights are not needed;
what matters is liquidity and data availability via yfinance.
"""

from typing import List

# ── Nifty 50 ──────────────────────────────────────────────────────────────────
NIFTY50: List[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
    "INFOSYS.NS", "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "KOTAKBANK.NS",
    "LT.NS", "HCLTECH.NS", "BAJFINANCE.NS", "ASIANPAINT.NS", "AXISBANK.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "NESTLEIND.NS", "WIPRO.NS",
    "ULTRACEMCO.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "ADANIENT.NS",
    "M&M.NS", "BAJAJFINSV.NS", "JSWSTEEL.NS", "TATACONSUM.NS", "TATAMOTORS.NS",
    "HDFCLIFE.NS", "SBILIFE.NS", "TECHM.NS", "GRASIM.NS", "INDUSINDBK.NS",
    "BRITANNIA.NS", "APOLLOHOSP.NS", "COALINDIA.NS", "CIPLA.NS", "EICHERMOT.NS",
    "DRREDDY.NS", "ADANIPORTS.NS", "BPCL.NS", "TATASTEELS.NS", "HEROMOTOCO.NS",
    "DIVISLAB.NS", "HINDALCO.NS", "BAJAJ-AUTO.NS", "SHRIRAMFIN.NS", "BEL.NS",
]

# ── Nifty Next 50 (Nifty 100 minus Nifty 50) ─────────────────────────────────
NIFTY_NEXT50: List[str] = [
    "ADANIGREEN.NS", "ADANIPWR.NS", "AMBUJACEM.NS", "BERGEPAINT.NS", "BIOCON.NS",
    "BOSCHLTD.NS", "CANBK.NS", "CHOLAFIN.NS", "COLPAL.NS", "DABUR.NS",
    "DLF.NS", "GODREJCP.NS", "HAVELLS.NS", "HDFCAMC.NS", "ICICIPRULI.NS",
    "ICICIGI.NS", "INDIGO.NS", "INDUSTOWER.NS", "IRCTC.NS", "JIOFIN.NS",
    "LICI.NS", "MARICO.NS", "MUTHOOTFIN.NS", "OFSS.NS", "PIDILITIND.NS",
    "RECLTD.NS", "SIEMENS.NS", "TORNTPHARM.NS", "TRENT.NS", "VEDL.NS",
    "VOLTAS.NS", "ZOMATO.NS", "ZYDUSLIFE.NS", "PNB.NS", "BANKBARODA.NS",
    "AUROPHARMA.NS", "ALKEM.NS", "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS",
    "TATAPOWER.NS", "TATACHEM.NS", "PIIND.NS", "DMART.NS", "FEDERALBNK.NS",
    "IDFCFIRSTB.NS", "BANDHANBNK.NS", "ABCAPITAL.NS", "LTF.NS", "NYKAA.NS",
]

# ── Nifty 100 (combined) ──────────────────────────────────────────────────────
NIFTY100: List[str] = NIFTY50 + NIFTY_NEXT50

# ── Additional 100 stocks to reach Nifty 200 ─────────────────────────────────
# Curated from Nifty Midcap 100 and large-cap universe, filtered for yfinance reliability
NIFTY_MIDCAP_SELECTION: List[str] = [
    # Banking & Finance
    "AUBANK.NS", "CANFINHOME.NS", "LICHSGFIN.NS", "M&MFIN.NS", "MANAPPURAM.NS",
    "PFC.NS", "ISEC.NS", "MCX.NS", "IRFC.NS", "STARHEALTH.NS",
    # IT & Tech
    "KPITTECH.NS", "LTTS.NS", "TATAELXSI.NS", "MINDTREE.NS", "HAPPSTMNDS.NS",
    "CYIENT.NS", "MASTEK.NS", "ROUTE.NS", "RAILTEL.NS", "BSE.NS",
    # Pharma & Healthcare
    "LUPIN.NS", "IPCALAB.NS", "APLLTD.NS", "GLAND.NS", "GRANULES.NS",
    "METROPOLIS.NS", "FORTIS.NS", "MAXHEALTH.NS", "LALPATHLAB.NS", "AJANTPHARM.NS",
    # Auto & Ancillary
    "BALKRISIND.NS", "EXIDEIND.NS", "CEATLTD.NS", "MOTHERSON.NS", "ESCORTS.NS",
    "TIINDIA.NS", "SUNDRMFAST.NS", "APOLLOTYRE.NS", "MRF.NS", "BHARATFORG.NS",
    # FMCG & Consumer
    "EMAMILTD.NS", "TATACONSUM.NS", "BATAINDIA.NS", "PAGEIND.NS", "RELAXO.NS",
    "RADICO.NS", "MCDOWELL-N.NS", "VSTIND.NS", "JUBLFOOD.NS", "DEVYANI.NS",
    # Infrastructure & Capital Goods
    "BHEL.NS", "CONCOR.NS", "CUMMINSIND.NS", "GRINDWELL.NS", "ABB.NS",
    "THERMAX.NS", "KHAITAN.NS", "KEI.NS", "POLYCAB.NS", "CGPOWER.NS",
    # Metals & Mining
    "NATIONALUM.NS", "NMDC.NS", "SAIL.NS", "JINDALSTEL.NS", "WELCORP.NS",
    "RATNAMANI.NS", "HINDCOPPER.NS", "APL.NS", "JSWENERGY.NS", "TATAPOWER.NS",
    # Cement & Real Estate
    "ACC.NS", "RAMCOCEM.NS", "JKCEMENT.NS", "SOBHA.NS", "GODREJPROP.NS",
    "DLF.NS", "PRESTIGE.NS", "BRIGADE.NS", "PHOENIXLTD.NS", "NUVOCO.NS",
    # Chemicals
    "DEEPAKNTR.NS", "NAVINFLUOR.NS", "AARTIIND.NS", "TATACHEM.NS", "CLEAN.NS",
    "CHEMPLASTS.NS", "FINEORG.NS", "GNFC.NS", "CHAMBLFERT.NS", "GSFC.NS",
    # Energy & Utilities
    "GAIL.NS", "IGL.NS", "MGL.NS", "PETRONET.NS", "NHPC.NS",
    "SJVN.NS", "TORNTPOWER.NS", "CESC.NS", "HINDPETRO.NS", "MRPL.NS",
]

# ── Nifty 200 (full universe for nightly pre-computation) ────────────────────
NIFTY200: List[str] = list(dict.fromkeys(NIFTY100 + NIFTY_MIDCAP_SELECTION))

# Deduplicate and ensure max 200
NIFTY200 = NIFTY200[:200]

# ── Convenience mapping ───────────────────────────────────────────────────────
UNIVERSE_MAP = {
    "nifty50":  NIFTY50,
    "nifty100": NIFTY100,
    "nifty200": NIFTY200,
}


def get_universe(name: str) -> List[str]:
    """Return symbol list for a named universe. Falls back to Nifty 50."""
    return UNIVERSE_MAP.get(name.lower(), NIFTY50)
