"""
Weekly Stock Screener για Βασίλη
Τρέχει αυτόματα μέσω GitHub Actions κάθε Δευτέρα πρωί
"""

import yfinance as yf
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from datetime import datetime

# ── Ρυθμίσεις email ──────────────────────────────────────────────
SENDER_EMAIL = "vasilisglaros@gmail.com"
RECEIVER_EMAIL = "vasilisglaros@gmail.com"
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")  # από GitHub Secrets

# ── Λίστα μετοχών για scanning ───────────────────────────────────
# Μπορείς να προσθέτεις/αφαιρείς όποτε θέλεις
WATCHLIST_US = [
    # Mega cap / Growth
    "AMZN", "MSFT", "GOOGL", "META", "NVDA", "AAPL",
    # Mid cap Growth
    "FROG", "TTWO", "DDOG", "SNOW", "CRWD", "NET",
    # Value / Dividend
    "BRK-B", "JPM", "BAC", "XOM", "CVX",
    # Semiconductors
    "AMD", "INTC", "QCOM", "AVGO", "MU",
]

WATCHLIST_EU = [
    # Ελληνικές
    "PPC.AT", "MYTIL.AT", "OPAP.AT", "EUROB.AT",
    # Ευρωπαϊκές
    "ASML.AS", "SAP.DE", "NOVO-B.CO", "RR.L",
]

ALL_TICKERS = WATCHLIST_US + WATCHLIST_EU

# ── Κριτήρια φιλτραρίσματος ──────────────────────────────────────
FILTERS = {
    "max_pe": 30,               # P/E κάτω από 30
    "min_revenue_growth": 0.10, # Revenue growth > 10% YoY
    "max_debt_equity": 2.0,     # Debt/Equity < 2
    "min_from_52w_high": -0.30, # Τουλάχιστον -30% από 52w high (value opportunity)
    "min_analyst_upside": 0.15, # Analyst target > 15% από τρέχουσα τιμή
}


