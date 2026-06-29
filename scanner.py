# ============================================================
# scanner.py — Core scanning logic
# Checks all 4 conditions and computes stop loss
# ============================================================

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import config


def get_daily_candles(dhan_client, security_id, days=150):
    """Fetch daily OHLCV candles. Returns DataFrame or None."""
    today = datetime.today()
    from_date = (today - timedelta(days=days)).strftime('%Y-%m-%d')
    to_date = today.strftime('%Y-%m-%d')

    try:
        resp = dhan_client.get_historical_data(
            security_id=security_id,
            exchange_segment="NSE_EQ",
            instrument_type="EQUITY",
            from_date=from_date,
            to_date=to_date,
            interval="1"
        )
        if not resp or 'data' not in resp or len(resp['data']) < 20:
            return None

        df = pd.DataFrame(resp['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df

    except:
        return None


def get_intraday_first10min_volume(dhan_client, security_id):
    """
    Fetch today's 1-min candles and sum volume of first 10 minutes (9:15–9:24).
    Returns total volume in first 10 min, or None if unavailable.
    """
    today = datetime.today().strftime('%Y-%m-%d')
    try:
        resp = dhan_client.intraday_daily_minute_data(
            security_id=security_id,
            exchange_segment="NSE_EQ",
            instrument_type="EQUITY"
        )
        if not resp or 'data' not in resp:
            return None

        df = pd.DataFrame(resp['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Filter 9:15 to 9:24 (first 10 minutes)
        market_open = pd.Timestamp(today + " 09:15:00")
        cutoff      = pd.Timestamp(today + " 09:25:00")
        first10 = df[(df['timestamp'] >= market_open) & (df['timestamp'] < cutoff)]

        if first10.empty:
            return None

        return int(first10['volume'].sum())

    except:
        return None


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

    # Get the last 90 trading days (excluding today's candle = last row)
    momentum_window = df.iloc[-(config.MOMENTUM_DAYS + config.CONSOLIDATION_MAX_DAYS + 1):-1]

    if len(momentum_window) < config.MOMENTUM_DAYS:
        return False, None, None

    # Find the lowest close in momentum window as the base
    base_close = momentum_window['close'].iloc[0]
    swing_high = momentum_window['high'].max()
    swing_high_idx = momentum_window['high'].idxmax()

    # Check if the move from base to swing_high is >= 30%
    move_pct = ((swing_high - base_close) / base_close) * 100
    if move_pct < config.MOMENTUM_MIN_PCT:
        return False, None, None

    # Everything AFTER the swing high is the consolidation zone
    post_swing = df.loc[swing_high_idx + 1:].iloc[-config.CONSOLIDATION_MAX_DAYS:]

    if len(post_swing) < 1:
        return False, None, None
    if len(post_swing) > config.CONSOLIDATION_MAX_DAYS:
        return False, None, None

    # Price must stay within 25% below swing high during consolidation
    consol_low = post_swing['low'].min()
    max_pullback_pct = ((swing_high - consol_low) / swing_high) * 100
    if max_pullback_pct > config.CONSOLIDATION_MAX_PCT:
        return False, None, None

    # Consolidation range must be REDUCING (contracting volatility)
    # Check: daily range (high-low) trend should be declining
    post_swing = post_swing.copy()
    post_swing['daily_range'] = post_swing['high'] - post_swing['low']
    if len(post_swing) >= 3:
        first_half_range = post_swing['daily_range'].iloc[:len(post_swing)//2].mean()
        second_half_range = post_swing['daily_range'].iloc[len(post_swing)//2:].mean()
        if second_half_range >= first_half_range:
            return False, None, None  # Range not contracting

    return True, swing_high, consol_low


def check_condition2_above_ma(df):
    """
    Condition 2: Latest close must be above 14-day MA.
    Returns: (passed: bool, ma14_value: float)
    """
    if len(df) < config.MA_FAST + 1:
        return False, None

    ma14 = df['close'].rolling(config.MA_FAST).mean().iloc[-2]  # yesterday's MA
    last_close = df['close'].iloc[-2]

    return (last_close > ma14), round(ma14, 2)


def check_condition3_gap_up(df):
    """
    Condition 3: Today's open > yesterday's close.
    Returns: (passed: bool, gap_pct: float)
    """
    if len(df) < 2:
        return False, None

    today_open = df['open'].iloc[-1]
    prev_close = df['close'].iloc[-2]

    gap_pct = ((today_open - prev_close) / prev_close) * 100
    return (today_open > prev_close), round(gap_pct, 2)


def check_condition4_relative_volume(df, first10_vol):
    """
    Condition 4: First 10-min volume > 110% of (20-day avg daily volume ÷ trading_minutes_per_day * 10)
    Baseline: 20-day avg full-day volume. We scale it to 10-min equivalent.
    NSE trading day = 375 minutes. 10/375 = 2.67% of day expected in first 10 min.
    RVOL threshold = baseline_10min * (1 + RVOL_MIN_PCT/100)
    Returns: (passed: bool, rvol_pct: float)
    """
    if first10_vol is None:
        return False, None

    if len(df) < config.RVOL_BASELINE_DAYS + 1:
        return False, None

    avg_daily_vol = df['volume'].iloc[-(config.RVOL_BASELINE_DAYS + 1):-1].mean()
    trading_minutes = 375
    baseline_10min = avg_daily_vol * (10 / trading_minutes)

    rvol_pct = ((first10_vol - baseline_10min) / baseline_10min) * 100
    passed = rvol_pct >= config.RVOL_MIN_PCT

    return passed, round(rvol_pct, 2)


def compute_stop_loss(df):
    """
    SL = lower of:
    1. 20-day MA value
    2. 3% below today's open (alert price proxy)
    Returns: (sl_price: float, sl_type: str)
    """
    ma20 = df['close'].rolling(config.MA_SL).mean().iloc[-1]
    alert_price = df['open'].iloc[-1]
    sl_from_pct = round(alert_price * (1 - config.SL_PCT / 100), 2)
    sl_from_ma = round(ma20, 2)

    if sl_from_ma < sl_from_pct:
        return sl_from_ma, f"20MA (₹{sl_from_ma})"
    else:
        return sl_from_pct, f"3% ({config.SL_PCT}% below ₹{alert_price} = ₹{sl_from_pct})"


def scan_stock(dhan_client, stock):
    """
    Run all conditions on a single stock.
    Returns result dict if all pass, else None.
    """
    sec_id = stock['security_id']
    symbol = stock['symbol']

    # Fetch daily data
    df = get_daily_candles(dhan_client, sec_id, days=200)
    if df is None or len(df) < 100:
        return None

    # Condition 1
    c1, swing_high, consol_low = check_condition1_momentum_consolidation(df)
    if not c1:
        return None

    # Condition 2
    c2, ma14 = check_condition2_above_ma(df)
    if not c2:
        return None

    # Condition 3
    c3, gap_pct = check_condition3_gap_up(df)
    if not c3:
        return None

    # Condition 4 — intraday first 10 min volume
    first10_vol = get_intraday_first10min_volume(dhan_client, sec_id)
    c4, rvol_pct = check_condition4_relative_volume(df, first10_vol)
    if not c4:
        return None

    # All passed — compute SL
    sl_price, sl_label = compute_stop_loss(df)
    alert_price = round(df['open'].iloc[-1], 2)

    return {
        'symbol': symbol,
        'company_name': stock['company_name'],
        'market_cap_cr': stock['market_cap_cr'],
        'universe_reason': stock['universe_reason'],
        'alert_price': alert_price,
        'swing_high': round(swing_high, 2),
        'consol_low': round(consol_low, 2),
        'ma14': ma14,
        'gap_up_pct': gap_pct,
        'rvol_pct': rvol_pct,
        'stop_loss': sl_price,
        'sl_label': sl_label,
        'risk_pct': round(((alert_price - sl_price) / alert_price) * 100, 2)
    }
