"""
Weekly Stock Screener
Διαβάζει το watchlist.json από το build_watchlist.py
και στέλνει report στο email
"""

import yfinance as yf
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from datetime import datetime

SENDER_EMAIL = "vasilisglaros@gmail.com"
RECEIVER_EMAIL = "vasilisglaros@gmail.com"
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

FILTERS = {
    "max_pe": 30,
    "min_revenue_growth": 0.10,
    "max_debt_equity": 2.0,
    "min_from_52w_high": -0.30,
    "min_analyst_upside": 0.15,
}

MAX_TICKERS = 500


def load_watchlist():
    try:
        with open("watchlist.json", "r") as f:
            data = json.load(f)
        tickers = [t["symbol"] for t in data["tickers"][:MAX_TICKERS]]
        print(f"📋 Loaded {len(tickers)} tickers (generated: {data['generated_at'][:10]})")
        return tickers, data
    except FileNotFoundError:
        print("❌ watchlist.json not found! Run build_watchlist.py first.")
        return [], {}


def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        week52_high = info.get("fiftyTwoWeekHigh")
        week52_low = info.get("fiftyTwoWeekLow")
        target_price = info.get("targetMeanPrice")
        pe_ratio = info.get("trailingPE")
        revenue_growth = info.get("revenueGrowth")
        debt_equity = info.get("debtToEquity")
        market_cap = info.get("marketCap")
        name = info.get("shortName", ticker)
        sector = info.get("sector", "N/A")
        recommendation = info.get("recommendationKey", "N/A")
        num_analysts = info.get("numberOfAnalystOpinions", 0)

        if not current_price or not week52_high:
            return None

        pct_from_high = (current_price - week52_high) / week52_high
        pct_from_low = (current_price - week52_low) / week52_low if week52_low else None
        analyst_upside = ((target_price - current_price) / current_price) if target_price else None

        return {
            "ticker": ticker, "name": name, "sector": sector,
            "price": current_price, "52w_high": week52_high, "52w_low": week52_low,
            "pct_from_high": pct_from_high, "pct_from_low": pct_from_low,
            "pe": pe_ratio, "revenue_growth": revenue_growth,
            "debt_equity": debt_equity / 100 if debt_equity else None,
            "market_cap": market_cap, "target_price": target_price,
            "analyst_upside": analyst_upside, "recommendation": recommendation,
            "num_analysts": num_analysts,
        }
    except Exception as e:
        print(f"  ⚠️ Error {ticker}: {e}")
        return None


def apply_filters(data, priority=1):
    score = 0
    flags = []

    if priority >= 2:
        score += 1
        flags.append(f"🔥 {priority} Finviz screens")

    if data["pct_from_high"] and data["pct_from_high"] <= FILTERS["min_from_52w_high"]:
        score += 2
        flags.append(f"📉 -{abs(data['pct_from_high']):.0%} από 52w high")

    if data["analyst_upside"] and data["analyst_upside"] >= FILTERS["min_analyst_upside"]:
        score += 2
        flags.append(f"🎯 Upside: +{data['analyst_upside']:.0%}")

    if data["pe"] and 0 < data["pe"] <= FILTERS["max_pe"]:
        score += 1
        flags.append(f"💰 P/E: {data['pe']:.1f}x")

    if data["revenue_growth"] and data["revenue_growth"] >= FILTERS["min_revenue_growth"]:
        score += 2
        flags.append(f"📈 Rev growth: +{data['revenue_growth']:.0%}")

    if data["debt_equity"] and data["debt_equity"] <= FILTERS["max_debt_equity"]:
        score += 1
        flags.append(f"✅ D/E: {data['debt_equity']:.1f}x")

    if data["recommendation"] in ["strongBuy", "buy"]:
        score += 1
        flags.append(f"⭐ {data['recommendation'].upper()}")

    if data["num_analysts"] and data["num_analysts"] >= 10:
        score += 1
        flags.append(f"👥 {data['num_analysts']} analysts")

    return score, flags


def format_market_cap(mc):
    if not mc: return "N/A"
    if mc >= 1e12: return f"${mc/1e12:.1f}T"
    if mc >= 1e9: return f"${mc/1e9:.1f}B"
    return f"${mc/1e6:.0f}M"


