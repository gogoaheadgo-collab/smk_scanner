# ============================================================
# alerts.py — Format and send email alerts
# ============================================================

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import config


def format_alert_email(results):
    """
    Build a clean HTML email with all qualifying stocks.
    results = list of dicts from scanner.scan_stock()
    """
    today = datetime.today().strftime('%d %b %Y')
    count = len(results)

    # TradingView copy box — one symbol per line, NSE prefix for TV
    symbols_block = "<br>".join([f"NSE:{r['symbol']}" for r in results])

    rows = ""
    for r in results:
        rows += f"""
        <tr>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; font-weight:bold; color:#1a2e5a;">
                {r['symbol']}
            </td>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; font-size:12px; color:#555;">
                {r['company_name']}
            </td>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; text-align:center;">
                ₹{r['alert_price']}
            </td>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; text-align:center; color:#c0392b; font-weight:bold;">
                ₹{r['stop_loss']}
            </td>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; text-align:center; color:#c0392b;">
                {r['risk_pct']}%
            </td>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; text-align:center; color:#27ae60;">
                +{r['gap_up_pct']}%
            </td>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; text-align:center; color:#27ae60;">
                +{r['rvol_pct']}%
            </td>
            <td style="padding:10px; border-bottom:1px solid #e0d5b0; text-align:center; font-size:11px; color:#888;">
                {r['universe_reason']}
            </td>
        </tr>
        """

    html = f"""
    <html>
    <body style="margin:0; padding:0; background:#f5f0e8; font-family: Georgia, serif;">

    <div style="max-width:900px; margin:30px auto; background:#ffffff;
                border:2px solid #c9a84c; border-radius:8px; overflow:hidden;">

        <!-- Header -->
        <div style="background: linear-gradient(135deg, #1a2e5a, #2c4a8a);
                    padding: 24px 30px; text-align:center;">
            <div style="color:#c9a84c; font-size:22px; font-weight:bold; letter-spacing:2px;">
                SMK WEALTH SOLUTIONS
            </div>
            <div style="color:#a0b4d0; font-size:13px; margin-top:4px; letter-spacing:1px;">
                Grounded in truth, guided by grace
            </div>
            <div style="color:#ffffff; font-size:16px; margin-top:12px; font-weight:bold;">
                🔔 Swing Trade Alert — {today}
            </div>
            <div style="color:#c9a84c; font-size:13px; margin-top:4px;">
                {count} stock{"s" if count != 1 else ""} qualified all 4 conditions today
            </div>
        </div>

        <!-- Table -->
        <div style="padding:20px 24px;">
            <table style="width:100%; border-collapse:collapse; font-size:13px;">
                <thead>
                    <tr style="background:#1a2e5a; color:#c9a84c;">
                        <th style="padding:10px; text-align:left;">Symbol</th>
                        <th style="padding:10px; text-align:left;">Company</th>
                        <th style="padding:10px; text-align:center;">Alert Price</th>
                        <th style="padding:10px; text-align:center;">Stop Loss</th>
                        <th style="padding:10px; text-align:center;">Risk %</th>
                        <th style="padding:10px; text-align:center;">Gap Up</th>
                        <th style="padding:10px; text-align:center;">RVOL %</th>
                        <th style="padding:10px; text-align:center;">Reason</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>

        <!-- TradingView Copy Box -->
        <div style="padding:0 24px 16px;">
            <div style="font-size:12px; font-weight:bold; color:#1a2e5a; margin-bottom:6px; letter-spacing:0.5px;">
                📋 COPY FOR TRADINGVIEW WATCHLIST
            </div>
            <div style="background:#f0f4ff; border:1.5px dashed #c9a84c; border-radius:6px; padding:14px 16px;
                        font-family:monospace; font-size:14px; font-weight:bold; color:#1a2e5a;
                        letter-spacing:1px; line-height:2;">
                {symbols_block}
            </div>
            <div style="font-size:11px; color:#999; margin-top:6px;">
                TradingView → Watchlist → Import → paste above symbols (one per line)
            </div>
        </div>

        <!-- Condition Summary -->
        <div style="padding:0 24px 16px;">
            <div style="background:#f9f5ec; border-left:4px solid #c9a84c;
                        padding:14px 16px; font-size:12px; color:#555; line-height:1.8;">
                <strong style="color:#1a2e5a;">Conditions checked:</strong><br>
                ✅ 30%+ move in last 90 trading days → consolidation (max 10 days, contracting range, within 25% of swing high)<br>
                ✅ Price above 14-day MA<br>
                ✅ Today open > yesterday close (gap up)<br>
                ✅ First 10-min volume > 10% above 20-day average baseline<br><br>
                <strong style="color:#c0392b;">Stop Loss:</strong> Lower of 20-day MA or 3% below alert price.
            </div>
        </div>

        <!-- Disclaimer -->
        <div style="background:#1a2e5a; padding:14px 24px; text-align:center;">
            <div style="color:#a0b4d0; font-size:11px;">
                This alert is for educational and informational purposes only. Not a buy/sell recommendation.
                Always apply your own judgement. SMK Wealth Solutions.
            </div>
        </div>

    </div>
    </body>
    </html>
    """
    return html


def send_alert_email(results):
    """Send the alert email. Skips if no results."""
    if not results:
        print("No stocks qualified today. No email sent.")
        return

    today = datetime.today().strftime('%d %b %Y')
    subject = f"SMK Alert | {len(results)} Swing Setup(s) | {today}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = config.EMAIL_SENDER
    msg['To'] = config.EMAIL_RECEIVER

    html_body = format_alert_email(results)
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_SENDER, config.EMAIL_RECEIVER, msg.as_string())
        print(f"✅ Alert email sent: {len(results)} stocks — {subject}")
    except Exception as e:
        print(f"❌ Email failed: {e}")


def send_no_signal_email():
    """Optional: send a daily 'no signal' confirmation so you know the scanner ran."""
    today = datetime.today().strftime('%d %b %Y')
    subject = f"SMK Scanner | No Signals Today | {today}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = config.EMAIL_SENDER
    msg['To'] = config.EMAIL_RECEIVER

    body = f"""
    <html><body style="font-family:Georgia; padding:30px; color:#1a2e5a;">
    <h3>SMK Wealth Solutions — Daily Scanner Report</h3>
    <p>Date: <strong>{today}</strong></p>
    <p>Scanner ran successfully at 9:25 AM. <strong>No stocks qualified</strong> all 4 conditions today.</p>
    <p style="color:#888; font-size:12px;">Grounded in truth, guided by grace.</p>
    </body></html>
    """
    msg.attach(MIMEText(body, 'html'))

    try:
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_SENDER, config.EMAIL_RECEIVER, msg.as_string())
        print("📭 No-signal email sent.")
    except Exception as e:
        print(f"❌ No-signal email failed: {e}")