def get_stock_data(ticker):
    """Τραβάει δεδομένα για μία μετοχή"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        week52_high = info.get("fiftyTwoWeekHigh")
        target_price = info.get("targetMeanPrice")
        pe_ratio = info.get("trailingPE")
        revenue_growth = info.get("revenueGrowth")
        debt_equity = info.get("debtToEquity")
        market_cap = info.get("marketCap")
        name = info.get("shortName", ticker)
        sector = info.get("sector", "N/A")
        recommendation = info.get("recommendationKey", "N/A")

        if not current_price or not week52_high:
            return None

        pct_from_high = (current_price - week52_high) / week52_high
        analyst_upside = ((target_price - current_price) / current_price) if target_price else None

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "price": current_price,
            "52w_high": week52_high,
            "pct_from_high": pct_from_high,
            "pe": pe_ratio,
            "revenue_growth": revenue_growth,
            "debt_equity": debt_equity / 100 if debt_equity else None,
            "market_cap": market_cap,
            "target_price": target_price,
            "analyst_upside": analyst_upside,
            "recommendation": recommendation,
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


def apply_filters(data):
    """Εφαρμόζει τα φίλτρα και επιστρέφει score"""
    score = 0
    flags = []

    # Value opportunity — έχει πέσει από high
    if data["pct_from_high"] and data["pct_from_high"] <= FILTERS["min_from_52w_high"]:
        score += 2
        flags.append(f"📉 -{abs(data['pct_from_high']):.0%} από 52w high")

    # Analyst upside
    if data["analyst_upside"] and data["analyst_upside"] >= FILTERS["min_analyst_upside"]:
        score += 2
        flags.append(f"🎯 Analyst upside: +{data['analyst_upside']:.0%}")

    # Reasonable P/E
    if data["pe"] and 0 < data["pe"] <= FILTERS["max_pe"]:
        score += 1
        flags.append(f"💰 P/E: {data['pe']:.1f}x")

    # Revenue growth
    if data["revenue_growth"] and data["revenue_growth"] >= FILTERS["min_revenue_growth"]:
        score += 2
        flags.append(f"📈 Revenue growth: +{data['revenue_growth']:.0%}")

    # Low debt
    if data["debt_equity"] and data["debt_equity"] <= FILTERS["max_debt_equity"]:
        score += 1
        flags.append(f"✅ Debt/Equity: {data['debt_equity']:.1f}x")

    # Strong buy recommendation
    if data["recommendation"] in ["strongBuy", "buy"]:
        score += 1
        flags.append(f"⭐ Analysts: {data['recommendation'].upper()}")

    return score, flags


def format_market_cap(mc):
    if not mc:
        return "N/A"
    if mc >= 1e12:
        return f"${mc/1e12:.1f}T"
    if mc >= 1e9:
        return f"${mc/1e9:.1f}B"
    return f"${mc/1e6:.0f}M"


def build_html_report(results):
    """Φτιάχνει το HTML email report"""
    date_str = datetime.now().strftime("%d/%m/%Y")

    # Ταξινόμηση βάσει score
    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)
    top_picks = [r for r in results_sorted if r["score"] >= 4]
    watchlist = [r for r in results_sorted if 2 <= r["score"] < 4]

    def stock_row(r):
        upside_str = f"+{r['data']['analyst_upside']:.0%}" if r['data']['analyst_upside'] else "N/A"
        high_str = f"{r['data']['pct_from_high']:.0%}" if r['data']['pct_from_high'] else "N/A"
        flags_str = "<br>".join(r["flags"])
        return f"""
        <tr>
            <td><b>{r['data']['ticker']}</b><br><small>{r['data']['name']}</small></td>
            <td>{r['data']['sector']}</td>
            <td><b>${r['data']['price']:.2f}</b></td>
            <td style="color:{'red' if r['data']['pct_from_high'] and r['data']['pct_from_high'] < -0.2 else 'black'}">{high_str}</td>
            <td style="color:green">{upside_str}</td>
            <td>{format_market_cap(r['data']['market_cap'])}</td>
            <td>{"⭐" * r['score']}</td>
            <td><small>{flags_str}</small></td>
        </tr>"""

    top_rows = "".join([stock_row(r) for r in top_picks]) if top_picks else "<tr><td colspan='8'>Δεν βρέθηκαν top picks αυτή την εβδομάδα</td></tr>"
    watch_rows = "".join([stock_row(r) for r in watchlist]) if watchlist else "<tr><td colspan='8'>—</td></tr>"

    html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto;">
    <div style="background:#0f0f11; color:white; padding:20px; border-radius:10px; margin-bottom:20px;">
        <h1 style="margin:0;">📊 Weekly Stock Screener</h1>
        <p style="margin:5px 0; color:#888;">Βασίλης · {date_str}</p>
    </div>

    <h2>🔥 Top Picks (Score ≥ 4)</h2>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%; font-size:13px;">
        <tr style="background:#f0f0f0;">
            <th>Μετοχή</th><th>Sector</th><th>Τιμή</th>
            <th>vs 52w High</th><th>Analyst Upside</th>
            <th>Market Cap</th><th>Score</th><th>Σήματα</th>
        </tr>
        {top_rows}
    </table>

    <h2 style="margin-top:30px;">👀 Watchlist (Score 2-3)</h2>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; width:100%; font-size:13px;">
        <tr style="background:#f0f0f0;">
            <th>Μετοχή</th><th>Sector</th><th>Τιμή</th>
            <th>vs 52w High</th><th>Analyst Upside</th>
            <th>Market Cap</th><th>Score</th><th>Σήματα</th>
        </tr>
        {watch_rows}
    </table>

    <div style="margin-top:30px; padding:15px; background:#f9f9f9; border-radius:8px; font-size:12px; color:#666;">
        <b>⚠️ Disclaimer:</b> Αυτό το report είναι για ενημερωτικούς σκοπούς μόνο.
        Δεν αποτελεί επενδυτική συμβουλή. Πάντα να κάνεις τη δική σου έρευνα.
    </div>
    </body></html>
    """
    return html


def send_email(html_content):
    """Στέλνει το report στο email"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Weekly Stock Screener — {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    print("✅ Email sent!")


def main():
    print(f"🔍 Scanning {len(ALL_TICKERS)} tickers...")
    results = []

    for ticker in ALL_TICKERS:
        print(f"  → {ticker}")
        data = get_stock_data(ticker)
        if data:
            score, flags = apply_filters(data)
            if score >= 2:  # Μόνο αν έχει τουλάχιστον 2 θετικά σήματα
                results.append({"data": data, "score": score, "flags": flags})

    print(f"✅ Found {len(results)} interesting stocks")
    html = build_html_report(results)
    send_email(html)


if __name__ == "__main__":
    main()
