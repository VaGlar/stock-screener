"""
Weekly Stock Screener — v3
7-Pillar scoring framework με sector-aware benchmarks
"""

import yfinance as yf
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import time
import numpy as np
from datetime import datetime

SENDER_EMAIL = "vasilisglaros@gmail.com"
RECEIVER_EMAIL = "vasilisglaros@gmail.com"
EMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
MAX_TICKERS = 2000
MAX_REPORT = 30


# ── Safe float helper ─────────────────────────────────────────────

def sf(val):
    """Safe float conversion — αποφεύγει TypeError από string values"""
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# ── Config ────────────────────────────────────────────────────────

def load_config():
    try:
        with open("sector_config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("⚠️ sector_config.json not found — using defaults")
        return {
            "industry_mapping": {
                "Software—Application": "saas_cloud",
                "Software—Infrastructure": "saas_cloud",
                "Semiconductors": "semiconductors",
                "Biotechnology": "healthcare_biotech",
                "Drug Manufacturers—General": "healthcare_biotech",
                "Oil & Gas E&P": "energy",
                "Oil & Gas Integrated": "energy",
                "Beverages—Non-Alcoholic": "consumer_beverages",
            },
            "sector_mapping": {
                "Technology": "saas_cloud",
                "Healthcare": "healthcare_biotech",
                "Energy": "energy",
                "Consumer Cyclical": "consumer_beverages",
                "Consumer Defensive": "consumer_beverages",
                "Communication Services": "mega_cap_tech",
            },
            "sectors": {}
        }


def get_sector_config(info, config):
    industry = info.get("industry", "")
    sector = info.get("sector", "")
    industry_map = config.get("industry_mapping", {})
    sector_map = config.get("sector_mapping", {})
    sectors = config.get("sectors", {})
    mapped = industry_map.get(industry) or sector_map.get(sector) or "default"
    return sectors.get(mapped, sectors.get("default", {})), mapped


# ── Data ──────────────────────────────────────────────────────────

def get_stock_data(ticker, retries=1, delay=3):
    for attempt in range(retries + 1):
      try:
        stock = yf.Ticker(ticker)
        info = stock.info

        current_price = sf(info.get("currentPrice") or info.get("regularMarketPrice"))
        if not current_price:
            return None

        # Αν λείπουν fundamentals → retry
        gm = sf(info.get("grossMargins"))
        om = sf(info.get("operatingMargins"))
        pe = sf(info.get("trailingPE"))
        if gm is None and om is None and pe is None and attempt < retries:
            print(f"  ⚠️ {ticker} missing fundamentals, retry {attempt+1}/{retries}...")
            time.sleep(delay)
            continue

        hist = stock.history(period="1y")
        if hist.empty:
            return None

        closes = hist["Close"]
        dma200 = float(closes.rolling(200).mean().iloc[-1]) if len(closes) >= 200 else float(closes.mean())

        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])

        # Revenue QoQ acceleration
        try:
            quarterly = stock.quarterly_financials
            if quarterly is not None and "Total Revenue" in quarterly.index:
                rev_q = quarterly.loc["Total Revenue"].dropna()
                if len(rev_q) >= 3:
                    q0, q1, q2 = rev_q.iloc[0], rev_q.iloc[1], rev_q.iloc[2]
                    qoq_recent = (q0 - q1) / abs(q1) if q1 != 0 else None
                    qoq_prev = (q1 - q2) / abs(q2) if q2 != 0 else None
                    rev_accelerating = (qoq_recent > qoq_prev) if (qoq_recent and qoq_prev) else None
                else:
                    rev_accelerating = None
            else:
                rev_accelerating = None
        except:
            rev_accelerating = None

        # ROIC
        try:
            q_income = stock.quarterly_financials
            q_balance = stock.quarterly_balance_sheet
            roic_values = []
            if q_income is not None and q_balance is not None:
                for i in range(min(4, q_income.shape[1])):
                    try:
                        ebit = q_income.iloc[:, i].get("EBIT") or q_income.iloc[:, i].get("Operating Income")
                        nopat = ebit * 0.79 if ebit else None
                        total_assets = q_balance.iloc[:, i].get("Total Assets")
                        current_liab = q_balance.iloc[:, i].get("Current Liabilities")
                        invested_capital = (total_assets - current_liab) if (total_assets and current_liab) else None
                        if nopat and invested_capital and invested_capital > 0:
                            roic_values.append(nopat / invested_capital)
                    except:
                        continue
            roic_current = roic_values[0] if roic_values else None
            roic_trend_improving = (roic_values[0] > roic_values[-1]) if len(roic_values) >= 2 else None
        except:
            roic_current = None
            roic_trend_improving = None

        fcf = sf(info.get("freeCashflow"))
        market_cap = sf(info.get("marketCap"))
        fcf_yield = (fcf / market_cap) if (fcf and market_cap and market_cap > 0) else None

        beta = sf(info.get("beta")) or 1.0
        wacc = 0.045 + beta * 0.055
        roic_wacc_spread = (roic_current - wacc) if roic_current else None

        week52_high = sf(info.get("fiftyTwoWeekHigh"))

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "price": current_price,
            "52w_high": week52_high,
            "52w_low": sf(info.get("fiftyTwoWeekLow")),
            "market_cap": market_cap,
            "target_price": sf(info.get("targetMeanPrice")),
            "num_analysts": info.get("numberOfAnalystOpinions", 0) or 0,
            "recommendation": info.get("recommendationKey", "N/A"),
            "pe": sf(info.get("trailingPE")),
            "forward_pe": sf(info.get("forwardPE")),
            "ev_ebitda": sf(info.get("enterpriseToEbitda")),
            "ev_revenue": sf(info.get("enterpriseToRevenue")),
            "peg": sf(info.get("pegRatio")),
            "fcf_yield": fcf_yield,
            "revenue_growth": sf(info.get("revenueGrowth")),
            "earnings_growth": sf(info.get("earningsGrowth")),
            "rev_accelerating": rev_accelerating,
            "roic": roic_current,
            "roic_trend_improving": roic_trend_improving,
            "roic_wacc_spread": roic_wacc_spread,
            "wacc": wacc,
            "gross_margin": sf(info.get("grossMargins")),
            "operating_margin": sf(info.get("operatingMargins")),
            "debt_equity": sf(info.get("debtToEquity")),
            "dma200": dma200,
            "rsi": rsi,
            "pct_from_high": (current_price - week52_high) / week52_high if week52_high else None,
            "pct_vs_200dma": (current_price - dma200) / dma200,
        }
      except Exception as e:
        if attempt < retries:
            print(f"  ⚠️ {ticker} error, retry {attempt+1}/{retries}: {e}")
            time.sleep(delay)
            continue
        print(f"  ⚠️ Error {ticker}: {e}")
        return None
    return None


