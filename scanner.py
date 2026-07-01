# ============================================================
# scanner.py — Core scanning logic (Yahoo Finance edition)
# Checks all 4 conditions and computes stop loss
# ============================================================

import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
import config

# Diagnostic counters — reset per scan run, reported at end of main.py
NSE_STATS = {
    'attempts': 0,
    'success': 0,
    'session_warmup_failed': 0,
    'quote_fetch_failed': 0,
    'json_parse_failed': 0,
    'no_open_price': 0,
    'no_volume_data': 0,
    'last_error_sample': None,
}

_nse_session = None


def get_nse_session():
    """Reuse a single NSE session across all stock checks in a run.
    Creating a fresh session per stock (old behavior) increases the
    chance of NSE rate-limiting / blocking the scanner."""
    global _nse_session
    if _nse_session is None:
        _nse_session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        try:
            _nse_session.get("https://www.nseindia.com", headers=headers, timeout=10)
        except Exception as e:
            NSE_STATS['session_warmup_failed'] += 1
            NSE_STATS['last_error_sample'] = f"session_warmup: {type(e).__name__}: {e}"
    return _nse_session


def reset_nse_session():
    """Force a fresh session (e.g. if we suspect we got blocked)."""
    global _nse_session
    _nse_session = None


def get_daily_candles(symbol, days=300):
    """
    Fetch daily OHLCV candles from Yahoo Finance.
    NSE stocks use .NS suffix on Yahoo.
    Returns DataFrame or None.
    """
    try:
        ticker = symbol + ".NS"
        df = yf.download(ticker, period=f"{days}d", interval="1d",
                          progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 20:
            return None

        # yfinance returns MultiIndex columns when single ticker — flatten
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={'date': 'timestamp'})
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df

    except Exception:
        return None


def get_today_open_and_first10min_volume(symbol):
    """
    Fetch today's live open price + approximate first-10-min volume
    using NSE's public quote API.
    Returns: (today_open, first10_vol_estimate) or (None, None)
    Tracks detailed failure reasons in NSE_STATS for diagnostics.
    """
    NSE_STATS['attempts'] += 1

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': f'https://www.nseindia.com/get-quotes/equity?symbol={symbol}',
    }

    session = get_nse_session()
    if session is None:
        return None, None

    try:
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        resp = session.get(url, headers=headers, timeout=10)

        if resp.status_code != 200:
            NSE_STATS['quote_fetch_failed'] += 1
            NSE_STATS['last_error_sample'] = f"{symbol}: HTTP {resp.status_code}"
            # If we're being blocked (403/429), refresh session for next call
            if resp.status_code in (403, 429):
                reset_nse_session()
            return None, None

        try:
            data = resp.json()
        except Exception as e:
            NSE_STATS['json_parse_failed'] += 1
            NSE_STATS['last_error_sample'] = f"{symbol}: JSON parse failed: {type(e).__name__}"
            return None, None

        today_open = data.get('priceInfo', {}).get('open', None)
        if today_open is None:
            NSE_STATS['no_open_price'] += 1
            NSE_STATS['last_error_sample'] = f"{symbol}: no open price in response (keys: {list(data.keys())[:5]})"
            return None, None

        total_vol_so_far = None
        try:
            total_vol_so_far = data.get('marketDeptOrderBook', {}).get('tradeInfo', {}).get('totalTradedVolume', None)
            if total_vol_so_far is None:
                total_vol_so_far = data.get('preOpenMarket', {}).get('totalTradedVolume', None)
        except Exception:
            pass

        if total_vol_so_far is None:
            NSE_STATS['no_volume_data'] += 1
            NSE_STATS['last_error_sample'] = f"{symbol}: open found ({today_open}) but no volume data"
            return today_open, None

        NSE_STATS['success'] += 1
        return today_open, total_vol_so_far

    except requests.exceptions.RequestException as e:
        NSE_STATS['quote_fetch_failed'] += 1
        NSE_STATS['last_error_sample'] = f"{symbol}: {type(e).__name__}: {e}"
        return None, None
    except Exception as e:
        NSE_STATS['quote_fetch_failed'] += 1
        NSE_STATS['last_error_sample'] = f"{symbol}: unexpected {type(e).__name__}: {e}"
        return None, None


