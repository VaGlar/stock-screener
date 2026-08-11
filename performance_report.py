"""
Performance Report — v1
Διαβάζει το recommendations_log.csv (πραγματικές προτάσεις που στάλθηκαν με email)
και υπολογίζει την πραγματική απόδοση κάθε πρότασης μέχρι σήμερα, βάσει τρέχουσας τιμής.
"""

import csv
import os
from datetime import datetime
import yfinance as yf

LOG_FILE = "recommendations_log.csv"
REPORT_FILE = "performance_report.csv"


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


def render_html_summary(report_rows):
    """Συμπαγές HTML section για ενσωμάτωση στο κάτω μέρος του weekly report."""
    valid = [r for r in report_rows if r.get("return_pct") is not None]
    if not valid:
        return ""

    avg_ret = sum(r["return_pct"] for r in valid) / len(valid)
    hit_rate = sum(1 for r in valid if r["return_pct"] > 0) / len(valid)
    avg_color = "#16a34a" if avg_ret >= 0 else "#dc2626"

    by_action = {}
    for r in valid:
        by_action.setdefault(r["action"], []).append(r)

    rows_html = ""
    for action in ["STRONG BUY", "BUY", "WATCH", "PASS"]:
        sub = by_action.get(action)
        if not sub:
            continue
        avg = sum(r["return_pct"] for r in sub) / len(sub)
        hr = sum(1 for r in sub if r["return_pct"] > 0) / len(sub)
        color = "#16a34a" if avg >= 0 else "#dc2626"
        rows_html += f"""<tr>
            <td style="padding:6px 8px">{action}</td>
            <td style="padding:6px 8px">{len(sub)}</td>
            <td style="padding:6px 8px;color:{color}">{avg:+.1%}</td>
            <td style="padding:6px 8px">{hr:.0%}</td>
        </tr>"""

    return f"""
    <div style="margin-top:28px">
        <h2 style="font-size:16px;font-weight:600;margin-bottom:12px">📈 Πραγματική απόδοση προτάσεων ({len(valid)} tracked)</h2>
        <div style="background:white;border:0.5px solid #e5e7eb;border-radius:12px;padding:16px;margin-bottom:12px;">
            <div style="font-size:13px;color:#6b7280">Μέση απόδοση: <strong style="color:{avg_color}">{avg_ret:+.1%}</strong> · Hit rate: <strong>{hit_rate:.0%}</strong></div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <tr style="background:#f3f4f6;font-size:11px;color:#6b7280">
                <th style="padding:6px 8px;text-align:left">Action</th>
                <th style="padding:6px 8px;text-align:left">n</th>
                <th style="padding:6px 8px;text-align:left">Μέση απόδοση</th>
                <th style="padding:6px 8px;text-align:left">Hit rate</th>
            </tr>
            {rows_html}
        </table>
    </div>"""


def summarize(rows):
    valid = [r for r in rows if r["return_pct"] is not None]
    if not valid:
        print("⚠️ Δεν υπάρχουν έγκυρες αποδόσεις για υπολογισμό.")
        return

    avg_ret = sum(r["return_pct"] for r in valid) / len(valid)
    hit_rate = sum(1 for r in valid if r["return_pct"] > 0) / len(valid)
    print(f"\n📊 Συνολική απόδοση ({len(valid)} προτάσεις με valid data):")
    print(f"  Μέση απόδοση: {avg_ret:+.1%}   Hit rate: {hit_rate:.1%}")

    print("\n📊 Ανά action label:")
    for action in sorted({r["action"] for r in valid}):
        sub = [r for r in valid if r["action"] == action]
        avg = sum(r["return_pct"] for r in sub) / len(sub)
        hr = sum(1 for r in sub if r["return_pct"] > 0) / len(sub)
        print(f"  {action:12s} n={len(sub):3d}  avg={avg:+.1%}  hit_rate={hr:.1%}")

    print("\n📊 Ανά holding period:")
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
        print("❌ recommendations_log.csv δεν βρέθηκε ή είναι άδειο — δεν υπάρχει ακόμα ιστορικό προτάσεων.")
        return

    tickers = sorted({r["ticker"] for r in rows})
    print(f"🔍 Υπολογισμός απόδοσης για {len(rows)} προτάσεις, {len(tickers)} unique tickers...")
    current_prices = get_current_prices(tickers)

    report_rows = compute_report_rows(rows, current_prices)

    with open(REPORT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"✅ {len(report_rows)} γραμμές saved σε {REPORT_FILE}")

    summarize(report_rows)


if __name__ == "__main__":
    main()
