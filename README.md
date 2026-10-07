Let's go through it in detail:

---

**Step 1 — build_watchlist.py (builds the universe, no scoring)**

Collects tickers from 3 sources, with no quality pre-filter — everything moves on to the screener:
- **S&P 500** (GitHub CSV)
- **Wikipedia indices**: FTSE 100 🇬🇧, DAX 🇩🇪, CAC 40 🇫🇷, Euro Stoxx 50 🇪🇺, BSE Sensex 🇮🇳, KOSPI 200 🇰🇷
- **Yahoo Finance screens**: undervalued_growth_stocks, growth_technology_stocks, undervalued_large_caps, aggressive_small_caps, day_gainers, most_actives

The result (up to `MAX_TICKERS` = 2000) is written to `watchlist.json` and passed on in full to screener.py. Along with the tickers, it also keeps a `names` mapping (ticker → company name) from the sources that provide one (S&P 500 CSV, Wikipedia tables) — screener.py uses it as a fallback when yfinance has no `shortName`/`longName` for the ticker (common for markets like Korea, where otherwise only the raw code would show up, e.g. `000660.KS` instead of "SK Hynix").

---

**Filter — screener.py (Total Score ≥ 40/150)**

After the 7-pillar scoring, if the total < 40 → it **does not appear** in the report.

---

**The 7 Pillars:**

**1. Moat /30**
- Gross margin vs sector threshold → 0-15 points
- Operating margin → 0-10 points
- Strong Buy consensus → +5

**2. Growth /30**
- Revenue growth YoY vs sector threshold → 0-15
- Earnings growth → 0-8
- Revenue accelerating QoQ → +7 if yes, 0 if no

**3. Valuation /20**
- P/E vs sector benchmarks → 0-7
- EV/EBITDA vs sector benchmarks → 0-6
- PEG ≤ 1 → +4, PEG ≤ 2 → +2
- FCF yield ≥ 5% → +3

**4. EVA /20**
- ROIC level vs sector threshold → 0-10
- ROIC-WACC spread → 0-7
- ROIC trend improving → +3

**5. Technicals /15** *(bidirectional — rewards either a dip-reversal or a momentum setup)*
- % from 52w high: deep value dip → 0-6, or near/at a new high (momentum) → +4
- vs 200DMA: close to the DMA → +4, steady uptrend above the DMA → +3, below the DMA → +1
- RSI ≤ 30 (oversold) → +5, RSI ≤ 45 → +3, RSI 45-70 (bullish momentum) → +3, RSI ≥ 70 (overbought) → 0

**6. SAM /15** *(quantitative proxy)*
- Market cap size → 0-5 (smaller = more headroom)
- Industry type → 0-5
- Revenue growth proxy → 0-5

**7. Catalyst /20** *(quantitative proxy)*
- RSI oversold → 0-5
- Analyst upside → 0-5
- Number of analysts → 0-3
- Deep value bonus → +2
- Insider buying (net % bought vs sold, last 6 months) → +5 if ≥2% net buying, +3 if positive

---

**Action labels based on sector thresholds:**
- **≥100** → STRONG BUY
- **80-99** → BUY
- **65-79** → WATCH
- **<65** → PASS

Thresholds are read per sector from `sector_config.json` (they can differ by sector), but right now every configured sector uses the same 65/80/100 — if you want different limits for a given sector, change them there.

---

**Pillar minimums (gate):** Only the core-quality pillars (Moat, Growth, EVA) need to clear a minimum for a stock to not be excluded. Valuation/Technicals/SAM/Catalyst affect the total score but no longer exclude on their own — so an expensive, momentum-quality stock (e.g. near a 52w high) isn't excluded just for not being "cheap" or not having dropped.

---

## Recommendations ledger & report extras

Every time screener.py sends an email, it logs what was actually recommended (ticker, date, price, score, action) to `recommendations_log.csv`. This ledger feeds two things:

- **Badges in the weekly report itself** — each stock shows whether it's a `🆕 New pick` or, if it's been recommended before, `🔁 Recommended 3x · Δscore +18 (95→113) · +12.4% since last pick`. No extra API calls — it compares against what's already logged.
- **Performance section** (`render_html_summary()` in `performance_report.py`) — appears in **two places**:
  - **Embedded at the bottom of every weekly email** (compact: top 5 winners/laggards)
  - **Separate monthly email** from `performance_report.py` (more complete: top 20 winners/laggards)

  Both show: overall avg return + hit rate, a breakdown by action label, by holding period (`<30d`, `30-90d`, `90-180d`, `180d+`), and by sector (sorted with the most common sector first). Winners/laggards are STRONG BUY/BUY only (not WATCH/PASS — you wouldn't buy those), and a ticker appears only once even if it was recommended multiple times (all its entries shown together on the same line, e.g. `7d/14d` with `+22.4%/+30.5%`, most recent first). The `#` in each breakdown counts ledger rows (recommendation instances), not unique tickers.

  The ledger only starts accumulating from the moment logging was turned on — it can't reconstruct what was recommended before that. Both emails are in English.

The weekly report also shows a small stats banner (average score, dominant sector), zebra striping on the Watchlist table, and a colored border on the top-5 cards based on the action tier.

---

## Tools

- **`test_ticker.py`** — check a single stock without running the whole pipeline: `python test_ticker.py MSFT`. Prints a breakdown per pillar (same flags as the real email) and whether it clears the gate.
- **`backtest.py`** — runs `score_stock()` over historical price points to check whether the total score predicts forward returns. Technicals/Catalyst are correctly point-in-time; the fundamentals pillars use yfinance's current snapshot for every historical date (look-ahead bias — more reliable for timing than for the fundamentals pillars). Outputs `backtest_results.csv`.
- **`performance_report.py`** — sends the monthly performance email (see above) and also writes the full `performance_report.csv` (one row per recommendation instance, with `current_price`/`days_held`/`return_pct`) for drill-down in Excel/Sheets.

---

## GitHub Actions

| Workflow | When it runs | What it does |
|---|---|---|
| `weekly_screener.yml` | Every Monday 07:00 (Greece) + manual | Builds the watchlist, runs the screener, sends the email, commits the ledger back to the repo |
| `backtest.yml` | Manual only | Builds the watchlist, runs `backtest.py`, uploads `backtest_results.csv` as an artifact |
| `performance_report.yml` | 1st of every month 07:00 (Greece) + manual | Runs `performance_report.py`, sends the monthly performance email, uploads `performance_report.csv` as an artifact |
| `debug_wikipedia.yml` | Manual only | Shows the structure (columns, table index) of every Wikipedia source — useful before adding a new market to `WIKI_INDICES` |

When you trigger any workflow manually, make sure you've selected the right branch in the "Run workflow" dropdown — otherwise it'll run against `main` no matter what feature branch you're working on.