def build_html_report(results, watchlist_meta):
    date_str = datetime.now().strftime("%d/%m/%Y")
    generated = watchlist_meta.get("generated_at", "")[:10]
    total_scanned = watchlist_meta.get("total_tickers", "N/A")

    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)
    top_picks = [r for r in results_sorted if r["score"] >= 5]
    watchlist_items = [r for r in results_sorted if 3 <= r["score"] < 5]

    def stock_row(r, highlight=False):
        bg = "#fff9e6" if highlight else "white"
        upside_str = f"+{r['data']['analyst_upside']:.0%}" if r['data']['analyst_upside'] else "N/A"
        high_str = f"{r['data']['pct_from_high']:.0%}" if r['data']['pct_from_high'] else "N/A"
        high_color = "red" if r['data']['pct_from_high'] and r['data']['pct_from_high'] < -0.2 else "#333"
        flags_str = "<br>".join(r["flags"])
        screens_str = ", ".join(r.get("screens", []))
        return f"""<tr style="background:{bg}">
            <td><b>{r['data']['ticker']}</b><br><small style="color:#666">{r['data']['name']}</small></td>
            <td><small>{r['data']['sector']}</small></td>
            <td><b>${r['data']['price']:.2f}</b></td>
            <td style="color:{high_color}">{high_str}</td>
            <td style="color:green"><b>{upside_str}</b></td>
            <td>{format_market_cap(r['data']['market_cap'])}</td>
            <td>{"⭐" * min(r['score'], 8)}</td>
            <td><small>{flags_str}</small></td>
            <td><small style="color:#888">{screens_str}</small></td>
        </tr>"""

    header = """<tr style="background:#1a1a2e; color:white;">
        <th>Μετοχή</th><th>Sector</th><th>Τιμή</th><th>vs 52w High</th>
        <th>Analyst Upside</th><th>Market Cap</th><th>Score</th><th>Σήματα</th><th>Finviz Screens</th>
    </tr>"""

    top_rows = "".join([stock_row(r, True) for r in top_picks]) or \
        "<tr><td colspan='9' style='color:#888;padding:12px'>Δεν βρέθηκαν top picks αυτή την εβδομάδα</td></tr>"
    watch_rows = "".join([stock_row(r) for r in watchlist_items]) or \
        "<tr><td colspan='9' style='color:#888;padding:12px'>—</td></tr>"

    return f"""<html><body style="font-family:Arial,sans-serif;max-width:1000px;margin:0 auto;padding:20px;">
    <div style="background:#0f0f11;color:white;padding:24px;border-radius:12px;margin-bottom:24px;">
        <h1 style="margin:0;font-size:24px;">📊 Weekly Stock Screener</h1>
        <p style="margin:8px 0 0;color:#aaa;">Βασίλης · {date_str} · Scanned <b style="color:white">{total_scanned}</b> μετοχές από Finviz (watchlist: {generated})</p>
    </div>
    <h2>🔥 Top Picks (Score ≥ 5)</h2>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px;">{header}{top_rows}</table>
    <h2 style="margin-top:32px;">👀 Watchlist (Score 3-4)</h2>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;font-size:13px;">{header}{watch_rows}</table>
    <div style="margin-top:32px;padding:16px;background:#f5f5f5;border-radius:8px;font-size:12px;color:#666;">
        <b>⚠️ Disclaimer:</b> Ενημερωτικός σκοπός μόνο. Δεν αποτελεί επενδυτική συμβουλή.
    </div></body></html>"""


def send_email(html_content):
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
    tickers, watchlist_meta = load_watchlist()
    if not tickers:
        return

    priority_map = {
        t["symbol"]: (t["priority"], t["screens"])
        for t in watchlist_meta.get("tickers", [])
    }

    print(f"\n🔍 Analyzing {len(tickers)} tickers...")
    results = []

    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {ticker}")
        data = get_stock_data(ticker)
        if data:
            priority, screens = priority_map.get(ticker, (1, []))
            score, flags = apply_filters(data, priority)
            if score >= 3:
                results.append({"data": data, "score": score, "flags": flags, "screens": screens})

    print(f"\n✅ {len(results)} interesting stocks found")
    html = build_html_report(results, watchlist_meta)
    send_email(html)


if __name__ == "__main__":
    main()
