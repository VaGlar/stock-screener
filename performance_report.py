"""
Performance Report — v1
Reads recommendations_log.csv (the actual recommendations sent by email)
and computes each recommendation's real performance to date, based on current price.
"""

import csv
import html
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import yfinance as yf

LOG_FILE = "recommendations_log.csv"
REPORT_FILE = "performance_report.csv"
SENDER_EMAIL = "vasilisglaros@gmail.com"
RECEIVER_EMAIL = "vasilisglaros@gmail.com"
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")


def load_log():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, newline="") as f:
        return list(csv.DictReader(f))


def get_current_prices(tickers):
    prices = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            prices[t] = info.get("currentPrice") or info.get("regularMarketPrice")
        except Exception as e:
            print(f"  ⚠️ {t}: {e}")
            prices[t] = None
    return prices


def bucket_days(days):
    if days < 30: return "<30d"
    if days < 90: return "30-90d"
    if days < 180: return "90-180d"
    return "180d+"


def compute_report_rows(rows, current_prices):
    today = datetime.now().date()
    report_rows = []
    for r in rows:
        entry_price = float(r["price"]) if r.get("price") else None
        cur_price = current_prices.get(r["ticker"])
        rec_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
        days_held = (today - rec_date).days
        ret = ((cur_price - entry_price) / entry_price) if (entry_price and cur_price) else None
        report_rows.append({
            **r,
            "current_price": cur_price,
            "days_held": days_held,
            "return_pct": ret,
        })
    return report_rows


def _breakdown_table(groups, order):
    """groups: {label: [rows]}, order: which order/which labels to show if present"""
    rows_html = ""
    for label in order:
        sub = groups.get(label)
        if not sub:
            continue
        avg = sum(r["return_pct"] for r in sub) / len(sub)
        hr = sum(1 for r in sub if r["return_pct"] > 0) / len(sub)
        color = "#16a34a" if avg >= 0 else "#dc2626"
        rows_html += f"""<tr>
            <td style="padding:6px 8px">{html.escape(str(label))}</td>
            <td style="padding:6px 8px">{len(sub)}</td>
            <td style="padding:6px 8px;color:{color}">{avg:+.1%}</td>
            <td style="padding:6px 8px">{hr:.0%}</td>
        </tr>"""
    return f"""<table style="width:100%;border-collapse:collapse;font-size:13px;">
            <tr style="background:#f3f4f6;font-size:11px;color:#6b7280">
                <th style="padding:6px 8px;text-align:left"></th>
                <th style="padding:6px 8px;text-align:left">#</th>
                <th style="padding:6px 8px;text-align:left">Avg return</th>
                <th style="padding:6px 8px;text-align:left">Hit rate</th>
            </tr>
            {rows_html}
        </table>"""


def _stock_row_multi(ticker, rows):
    """rows: all entries for this ticker, sorted most recent first.
    Shows days_held/return per entry on the same line (e.g. 7d/14d, +22.4%/+30.5%)
    instead of picking just one and discarding the rest."""
    action = rows[0]["action"]
    days_str = "/".join(f"{r['days_held']}d" for r in rows)
    ret_str = "/".join(
        f'<span style="color:{"#16a34a" if r["return_pct"] >= 0 else "#dc2626"}">{r["return_pct"]:+.1%}</span>'
        for r in rows
    )
    return f"""<tr>
        <td style="padding:6px 8px;font-weight:500">{html.escape(str(ticker))}</td>
        <td style="padding:6px 8px;font-size:11px;color:#6b7280">{html.escape(str(action))}</td>
        <td style="padding:6px 8px;font-size:11px;color:#6b7280">{days_str}</td>
        <td style="padding:6px 8px;font-weight:600">{ret_str}</td>
    </tr>"""


