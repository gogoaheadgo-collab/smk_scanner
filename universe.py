# ============================================================
# universe.py — Build the eligible stock universe
# ============================================================

import os
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import config

DHAN_INSTRUMENTS_FILE = "api-scrip-master.csv"
DHAN_INSTRUMENTS_URL  = "https://images.dhan.co/api-data/api-scrip-master.csv"

NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Referer': 'https://www.nseindia.com/',
}


def fetch_nse_instruments():
    """Load NSE equity instrument list from local CSV."""
    print("Loading NSE instrument master from local file...")

    if not os.path.exists(DHAN_INSTRUMENTS_FILE):
        print("\n" + "="*60)
        print("ERROR: api-scrip-master.csv not found.")
        print("  1. Open in browser: " + DHAN_INSTRUMENTS_URL)
        print("  2. Move downloaded file to smk_scanner folder")
        print("  3. Run scanner again")
        print("="*60 + "\n")
        raise FileNotFoundError("api-scrip-master.csv missing.")

    df = pd.read_csv(DHAN_INSTRUMENTS_FILE, low_memory=False)
    df = df[df['SEM_EXM_EXCH_ID'] == 'NSE']
    df = df[df['SEM_INSTRUMENT_NAME'] == 'EQUITY']
    df = df[['SEM_SMST_SECURITY_ID', 'SEM_TRADING_SYMBOL', 'SEM_CUSTOM_SYMBOL', 'SM_SYMBOL_NAME']].copy()
    df.columns = ['security_id', 'symbol', 'trading_symbol', 'company_name']
    df['security_id'] = df['security_id'].astype(str)
    df['symbol'] = df['symbol'].str.strip()

    print(f"  Total NSE equity stocks: {len(df)}")
    return df


