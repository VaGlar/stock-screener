"""
Dynamic Watchlist Builder — v4
Sources:
1. Wikipedia index constituents (S&P500, FTSE100, DAX, CAC40, Nikkei, κλπ)
2. Yahoo Finance screens — always included
3. S&P 500 από GitHub dataset — fallback
"""

import yfinance as yf
import json
import time
import re
import csv
import io
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
MAX_TICKERS = 2000

# ── Wikipedia Index Sources ───────────────────────────────────────

WIKIPEDIA_INDICES = {
    "FTSE 100 🇬🇧": {
        "url": "https://en.wikipedia.org/wiki/FTSE_100",
        "ticker_col": 0,
        "suffix": ".L",
    },
    "DAX 🇩🇪": {
        "url": "https://en.wikipedia.org/wiki/DAX",
        "ticker_col": 1,
        "suffix": ".DE",
    },
    "CAC 40 🇫🇷": {
        "url": "https://en.wikipedia.org/wiki/CAC_40",
        "ticker_col": 3,
        "suffix": ".PA",
    },
    "Eurostoxx 50 🇪🇺": {
        "url": "https://en.wikipedia.org/wiki/Euro_Stoxx_50",
        "ticker_col": 2,
        "suffix": "",
    },
    "ASX 200 🇦🇺": {
        "url": "https://en.wikipedia.org/wiki/S%26P/ASX_200",
        "ticker_col": 0,
        "suffix": ".AX",
    },
    "Hang Seng 🇭🇰": {
        "url": "https://en.wikipedia.org/wiki/Hang_Seng_Index",
        "ticker_col": 1,
        "suffix": ".HK",
    },
    "Nikkei 225 🇯🇵": {
        "url": "https://en.wikipedia.org/wiki/Nikkei_225",
        "ticker_col": 1,
        "suffix": ".T",
    },
    "BSE Sensex 🇮🇳": {
        "url": "https://en.wikipedia.org/wiki/BSE_SENSEX",
        "ticker_col": 1,
        "suffix": ".BO",
    },
}


def parse_wikipedia_table(html, ticker_col=0, suffix=""):
    """Parse HTML table από Wikipedia και επιστρέφει tickers"""
    tickers = []
    
    # Find all table rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    
    for row in rows:
        # Extract cells
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
        if len(cells) > ticker_col:
            cell = cells[ticker_col]
            # Clean HTML tags
            clean = re.sub(r'<[^>]+>', '', cell).strip()
            # Remove citations like [1]
            clean = re.sub(r'\[\d+\]', '', clean).strip()
            # Take first word if multiple
            clean = clean.split()[0] if clean.split() else ""
            
            # Validate ticker format
            if clean and re.match(r'^[A-Z]{1,6}$', clean):
                ticker = clean + suffix
                tickers.append(ticker)
    
    return list(dict.fromkeys(tickers))  # deduplicate


def get_wikipedia_tickers():
    """Κατεβάζει tickers από Wikipedia indices"""
    print("\n📡 Source 1: Wikipedia Index Constituents...")
    
    all_tickers = []
    success_count = 0
    results = {}
    
    for index_name, config in WIKIPEDIA_INDICES.items():
        try:
            req = urllib.request.Request(config["url"], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8")
            
            tickers = parse_wikipedia_table(
                html, 
                config["ticker_col"], 
                config["suffix"]
            )
            
            if len(tickers) >= 10:
                all_tickers.extend(tickers)
                success_count += 1
                results[index_name] = len(tickers)
                print(f"  ✅ {index_name}: {len(tickers)} tickers")
            else:
                print(f"  ⚠️ {index_name}: μόνο {len(tickers)} tickers — skip")
            
            time.sleep(1)  # Respectful delay
            
        except Exception as e:
            print(f"  ❌ {index_name}: {e}")
    
    all_tickers = list(dict.fromkeys(all_tickers))
    
    if success_count >= 3:
        print(f"  ✅ SUCCESS — {len(all_tickers)} unique tickers από {success_count} indices")
        return all_tickers, True
    else:
        print(f"  ❌ FAILED — Μόνο {success_count} indices πέτυχαν")
        return all_tickers, success_count > 0


# ── S&P 500 GitHub fallback ───────────────────────────────────────

def get_sp500_tickers():
    """Κατεβάζει S&P 500 από GitHub dataset"""
    print("\n📡 Source 2: S&P 500 από GitHub...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        tickers = [row["Symbol"].replace(".", "-") for row in reader]
        print(f"  ✅ SUCCESS — {len(tickers)} tickers")
        return tickers, True
    except Exception as e:
        print(f"  ❌ FAILED — {e}")
        return [], False


# ── Yahoo Finance Screens ─────────────────────────────────────────

def get_yahoo_screens():
    """Τραβάει dynamic screens από Yahoo Finance"""
    print("\n📡 Source 3: Yahoo Finance screens...")
    screens = [
        "undervalued_growth_stocks",
        "growth_technology_stocks",
        "undervalued_large_caps",
        "aggressive_small_caps",
        "day_gainers",
        "most_actives",
    ]
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


# ── Quick scoring ─────────────────────────────────────────────────

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


# ── Main ──────────────────────────────────────────────────────────

def build_watchlist():
    print(f"\n🔍 Building watchlist — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    wiki_tickers, wiki_ok = get_wikipedia_tickers()
    sp500_tickers, sp500_ok = get_sp500_tickers()
    yahoo_tickers, yahoo_ok = get_yahoo_screens()

    print("\n" + "=" * 60)
    print("📊 SOURCE STATUS REPORT:")
    print(f"  {'✅' if wiki_ok else '❌'} Wikipedia Indices: {'OK' if wiki_ok else 'FAILED'} ({len(wiki_tickers)} tickers)")
    print(f"  {'✅' if sp500_ok else '❌'} S&P 500 GitHub:    {'OK' if sp500_ok else 'FAILED'} ({len(sp500_tickers)} tickers)")
    print(f"  {'✅' if yahoo_ok else '❌'} Yahoo Screens:     {'OK' if yahoo_ok else 'FAILED'} ({len(yahoo_tickers)} tickers)")
    print("=" * 60)

    if not wiki_ok and not sp500_ok and not yahoo_ok:
        print("\n❌ CRITICAL: Όλες οι πηγές απέτυχαν! Abort.")
        return None

    # Yahoo πρώτα (momentum), μετά Wikipedia, μετά S&P fallback
    all_ordered = list(dict.fromkeys(yahoo_tickers + wiki_tickers + sp500_tickers))
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
            if ticker in wiki_tickers:
                all_results[ticker]["screens"].append("wikipedia")
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
            "wikipedia": {"ok": wiki_ok, "count": len(wiki_tickers)},
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
        print(f"  {r['symbol']:10} score={r['score']} upside={r['analyst_upside']:.0%} sources={r['screens']}")

    return watchlist


if __name__ == "__main__":
    build_watchlist()