def render_html_summary(report_rows, top_n=5):
    """Compact HTML section for embedding at the bottom of the weekly report (or, with
    a larger top_n, the full monthly performance report).
    # = number of entries (ledger rows) in the group, not unique tickers — a stock
    recommended multiple times counts once per recommendation."""
    valid = [r for r in report_rows if r.get("return_pct") is not None]
    if not valid:
        return ""

    avg_ret = sum(r["return_pct"] for r in valid) / len(valid)
    hit_rate = sum(1 for r in valid if r["return_pct"] > 0) / len(valid)
    avg_color = "#16a34a" if avg_ret >= 0 else "#dc2626"

    by_action = {}
    for r in valid:
        by_action.setdefault(r["action"], []).append(r)
    action_table = _breakdown_table(by_action, ["STRONG BUY", "BUY", "WATCH", "PASS"])

    by_period = {}
    for r in valid:
        by_period.setdefault(bucket_days(r["days_held"]), []).append(r)
    period_table = _breakdown_table(by_period, ["<30d", "30-90d", "90-180d", "180d+"])

    by_sector = {}
    for r in valid:
        by_sector.setdefault(r.get("sector") or "N/A", []).append(r)
    sector_order = sorted(by_sector, key=lambda s: len(by_sector[s]), reverse=True)  # most common sector first
    sector_table = _breakdown_table(by_sector, sector_order)

    # Winners/laggards from STRONG BUY/BUY only — what you'd actually buy, not WATCH/PASS
    actionable = [r for r in valid if r["action"] in ("STRONG BUY", "BUY")]
    # One row per ticker, with ALL of its entries (most recent first) — we don't drop
    # any recommendation, we just show them together on the same line instead of duplicating the ticker
    by_ticker = {}
    for r in actionable:
        by_ticker.setdefault(r["ticker"], []).append(r)
    for t in by_ticker:
        by_ticker[t].sort(key=lambda r: r["days_held"])  # most recent (fewest days) first

    ticker_items = list(by_ticker.items())
    winner_tickers = sorted(ticker_items, key=lambda kv: max(r["return_pct"] for r in kv[1]), reverse=True)[:top_n]
    loser_tickers = sorted(ticker_items, key=lambda kv: min(r["return_pct"] for r in kv[1]))[:top_n]
    highlights = "" if not actionable else f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px;">
            <div>
                <div style="font-size:12px;color:#16a34a;font-weight:600;margin-bottom:6px">🏆 Top {top_n} winners</div>
                <table style="width:100%;border-collapse:collapse;font-size:12px;">{''.join(_stock_row_multi(t, rows) for t, rows in winner_tickers)}</table>
            </div>
            <div>
                <div style="font-size:12px;color:#dc2626;font-weight:600;margin-bottom:6px">📉 Top {top_n} laggards</div>
                <table style="width:100%;border-collapse:collapse;font-size:12px;">{''.join(_stock_row_multi(t, rows) for t, rows in loser_tickers)}</table>
            </div>
        </div>"""

    return f"""
    <div style="margin-top:28px">
        <h2 style="font-size:16px;font-weight:600;margin-bottom:12px">📈 Real recommendation performance ({len(valid)} tracked)</h2>
        <div style="background:white;border:0.5px solid #e5e7eb;border-radius:12px;padding:16px;margin-bottom:12px;">
            <div style="font-size:13px;color:#6b7280;margin-bottom:14px">Avg return: <strong style="color:{avg_color}">{avg_ret:+.1%}</strong> · Hit rate: <strong>{hit_rate:.0%}</strong></div>
            <div style="font-size:11px;color:#9ca3af;margin-bottom:4px">By action label</div>
            {action_table}
            <div style="font-size:11px;color:#9ca3af;margin:14px 0 4px">By holding period</div>
            {period_table}
            <div style="font-size:11px;color:#9ca3af;margin:14px 0 4px">By sector</div>
            {sector_table}
            {highlights}
        </div>
    </div>"""


def build_html_report(report_rows):
    valid = [r for r in report_rows if r.get("return_pct") is not None]
    date_str = datetime.now().strftime("%d/%m/%Y")
    summary = render_html_summary(report_rows, top_n=20)
    if not summary:
        summary = '<p style="color:#6b7280;font-size:13px;">Not enough data yet to calculate performance.</p>'

    return f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:24px;background:#f9fafb;">
    <div style="background:#0f0f11;color:white;padding:24px;border-radius:12px;margin-bottom:24px;">
        <div style="font-size:22px;font-weight:600">📈 Monthly Performance Report</div>
        <div style="font-size:13px;color:#9ca3af;margin-top:4px">
            {date_str} · {len(valid)} recommendations tracked
        </div>
    </div>
    {summary}
    </body></html>"""


def send_email(html):
    if not EMAIL_PASSWORD:
        raise RuntimeError("GMAIL_APP_PASSWORD is not set — cannot send email. Set it as an env var / GitHub Actions secret.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 Performance Report — {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    print("✅ Email sent!")


def summarize(rows):
    valid = [r for r in rows if r["return_pct"] is not None]
    if not valid:
        print("⚠️ No valid returns to compute.")
        return

    avg_ret = sum(r["return_pct"] for r in valid) / len(valid)
    hit_rate = sum(1 for r in valid if r["return_pct"] > 0) / len(valid)
    print(f"\n📊 Overall performance ({len(valid)} recommendations with valid data):")
    print(f"  Avg return: {avg_ret:+.1%}   Hit rate: {hit_rate:.1%}")

    print("\n📊 By action label:")
    for action in sorted({r["action"] for r in valid}):
        sub = [r for r in valid if r["action"] == action]
        avg = sum(r["return_pct"] for r in sub) / len(sub)
        hr = sum(1 for r in sub if r["return_pct"] > 0) / len(sub)
        print(f"  {action:12s} n={len(sub):3d}  avg={avg:+.1%}  hit_rate={hr:.1%}")

    print("\n📊 By holding period:")
    buckets = {}
    for r in valid:
        b = bucket_days(r["days_held"])
        buckets.setdefault(b, []).append(r)
    for b in ["<30d", "30-90d", "90-180d", "180d+"]:
        sub = buckets.get(b, [])
        if not sub:
            continue
        avg = sum(r["return_pct"] for r in sub) / len(sub)
        hr = sum(1 for r in sub if r["return_pct"] > 0) / len(sub)
        print(f"  {b:10s} n={len(sub):3d}  avg={avg:+.1%}  hit_rate={hr:.1%}")


def main():
    rows = load_log()
    if not rows:
        print("❌ recommendations_log.csv not found or empty — no recommendation history yet.")
        return

    tickers = sorted({r["ticker"] for r in rows})
    print(f"🔍 Computing performance for {len(rows)} recommendations, {len(tickers)} unique tickers...")
    current_prices = get_current_prices(tickers)

    report_rows = compute_report_rows(rows, current_prices)

    with open(REPORT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"✅ {len(report_rows)} rows saved to {REPORT_FILE}")

    summarize(report_rows)

    html = build_html_report(report_rows)
    send_email(html)


if __name__ == "__main__":
    main()
