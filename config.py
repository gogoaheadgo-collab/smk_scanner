# ============================================================
# SMK Wealth Solutions — Swing Trade Alert System
# config.py — All credentials and parameters in one place
# ============================================================

# --- Dhan API Credentials ---
DHAN_CLIENT_ID = "YOUR_CLIENT_ID"
DHAN_ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"

# --- Email Settings ---
import os
EMAIL_SENDER   = os.environ.get("EMAIL_SENDER",   "gogoaheadgo@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD",  "lfpanywavsmtiggr")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER",  "gogoaheadgo@gmail.com")SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- Scanner Parameters ---
MIN_MARKET_CAP_CR = 1000          # Minimum market cap in crores
IPO_FROM_YEAR = 2022              # IPO listed on or after Jan 1 of this year

ATH_LOOKBACK_DAYS = 45            # Stock must have touched ATH within this many trading days
WEEK52_LOOKBACK_DAYS = 30         # Stock must have touched 52W high within this many trading days

MOMENTUM_DAYS = 90                # Trading days to measure the 30% move
MOMENTUM_MIN_PCT = 30             # Minimum % move required

CONSOLIDATION_MAX_DAYS = 10       # Max consolidation days after the big move
CONSOLIDATION_MAX_PCT = 25        # Consolidation must stay within 25% of swing high

MA_FAST = 14                      # Fast MA for Condition 2 (price above this)
MA_SL = 20                        # Slow MA for stop loss calculation
SL_PCT = 3.0                      # SL % below alert price (alternative to MA SL)

RVOL_BASELINE_DAYS = 20           # Days to compute average volume for relative volume
RVOL_MIN_PCT = 10                 # First 10-min relative volume must exceed avg by this %

SCAN_TIME = "09:25"               # Time to run scan daily (IST, 24hr format)