# ── 7-Pillar Scoring ──────────────────────────────────────────────

def score_stock(data, sector_cfg):
    scores = {}
    flags = {}

    # 1. MOAT /30
    moat_cfg = sector_cfg.get("moat", {})
    s, f = 0, []
    gm = data.get("gross_margin")
    om = data.get("operating_margin")
    if gm and isinstance(gm, (int, float)):
        if gm >= moat_cfg.get("gross_margin_strong", 0.50): s += 15; f.append(f"✅ Gross margin {gm:.0%}")
        elif gm >= moat_cfg.get("gross_margin_ok", 0.35): s += 8; f.append(f"🟡 Gross margin {gm:.0%}")
        else: f.append(f"🔴 Gross margin {gm:.0%}")
    if om and isinstance(om, (int, float)):
        if om >= 0.20: s += 10; f.append(f"✅ Op margin {om:.0%}")
        elif om >= 0.10: s += 5; f.append(f"🟡 Op margin {om:.0%}")
        elif om > 0: s += 2; f.append(f"🔴 Op margin {om:.0%}")
    if gm is None and om is None:
        # Fallback proxy — max 20/30 (δεν φτάνει "εξαιρετικό")
        rec = data.get("recommendation", "")
        na = data.get("num_analysts") or 0
        if rec == "strongBuy" and na >= 10: s += 15; f.append("🟡 Margins N/A — strong consensus proxy")
        elif rec in ["strongBuy", "buy"] and na >= 5: s += 12; f.append("🟡 Margins N/A — buy consensus proxy")
        elif rec in ["strongBuy", "buy"]: s += 8; f.append("🟡 Margins N/A — buy proxy")
        else: s += 3; f.append("🟡 Margins N/A — neutral proxy")
    if data.get("recommendation") in ["strongBuy", "buy"]: s += 5; f.append("⭐ Strong Buy consensus")
    scores["moat"], flags["moat"] = min(s, 30), f

    # 2. GROWTH /30
    growth_cfg = sector_cfg.get("growth", {})
    s, f = 0, []
    rg = data.get("revenue_growth")
    eg = data.get("earnings_growth")
    if rg and isinstance(rg, (int, float)):
        if rg >= growth_cfg.get("revenue_growth_strong", 0.20): s += 15; f.append(f"🚀 Rev growth {rg:.0%}")
        elif rg >= growth_cfg.get("revenue_growth_ok", 0.10): s += 8; f.append(f"📈 Rev growth {rg:.0%}")
        elif rg >= growth_cfg.get("revenue_growth_weak", 0.05): s += 3; f.append(f"🟡 Rev growth {rg:.0%}")
        else: f.append(f"🔴 Rev growth {rg:.0%}")
    if eg and isinstance(eg, (int, float)) and eg > 0:
        if eg >= 0.25: s += 8; f.append(f"🚀 EPS growth {eg:.0%}")
        elif eg >= 0.10: s += 4; f.append(f"📈 EPS growth {eg:.0%}")
    if rg is None and eg is None:
        # Fallback proxy — max 20/30
        target = data.get("target_price")
        price = data.get("price")
        upside = ((target - price) / price) if (target and price) else 0
        if upside >= 0.30: s += 15; f.append("🟡 Growth N/A — high analyst upside proxy")
        elif upside >= 0.15: s += 10; f.append("🟡 Growth N/A — moderate upside proxy")
        else: s += 5; f.append("🟡 Growth N/A — low upside proxy")
    if data.get("rev_accelerating") is True: s += 7; f.append("⚡ Revenue accelerating QoQ")
    elif data.get("rev_accelerating") is False: f.append("⚠️ Revenue decelerating")
    scores["growth"], flags["growth"] = min(s, 30), f

    # 3. VALUATION /20
    val_cfg = sector_cfg.get("valuation", {})
    s, f = 0, []
    pe = data.get("pe")
    ev_eb = data.get("ev_ebitda")
    ev_rev = data.get("ev_revenue")
    peg = data.get("peg")
    fcf = data.get("fcf_yield")
    if pe and isinstance(pe, (int, float)) and pe > 0:
        if pe <= val_cfg.get("pe_cheap", 20): s += 7; f.append(f"💰 P/E {pe:.1f}x (cheap)")
        elif pe <= val_cfg.get("pe_fair", 30): s += 4; f.append(f"🟡 P/E {pe:.1f}x (fair)")
        else: f.append(f"🔴 P/E {pe:.1f}x")
    # Sectors που ορίζουν ev_revenue thresholds τιμολογούνται σε EV/Revenue (π.χ. SaaS) — αλλιώς EV/EBITDA
    uses_ev_revenue = "ev_revenue_cheap" in val_cfg
    if uses_ev_revenue:
        if ev_rev and isinstance(ev_rev, (int, float)) and ev_rev > 0:
            if ev_rev <= val_cfg.get("ev_revenue_cheap", 8): s += 6; f.append(f"💰 EV/Revenue {ev_rev:.1f}x")
            elif ev_rev <= val_cfg.get("ev_revenue_fair", 15): s += 3; f.append(f"🟡 EV/Revenue {ev_rev:.1f}x")
        ev_metric_missing = ev_rev is None
    else:
        if ev_eb and isinstance(ev_eb, (int, float)) and ev_eb > 0:
            if ev_eb <= val_cfg.get("ev_ebitda_cheap", 12): s += 6; f.append(f"💰 EV/EBITDA {ev_eb:.1f}x")
            elif ev_eb <= val_cfg.get("ev_ebitda_fair", 20): s += 3; f.append(f"🟡 EV/EBITDA {ev_eb:.1f}x")
        ev_metric_missing = ev_eb is None
    if peg and isinstance(peg, (int, float)) and 0 < peg <= 1.0: s += 4; f.append(f"💰 PEG {peg:.1f}")
    elif peg and isinstance(peg, (int, float)) and peg <= 2.0: s += 2; f.append(f"🟡 PEG {peg:.1f}")
    if fcf and isinstance(fcf, (int, float)):
        if fcf >= 0.05: s += 3; f.append(f"💰 FCF yield {fcf:.1%}")
        elif fcf >= 0.02: s += 1; f.append(f"🟡 FCF yield {fcf:.1%}")
    if pe is None and ev_metric_missing and peg is None and fcf is None:
        # Fallback proxy — max 13/20
        pct = data.get("pct_from_high") or 0
        if pct <= -0.40: s += 13; f.append("🟡 Valuation N/A — deep discount proxy")
        elif pct <= -0.20: s += 9; f.append("🟡 Valuation N/A — discount proxy")
        else: s += 5; f.append("🟡 Valuation N/A — neutral proxy")
    scores["valuation"], flags["valuation"] = min(s, 20), f

    # 4. EVA /20
    eva_cfg = sector_cfg.get("eva", {})
    s, f = 0, []
    roic = data.get("roic")
    spread = data.get("roic_wacc_spread")
    if roic and isinstance(roic, (int, float)):
        if roic >= eva_cfg.get("roic_strong", 0.20): s += 10; f.append(f"✅ ROIC {roic:.1%}")
        elif roic >= eva_cfg.get("roic_ok", 0.10): s += 5; f.append(f"🟡 ROIC {roic:.1%}")
        else: f.append(f"🔴 ROIC {roic:.1%}")
    if spread and isinstance(spread, (int, float)):
        if spread > 0.05: s += 7; f.append(f"✅ ROIC-WACC +{spread:.1%}")
        elif spread > 0: s += 3; f.append(f"🟡 ROIC-WACC +{spread:.1%}")
        else: f.append(f"🔴 ROIC < WACC")
    if roic is None:
        # Fallback proxy — max 13/20
        fcf_y = data.get("fcf_yield") or 0
        rec = data.get("recommendation", "")
        if fcf_y >= 0.05: s += 13; f.append("🟡 ROIC N/A — strong FCF proxy")
        elif fcf_y >= 0.02: s += 9; f.append("🟡 ROIC N/A — moderate FCF proxy")
        elif rec in ["strongBuy", "buy"]: s += 6; f.append("🟡 ROIC N/A — buy consensus proxy")
        else: s += 3; f.append("🟡 ROIC N/A — neutral proxy")
    if data.get("roic_trend_improving"): s += 3; f.append("📈 ROIC improving")
    scores["eva"], flags["eva"] = min(s, 20), f

    # 5. TECHNICALS /15
    tech_cfg = sector_cfg.get("technicals", {})
    s, f = 0, []
    pct_high = data.get("pct_from_high")
    if pct_high and isinstance(pct_high, (int, float)):
        if pct_high <= tech_cfg.get("from_52w_high_deep_value", -0.50): s += 6; f.append(f"📉 -{abs(pct_high):.0%} (deep value)")
        elif pct_high <= tech_cfg.get("from_52w_high_opportunity", -0.30): s += 4; f.append(f"📉 -{abs(pct_high):.0%} από high")
        elif pct_high >= -0.05: s += 1; f.append(f"📈 Κοντά στο high")
    pct_dma = data.get("pct_vs_200dma")
    if pct_dma is not None and isinstance(pct_dma, (int, float)):
        if -0.05 <= pct_dma <= 0.10: s += 4; f.append(f"✅ Κοντά στο 200DMA ({pct_dma:+.1%})")
        elif pct_dma < -0.05: s += 2; f.append(f"⚠️ Κάτω από 200DMA ({pct_dma:+.1%})")
        else: s += 1; f.append(f"📈 Πάνω από 200DMA ({pct_dma:+.1%})")
    rsi = data.get("rsi")
    if rsi and isinstance(rsi, (int, float)):
        if rsi <= 30: s += 5; f.append(f"🟢 RSI {rsi:.0f} (oversold)")
        elif rsi <= 45: s += 3; f.append(f"🟡 RSI {rsi:.0f}")
        elif rsi >= 70: f.append(f"🔴 RSI {rsi:.0f} (overbought)")
        else: s += 1; f.append(f"RSI {rsi:.0f}")
    scores["technicals"], flags["technicals"] = min(s, 15), f

    # 6. SAM /15
    s, f = 0, []
    mc = data.get("market_cap") or 0
    rg = data.get("revenue_growth") or 0
    if isinstance(mc, (int, float)):
        if mc < 2e9: s += 5; f.append("🌍 Small cap — μεγάλο TAM headroom")
        elif mc < 10e9: s += 3; f.append("🌍 Mid cap — TAM runway")
    industry = data.get("industry", "")
    if any(x in industry for x in ["Software", "Semiconductor", "Biotech", "Internet"]): s += 5; f.append("🌍 High-growth industry")
    elif any(x in industry for x in ["Healthcare", "Technology", "Energy"]): s += 3; f.append("🌍 Growth industry")
    if isinstance(rg, (int, float)):
        if rg >= 0.20: s += 5; f.append("🌍 Rev growth proxy SAM")
        elif rg >= 0.10: s += 3
    scores["sam"], flags["sam"] = min(s, 15), f

    # 7. CATALYST /15
    s, f = 0, []
    rsi = data.get("rsi") or 50
    pct_high = data.get("pct_from_high") or 0
    num_analysts = data.get("num_analysts") or 0
    target = data.get("target_price")
    price = data.get("price")
    upside = 0
    if target and price and isinstance(target, (int, float)) and isinstance(price, (int, float)):
        upside = (target - price) / price
    if isinstance(rsi, (int, float)):
        if rsi <= 35: s += 5; f.append("🎯 RSI oversold — reversal catalyst")
        elif rsi <= 45: s += 3; f.append("🎯 RSI neutral-low")
    if isinstance(upside, (int, float)):
        if upside >= 0.30: s += 5; f.append(f"🎯 Analyst upside {upside:.0%}")
        elif upside >= 0.15: s += 3; f.append(f"🎯 Analyst upside {upside:.0%}")
    if isinstance(num_analysts, (int, float)):
        if num_analysts >= 15: s += 3; f.append(f"🎯 {num_analysts} analysts covering")
        elif num_analysts >= 8: s += 2
    if isinstance(pct_high, (int, float)) and pct_high <= -0.40: s += 2; f.append("🎯 Deep value — mean reversion")
    scores["catalyst"], flags["catalyst"] = min(s, 15), f

    total = sum(scores.values())
    return scores, flags, total


