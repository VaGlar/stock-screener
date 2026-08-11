Πάμε αναλυτικά:

---

**Βήμα 1 — build_watchlist.py (χτίζει το universe, χωρίς scoring)**

Μαζεύει tickers από 3 πηγές, χωρίς κανένα quality pre-filter — όλα προχωράνε στο screener:
- **S&P 500** (GitHub CSV)
- **Wikipedia indices**: FTSE 100 🇬🇧, DAX 🇩🇪, CAC 40 🇫🇷, Euro Stoxx 50 🇪🇺, BSE Sensex 🇮🇳, KOSPI 200 🇰🇷
- **Yahoo Finance screens**: undervalued_growth_stocks, growth_technology_stocks, undervalued_large_caps, aggressive_small_caps, day_gainers, most_actives

Το αποτέλεσμα (μέχρι `MAX_TICKERS` = 2000) γράφεται στο `watchlist.json` και περνάει ολόκληρο στο screener.py. Μαζί με τα tickers, κρατάει και ένα `names` mapping (ticker → όνομα εταιρείας) από τις πηγές που το δίνουν (S&P 500 CSV, Wikipedia tables) — το screener.py το χρησιμοποιεί ως fallback όταν το yfinance δεν έχει `shortName`/`longName` για το ticker (συχνό σε αγορές όπως η Κορέα, όπου αλλιώς θα εμφανιζόταν μόνο ο κωδικός π.χ. `000660.KS` αντί για "SK Hynix").

---

**Φίλτρο — screener.py (Total Score ≥ 40/150)**

Μετά το 7-pillar scoring, αν το total < 40 → **δεν εμφανίζεται** στο report.

---

**Τα 7 Pillars:**

**1. Moat /30**
- Gross margin vs sector threshold → 0-15 πόντοι
- Operating margin → 0-10 πόντοι
- Strong Buy consensus → +5

**2. Growth /30**
- Revenue growth YoY vs sector threshold → 0-15
- Earnings growth → 0-8
- Revenue accelerating QoQ → +7 αν ναι, 0 αν όχι

**3. Valuation /20**
- P/E vs sector benchmarks → 0-7
- EV/EBITDA vs sector benchmarks → 0-6
- PEG ≤ 1 → +4, PEG ≤ 2 → +2
- FCF yield ≥ 5% → +3

**4. EVA /20**
- ROIC level vs sector threshold → 0-10
- ROIC-WACC spread → 0-7
- ROIC trend improving → +3

**5. Technicals /15** *(bidirectional — αμείβει είτε dip-reversal είτε momentum setup)*
- % από 52w high: deep value dip → 0-6, ή κοντά/σε new high (momentum) → +4
- vs 200DMA: κοντά στο DMA → +4, σταθερό uptrend πάνω από DMA → +3, κάτω από DMA → +1
- RSI ≤ 30 (oversold) → +5, RSI ≤ 45 → +3, RSI 45-70 (bullish momentum) → +3, RSI ≥ 70 (overbought) → 0

**6. SAM /15** *(quantitative proxy)*
- Market cap size → 0-5 (μικρότερο = περισσότερο headroom)
- Industry type → 0-5
- Revenue growth proxy → 0-5

**7. Catalyst /20** *(quantitative proxy)*
- RSI oversold → 0-5
- Analyst upside → 0-5
- Αριθμός αναλυτών → 0-3
- Deep value bonus → +2
- Insider buying (καθαρό % αγορών vs πωλήσεων, τελευταίοι 6 μήνες) → +5 αν ≥2% net buying, +3 αν θετικό

---

**Action labels βάσει sector thresholds:**
- **≥100** → STRONG BUY
- **80-99** → BUY
- **65-79** → WATCH
- **<65** → PASS

Τα thresholds διαβάζονται ανά sector από το `sector_config.json` (μπορούν να διαφέρουν ανά κλάδο), αλλά αυτή τη στιγμή όλα τα configured sectors χρησιμοποιούν τα ίδια 65/80/100 — αν θες διαφορετικά όρια για κάποιον κλάδο, άλλαξέ τα εκεί.

---

