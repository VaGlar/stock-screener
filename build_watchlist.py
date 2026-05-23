"""
Dynamic Watchlist Builder
Τραβάει μετοχές από Finviz με διάφορα φίλτρα
και φτιάχνει το watchlist.json για το screener.py
"""

import requests
import json
import time
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ── Finviz URLs ───────────────────────────────────────────────────
# Κάθε URL είναι ένα διαφορετικό φίλτρο στο Finviz
FINVIZ_SCREENS = {

    "value_opportunities": (
        "https://finviz.com/screener.ashx?v=111&f="
        "fa_pe_u30,"           # P/E κάτω από 30
        "fa_epsqoq_pos,"       # EPS growth θετικό
        "fa_salesqoq_o10,"     # Revenue growth > 10%
        "ta_perf_52w_dn30"     # -30% ή περισσότερο από 52w high
        "&ft=4&o=-marketcap"
    ),

    "growth_momentum": (
        "https://finviz.com/screener.ashx?v=111&f="
        "fa_salesqoq_o20,"     # Revenue growth > 20%
        "fa_epsqoq_pos,"       # Θετικό EPS growth
        "ta_perf_4w_up,"       # Ανοδικό momentum τελευταίες 4 εβδομάδες
        "sh_avgvol_o200"       # Average volume > 200k (liquidity)
        "&ft=4&o=-marketcap"
    ),

    "insider_buying": (
        "https://finviz.com/screener.ashx?v=111&f="
        "it_latestbuys,"       # Πρόσφατο insider buying
        "fa_debt_u1,"          # Debt/Equity < 1
        "sh_avgvol_o100"       # Volume > 100k
        "&ft=4&o=-marketcap"
    ),

    "near_52w_low_with_upside": (
        "https://finviz.com/screener.ashx?v=111&f="
        "ta_highlow52w_b20h,"  # Κοντά στο 52w low (within 20%)
        "an_recom_buybetter,"  # Analyst recommendation: Buy ή καλύτερο
        "fa_salesqoq_pos,"     # Θετικό revenue growth
        "sh_avgvol_o200"       # Liquidity
        "&ft=4&o=an_recom"
    ),

    "small_cap_growth": (
        "https://finviz.com/screener.ashx?v=111&f="
        "cap_small,"           # Small cap ($300M - $2B)
        "fa_salesqoq_o15,"     # Revenue growth > 15%
        "fa_epsqoq_pos,"       # Θετικό EPS
        "sh_avgvol_o100"       # Volume > 100k
        "&ft=4&o=-marketcap"
    ),
}

MAX_PER_SCREEN = 20  # Πόσες μετοχές από κάθε φίλτρο


def parse_finviz_table(html):
    """Parse το HTML table του Finviz και επιστρέφει λίστα tickers"""
    tickers = []
    try:
        # Ψάχνει για ticker symbols στο HTML
        import re
        # Finviz tickers εμφανίζονται ως: quote.ashx?t=TICKER
        matches = re.findall(r'quote\.ashx\?t=([A-Z]+)"', html)
        tickers = list(dict.fromkeys(matches))  # deduplicate διατηρώντας σειρά
    except Exception as e:
        print(f"  Parse error: {e}")
    return tickers


def fetch_finviz_screen(name, url, max_results=20):
    """Τραβάει μετοχές από ένα Finviz screen"""
    print(f"  Fetching: {name}...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠️ Status {resp.status_code} for {name}")
            return []

        tickers = parse_finviz_table(resp.text)[:max_results]
        print(f"  ✅ Found {len(tickers)} tickers")
        time.sleep(2)  # Respectful delay
        return tickers

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return []


def build_watchlist():
    """Χτίζει το δυναμικό watchlist από όλα τα screens"""
    print(f"\n🔍 Building dynamic watchlist — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    all_tickers = {}

    for screen_name, url in FINVIZ_SCREENS.items():
        tickers = fetch_finviz_screen(screen_name, url, MAX_PER_SCREEN)
        for ticker in tickers:
            if ticker not in all_tickers:
                all_tickers[ticker] = []
            all_tickers[ticker].append(screen_name)

    # Tickers που εμφανίζονται σε πολλά screens → υψηλότερη προτεραιότητα
    sorted_tickers = sorted(
        all_tickers.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )

    watchlist = {
        "generated_at": datetime.now().isoformat(),
        "total_tickers": len(all_tickers),
        "tickers": [
            {
                "symbol": ticker,
                "screens": screens,
                "priority": len(screens)  # Πόσα φίλτρα το εντόπισαν
            }
            for ticker, screens in sorted_tickers
        ]
    }

    # Αποθήκευση
    with open("watchlist.json", "w") as f:
        json.dump(watchlist, f, indent=2)

    print(f"\n✅ Watchlist built: {len(all_tickers)} unique tickers")
    print(f"🏆 High priority (2+ screens): {sum(1 for _, s in sorted_tickers if len(s) >= 2)}")

    # Preview top 10
    print("\nTop 10 tickers:")
    for ticker, screens in sorted_tickers[:10]:
        print(f"  {ticker:8} — {', '.join(screens)}")

    return watchlist


if __name__ == "__main__":
    build_watchlist()
