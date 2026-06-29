# SMK Swing Trade Alert System

**SMK Wealth Solutions | Built by Gopal**

Scans all NSE stocks daily at 9:25 AM and sends email alerts when a stock meets all 4 swing trade conditions.

---

## Setup (One Time)

### Step 1 — Install Python libraries
```bash
pip install -r requirements.txt
```

### Step 2 — Fill in your credentials in config.py

Open `config.py` and fill in:

```python
DHAN_CLIENT_ID = "your client id from Dhan developer portal"
DHAN_ACCESS_TOKEN = "your access token from Dhan developer portal"

EMAIL_SENDER = "yourgmail@gmail.com"
EMAIL_PASSWORD = "your Gmail App Password"   # See below
EMAIL_RECEIVER = "where you want alerts"
```

**How to get Gmail App Password:**
1. Go to Google Account → Security → 2-Step Verification (enable it)
2. Then go to Security → App Passwords
3. Create one for "Mail" → copy the 16-character password
4. Paste it in EMAIL_PASSWORD (not your regular Gmail password)

**How to get Dhan API credentials:**
1. Login to developer.dhanhq.co
2. Go to My Apps → Create App
3. Copy Client ID and generate Access Token

---

## Running

### Test immediately (to verify setup works):
```bash
python main.py --now
```

### Run on schedule (9:25 AM every weekday):
```bash
python main.py
```

Keep this terminal/process running. On a laptop, it runs as long as the terminal is open.

---

## Files

| File | Purpose |
|------|---------|
| `config.py` | All your credentials and scan parameters |
| `universe.py` | Builds eligible stock universe (market cap + IPO/ATH/52W) |
| `scanner.py` | Core logic — checks all 4 conditions, computes SL |
| `alerts.py` | Formats and sends HTML email alert |
| `main.py` | Scheduler — runs everything daily at 9:25 AM |

---

## What the Alert Email Shows

Each qualifying stock shows:
- Symbol + Company Name
- Alert Price (today's open)
- **Stop Loss** (lower of 20MA or 3% below alert price)
- Risk % (how far SL is from alert price)
- Gap Up % (how much above yesterday's close it opened)
- Relative Volume % (first 10-min volume vs 20-day baseline)
- Why it qualified (IPO_2022+ / ATH_45D / 52W_30D)

---

## Conditions Checked

1. **Momentum + Consolidation** — 30%+ move in 90 trading days → 1–10 day consolidation with contracting range, within 25% of swing high
2. **Above 14MA** — yesterday's close above 14-day moving average
3. **Gap Up** — today's open > yesterday's close
4. **Relative Volume** — first 10-min volume > 10% above 20-day average baseline

---

## To Run 24/7 Without Keeping Laptop On

Deploy to **Dhan Cloud** or a cheap VPS (₹500/month on DigitalOcean or Hetzner).
Dhan Cloud is recommended — handles SEBI static IP requirement automatically.