**Pillar minimums (gate):** Μόνο τα core-quality pillars (Moat, Growth, EVA) πρέπει να περάσουν ένα ελάχιστο για να μην αποκλειστεί μια μετοχή. Valuation/Technicals/SAM/Catalyst επηρεάζουν το total score αλλά δεν αποκλείουν πλέον μόνα τους — έτσι μια ακριβή, momentum-quality μετοχή (π.χ. κοντά σε 52w high) δεν αποκλείεται απλώς επειδή δεν είναι "φθηνή" ή δεν έχει πέσει.

---

## Recommendations ledger & report extras

Κάθε φορά που το screener.py στέλνει email, καταγράφει ό,τι πραγματικά προτάθηκε (ticker, ημερομηνία, τιμή, score, action) στο `recommendations_log.csv`. Αυτό το ledger χρησιμοποιείται με δύο τρόπους:

- **Badges στο ίδιο το report** — κάθε μετοχή δείχνει αν είναι `🆕 Νέα πρόταση` ή, αν έχει ξαναπροταθεί, `🔁 3η φορά · Δscore +18 (95→113) · +12.4% από τελευταία πρόταση`. Καμία επιπλέον κλήση API — συγκρίνει με ό,τι έχει ήδη καταγραφεί.
- **`performance_report.py`** — διαβάζει ολόκληρο το ledger, τραβάει τρέχουσες τιμές, και βγάζει breakdown πραγματικής απόδοσης ανά action label και holding period. Τρέχει μηνιαία (βλ. GitHub Actions παρακάτω). Το ledger χτίζεται μόνο από τη στιγμή που ενεργοποιήθηκε το logging και μετά — δεν μπορεί να ανακατασκευάσει τι προτάθηκε πριν.

Το report επίσης δείχνει ένα μικρό stats banner (μέσος όρος score, κυρίαρχος τομέας), zebra striping στον πίνακα Watchlist, και χρωματιστό border στις top-5 κάρτες ανάλογα με το action tier.

---

## Εργαλεία

- **`test_ticker.py`** — έλεγχος μίας μετοχής χωρίς να τρέξει όλο το pipeline: `python test_ticker.py MSFT`. Τυπώνει breakdown ανά pillar (ίδια flags με το πραγματικό email) και αν περνάει το gate.
- **`backtest.py`** — τρέχει το `score_stock()` πάνω σε ιστορικά σημεία τιμής για να ελέγξει αν το total score προβλέπει forward returns. Τα Technicals/Catalyst είναι σωστά point-in-time· τα fundamentals pillars χρησιμοποιούν το σημερινό snapshot του yfinance για κάθε ιστορική ημερομηνία (look-ahead bias — πιο αξιόπιστο για timing παρά για τα fundamentals pillars). Βγάζει `backtest_results.csv`.
- **`performance_report.py`** — βλ. παραπάνω.

---

## GitHub Actions

| Workflow | Πότε τρέχει | Τι κάνει |
|---|---|---|
| `weekly_screener.yml` | Κάθε Δευτέρα 07:00 (Ελλάδα) + manual | Χτίζει watchlist, τρέχει το screener, στέλνει email, commit-άρει το ledger πίσω στο repo |
| `backtest.yml` | Μόνο manual | Χτίζει watchlist, τρέχει το `backtest.py`, ανεβάζει `backtest_results.csv` ως artifact |
| `performance_report.yml` | 1η κάθε μήνα 07:00 (Ελλάδα) + manual | Τρέχει το `performance_report.py`, ανεβάζει `performance_report.csv` ως artifact |
| `debug_wikipedia.yml` | Μόνο manual | Δείχνει τη δομή (columns, table index) όλων των Wikipedia πηγών — χρήσιμο πριν προσθέσεις νέα αγορά στο `WIKI_INDICES` |

Όταν τρέχεις οποιοδήποτε workflow χειροκίνητα, βεβαιώσου ότι έχεις επιλέξει το σωστό branch στο dropdown του "Run workflow" — αλλιώς θα τρέξει πάνω στο `main` ό,τι κι αν δουλεύεις σε feature branch.
