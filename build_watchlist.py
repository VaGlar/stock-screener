"""
Dynamic Watchlist Builder — Yahoo Finance version
Χρησιμοποιεί yfinance αντί Finviz για να αποφύγει το blocking
"""

import yfinance as yf
import json
import time
from datetime import datetime

# ── Predefined sector lists ───────────────────────────────────────
# Καλύπτουν διαφορετικά profiles: value, growth, small cap, momentum
SECTOR_LISTS = {
    "sp500_value": [
        "AAPL","MSFT","GOOGL","AMZN","META","NVDA","BRK-B","JPM","JNJ","V",
        "PG","UNH","HD","MA","XOM","CVX","MRK","ABBV","PFE","KO",
        "PEP","TMO","COST","AVGO","MCD","ACN","LIN","DHR","ABT","TXN"
    ],
    "growth_tech": [
        "DDOG","SNOW","CRWD","NET","ZS","MDB","GTLB","BILL","HUBS","TEAM",
        "OKTA","ESTC","CFLT","DXCM","DOCU","FROG","TTD","CELH","ABNB","UBER",
        "DASH","RBLX","U","PINS","SNAP","LYFT","HOOD","COIN","AFRM","SOFI"
    ],
    "semiconductors": [
        "NVDA","AMD","INTC","QCOM","AVGO","MU","AMAT","LRCX","KLAC","MRVL",
        "ON","SWKS","MCHP","ADI","TXN","WOLF","SITM","CRUS","AMBA","SMTC"
    ],
    "small_cap_growth": [
        "IONQ","ARRY","JOBY","ACHR","LUNR","RDW","ASTS","SPCE","RKLB","PL",
        "LILM","EVTL","NKLA","BLDE","SKYW","DMRC","MAPS","GFAI","KTOS","AVAV"
    ],
    "healthcare_biotech": [
        "LLY","NVO","MRNA","BNTX","REGN","VRTX","BIIB","GILD","AMGN","BMY",
        "INCY","ALNY","SGEN","RARE","ACAD","EXAS","NTRA","PACB","VCYT","RXRX"
    ],
    "energy_commodities": [
        "XOM","CVX","COP","SLB","HAL","BKR","MPC","VLO","PSX","OXY",
        "DVN","EOG","PXD","FANG","APA","RIG","NOV","HP","NE","TDW"
    ],
    "european_us_listed": [
        "ASML","SAP","NVO","SHOP","SE","GRAB","BABA","JD","PDD","BIDU",
        "NIO","LI","XPEV","TSM","UMC","SMCI","LTHM","MP","CAMT","AEHR"
    ]
}

MAX_PER_SECTOR = 20


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

    for sector, tickers in SECTOR_LISTS.items():
        print(f"\n📂 {sector} ({len(tickers)} tickers)...")
        sector_count = 0

        for ticker in tickers[:MAX_PER_SECTOR]:
            result = get_basic_info(ticker)
            if result and result["score"] >= 2:
                if ticker not in all_results:
                    all_results[ticker] = result
                    all_results[ticker]["screens"] = [sector]
                else:
                    all_results[ticker]["screens"].append(sector)
                    all_results[ticker]["priority"] = len(all_results[ticker]["screens"])
                sector_count += 1
            time.sleep(0.3)  # Gentle delay

        print(f"  ✅ {sector_count} interesting tickers")

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
