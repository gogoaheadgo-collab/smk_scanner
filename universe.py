# ============================================================
# universe.py — Build the eligible stock universe (Yahoo Finance edition)
# ============================================================

import os
import requests
import pandas as pd
import yfinance as yf
from io import StringIO
from datetime import datetime, timedelta
import config

NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Referer': 'https://www.nseindia.com/',
}

NSE_SYMBOL_FILE = "nse_symbols.csv"  # optional local backup, not required now


def fetch_nifty500_symbols():
    """Fetch Nifty 500 symbol list — proxy for >1000Cr market cap."""
    print("Fetching Nifty 500 list...")
    url = 'https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv'
    try:
        resp = requests.get(url, headers=NSE_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        symbols = set(df['Symbol'].str.strip().tolist())
        names = dict(zip(df['Symbol'].str.strip(), df['Company Name'].str.strip()))
        print(f"  Nifty 500: {len(symbols)} symbols loaded")
        return symbols, names
    except Exception as e:
        print(f"  Warning: Could not fetch Nifty 500: {e}")
        return set(), {}


def fetch_nifty_midcap150_symbols():
    """Fetch Nifty Midcap 150 as additional universe."""
    print("Fetching Nifty Midcap 150...")
    url = 'https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv'
    try:
        resp = requests.get(url, headers=NSE_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        symbols = set(df['Symbol'].str.strip().tolist())
        names = dict(zip(df['Symbol'].str.strip(), df['Company Name'].str.strip()))
        print(f"  Nifty Midcap 150: {len(symbols)} symbols loaded")
        return symbols, names
    except Exception as e:
        print(f"  Warning: Could not fetch Midcap 150: {e}")
        return set(), {}


def fetch_ipo_listing_dates():
    """Fetch IPO listing dates from NSE EQUITY_L.csv."""
    print("Fetching IPO listing dates...")
    url = 'https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv'
    listing_dates = {}
    names = {}
    cutoff = datetime(config.IPO_FROM_YEAR, 1, 1)

    try:
        resp = requests.get(url, headers=NSE_HEADERS, timeout=20)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        df.columns = [c.strip() for c in df.columns]

        date_col = next((c for c in df.columns if 'DATE' in c.upper() and 'LIST' in c.upper()), None)
        sym_col  = next((c for c in df.columns if 'SYMBOL' in c.upper()), None)
        name_col = next((c for c in df.columns if 'NAME' in c.upper()), None)

        if date_col and sym_col:
            for _, row in df.iterrows():
                sym = str(row.get(sym_col, '')).strip()
                date_str = str(row.get(date_col, '')).strip()
                for fmt in ('%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y'):
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        if dt >= cutoff:
                            listing_dates[sym] = dt
                            if name_col:
                                names[sym] = str(row.get(name_col, sym)).strip()
                        break
                    except:
                        continue
    except Exception as e:
        print(f"  Warning: Could not fetch IPO dates: {e}")

    print(f"  IPO stocks from {config.IPO_FROM_YEAR}+: {len(listing_dates)}")
    return listing_dates, names


def check_ath_52w(symbol):
    """
    Use Yahoo Finance to check if stock touched ATH in last 45 days
    or 52W high in last 30 days.
    Returns: list of reason strings (e.g. ['ATH_45D', '52W_30D'])
    """
    try:
        ticker = symbol + ".NS"
        df = yf.download(ticker, period="5y", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 30:
            return []

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        highs = df['High'].dropna().values
        if len(highs) < 30:
            return []

        all_time_high = highs.max()
        year_high = highs[-252:].max() if len(highs) >= 252 else all_time_high
        recent_45 = highs[-config.ATH_LOOKBACK_DAYS:]
        recent_30 = highs[-config.WEEK52_LOOKBACK_DAYS:]

        reasons = []
        if recent_45.max() >= all_time_high * 0.995:
            reasons.append("ATH_45D")
        if recent_30.max() >= year_high * 0.995:
            reasons.append("52W_30D")

        return reasons

    except Exception:
        return []


def build_universe():
    """
    Build final eligible universe.
    Universe = Nifty500 + Midcap150 + IPO 2022+ stocks.
    Each stock tagged with reason: LARGECAP / IPO_2022+ / ATH_45D / 52W_30D
    """
    nifty500, names500 = fetch_nifty500_symbols()
    midcap150, names150 = fetch_nifty_midcap150_symbols()
    ipo_dates, ipo_names = fetch_ipo_listing_dates()

    all_names = {**names500, **names150, **ipo_names}
    large_cap_symbols = nifty500 | midcap150

    if not large_cap_symbols and not ipo_dates:
        print("  All NSE fetches failed — using Nifty 50 fallback...")
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

    all_symbols = large_cap_symbols | set(ipo_dates.keys())
    print(f"\nTotal unique symbols to evaluate: {len(all_symbols)}")

    eligible = []
    checked = 0

    for symbol in sorted(all_symbols):
        reasons = []

        if symbol in ipo_dates:
            reasons.append("IPO_2022+")

        ath_reasons = check_ath_52w(symbol)
        reasons.extend(ath_reasons)

        if symbol in large_cap_symbols and not reasons:
            reasons.append("LARGECAP")

        checked += 1
        if checked % 50 == 0:
            print(f"  Universe building: {checked}/{len(all_symbols)} checked, {len(eligible)} eligible so far...")

        if reasons:
            eligible.append({
                'symbol':          symbol,
                'company_name':    all_names.get(symbol, symbol),
                'market_cap_cr':   1000,
                'universe_reason': ", ".join(reasons)
            })

    print(f"\nEligible universe: {len(eligible)} stocks")
    return eligible
