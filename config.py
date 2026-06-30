import os

# ============================================================
# SMK Wealth Solutions — Swing Trade Alert System
# config.py — All credentials and parameters in one place
# Data source: Yahoo Finance (free) + NSE live quotes (free)
# ============================================================

# --- Email Settings ---
EMAIL_SENDER   = os.environ.get("EMAIL_SENDER",   "gogoaheadgo@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD",  "your_app_password")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER",  "gogoaheadgo@gmail.com")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- Scanner Parameters ---
MIN_MARKET_CAP_CR = 1000
IPO_FROM_YEAR = 2022
ATH_LOOKBACK_DAYS = 45
WEEK52_LOOKBACK_DAYS = 30
MOMENTUM_DAYS = 90
MOMENTUM_MIN_PCT = 30
CONSOLIDATION_MAX_DAYS = 10
CONSOLIDATION_MAX_PCT = 25
MA_FAST = 14
MA_SL = 20
SL_PCT = 3.0
RVOL_BASELINE_DAYS = 20
RVOL_MIN_PCT = 10
SCAN_TIME = "09:25"
