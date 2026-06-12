"""
Dynamic Watchlist Builder — v3
Sources:
1. justETF VWCE holdings (~3.700 μετοχές) — primary
2. S&P 500 από GitHub dataset — secondary  
3. Yahoo Finance screens — always included
"""

import yfinance as yf
import json
import time
import re
import csv
import io
import urllib.request
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_TICKERS = 500


def get_vwce_tickers():
    print("\n📡 Source 1: IWDA holdings από iShares (VWCE proxy)...")
    
    # iShares MSCI World UCITS ETF — 1.600 μετοχές, developed markets
    # Direct CSV download URL
    urls = [
        "https://www.ishares.com/uk/individual/en/products/251882/ISHARES_MSCI_WORLD_ETF/1478372549651.ajax?tab=holdings&fileType=csv",
        "https://www.ishares.com/us/products/239726/ISHARES_CORE_MSCI_WORLD_ETF/1467271812596.ajax?tab=holdings&fileType=csv",
    ]
    
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read().decode("utf-8")
            
            # Parse CSV — iShares format έχει header rows
            lines = content.split("\n")
            tickers = []
            for line in lines:
                cols = line.split(",")
                if len(cols) >= 3:
                    ticker = cols[0].strip().strip('"')
                    # Φιλτράρισε valid US tickers
                    if re.match(r'^[A-Z]{1,5}$', ticker):
                        tickers.append(ticker)
            
            tickers = list(dict.fromkeys(tickers))
            if len(tickers) > 100:
                print(f"  ✅ SUCCESS — {len(tickers)} tickers από iShares IWDA")
                return tickers, True
                
        except Exception as e:
            print(f"  ⚠️ URL failed: {e}")
            continue
    
    print("  ❌ FAILED — iShares δεν ήταν προσβάσιμο")
    return [], False


def get_sp500_tickers():
    print("\n📡 Source 2: S&P 500 από GitHub...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        tickers = [row["Symbol"].replace(".", "-") for row in reader]
        print(f"  ✅ SUCCESS — {len(tickers)} tickers από S&P 500")
        return tickers, True
    except Exception as e:
        print(f"  ❌ FAILED — {e}")
        return [], False


def get_yahoo_screens():
    print("\n📡 Source 3: Yahoo Finance screens...")
    screens = ["undervalued_growth_stocks", "growth_technology_stocks",
               "undervalued_large_caps", "aggressive_small_caps",
               "day_gainers", "most_actives"]
    all_tickers = []
    success_count = 0
    for screen in screens:
        try:
            df = yf.screen(screen)
            if df and "quotes" in df:
                tickers = [q["symbol"] for q in df["quotes"] if "symbol" in q]
                all_tickers.extend(tickers)
                success_count += 1
                print(f"  ✅ {screen}: {len(tickers)} tickers")
            time.sleep(1)
        except Exception as e:
            print(f"  ⚠️ {screen}: {e}")
    if success_count > 0:
        print(f"  ✅ SUCCESS — {len(all_tickers)} tickers από {success_count} screens")
        return all_tickers, True
    print("  ❌ FAILED — Κανένα Yahoo screen δεν δούλεψε")
    return [], False


def get_basic_info(ticker):
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
        score = 0
        if pct_from_high <= -0.25: score += 2
        if analyst_upside >= 0.20: score += 2
        if recommendation in ["strongBuy", "buy"]: score += 1
        if revenue_growth and revenue_growth >= 0.15: score += 1
        if pe and 0 < pe <= 25: score += 1
        return {
            "symbol": ticker, "score": score,
            "pct_from_high": pct_from_high,
            "analyst_upside": analyst_upside,
            "recommendation": recommendation,
            "screens": [], "priority": 1
        }
    except:
        return None


def build_watchlist():
    print(f"\n🔍 Building watchlist — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    vwce_tickers, vwce_ok = get_vwce_tickers()
    sp500_tickers, sp500_ok = get_sp500_tickers()
    yahoo_tickers, yahoo_ok = get_yahoo_screens()

    print("\n" + "=" * 60)
    print("📊 SOURCE STATUS REPORT:")
    print(f"  {'✅' if vwce_ok else '❌'} justETF VWCE:   {'OK' if vwce_ok else 'FAILED'} ({len(vwce_tickers)} tickers)")
    print(f"  {'✅' if sp500_ok else '❌'} S&P 500 GitHub: {'OK' if sp500_ok else 'FAILED'} ({len(sp500_tickers)} tickers)")
    print(f"  {'✅' if yahoo_ok else '❌'} Yahoo Screens:  {'OK' if yahoo_ok else 'FAILED'} ({len(yahoo_tickers)} tickers)")
    print("=" * 60)

    if not vwce_ok and not sp500_ok and not yahoo_ok:
        print("\n❌ CRITICAL: Όλες οι πηγές απέτυχαν! Abort.")
        return None

    all_ordered = list(dict.fromkeys(yahoo_tickers + vwce_tickers + sp500_tickers))
    all_ordered = all_ordered[:MAX_TICKERS]
    print(f"\n📋 Σύνολο unique tickers για ανάλυση: {len(all_ordered)}")

    print(f"\n⚡ Quick scoring...")
    all_results = {}
    for i, ticker in enumerate(all_ordered, 1):
        if i % 50 == 0:
            print(f"  [{i}/{len(all_ordered)}]...")
        result = get_basic_info(ticker)
        if result and result["score"] >= 2:
            if ticker not in all_results:
                all_results[ticker] = result
            else:
                all_results[ticker]["priority"] += 1
            if ticker in yahoo_tickers:
                all_results[ticker]["screens"].append("yahoo")
            if ticker in vwce_tickers:
                all_results[ticker]["screens"].append("vwce")
            if ticker in sp500_tickers:
                all_results[ticker]["screens"].append("sp500")
        time.sleep(0.3)

    sorted_results = sorted(
        all_results.values(),
        key=lambda x: (x["priority"], x["score"]),
        reverse=True
    )

    watchlist = {
        "generated_at": datetime.now().isoformat(),
        "total_tickers": len(sorted_results),
        "sources": {
            "vwce": {"ok": vwce_ok, "count": len(vwce_tickers)},
            "sp500": {"ok": sp500_ok, "count": len(sp500_tickers)},
            "yahoo": {"ok": yahoo_ok, "count": len(yahoo_tickers)}
        },
        "tickers": sorted_results
    }

    with open("watchlist.json", "w") as f:
        json.dump(watchlist, f, indent=2)

    print(f"\n✅ Watchlist saved: {len(sorted_results)} interesting tickers")
    print(f"🏆 Multi-source: {sum(1 for r in sorted_results if r['priority'] >= 2)}")
    print("\nTop 10:")
    for r in sorted_results[:10]:
        print(f"  {r['symbol']:8} score={r['score']} upside={r['analyst_upside']:.0%} sources={r['screens']}")

    return watchlist


if __name__ == "__main__":
    build_watchlist()