# ── Minimums ──────────────────────────────────────────────────────

PILLAR_MINIMUMS_WATCH = {
    "moat": 8, "growth": 5, "valuation": 4,
    "eva": 3, "technicals": 3, "sam": 4, "catalyst": 3
}
PILLAR_MINIMUMS_BUY = {
    "moat": 12, "growth": 8, "valuation": 6,
    "eva": 5, "technicals": 4, "sam": 5, "catalyst": 4
}

def passes_minimums(scores, thresholds, total):
    if total >= thresholds.get("buy", 100):
        mins = PILLAR_MINIMUMS_BUY
    else:
        mins = PILLAR_MINIMUMS_WATCH
    for pillar, min_score in mins.items():
        if (scores.get(pillar) or 0) < min_score:
            return False, pillar
    return True, None


def get_action(score, thresholds):
    if score >= thresholds.get("buy", 100): return "STRONG BUY", "#14532d", "#dcfce7"
    if score >= thresholds.get("watch", 80): return "BUY", "#166534", "#f0fdf4"
    if score >= thresholds.get("pass", 65): return "WATCH", "#92400e", "#fef3c7"
    return "PASS", "#7f1d1d", "#fef2f2"


def format_market_cap(mc):
    if not mc or not isinstance(mc, (int, float)): return "N/A"
    if mc >= 1e12: return f"${mc/1e12:.1f}T"
    if mc >= 1e9: return f"${mc/1e9:.1f}B"
    return f"${mc/1e6:.0f}M"


