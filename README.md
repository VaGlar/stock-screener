Πάμε αναλυτικά:

---

**Φίλτρο 1 — build_watchlist.py (Quick Score ≥ 2)**

Πριν καν φτάσει στο screener, κάθε μετοχή παίρνει quick score:
- Έπεσε >25% από 52w high → +2
- Analyst upside >20% → +2
- Buy/Strong Buy recommendation → +1
- Revenue growth >15% → +1
- P/E < 25 → +1

Αν score < 2 → **αποκλείεται εντελώς** από το watchlist.json

---

**Φίλτρο 2 — screener.py (Total Score ≥ 40/145)**

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

**5. Technicals /15**
- % κάτω από 52w high → 0-6
- vs 200DMA → 0-4
- RSI ≤ 30 → +5, RSI ≤ 45 → +3

**6. SAM /15** *(quantitative proxy)*
- Market cap size → 0-5 (μικρότερο = περισσότερο headroom)
- Industry type → 0-5
- Revenue growth proxy → 0-5

**7. Catalyst /15** *(quantitative proxy)*
- RSI oversold → 0-5
- Analyst upside → 0-5
- Αριθμός αναλυτών → 0-3
- Deep value bonus → +2

---

**Action labels βάσει sector thresholds:**
- **≥100** → STRONG BUY
- **80-99** → BUY
- **65-79** → WATCH
- **<65** → PASS

Τα thresholds αλλάζουν ανά sector — π.χ. Small Cap Growth έχει χαμηλότερα (90/70/55) γιατί είναι δύσκολο να πάρεις υψηλό score με ζημιογόνες εταιρείες.
