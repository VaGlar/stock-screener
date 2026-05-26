"""
Dynamic Watchlist Builder — Yahoo Finance version
Χρησιμοποιεί yfinance αντί Finviz για να αποφύγει το blocking
"""

import yfinance as yf
import json
import time
from datetime import datetime

def get_sp500_tickers():
    """Κατεβάζει S&P 500 από αξιόπιστο CSV dataset"""
    import urllib.request
    import csv
    import io

    # Primary source: GitHub datasets
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        tickers = [row["Symbol"].replace(".", "-") for row in reader]
        print(f"  ✅ S&P 500: {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"  ⚠️ S&P 500 fetch failed: {e}")
        return []


def get_yahoo_screens():
    """Τραβάει dynamic screens από Yahoo Finance"""
    import yfinance as yf
    screens = [
        "undervalued_growth_stocks",
        "growth_technology_stocks", 
        "undervalued_large_caps",
        "aggressive_small_caps",
        "day_gainers",
        "most_actives",
    ]
    all_tickers = []
    for screen in screens:
        try:
            df = yf.screen(screen)
            if df and "quotes" in df:
                tickers = [q["symbol"] for q in df["quotes"] if "symbol" in q]
                all_tickers.extend(tickers)
                print(f"  ✅ {screen}: {len(tickers)} tickers")
            time.sleep(1)
        except Exception as e:
            print(f"  ⚠️ {screen}: {e}")
    return all_tickers
    
def get_basic_info(ticker):
    """Τραβάει βασικά στοιχεία για scoring"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        week52_high = info.get("fiftyTwoWeekHigh")
        target_price = info.get("targetMeanPrice")
        revenue_growth = info.get("revenueGrowth")
        recommendation = info.get("recommendationKey", "")
        pe = info.get("trailingPE")

        if not current_price or not week52_high:
            return None

        pct_from_high = (current_price - week52_high) / week52_high
        analyst_upside = ((target_price - current_price) / current_price) if target_price else 0

        # Quick scoring για prioritization
        score = 0
        if pct_from_high <= -0.25: score += 2      # Έχει πέσει >25%
        if analyst_upside >= 0.20: score += 2       # Analyst upside >20%
        if recommendation in ["strongBuy", "buy"]: score += 1
        if revenue_growth and revenue_growth >= 0.15: score += 1
        if pe and 0 < pe <= 25: score += 1

        return {
            "symbol": ticker,
            "score": score,
            "pct_from_high": pct_from_high,
            "analyst_upside": analyst_upside,
            "recommendation": recommendation,
        }
    except:
        return None


def build_watchlist():
    print(f"\n🔍 Building watchlist — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    all_results = {}

    # Μάζεψε tickers από όλες τις πηγές
    print("\n📡 Fetching S&P 500 list...")
    sp500 = get_sp500_tickers()

    print("\n📡 Fetching Yahoo Finance screens...")
    yahoo = get_yahoo_screens()

    # Merge — Yahoo screens πρώτα (πιο relevant), μετά S&P 500
    all_tickers_ordered = list(dict.fromkeys(yahoo + sp500))
    print(f"\n📊 Total unique tickers: {len(all_tickers_ordered)}")

    for ticker in all_tickers_ordered:
        result = get_basic_info(ticker)
        if result and result["score"] >= 2:
            if ticker not in all_results:
                all_results[ticker] = result
                all_results[ticker]["screens"] = ["dynamic"]
            else:
                all_results[ticker]["screens"].append("dynamic")
                all_results[ticker]["priority"] = len(all_results[ticker]["screens"])
        time.sleep(0.3)

        print(f"  ✅ {len(all_results)} interesting tickers")

    # Ταξινόμηση — πρώτα αυτά με υψηλό score και πολλά sectors
    sorted_results = sorted(
        all_results.values(),
        key=lambda x: (x.get("priority", 1), x["score"]),
        reverse=True
    )

    # Πρόσθεσε priority field
    for r in sorted_results:
        r["priority"] = len(r.get("screens", []))

    watchlist = {
        "generated_at": datetime.now().isoformat(),
        "total_tickers": len(sorted_results),
        "tickers": sorted_results
    }

    with open("watchlist.json", "w") as f:
        json.dump(watchlist, f, indent=2)

    print(f"\n✅ Watchlist: {len(sorted_results)} tickers")
    print(f"🏆 Multi-sector hits: {sum(1 for r in sorted_results if r['priority'] >= 2)}")

    # Preview top 10
    print("\nTop 10:")
    for r in sorted_results[:10]:
        print(f"  {r['symbol']:8} score={r['score']} upside={r['analyst_upside']:.0%} sectors={r['screens']}")

    return watchlist


if __name__ == "__main__":
    build_watchlist()
