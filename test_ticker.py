"""
Test Ticker — γρήγορος έλεγχος score_stock() για μία μετοχή, χωρίς να τρέξει
όλο το πρόγραμμα (build_watchlist / email).

Usage: python test_ticker.py MSFT
"""

import sys
from screener import load_config, get_sector_config, get_stock_data, score_stock, passes_minimums, get_action

PILLAR_MAX = {
    "moat": 30, "growth": 30, "valuation": 20, "eva": 20,
    "technicals": 15, "sam": 15, "catalyst": 20,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_ticker.py TICKER")
        return
    ticker = sys.argv[1].upper()

    config = load_config()
    print(f"🔍 Fetching {ticker}...")
    data = get_stock_data(ticker)
    if not data:
        print(f"❌ {ticker}: δεν βρέθηκαν δεδομένα (yfinance)")
        return

    sector_cfg, sector_key = get_sector_config(data, config)
    thresholds = sector_cfg.get("thresholds", {"pass": 65, "watch": 80, "buy": 100})
    scores, flags, total = score_stock(data, sector_cfg)
    passes, failed_pillar = passes_minimums(scores, thresholds, total)
    action, _, _ = get_action(total, thresholds)

    print(f"\n{ticker} @ ${data['price']:.2f} — sector: {sector_key} ({data['industry']})")
    for pillar, max_p in PILLAR_MAX.items():
        print(f"\n{pillar.upper()} {scores[pillar]}/{max_p}")
        for f in flags[pillar]:
            print(f"  {f}")

    print(f"\nTOTAL: {total}/150 → {action}")
    print(f"Gate: {'✅ PASSES' if passes else f'❌ FAILS — {failed_pillar} below minimum'}")


if __name__ == "__main__":
    main()