def fetch_nifty500_symbols():
    """Fetch Nifty 500 symbol list — all >1000Cr market cap."""
    print("Fetching Nifty 500 list...")
    url = 'https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv'
    try:
        resp = requests.get(url, headers=NSE_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        symbols = set(df['Symbol'].str.strip().tolist())
        print(f"  Nifty 500: {len(symbols)} symbols loaded")
        return symbols
    except Exception as e:
        print(f"  Warning: Could not fetch Nifty 500: {e}")
        return set()


def fetch_nifty_midsmall_symbols():
    """Fetch Nifty Midcap 150 as additional universe."""
    print("Fetching Nifty Midcap 150...")
    url = 'https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv'
    try:
        resp = requests.get(url, headers=NSE_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        symbols = set(df['Symbol'].str.strip().tolist())
        print(f"  Nifty Midcap 150: {len(symbols)} symbols loaded")
        return symbols
    except Exception as e:
        print(f"  Warning: Could not fetch Midcap 150: {e}")
        return set()


def fetch_ipo_listing_dates():
    """Fetch IPO listing dates from NSE EQUITY_L.csv."""
    print("Fetching IPO listing dates...")
    url = 'https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv'
    listing_dates = {}
    cutoff = datetime(config.IPO_FROM_YEAR, 1, 1)

    try:
        resp = requests.get(url, headers=NSE_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]

        date_col = next((c for c in df.columns if 'DATE' in c.upper() and 'LIST' in c.upper()), None)
        sym_col  = next((c for c in df.columns if 'SYMBOL' in c.upper()), None)

        if date_col and sym_col:
            for _, row in df.iterrows():
                sym = str(row.get(sym_col, '')).strip()
                date_str = str(row.get(date_col, '')).strip()
                for fmt in ('%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y'):
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        if dt >= cutoff:
                            listing_dates[sym] = dt
                        break
                    except:
                        continue
        else:
            print(f"  Columns found: {list(df.columns)}")

    except Exception as e:
        print(f"  Warning: Could not fetch IPO dates: {e}")

    print(f"  IPO stocks from {config.IPO_FROM_YEAR}+: {len(listing_dates)}")
    return listing_dates


def build_universe(dhan_client):
    """
    Build final eligible universe.
    Universe = Nifty500 + Midcap150 + IPO 2022+ stocks
    All of these are effectively >1000Cr or recently listed.
    """
    instruments  = fetch_nse_instruments()
    nifty500     = fetch_nifty500_symbols()
    midcap150    = fetch_nifty_midsmall_symbols()
    ipo_dates    = fetch_ipo_listing_dates()

    # Combined eligible symbols
    large_cap_symbols = nifty500 | midcap150

    # Fallback if NSE fetch failed
    if not large_cap_symbols:
        print("  Using Nifty 50 fallback...")
        large_cap_symbols = {
            'RELIANCE','TCS','HDFCBANK','INFY','ICICIBANK','HINDUNILVR','ITC',
            'SBIN','BHARTIARTL','KOTAKBANK','LT','AXISBANK','ASIANPAINT','MARUTI',
            'TITAN','SUNPHARMA','ULTRACEMCO','BAJFINANCE','NESTLEIND','WIPRO',
            'POWERGRID','NTPC','TECHM','HCLTECH','ONGC','COALINDIA','JSWSTEEL',
            'TATAMOTORS','ADANIENT','ADANIPORTS','BAJAJFINSV','DIVISLAB','DRREDDY',
            'EICHERMOT','GRASIM','HEROMOTOCO','HINDALCO','INDUSINDBK',
            'SBILIFE','TATACONSUM','TATASTEEL','CIPLA','BPCL','BRITANNIA',
            'APOLLOHOSP','HDFCLIFE'
        }

    today    = datetime.today()
    eligible = []
    checked  = 0

    for _, row in instruments.iterrows():
        symbol = row['symbol']
        sec_id = row['security_id']

        # Determine if eligible for universe
        is_large_cap = symbol in large_cap_symbols
        is_ipo       = symbol in ipo_dates

        if not is_large_cap and not is_ipo:
            continue

        reasons = []
        if is_ipo:
            reasons.append("IPO_2022+")

        # ATH / 52W check via Dhan historical data
        try:
            hist = dhan_client.get_historical_data(
                security_id=sec_id,
                exchange_segment="NSE_EQ",
                instrument_type="EQUITY",
                from_date=(today - timedelta(days=400)).strftime('%Y-%m-%d'),
                to_date=today.strftime('%Y-%m-%d'),
                interval="1"
            )
            if not hist or 'data' not in hist or len(hist['data']) < 30:
                # For large caps with no data issue, still include with no ATH reason
                if is_large_cap and not reasons:
                    reasons.append("LARGECAP")
            else:
                highs     = [candle[2] for candle in hist['data']]
                ath       = max(highs)
                year_high = max(highs[-252:]) if len(highs) >= 252 else ath
                recent_45 = highs[-config.ATH_LOOKBACK_DAYS:]
                recent_30 = highs[-config.WEEK52_LOOKBACK_DAYS:]

                if max(recent_45) >= ath * 0.995:
                    reasons.append("ATH_45D")
                if max(recent_30) >= year_high * 0.995:
                    reasons.append("52W_30D")

                # Large cap with no ATH/52W signal — still include for scanning
                if is_large_cap and not any(r in reasons for r in ['ATH_45D','52W_30D']):
                    reasons.append("LARGECAP")

        except Exception:
            if is_large_cap:
                reasons.append("LARGECAP")

        checked += 1
        if checked % 100 == 0:
            print(f"  Universe building: {checked} stocks checked, {len(eligible)} eligible so far...")

        eligible.append({
            'security_id':     sec_id,
            'symbol':          symbol,
            'company_name':    row['company_name'],
            'market_cap_cr':   1000,
            'universe_reason': ", ".join(reasons)
        })

    print(f"\nEligible universe: {len(eligible)} stocks")
    return eligible
