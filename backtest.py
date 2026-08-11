"""
Backtest / Validation — v1
Ελέγχει αν το 7-pillar total score προβλέπει forward returns, τρέχοντας το score_stock()
πάνω σε ιστορικά σημεία τιμής αντί για live δεδομένα.

ΠΕΡΙΟΡΙΣΜΟΣ: το yfinance δεν δίνει point-in-time fundamentals (margins, growth, PE...).
Τα technicals (RSI, 200DMA, % από high) υπολογίζονται σωστά point-in-time από το ιστορικό
των τιμών, αλλά τα fundamentals pillars (Moat/Growth/Valuation/EVA/SAM) χρησιμοποιούν το
ΤΡΕΧΟΝ snapshot του yfinance για κάθε ημερομηνία — άρα υπάρχει look-ahead bias εκεί. Το
backtest είναι πιο αξιόπιστο για να αξιολογήσει το πόσο καλά το Technicals/Catalyst timing
προβλέπει βραχυπρόθεσμα forward returns, λιγότερο αξιόπιστο για τα fundamentals pillars.
"""

import json
import time
import pandas as pd
import yfinance as yf

from screener import load_config, get_sector_config, score_stock, passes_minimums, get_action, sf

LOOKBACK_YEARS = "3y"
FORWARD_DAYS = [21, 63]      # ~1 μήνας, ~3 μήνες forward return horizons
SAMPLE_STEP_DAYS = 5         # δειγματοληψία κάθε ~εβδομάδα (trading days) μέσα στο ιστορικό
MAX_TICKERS = 100            # subset του watchlist για ταχύτητα σε πρώτο πέρασμα
MIN_HISTORY_DAYS = 260       # χρειάζεται buffer >=252 μέρες πριν ξεκινήσει η δειγματοληψία


def load_universe():
    with open("watchlist.json") as f:
        data = json.load(f)
    raw = data["tickers"]
    tickers = [t["symbol"] for t in raw] if raw and isinstance(raw[0], dict) else raw
    return tickers[:MAX_TICKERS]


def compute_technicals(closes, i):
    """Technicals pillar inputs υπολογισμένα point-in-time, βλέποντας μόνο μέχρι το index i."""
    window = closes.iloc[: i + 1]
    if len(window) < 30:
        return None
    dma200 = float(window.rolling(200).mean().iloc[-1]) if len(window) >= 200 else float(window.mean())
    delta = window.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = (100 - (100 / (1 + rs))).iloc[-1]
    high_52w = float(window.iloc[-252:].max()) if len(window) >= 252 else float(window.max())
    price = float(window.iloc[-1])
    return {
        "price": price,
        "dma200": dma200,
        "rsi": float(rsi_val) if pd.notna(rsi_val) else 50.0,
        "pct_from_high": (price - high_52w) / high_52w,
        "pct_vs_200dma": (price - dma200) / dma200,
    }


def fundamentals_from_info(info):
    fcf = sf(info.get("freeCashflow"))
    mc = sf(info.get("marketCap"))
    return {
        "gross_margin": sf(info.get("grossMargins")),
        "operating_margin": sf(info.get("operatingMargins")),
        "recommendation": info.get("recommendationKey", "N/A"),
        "num_analysts": info.get("numberOfAnalystOpinions", 0) or 0,
        "revenue_growth": sf(info.get("revenueGrowth")),
        "earnings_growth": sf(info.get("earningsGrowth")),
        "rev_accelerating": None,  # δεν αναπαράγεται point-in-time εδώ
        "pe": sf(info.get("trailingPE")),
        "ev_ebitda": sf(info.get("enterpriseToEbitda")),
        "ev_revenue": sf(info.get("enterpriseToRevenue")),
        "peg": sf(info.get("pegRatio")),
        "fcf_yield": (fcf / mc) if (fcf and mc and mc > 0) else None,
        "roic": None,  # δεν αναπαράγεται point-in-time εδώ — πέφτει στο fallback proxy
        "roic_wacc_spread": None,
        "roic_trend_improving": None,
        "market_cap": mc,
        "industry": info.get("industry", "N/A"),
        "sector": info.get("sector", "N/A"),
        "target_price": sf(info.get("targetMeanPrice")),
    }


def run_backtest():
    config = load_config()
    tickers = load_universe()
    print(f"🔍 Backtest σε {len(tickers)} tickers, ιστορικό {LOOKBACK_YEARS}, horizons {FORWARD_DAYS}d")

    rows = []
    for ti, ticker in enumerate(tickers, 1):
        print(f"  [{ti}/{len(tickers)}] {ticker}")
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period=LOOKBACK_YEARS)
            if hist.empty or len(hist) < MIN_HISTORY_DAYS:
                continue
            closes = hist["Close"]

            fundamentals = fundamentals_from_info(info)
            sector_cfg, sector_key = get_sector_config(fundamentals, config)
            thresholds = sector_cfg.get("thresholds", {"pass": 65, "watch": 80, "buy": 100})

            max_forward = max(FORWARD_DAYS)
            n = len(closes)
            sample_points = range(252, n - max_forward, SAMPLE_STEP_DAYS)

            for i in sample_points:
                tech = compute_technicals(closes, i)
                if not tech:
                    continue
                data = {**fundamentals, **tech, "ticker": ticker, "name": info.get("shortName", ticker)}
                scores, flags, total = score_stock(data, sector_cfg)
                passes, failed_pillar = passes_minimums(scores, thresholds, total)
                action = get_action(total, thresholds)[0]

                price_now = closes.iloc[i]
                row = {
                    "ticker": ticker,
                    "date": closes.index[i].date().isoformat(),
                    "sector_key": sector_key,
                    "total_score": total,
                    "action": action,
                    "passes_gate": passes,
                    "failed_pillar": failed_pillar,
                }
                for pillar, val in scores.items():
                    row[f"score_{pillar}"] = val
                for d in FORWARD_DAYS:
                    price_fwd = closes.iloc[i + d]
                    row[f"fwd_ret_{d}d"] = float((price_fwd - price_now) / price_now)
                rows.append(row)

            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ {ticker}: {e}")
            continue

    if not rows:
        print("❌ Δεν παράχθηκαν δεδομένα backtest.")
        return

    df = pd.DataFrame(rows)
    df.to_csv("backtest_results.csv", index=False)
    print(f"\n✅ {len(df)} observations saved σε backtest_results.csv")

    summarize(df)


def summarize(df):
    bins = [-1, 39, 64, 79, 99, 10_000]
    labels = ["<40 (excluded)", "40-64 (PASS)", "65-79 (WATCH)", "80-99 (BUY)", "100+ (STRONG BUY)"]
    df["score_bucket"] = pd.cut(df["total_score"], bins=bins, labels=labels)

    print("\n📊 Forward returns ανά score bucket:")
    for d in FORWARD_DAYS:
        col = f"fwd_ret_{d}d"
        g = df.groupby("score_bucket", observed=True)[col]
        summary = pd.DataFrame({
            "n": g.count(),
            "mean_return": g.mean(),
            "median_return": g.median(),
            "hit_rate": g.apply(lambda x: (x > 0).mean()),
        })
        print(f"\n--- {d}-day forward return ---")
        print(summary.to_string(formatters={
            "mean_return": "{:.2%}".format,
            "median_return": "{:.2%}".format,
            "hit_rate": "{:.1%}".format,
        }))

    print(f"\n📈 Gate stats: {df['passes_gate'].mean():.1%} περνάνε το core-quality gate")


if __name__ == "__main__":
    run_backtest()