# ── HTML Report ───────────────────────────────────────────────────

def build_html_report(results, watchlist_meta):
    date_str = datetime.now().strftime("%d/%m/%Y")
    total_scanned = watchlist_meta.get("total_tickers", "N/A")

    results_sorted = sorted(results, key=lambda x: x["total_score"], reverse=True)[:MAX_REPORT]
    top5 = results_sorted[:5]
    rest = results_sorted[5:]

    def pillar_bar(label, score, max_score):
        score = score or 0
        pct = int((score / max_score) * 100)
        color = "#16a34a" if pct >= 70 else "#ca8a04" if pct >= 40 else "#dc2626"
        return f"""<div style="margin-bottom:5px;">
            <div style="display:flex;justify-content:space-between;font-size:11px;color:#6b7280;margin-bottom:2px;">
                <span>{label}</span><span>{score}/{max_score}</span>
            </div>
            <div style="background:#f3f4f6;border-radius:3px;height:5px;">
                <div style="background:{color};width:{pct}%;height:5px;border-radius:3px;"></div>
            </div>
        </div>"""

    cards_html = ""
    for r in top5:
        d = r["data"]
        total = r["total_score"]
        thresholds = r.get("thresholds", {"buy": 100, "watch": 80, "pass": 65})
        label, lc, lb = get_action(total, thresholds)
        price = d.get('price') or 0
        target = d.get('target_price')
        upside = f"+{((target-price)/price):.0%}" if (target and price and isinstance(target, (int,float)) and isinstance(price, (int,float))) else "N/A"
        pct_high = d.get('pct_from_high') or 0
        rsi_val = d.get('rsi') or 0

        cards_html += f"""
        <div style="background:white;border:0.5px solid #e5e7eb;border-radius:12px;padding:18px;margin-bottom:14px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
                <div>
                    <span style="font-size:20px;font-weight:600">{d['ticker']}</span>
                    <span style="font-size:13px;color:#6b7280;margin-left:8px">{d['name']}</span>
                    <div style="font-size:11px;color:#9ca3af;margin-top:2px">{d['industry']} · {d['sector']}</div>
                </div>
                <div style="text-align:right">
                    <span style="background:{lb};color:{lc};font-size:11px;font-weight:600;padding:3px 10px;border-radius:6px">{label}</span>
                    <div style="font-size:22px;font-weight:700;margin-top:4px">{total}<span style="font-size:12px;color:#9ca3af;font-weight:400">/145</span></div>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-bottom:14px;">
                <div style="background:#f9fafb;border-radius:6px;padding:7px;text-align:center">
                    <div style="font-size:10px;color:#9ca3af">Price</div>
                    <div style="font-size:14px;font-weight:600">${price:.2f}</div>
                </div>
                <div style="background:#f9fafb;border-radius:6px;padding:7px;text-align:center">
                    <div style="font-size:10px;color:#9ca3af">vs 52w High</div>
                    <div style="font-size:14px;font-weight:600;color:#dc2626">{pct_high:.0%}</div>
                </div>
                <div style="background:#f9fafb;border-radius:6px;padding:7px;text-align:center">
                    <div style="font-size:10px;color:#9ca3af">Analyst Upside</div>
                    <div style="font-size:14px;font-weight:600;color:#16a34a">{upside}</div>
                </div>
                <div style="background:#f9fafb;border-radius:6px;padding:7px;text-align:center">
                    <div style="font-size:10px;color:#9ca3af">RSI</div>
                    <div style="font-size:14px;font-weight:600">{rsi_val:.0f}</div>
                </div>
                <div style="background:#f9fafb;border-radius:6px;padding:7px;text-align:center">
                    <div style="font-size:10px;color:#9ca3af">Mkt Cap</div>
                    <div style="font-size:14px;font-weight:600">{format_market_cap(d['market_cap'])}</div>
                </div>
            </div>
            <div style="margin-bottom:4px">
                {pillar_bar("Moat", r['scores'].get('moat'), 30)}
                {pillar_bar("Growth", r['scores'].get('growth'), 30)}
                {pillar_bar("Valuation", r['scores'].get('valuation'), 20)}
                {pillar_bar("EVA", r['scores'].get('eva'), 20)}
                {pillar_bar("Technicals", r['scores'].get('technicals'), 15)}
                {pillar_bar("SAM", r['scores'].get('sam'), 15)}
                {pillar_bar("Catalyst", r['scores'].get('catalyst'), 15)}
            </div>
        </div>"""

    rest_rows = ""
    for r in rest:
        d = r["data"]
        total = r["total_score"]
        thresholds = r.get("thresholds", {"buy": 100, "watch": 80, "pass": 65})
        label, lc, lb = get_action(total, thresholds)
        price = d.get('price') or 0
        target = d.get('target_price')
        upside = f"+{((target-price)/price):.0%}" if (target and price and isinstance(target, (int,float)) and isinstance(price, (int,float))) else "N/A"
        pct_high = d.get('pct_from_high') or 0
        rsi_val = d.get('rsi') or 0
        rest_rows += f"""<tr>
            <td style="padding:7px 8px;font-weight:500">{d['ticker']}<br>
                <small style="color:#9ca3af;font-weight:400">{d['industry'][:22]}</small></td>
            <td style="padding:7px 8px">${price:.2f}</td>
            <td style="padding:7px 8px;color:#dc2626">{pct_high:.0%}</td>
            <td style="padding:7px 8px;color:#16a34a">{upside}</td>
            <td style="padding:7px 8px">{rsi_val:.0f}</td>
            <td style="padding:7px 8px">{format_market_cap(d['market_cap'])}</td>
            <td style="padding:7px 8px;font-weight:600">{total}/145</td>
            <td style="padding:7px 8px">
                <span style="background:{lb};color:{lc};font-size:11px;padding:2px 8px;border-radius:5px">{label}</span>
            </td>
        </tr>"""

    rest_html = ""
    if rest:
        rest_html = f"""
        <div style="margin-top:28px">
            <h2 style="font-size:16px;font-weight:600;margin-bottom:12px">👀 Watchlist ({len(rest)} stocks)</h2>
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                <tr style="background:#f3f4f6;font-size:11px;color:#6b7280">
                    <th style="padding:7px 8px;text-align:left">Stock</th>
                    <th style="padding:7px 8px;text-align:left">Price</th>
                    <th style="padding:7px 8px;text-align:left">vs 52w</th>
                    <th style="padding:7px 8px;text-align:left">Upside</th>
                    <th style="padding:7px 8px;text-align:left">RSI</th>
                    <th style="padding:7px 8px;text-align:left">Mkt Cap</th>
                    <th style="padding:7px 8px;text-align:left">Score</th>
                    <th style="padding:7px 8px;text-align:left">Action</th>
                </tr>
                {rest_rows}
            </table>
        </div>"""

    return f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:24px;background:#f9fafb;">
    <div style="background:#0f0f11;color:white;padding:24px;border-radius:12px;margin-bottom:24px;">
        <div style="font-size:22px;font-weight:600">📊 Weekly Stock Screener</div>
        <div style="font-size:13px;color:#9ca3af;margin-top:4px">
            {date_str} · {total_scanned} stocks scanned · Top {MAX_REPORT}
        </div>
    </div>
    <div style="font-size:16px;font-weight:600;margin-bottom:14px">🔥 Top 5 of the week</div>
    {cards_html}
    {rest_html}
    <div style="margin-top:28px;padding:12px;background:#f3f4f6;border-radius:8px;font-size:11px;color:#9ca3af;">
        ⚠️ Ενημερωτικός σκοπός μόνο. Δεν αποτελεί επενδυτική συμβουλή.
    </div>
    </body></html>"""


# ── Email ─────────────────────────────────────────────────────────

def send_email(html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Weekly Screener — {datetime.now().strftime('%d/%m/%Y')}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
    print("✅ Email sent!")


# ── Main ──────────────────────────────────────────────────────────

def main():
    config = load_config()

    try:
        with open("watchlist.json", "r") as f:
            watchlist_data = json.load(f)
        # Νέο format: tickers είναι απλή λίστα strings
        raw = watchlist_data["tickers"]
        if raw and isinstance(raw[0], dict):
            tickers = [t["symbol"] for t in raw[:MAX_TICKERS]]
        else:
            tickers = raw[:MAX_TICKERS]
    except FileNotFoundError:
        print("❌ watchlist.json not found!")
        return

    print(f"\n🔍 Analyzing {len(tickers)} tickers...")
    results = []

    for i, ticker in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {ticker}")
        data = get_stock_data(ticker)
        if not data:
            continue
        sector_cfg, sector_key = get_sector_config(data, config)
        thresholds = sector_cfg.get("thresholds", {"pass": 65, "watch": 80, "buy": 100})
        scores, flags, total = score_stock(data, sector_cfg)
        passes, failed_pillar = passes_minimums(scores, thresholds, total)
        if total >= 40 and passes:
            results.append({
                "data": data,
                "scores": scores,
                "flags": flags,
                "total_score": total,
                "sector_key": sector_key,
                "thresholds": thresholds,
            })
        else:
            if not passes:
                print(f"  ❌ {ticker} cut — {failed_pillar} below minimum")
        time.sleep(0.5)

    print(f"\n✅ {len(results)} stocks passed filters")
    html = build_html_report(results, watchlist_data)
    send_email(html)


if __name__ == "__main__":
    main()
