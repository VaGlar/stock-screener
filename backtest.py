"""
Backtest / Validation — v1
Checks whether the 7-pillar total score predicts forward returns, by running score_stock()
over historical price points instead of live data.

LIMITATION: yfinance does not provide point-in-time fundamentals (margins, growth, PE...).
The technicals (RSI, 200DMA, % from high) are correctly computed point-in-time from the price
history, but the fundamentals pillars (Moat/Growth/Valuation/EVA/SAM) use yfinance's
CURRENT snapshot for every date — so there is look-ahead bias there. The
backtest is more reliable for evaluating how well Technicals/Catalyst timing
predicts short-term forward returns, less reliable for the fundamentals pillars.
"""

import json
import time
import pandas as pd
import yfinance as yf

from screener import load_config, get_sector_config, score_stock, passes_minimums, get_action, sf

LOOKBACK_YEARS = "3y"
FORWARD_DAYS = [21, 63]      # ~1 month, ~3 months forward return horizons
SAMPLE_STEP_DAYS = 5         # sample every ~week (trading days) within the history
MAX_TICKERS = 100            # subset of the watchlist for speed on a first pass
MIN_HISTORY_DAYS = 260       # needs a buffer of >=252 days before sampling starts


def load_universe():
    with open("watchlist.json") as f:
        data = json.load(f)
    raw = data["tickers"]
    tickers = [t["symbol"] for t in raw] if raw and isinstance(raw[0], dict) else raw
    return tickers[:MAX_TICKERS]


def compute_technicals(closes, i):
    """Technicals pillar inputs computed point-in-time, looking only up to index i."""
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


def fundamentals_from_info(info, insider_net_pct=None):
    fcf = sf(info.get("freeCashflow"))
    mc = sf(info.get("marketCap"))
    return {
        "gross_margin": sf(info.get("grossMargins")),
        "operating_margin": sf(info.get("operatingMargins")),
        "recommendation": info.get("recommendationKey", "N/A"),
        "num_analysts": info.get("numberOfAnalystOpinions", 0) or 0,
        "revenue_growth": sf(info.get("revenueGrowth")),
        "earnings_growth": sf(info.get("earningsGrowth")),
        "rev_accelerating": None,  # not reproduced point-in-time here
        "pe": sf(info.get("trailingPE")),
        "ev_ebitda": sf(info.get("enterpriseToEbitda")),
        "ev_revenue": sf(info.get("enterpriseToRevenue")),
        "peg": sf(info.get("pegRatio")),
        "fcf_yield": (fcf / mc) if (fcf and mc and mc > 0) else None,
        "roic": None,  # not reproduced point-in-time here — falls to the fallback proxy
        "roic_wacc_spread": None,
        "roic_trend_improving": None,
        "market_cap": mc,
        "industry": info.get("industry", "N/A"),
        "sector": info.get("sector", "N/A"),
        "target_price": sf(info.get("targetMeanPrice")),
        "insider_net_pct": insider_net_pct,  # current-moment snapshot, same limitation as the other fundamentals
    }


def get_insider_net_pct(stock):
    try:
        insider_df = stock.insider_purchases
        if insider_df is None or insider_df.empty:
            return None
        label_col = insider_df.columns[0]
        for _, row in insider_df.iterrows():
            label = str(row[label_col])
            if "% Net Shares Purchased" in label:
                val = row.get("Shares") if "Shares" in insider_df.columns else row.iloc[-1]
                if isinstance(val, str):
                    val = val.strip().rstrip("%")
                pct = sf(val)
                if pct is not None and abs(pct) > 1:
                    pct /= 100
                return pct
    except Exception:
        return None
    return None


def run_backtest():
    config = load_config()
    tickers = load_universe()
    print(f"🔍 Backtest on {len(tickers)} tickers, history {LOOKBACK_YEARS}, horizons {FORWARD_DAYS}d")

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

            fundamentals = fundamentals_from_info(info, get_insider_net_pct(stock))
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
        print("❌ No backtest data was produced.")
        return

    df = pd.DataFrame(rows)
    df.to_csv("backtest_results.csv", index=False)
    print(f"\n✅ {len(df)} observations saved to backtest_results.csv")

    summarize(df)


def summarize(df):
    bins = [-1, 39, 64, 79, 99, 10_000]
    labels = ["<40 (excluded)", "40-64 (PASS)", "65-79 (WATCH)", "80-99 (BUY)", "100+ (STRONG BUY)"]
    df["score_bucket"] = pd.cut(df["total_score"], bins=bins, labels=labels)

    print("\n📊 Forward returns by score bucket:")
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

    print(f"\n📈 Gate stats: {df['passes_gate'].mean():.1%} pass the core-quality gate")


if __name__ == "__main__":
    run_backtest()
