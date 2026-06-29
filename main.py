# ============================================================
# main.py — Entry point. Runs scanner daily at 9:25 AM IST.
# ============================================================

import schedule
import time
from datetime import datetime
from dhanhq import DhanContext, dhanhq

import config
from universe import build_universe
from scanner import scan_stock
from alerts import send_alert_email, send_no_signal_email

# Track which stocks alerted today (reset daily)
alerted_today = {}
last_universe_date = None
cached_universe = []


def get_dhan_client():
    ctx = DhanContext(config.DHAN_CLIENT_ID, config.DHAN_ACCESS_TOKEN)
    return dhanhq(ctx)


def refresh_universe_if_needed(dhan_client):
    """Rebuild universe once per day (runs before scan)."""
    global cached_universe, last_universe_date
    today = datetime.today().date()
    if last_universe_date != today:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Rebuilding stock universe...")
        cached_universe = build_universe(dhan_client)
        last_universe_date = today
        print(f"Universe ready: {len(cached_universe)} stocks eligible")


def run_scan():
    """Main scan job — runs at 9:25 AM every trading day."""
    global alerted_today

    today_str = datetime.today().strftime('%Y-%m-%d')

    # Skip weekends
    if datetime.today().weekday() >= 5:
        print("Weekend — skipping scan.")
        return

    print(f"\n{'='*60}")
    print(f"SMK SCANNER RUNNING — {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
    print(f"{'='*60}")

    # Reset daily alert tracker
    if alerted_today.get('date') != today_str:
        alerted_today = {'date': today_str, 'symbols': set()}

    dhan_client = get_dhan_client()
    refresh_universe_if_needed(dhan_client)

    if not cached_universe:
        print("Universe is empty. Skipping scan.")
        return

    qualified = []
    total = len(cached_universe)

    for i, stock in enumerate(cached_universe, 1):
        symbol = stock['symbol']

        # Skip if already alerted today
        if symbol in alerted_today['symbols']:
            continue

        print(f"  Scanning [{i}/{total}] {symbol}...", end='\r')

        result = scan_stock(dhan_client, stock)
        if result:
            qualified.append(result)
            alerted_today['symbols'].add(symbol)
            print(f"  ✅ QUALIFIED: {symbol} | Alert ₹{result['alert_price']} | SL ₹{result['stop_loss']}")

    print(f"\nScan complete. {len(qualified)} stock(s) qualified.")

    if qualified:
        send_alert_email(qualified)
    else:
        send_no_signal_email()


def run_once():
    """Run scan immediately — for testing."""
    run_scan()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        # Run immediately (for testing)
        print("Running scan NOW (test mode)...")
        run_once()
    else:
        # Schedule for 9:25 AM daily
        print(f"SMK Swing Trade Scanner started.")
        print(f"Scheduled to run at {config.SCAN_TIME} IST every weekday.")
        print(f"Run 'python main.py --now' to test immediately.\n")

        schedule.every().day.at(config.SCAN_TIME).do(run_scan)

        while True:
            schedule.run_pending()
            time.sleep(30)
