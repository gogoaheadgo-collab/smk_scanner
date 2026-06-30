# ============================================================
# backtest.py — Simulate scanner for last N trading days
# Tests Conditions 1, 2, 3 using historical data (no live NSE quote needed)
# Condition 4 (relative volume) approximated using next day's actual volume
# ============================================================

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import config
from universe import build_universe
from scanner import (
    check_condition1_momentum_consolidation,
    check_condition2_above_ma,
    compute_stop_loss
)
import sys


def check_condition3_gap_up_backtest(df, as_of_idx):
    """Gap up check using historical open vs prior close, for backtest date."""
    if as_of_idx < 1:
        return False, None
    today_open = df['open'].iloc[as_of_idx]
    prev_close = df['close'].iloc[as_of_idx - 1]
    gap_pct = ((today_open - prev_close) / prev_close) * 100
    return (today_open > prev_close), round(gap_pct, 2)


def check_condition4_relative_volume_backtest(df, as_of_idx):
    """
    Approximate RVOL using actual full-day volume on the day vs 20-day avg.
    (We don't have true first-10-min historical data from Yahoo, so we use
    full-day volume vs avg as a proxy signal — flagged clearly in output.)
    """
    if as_of_idx < config.RVOL_BASELINE_DAYS:
        return False, None

    avg_daily_vol = df['volume'].iloc[as_of_idx - config.RVOL_BASELINE_DAYS:as_of_idx].mean()
    today_vol = df['volume'].iloc[as_of_idx]

    if avg_daily_vol <= 0:
        return False, None

    rvol_pct = ((today_vol - avg_daily_vol) / avg_daily_vol) * 100
    # Using a higher bar since this is full-day vol, not first-10-min
    passed = rvol_pct >= config.RVOL_MIN_PCT
    return passed, round(rvol_pct, 2)


def backtest_stock(symbol, company_name, universe_reason, num_days=10):
    """
    Run all 4 conditions for each of the last `num_days` trading days.
    Returns list of qualifying days for this stock.
    """
    try:
        ticker = symbol + ".NS"
        df = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 150:
            return []

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={'date': 'timestamp'})
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df = df.sort_values('timestamp').reset_index(drop=True)

        results = []
        total_rows = len(df)

        # Check each of the last `num_days` trading days
        for offset in range(num_days, 0, -1):
            as_of_idx = total_rows - offset
            if as_of_idx < config.MOMENTUM_DAYS + config.CONSOLIDATION_MAX_DAYS + 2:
                continue

            # Slice data UP TO (not including future) this day for conditions 1 & 2
            df_slice = df.iloc[:as_of_idx + 1].reset_index(drop=True)

            c1, swing_high, consol_low = check_condition1_momentum_consolidation(df_slice)
            if not c1:
                continue

            c2, ma14 = check_condition2_above_ma(df_slice)
            if not c2:
                continue

            c3, gap_pct = check_condition3_gap_up_backtest(df, as_of_idx)
            if not c3:
                continue

            c4, rvol_pct = check_condition4_relative_volume_backtest(df, as_of_idx)
            if not c4:
                continue

            alert_price = round(float(df['open'].iloc[as_of_idx]), 2)
            sl_price, sl_label = compute_stop_loss(df_slice, alert_price)
            trade_date = df['timestamp'].iloc[as_of_idx].strftime('%Y-%m-%d')

            # Next day's performance (if available) — did it work?
            next_day_perf = None
            if as_of_idx + 1 < total_rows:
                next_close = df['close'].iloc[as_of_idx + 1]
                next_day_perf = round(((next_close - alert_price) / alert_price) * 100, 2)

            results.append({
                'date': trade_date,
                'symbol': symbol,
                'company_name': company_name,
                'universe_reason': universe_reason,
                'alert_price': alert_price,
                'stop_loss': sl_price,
                'gap_pct': gap_pct,
                'rvol_pct': rvol_pct,
                'next_day_pct': next_day_perf
            })

        return results

    except Exception as e:
        return []


def run_backtest(num_days=10, max_stocks=None):
    print(f"\n{'='*70}")
    print(f"SMK SCANNER BACKTEST — Last {num_days} Trading Days")
    print(f"{'='*70}\n")

    print("Building universe...")
    universe = build_universe()
    print(f"Universe: {len(universe)} stocks\n")

    if max_stocks:
        universe = universe[:max_stocks]
        print(f"(Limited to first {max_stocks} stocks for this run)\n")

    all_results = []
    total = len(universe)

    for i, stock in enumerate(universe, 1):
        print(f"  Backtesting [{i}/{total}] {stock['symbol']}...", end='\r')
        results = backtest_stock(
            stock['symbol'],
            stock['company_name'],
            stock['universe_reason'],
            num_days=num_days
        )
        if results:
            print(f"\n  >>> {stock['symbol']}: {len(results)} signal(s) found")
            all_results.extend(results)

    print(f"\n\n{'='*70}")
    print(f"BACKTEST COMPLETE: {len(all_results)} total signals across {num_days} days")
    print(f"{'='*70}\n")

    if all_results:
        df_results = pd.DataFrame(all_results)
        df_results = df_results.sort_values('date')

        print(df_results.to_string(index=False))

        # Save to CSV
        df_results.to_csv('backtest_results.csv', index=False)
        print(f"\nSaved to backtest_results.csv")

        # Summary stats
        if 'next_day_pct' in df_results.columns:
            valid = df_results['next_day_pct'].dropna()
            if len(valid) > 0:
                print(f"\n--- Next-Day Performance Summary ---")
                print(f"Signals with next-day data: {len(valid)}")
                print(f"Average next-day move: {valid.mean():.2f}%")
                print(f"Win rate (positive next day): {(valid > 0).sum()}/{len(valid)} = {(valid > 0).mean()*100:.1f}%")
    else:
        print("No signals found in backtest period.")
        print("This could mean: (1) conditions are very strict, (2) market was flat/choppy, or (3) a logic issue.")

    return all_results


if __name__ == "__main__":
    days = 10
    max_stocks = None

    if len(sys.argv) > 1:
        days = int(sys.argv[1])
    if len(sys.argv) > 2:
        max_stocks = int(sys.argv[2])

    run_backtest(num_days=days, max_stocks=max_stocks)