def print_nse_diagnostics():
    """Print a summary of NSE live-quote call success/failure to the run log."""
    s = NSE_STATS
    print(f"\n{'='*60}")
    print(f"NSE LIVE QUOTE DIAGNOSTICS (Condition 3 & 4 data source)")
    print(f"{'='*60}")
    print(f"  Total attempts:          {s['attempts']}")
    print(f"  Successful (open+vol):   {s['success']}")
    print(f"  Session warmup failed:   {s['session_warmup_failed']}")
    print(f"  Quote fetch failed:      {s['quote_fetch_failed']}  (network/HTTP errors, incl. 403/429 blocks)")
    print(f"  JSON parse failed:       {s['json_parse_failed']}  (NSE returned non-JSON, likely a block page)")
    print(f"  No open price in resp:   {s['no_open_price']}")
    print(f"  No volume data:          {s['no_volume_data']}")
    if s['attempts'] > 0:
        success_rate = (s['success'] / s['attempts']) * 100
        print(f"  Success rate:            {success_rate:.1f}%")
        if success_rate < 50:
            print(f"\n  WARNING: Success rate below 50%. NSE is likely blocking or rate-limiting")
            print(f"  this scanner's IP (common for GitHub Actions shared IPs). If this persists,")
            print(f"  Conditions 3 & 4 cannot work reliably from GitHub Actions and we'd need an")
            print(f"  alternative live-quote source.")
    if s['last_error_sample']:
        print(f"\n  Last error sample: {s['last_error_sample']}")
    print(f"{'='*60}\n")


