"""
Dynamic Watchlist Builder — v5
Clean rebuild με pandas για Wikipedia parsing
Output: watchlist.json με μόνο λίστα symbols
"""

import json
import time
import re
import csv
import io
import urllib.request
from datetime import datetime

try:
    import pandas as pd
    PANDAS_OK = True
except ImportError:
    PANDAS_OK = False

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ── Source 1: S&P 500 από GitHub ──────────────────────────────────

def get_sp500():
    print("\n📡 S&P 500 από GitHub...")
    try:
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        tickers = [row["Symbol"].replace(".", "-") for row in reader]
        print(f"  ✅ {len(tickers)} tickers")
        return tickers
    except Exception as e:
        print(f"  ❌ {e}")
        return []


# ── Source 2: Wikipedia indices με pandas ─────────────────────────

WIKI_INDICES = {
    "FTSE 100 🇬🇧": {
        "url": "https://en.wikipedia.org/wiki/FTSE_100",
        "col": "Ticker",
        "suffix": ".L",
        "table_idx": 4,  # Ποιο table στη σελίδα (0-indexed)
    },
    "DAX 🇩🇪": {
        "url": "https://en.wikipedia.org/wiki/DAX",
        "col": "Ticker",
        "suffix": ".DE",
        "table_idx": 3,
    },
    "CAC 40 🇫🇷": {
        "url": "https://en.wikipedia.org/wiki/CAC_40",
        "col": "Ticker",
        "suffix": ".PA",
        "table_idx": 2,
    },
    "Eurostoxx 50 🇪🇺": {
        "url": "https://en.wikipedia.org/wiki/Euro_Stoxx_50",
        "col": "Ticker",
        "suffix": "",
        "table_idx": 3,
    },
    "ASX 200 🇦🇺": {
        "url": "https://en.wikipedia.org/wiki/S%26P/ASX_200",
        "col": "Code",
        "suffix": ".AX",
        "table_idx": 2,
    },
    "Hang Seng 🇭🇰": {
        "url": "https://en.wikipedia.org/wiki/Hang_Seng_Index",
        "col": "Ticker",
        "suffix": "",
        "table_idx": 2,
    },
    "Nikkei 225 🇯🇵": {
        "url": "https://en.wikipedia.org/wiki/Nikkei_225",
        "col": "Ticker symbol",
        "suffix": ".T",
        "table_idx": 2,
    },
    "BSE Sensex 🇮🇳": {
        "url": "https://en.wikipedia.org/wiki/BSE_SENSEX",
        "col": "Symbol",
        "suffix": ".BO",
        "table_idx": 1,
    },
}


def get_wikipedia_tickers():
    print("\n📡 Wikipedia indices...")
    if not PANDAS_OK:
        print("  ❌ pandas not available")
        return []

    all_tickers = []
    success_count = 0

    for name, cfg in WIKI_INDICES.items():
        try:
            # Κατέβασε HTML
            req = urllib.request.Request(cfg["url"], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8")

            # Parse όλα τα tables
            tables = pd.read_html(io.StringIO(html))

            tickers = []

            # Πρώτα δοκίμασε το συγκεκριμένο table_idx
            indices_to_try = [cfg["table_idx"]] + list(range(len(tables)))

            for idx in indices_to_try:
                if idx >= len(tables):
                    continue
                table = tables[idx]

                # Ψάξε τη στήλη με ticker
                col_found = None
                for col in table.columns:
                    col_str = str(col).strip()
                    if col_str == cfg["col"]:
                        col_found = col
                        break
                    # Fallback — ψάξε partial match
                    if any(k in col_str.lower() for k in ["ticker", "symbol", "code"]):
                        col_found = col

                if col_found is not None:
                    raw = table[col_found].dropna().astype(str).tolist()
                    # Καθαρό validation — μόνο αλφαβητικά, 2-6 chars
                    clean = []
                    for t in raw:
                        t = t.strip().split()[0]  # Πάρε πρώτη λέξη
                        t = re.sub(r'[^A-Z0-9]', '', t.upper())  # Κράτα μόνο alphanumeric
                        if re.match(r'^[A-Z]{2,6}$', t):  # Μόνο γράμματα, 2-6 chars
                            clean.append(t + cfg["suffix"])

                    if len(clean) >= 10:
                        tickers = clean
                        break

            if tickers:
                all_tickers.extend(tickers)
                success_count += 1
                print(f"  ✅ {name}: {len(tickers)} tickers")
            else:
                print(f"  ⚠️ {name}: δεν βρέθηκε στήλη ticker")

            time.sleep(1)

        except Exception as e:
            print(f"  ❌ {name}: {e}")

    all_tickers = list(dict.fromkeys(all_tickers))
    print(f"  → Σύνολο non-US: {len(all_tickers)} tickers από {success_count} indices")
    return all_tickers


# ── Source 3: Yahoo Finance screens ──────────────────────────────

def get_yahoo_screens():
    print("\n📡 Yahoo Finance screens...")
    if not YF_OK:
        print("  ❌ yfinance not available")
        return []

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

    print(f"  → Σύνολο Yahoo: {len(all_tickers)} tickers")
    return all_tickers


# ── Main ──────────────────────────────────────────────────────────

def build_watchlist():
    print(f"\n🔍 Building watchlist — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    sp500 = get_sp500()
    wiki = get_wikipedia_tickers()
    yahoo = get_yahoo_screens()

    # Status report
    print("\n" + "=" * 60)
    print("📊 SOURCE STATUS:")
    print(f"  {'✅' if sp500 else '❌'} S&P 500:          {len(sp500)} tickers")
    print(f"  {'✅' if wiki else '❌'} Wikipedia non-US: {len(wiki)} tickers")
    print(f"  {'✅' if yahoo else '❌'} Yahoo screens:    {len(yahoo)} tickers")
    print("=" * 60)

    if not sp500 and not wiki and not yahoo:
        print("❌ CRITICAL: Όλες οι πηγές απέτυχαν!")
        return None

    # Merge — Yahoo πρώτα (momentum), S&P 500 δεύτερο, non-US τελευταίο
    all_tickers = list(dict.fromkeys(yahoo + sp500 + wiki))

    print(f"\n📋 Σύνολο unique tickers: {len(all_tickers)}")
    print(f"   US (S&P500 + Yahoo): ~{len(list(dict.fromkeys(yahoo + sp500)))}")
    print(f"   Non-US (Wikipedia): ~{len(wiki)}")

    # Αποθήκευση — μόνο symbols, τίποτα άλλο
    watchlist = {
        "generated_at": datetime.now().isoformat(),
        "total_tickers": len(all_tickers),
        "sources": {
            "sp500": len(sp500),
            "wikipedia": len(wiki),
            "yahoo": len(yahoo),
        },
        "tickers": all_tickers  # Απλή λίστα από strings
    }

    with open("watchlist.json", "w") as f:
        json.dump(watchlist, f, indent=2)

    print(f"\n✅ watchlist.json saved!")
    print(f"\nSample (first 10): {all_tickers[:10]}")
    print(f"Sample (last 10):  {all_tickers[-10:]}")

    return watchlist


if __name__ == "__main__":
    build_watchlist()
