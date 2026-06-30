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
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.nseindia.com/get-quotes/equity',
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        resp = session.get(url, headers=headers, timeout=10)
        data = resp.json()

        today_open = data.get('priceInfo', {}).get('open', None)

        # NSE quote API gives full day's running volume, not first-10-min specifically.
        # We approximate: at 9:25 AM, ~10 min of trading has occurred.
        # totalTradedVolume reflects volume traded so far in the session.
        total_vol_so_far = data.get('preOpenMarket', {}).get('totalTradedVolume', None)
        if total_vol_so_far is None:
            total_vol_so_far = data.get('marketDeptOrderBook', {}).get('tradeInfo', {}).get('totalTradedVolume', None)

        return today_open, total_vol_so_far

    except Exception:
        return None, None


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


def scan_stock(stock):
    """
    Run all conditions on a single stock using Yahoo Finance + NSE live quote.
    Returns result dict if all pass, else None.
    """
    symbol = stock['symbol']

    df = get_daily_candles(symbol, days=300)
    if df is None or len(df) < 100:
        return None

    # Condition 1 — momentum + consolidation (historical, Yahoo data)
    c1, swing_high, consol_low = check_condition1_momentum_consolidation(df)
    if not c1:
        return None

    # Condition 2 — above 14MA (historical, Yahoo data)
    c2, ma14 = check_condition2_above_ma(df)
    if not c2:
        return None

    # Fetch TODAY's live open + volume from NSE (only for stocks that passed C1+C2 — saves API calls)
    today_open, first10_vol = get_today_open_and_first10min_volume(symbol)

    # Condition 3 — gap up (live data)
    c3, gap_pct = check_condition3_gap_up(df, today_open)
    if not c3:
        return None

    # Condition 4 — relative volume (live data)
    c4, rvol_pct = check_condition4_relative_volume(df, first10_vol)
    if not c4:
        return None

    alert_price = round(today_open, 2)
    sl_price, sl_label = compute_stop_loss(df, alert_price)

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