def check_condition1_momentum_consolidation(df):
    """
    Condition 1:
    - Stock moved 30%+ in last 90 trading days
    - Followed by consolidation of max 10 days
    - Consolidation within 25% of swing high
    - Consolidation range must be reducing (contracting)
    Returns: (passed: bool, swing_high: float, consol_low: float)
    """
    if len(df) < config.MOMENTUM_DAYS + 2:
        return False, None, None

    momentum_window = df.iloc[-(config.MOMENTUM_DAYS + config.CONSOLIDATION_MAX_DAYS + 1):-1]

    if len(momentum_window) < config.MOMENTUM_DAYS:
        return False, None, None

    base_close = momentum_window['close'].iloc[0]
    swing_high = momentum_window['high'].max()
    swing_high_idx = momentum_window['high'].idxmax()

    move_pct = ((swing_high - base_close) / base_close) * 100
    if move_pct < config.MOMENTUM_MIN_PCT:
        return False, None, None

    post_swing = df.loc[swing_high_idx + 1:].iloc[-config.CONSOLIDATION_MAX_DAYS:]

    if len(post_swing) < 1 or len(post_swing) > config.CONSOLIDATION_MAX_DAYS:
        return False, None, None

    consol_low = post_swing['low'].min()
    max_pullback_pct = ((swing_high - consol_low) / swing_high) * 100
    if max_pullback_pct > config.CONSOLIDATION_MAX_PCT:
        return False, None, None

    post_swing = post_swing.copy()
    post_swing['daily_range'] = post_swing['high'] - post_swing['low']
    if len(post_swing) >= 3:
        first_half_range = post_swing['daily_range'].iloc[:len(post_swing)//2].mean()
        second_half_range = post_swing['daily_range'].iloc[len(post_swing)//2:].mean()
        if second_half_range >= first_half_range:
            return False, None, None

    return True, swing_high, consol_low


def check_condition2_above_ma(df):
    """Condition 2: Latest close must be above 14-day MA."""
    if len(df) < config.MA_FAST + 1:
        return False, None

    ma14 = df['close'].rolling(config.MA_FAST).mean().iloc[-2]
    last_close = df['close'].iloc[-2]

    return (last_close > ma14), round(float(ma14), 2)


def check_condition3_gap_up(df, today_open):
    """
    Condition 3: Today's open > yesterday's close.
    Uses LIVE today_open from NSE quote API (not Yahoo, which lags).
    """
    if len(df) < 1 or today_open is None:
        return False, None

    prev_close = df['close'].iloc[-1]  # yesterday's close (Yahoo daily data, latest complete day)
    gap_pct = ((today_open - prev_close) / prev_close) * 100
    return (today_open > prev_close), round(gap_pct, 2)


def check_condition4_relative_volume(df, first10_vol_estimate):
    """
    Condition 4: First 10-min volume > 10% above 20-day average baseline.
    """
    if first10_vol_estimate is None:
        return False, None

    if len(df) < config.RVOL_BASELINE_DAYS:
        return False, None

    avg_daily_vol = df['volume'].iloc[-config.RVOL_BASELINE_DAYS:].mean()
    trading_minutes = 375
    baseline_10min = avg_daily_vol * (10 / trading_minutes)

    if baseline_10min <= 0:
        return False, None

    rvol_pct = ((first10_vol_estimate - baseline_10min) / baseline_10min) * 100
    passed = rvol_pct >= config.RVOL_MIN_PCT

    return passed, round(rvol_pct, 2)


def compute_stop_loss(df, alert_price):
    """SL = lower of 20-day MA or 3% below alert price."""
    ma20 = df['close'].rolling(config.MA_SL).mean().iloc[-1]
    sl_from_pct = round(alert_price * (1 - config.SL_PCT / 100), 2)
    sl_from_ma = round(float(ma20), 2)

    if sl_from_ma < sl_from_pct:
        return sl_from_ma, f"20MA (₹{sl_from_ma})"
    else:
        return sl_from_pct, f"3% ({config.SL_PCT}% below ₹{alert_price} = ₹{sl_from_pct})"


# Funnel diagnostics — how many stocks pass each condition
FUNNEL_STATS = {
    'total_scanned': 0,
    'passed_c1_momentum': 0,
    'passed_c2_ma': 0,
    'passed_c3_gap': 0,
    'passed_c4_volume': 0,
    'fully_qualified': 0,
}


def print_funnel_diagnostics():
    f = FUNNEL_STATS
    print(f"\n{'='*60}")
    print(f"CONDITION FUNNEL DIAGNOSTICS")
    print(f"{'='*60}")
    print(f"  Total stocks scanned:        {f['total_scanned']}")
    print(f"  Passed C1 (momentum/consol): {f['passed_c1_momentum']}")
    print(f"  Passed C2 (above 14MA):      {f['passed_c2_ma']}")
    print(f"  Passed C3 (gap up):          {f['passed_c3_gap']}")
    print(f"  Passed C4 (relative volume): {f['passed_c4_volume']}")
    print(f"  Fully qualified:             {f['fully_qualified']}")
    print(f"{'='*60}\n")


def scan_stock(stock):
    """
    Run all conditions on a single stock using Yahoo Finance + NSE live quote.
    Returns result dict if all pass, else None.
    """
    symbol = stock['symbol']
    FUNNEL_STATS['total_scanned'] += 1

    df = get_daily_candles(symbol, days=300)
    if df is None or len(df) < 100:
        return None

    # Condition 1 — momentum + consolidation (historical, Yahoo data)
    c1, swing_high, consol_low = check_condition1_momentum_consolidation(df)
    if not c1:
        return None
    FUNNEL_STATS['passed_c1_momentum'] += 1

    # Condition 2 — above 14MA (historical, Yahoo data)
    c2, ma14 = check_condition2_above_ma(df)
    if not c2:
        return None
    FUNNEL_STATS['passed_c2_ma'] += 1

    # Fetch TODAY's live open + volume from NSE (only for stocks that passed C1+C2 — saves API calls)
    today_open, first10_vol = get_today_open_and_first10min_volume(symbol)

    # Condition 3 — gap up (live data)
    c3, gap_pct = check_condition3_gap_up(df, today_open)
    if not c3:
        return None
    FUNNEL_STATS['passed_c3_gap'] += 1

    # Condition 4 — relative volume (live data)
    c4, rvol_pct = check_condition4_relative_volume(df, first10_vol)
    if not c4:
        return None
    FUNNEL_STATS['passed_c4_volume'] += 1

    alert_price = round(today_open, 2)
    sl_price, sl_label = compute_stop_loss(df, alert_price)

    FUNNEL_STATS['fully_qualified'] += 1

    return {
        'symbol': symbol,
        'company_name': stock['company_name'],
        'market_cap_cr': stock['market_cap_cr'],
        'universe_reason': stock['universe_reason'],
        'alert_price': alert_price,
        'swing_high': round(float(swing_high), 2),
        'consol_low': round(float(consol_low), 2),
        'ma14': ma14,
        'gap_up_pct': gap_pct,
        'rvol_pct': rvol_pct,
        'stop_loss': sl_price,
        'sl_label': sl_label,
        'risk_pct': round(((alert_price - sl_price) / alert_price) * 100, 2)
    }
