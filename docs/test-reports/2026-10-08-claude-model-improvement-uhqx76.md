# Test Report — stock-screener — 2026-10-08

**Branch:** `claude/model-improvement-uhqx76` (HEAD = `origin/main`, κανένα pending diff αυτή τη στιγμή)
**Mode:** analyze (read-only ανάλυση — καμία αλλαγή σε product code)

## 1. Verdict

Καμία BLOCKING εύρεση. Το σημαντικότερο κενό: **δεν υπάρχει κανένα test στο repo**, και η χειροκίνητη επαλήθευση αποκάλυψε ένα πραγματικό, αναπαραγώγιμο bug στο scoring model — οι μετρικές με πραγματική τιμή `0` (π.χ. gross margin 0%, ή μετοχή ακριβώς στο 52-week high) αντιμετωπίζονται σαν "δεν υπάρχει δεδομένο" λόγω `if x and ...` ελέγχων, με αποτέλεσμα να βαθμολογούνται **χειρότερα** από μια μετοχή με εντελώς ελλιπή δεδομένα.

## 2. BLOCKING

Καμία. (Δεν υπάρχει προηγούμενο πράσινο test που να έγινε κόκκινο, δεν βρέθηκε secret, δεν βρέθηκε critical/high dependency advisory σε πακέτο που όντως χρησιμοποιείται, και δεν υπάρχει mutation threshold ορισμένο πουθενά.)

## 3. Gaps (με προτεραιότητα)

### G1 — [HIGH] Πραγματικές τιμές `0` αντιμετωπίζονται σαν ελλιπές δεδομένο στο scoring model
**Πού:** `screener.py`, `score_stock()` — όλοι οι pillars (π.χ. γραμμές 235, 239, 259, 264, 287, 294, 299, 321, 325, 344, 349, 354, 386, 389, 397 κ.ά.) χρησιμοποιούν `if x and isinstance(x, (int, float))` αντί για `if x is not None and isinstance(x, (int, float))`.

**Γιατί έχει σημασία:** Στην Python, `0` και `0.0` είναι falsy, άρα είναι αδιακριτοποίητα από `None`. Μια μετοχή με **πραγματικό** gross margin 0%, revenue growth 0%, ROIC 0%, ή μια μετοχή **ακριβώς** στο 52-week high (`pct_from_high == 0.0`) χάνει εντελώς τη βαθμολόγηση του αντίστοιχου pillar — ΚΑΙ δεν πέφτει στο fallback proxy (αφού το proxy ενεργοποιείται μόνο όταν η τιμή είναι όντως `None`). Αποτέλεσμα: χειρότερη βαθμολόγηση από μια μετοχή για την οποία δεν υπάρχει ΚΑΘΟΛΟΥ δεδομένο.

**Αναπαραγωγή (έτρεξα το παρακάτω, πραγματικό output):**
```python
from screener import score_stock
sector_cfg = {...}  # βλ. script
data_zero = {... 'gross_margin': 0.0, 'revenue_growth': 0.0, 'pe': 0.0, 'roic': 0.0, ...}
# TOTAL με πραγματικά zero values:        12/150
# TOTAL με τα ΙΔΙΑ πεδία = None (no data): 28/150
```
Και πιο συγκεκριμένο παράδειγμα (Technicals pillar):
```
Μετοχή ΑΚΡΙΒΩΣ στο 52w high (pct_from_high=0.0)     -> technicals = 7
Μετοχή 1% ΚΑΤΩ από το 52w high (pct_from_high=-0.01) -> technicals = 11
```
Μια μετοχή που μόλις έκανε νέο high (το ισχυρότερο momentum signal που περιγράφει το ίδιο το μοντέλο) βαθμολογείται **χειρότερα** από μια μετοχή που είναι ελαφρώς χαμηλότερα, μόνο επειδή το `0.0` είναι falsy.

**Προτεινόμενη διόρθωση:** Αλλαγή όλων των `if x and isinstance(...)` σε `if x is not None and isinstance(...)` στο `score_stock()`. Developer action — δεν το άγγιξα (out of scope για tester σε analyze mode).

### G2 — [MEDIUM] Unescaped HTML injection από external-sourced strings στο email report
**Πού:** `screener.py`, `build_html_report()` (π.χ. γραμμή 549: `{d['name']}`) και `performance_report.py` — τα πεδία `ticker`/`name`/`industry`/`sector` μπαίνουν σε f-string HTML χωρίς `html.escape()`. Αυτά τα strings προέρχονται από το yfinance `shortName`/`longName` ή από το `names` mapping που φτιάχνει το `build_watchlist.py` scraping δημόσια επεξεργάσιμους πίνακες Wikipedia.

**Αναπαραγωγή (επιβεβαιωμένη, χωρίς δίκτυο):**
```python
malicious_name = '<img src=x onerror=alert(1)>Evil Corp'
html = build_html_report([{'data': {'ticker':'EVL','name': malicious_name, ...}, ...}], {...})
# '<img src=x onerror=' βρίσκεται ΑΥΤΟΛΕΞΕΙ μέσα στο παραγόμενο HTML
```
**Impact:** Χαμηλή πιθανότητα εκμετάλλευσης στην πράξη (απαιτεί vandalism σε σελίδα Wikipedia που scrapάρεται, ή "κακό" company name από το yfinance) και οι σύγχρονοι email clients (Gmail) φιλτράρουν `<script>`/event handlers σε HTML emails — αλλά η απουσία output encoding είναι πραγματικό κενό, και θα επιτρέψει τουλάχιστον layout injection / spoofing content μέσα στο δικό σου email.

**Προτεινόμενη διόρθωση:** `html.escape()` σε κάθε externally-sourced string πριν την ένθεση σε HTML (ticker, name, industry, sector — σε `screener.py` και `performance_report.py`).

### G3 — [MEDIUM] `requirements.txt` ελλιπές
**Πού:** `requirements.txt` λιστάρει μόνο `yfinance==0.2.38` και `pandas==2.2.0`. Το `screener.py`/`backtest.py` κάνουν `import numpy` που δεν είναι καταγεγραμμένο. Το `build_watchlist.py` χρειάζεται `lxml`/`html5lib` για το `pd.read_html()` — αυτά εγκαθίστανται ad-hoc μόνο μέσα στο `weekly_screener.yml`/`debug_wikipedia.yml` (`pip install yfinance pandas requests numpy lxml html5lib`), όχι από το `requirements.txt`. Αν κάποιος κάνει `pip install -r requirements.txt` τοπικά, το script θα σκάσει με `ModuleNotFoundError`.

**Προτεινόμενη διόρθωση:** Προσθήκη `numpy`, `lxml`, `html5lib` στο `requirements.txt`.

### G4 — [LOW] Πιθανό NaN leakage από τα quarterly financials του yfinance στο ROIC
**Πού:** `screener.py:136-137` — `ebit = q_income.iloc[:, i].get("EBIT") or q_income.iloc[:, i].get("Operating Income")`. Αν το EBIT είναι `NaN` (συχνό σε πραγματικά δεδομένα yfinance), το `NaN` είναι **truthy** στην Python (`bool(float('nan')) == True`), άρα το `or` δεν κάνει fallback στο "Operating Income", και το `nopat = ebit * 0.79 if ebit else None` παράγει `NaN` αντί για `None`. Αυτό το `NaN` μπορεί να προχωρήσει μέχρι το `roic_current`, και μετά μέχρι ένα flag σαν `"🔴 ROIC nan%"` στο πραγματικό email — cosmetic bug, όχι crash, αλλά χαλάει την εμπειρία. **Δεν το επιβεβαίωσα με πραγματικά δεδομένα** (δεν έχω πρόσβαση δικτύου στο yfinance εδώ) — review-only finding, χρειάζεται επιβεβαίωση με πραγματικό ticker.

### G5 — [LOW] Missing flags σε δύο σημεία του scoring (δεν εξηγείται το γιατί του score)
**Πού:** `screener.py:373` (SAM pillar, `elif rg >= 0.10: s += 3` — χωρίς `f.append(...)`) και `screener.py:394` (Catalyst pillar, `elif num_analysts >= 8: s += 2` — χωρίς `f.append(...)`). Οι άλλες επιλογές σε όλα τα pillars πάντα συνοδεύονται από ένα flag string· αυτές οι δύο είναι ασυνέπεια — ο χρήστης βλέπει +3/+2 πόντους στο breakdown χωρίς καμία εξήγηση.

### G6 — [LOW] Καμία προστασία αν λείπει το `GMAIL_APP_PASSWORD`
**Πού:** `screener.py`/`performance_report.py`, `send_email()`. Αν το env var δεν έχει οριστεί, `EMAIL_PASSWORD = None`, και `server.login(SENDER_EMAIL, None)` θα πετάξει ένα μη πιασμένο `smtplib` exception με μη φιλικό μήνυμα. Δεν είναι κρίσιμο (είναι batch script, το traceback πάει στο GitHub Actions log), αλλά ένα early check με φιλικό μήνυμα θα βοηθούσε το debugging.

### G7 — [LOW] CI/CD hardening
**Πού:** `.github/workflows/*.yml`. Μόνο το `weekly_screener.yml` δηλώνει explicit `permissions:`· τα άλλα 3 βασίζονται στο default του repo/org. Όλα τα `actions/*` είναι pinned σε major-version tag (`@v4`/`@v5`), όχι σε full commit SHA — αποδεκτό για official GitHub actions, αλλά πιο αυστηρό θα ήταν SHA pinning. Δεν υπάρχει `CODEOWNERS` για να επιβάλει review σε αλλαγές workflow. Κανένα workflow δεν τρέχει σε `pull_request`, άρα δεν υπάρχει CI gate πάνω σε PRs (μόνο schedule/manual).

### G8 — [LOW] Μη ιδεατή idempotency στο ledger
**Πού:** `screener.py`, `log_recommendations()`. Αν το `weekly_screener.yml` τρέξει δύο φορές την ίδια μέρα (π.χ. χειροκίνητο re-run), θα καταγραφούν διπλές γραμμές στο `recommendations_log.csv` για την ίδια ημερομηνία/ticker — δεν υπάρχει dedup-by-date-and-ticker έλεγχος.

## 4. Tests added

Κανένα — η λειτουργία είναι **analyze** (read-only), όχι write-tests. Οι παραπάνω αναπαραγωγές έγιναν με ad-hoc scripts εκτός repo (στο scratchpad / inline python -c), όχι committed test files.

## 5. Test breadth (F1-F15)

| ID | Κάλυψη από υπάρχοντα tests |
|----|------------------------------|
| F1 | **Καμία** — δεν υπάρχει test directory/framework configured στο repo |
| F2 | Καμία αυτοματοποιημένη κάλυψη· χειροκίνητος έλεγχος αποκάλυψε G1 |
| F3 | Καμία — error paths καλύπτονται μόνο από try/except στο ίδιο το production code |
| F4 | N/A — δεν υπάρχει bugfix σε αυτό το diff |
| F5 | Καμία — επιβεβαιώθηκε μόνο ότι τα modules κάνουν import χωρίς σφάλμα |
| F6 | N/A — δεν υπάρχει HTTP API |
| F7 | Καμία — βλ. G1, G4 |
| F8 | Καμία — βλ. G8 |
| F9 | Καμία — καθαρές συναρτήσεις όπως `sf()`, `format_market_cap()`, `get_action()`, `bucket_days()` δεν έχουν property-based tests |
| F10 | Καμία — και δεν μπορεί να τρέξει εδώ (βλ. §8) |
| F11 | N/A |
| F12 | Καμία — βλ. G3, G6 |
| F13 | Καμία — review-only, βλ. §8 |
| F14 | N/A by absence — δεν υπάρχει baseline tests για να γίνει mutation analysis |
| F15 | N/A — δεν υπάρχουν tests που να είναι flaky |

## 6. Applicability table

### Functional

| ID | Status | Evidence / Αποτέλεσμα |
|----|--------|------------------------|
| F1 | RUN | Κανένα test directory/framework στο repo → Gap καταγεγραμμένο στο §5 |
| F2 | RUN | Βρέθηκε G1 (zero-vs-None), επιβεβαιωμένο με script |
| F3 | RUN | Review: try/except υπάρχει σχεδόν παντού, αλλά χωρίς tests να το επιβεβαιώνουν· βλ. G6 |
| F4 | N/A | Το commit υπό εξέταση είναι translation-only (comments/strings), καμία λογική αλλαγή — `git diff` επιβεβαίωσε 169 ins/169 del, μόνο σε strings |
| F5 | RUN | `python3 -c "import screener, build_watchlist, performance_report, backtest, test_ticker"` → OK |
| F6 | N/A | HTTP_API=false — δεν υπάρχει server/routes πουθενά στο repo |
| F7 | RUN | Βρέθηκαν G1, G4 |
| F8 | RUN | Βρέθηκε G8 |
| F9 | RUN | Ad-hoc manual checks σε `sf`, `format_market_cap`, `get_action`, `bucket_days`, `passes_minimums` — βλ. §Πρόσθετοι έλεγχοι· χωρίς committed property tests |
| F10 | CANNOT_CHECK | Χρειάζεται πραγματικό yfinance/Wikipedia δίκτυο (εδώ: `curl` στο Yahoo Finance έδωσε HTTP 429) + πραγματικό `GMAIL_APP_PASSWORD` για να σταλεί email — καμία από τα δύο δεν είναι διαθέσιμα σε αυτό το sandbox |
| F11 | N/A | DB_MIGRATIONS=false — δεν υπάρχει βάση δεδομένων, μόνο flat files |
| F12 | RUN | Βρέθηκαν G3, G6 |
| F13 | CANNOT_CHECK | Δεν μπορώ να τρέξω πραγματικό batch των ~2000 tickers χωρίς δίκτυο/χρόνο· review-only: `time.sleep(0.5)` ανά ticker σημαίνει ≥16 λεπτά μόνο σε sleeps για 2000 tickers |
| F14 | N/A | Δεν υπάρχει baseline test suite ή `TESTING.md` με mutation threshold |
| F15 | N/A | Δεν υπάρχουν tests που να τρέξουν ώστε να ελεγχθούν για flakiness |

### Security

| ID | Status | Evidence / Αποτέλεσμα |
|----|--------|------------------------|
| S01 | RUN | `detect-secrets scan --all-files` → `results: {}`· grep σε όλο το `git log --all -p` για password/api_key/secret/private-key patterns → καθαρό |
| S02 | RUN | `pip-audit -r requirements.txt` → "No known vulnerabilities found". Gap: G3 (ελλιπές requirements.txt, no lockfile) |
| S03 | N/A | AUTH=false, BAAS=false — δεν υπάρχει multi-user data model, μόνο flat files του ίδιου owner |
| S04 | N/A | DEPLOYED_PUBLIC=false, WEB_UI=false, HTTP_API=false — τίποτα δεν σερβίρεται πάνω από HTTP από αυτό το project |
| S05 | RUN | `smtplib.SMTP_SSL("smtp.gmail.com", 465)` σε `screener.py`/`performance_report.py` → σωστό implicit TLS, όχι plaintext. Καμία εύρεση |
| S06 | RUN | Βρέθηκε G2 (unescaped HTML από external-sourced strings), επιβεβαιωμένο με script |
| S07 | N/A | AUTH=false, HTTP_API=false, PAYMENTS=false — δεν υπάρχει exposed endpoint/login προς κατάχρηση |
| S08 | N/A | AUTH=false, SESSIONS=false, TOKENS_OAUTH=false — δεν υπάρχει login system πουθενά |
| S09 | RUN | Grep για `pickle.load`/`yaml.load`/`eval`/`marshal` → τίποτα. CI artifact trust: βλ. G7 (actions pinned σε tag, όχι SHA) |
| S10 | RUN | Grep σε όλα τα `print()` για `EMAIL_PASSWORD`/`GMAIL_APP_PASSWORD` → καμία διαρροή |
| S11 | RUN | Bandit B112 (bare `except:` σε `screener.py:143`) — low severity, καταγράφηκε ως μέρος του G1/G6 context |
| S12 | N/A | FILE_UPLOAD=false· όλα τα `open()` calls χρησιμοποιούν hardcoded string literals ως path (`recommendations_log.csv`, `watchlist.json`, κ.λπ.) — καμία μεταβλητή από external input φτάνει σε path |
| S13 | N/A | HTTP_API=false |
| S14 | RUN | Review όλων των `urlopen`/`yf.Ticker`/`pd.read_html`/`yf.screen` calls → όλα target hardcoded constant URLs/tickers, κανένα user-controlled input δεν φτάνει σε fetch call. Καμία εύρεση |
| S15 | N/A | WEB_UI=false, BROWSER_EXTENSION=false |
| S16 | N/A | LLM_FEATURES=false |
| S17 | N/A | PERSONAL_DATA=weak/false — μόνο το hardcoded email του ίδιου του owner, καμία αλλού προσωπικά δεδομένα τρίτων |
| S18 | RUN | Βρέθηκε G7 (ελλιπές explicit `permissions:` σε 3/4 workflows, no CODEOWNERS, tag-pinned actions). Κανένα `pull_request_target` πουθενά |

## 7. Project profile

- **Γλώσσα/runtime:** Python 3.11, καθαρά scripts (`if __name__ == "__main__"` σε κάθε entry point)
- **Σκοπός:** Προσωπικό pipeline που σκανάρει ~1000+ tickers μέσω yfinance/Wikipedia/Yahoo screens, τα βαθμολογεί με ένα custom 7-pillar μοντέλο, και στέλνει HTML email εβδομαδιαίως/μηνιαίως
- **Test framework:** Κανένα configured (ούτε `pytest.ini`/`pyproject.toml` με test config, ούτε `tests/` directory). `pytest` βρέθηκε εγκατεστημένο στο sandbox αλλά όχι στο `requirements.txt` ούτε χρησιμοποιημένο
- **Coverage/mutation tool:** Κανένα
- **TESTING.md / SPEC.md / CLAUDE.md:** Δεν υπάρχουν
- **Entry points:** `build_watchlist.py`, `screener.py`, `performance_report.py`, `backtest.py`, `test_ticker.py`
- **Dependencies:** `requirements.txt` (ελλιπές — G3)
- **CI:** 4 GitHub Actions workflows (`weekly_screener.yml` — schedule Δευτέρα 07:00 Ελλάδας + manual· `backtest.yml` — manual· `performance_report.yml` — schedule 1η του μήνα + manual· `debug_wikipedia.yml` — manual). Κανένα trigger σε `pull_request`
- **Flags:** `FILE_IO`=yes, `EXTERNAL_HTTP`=yes (hardcoded URLs μόνο), `SECRETS_USED`=yes (`GMAIL_APP_PASSWORD` via env/GH secret), `CLI_OR_SCRIPT`=yes, `DATA_PIPELINE`=yes, `CALCULATIONS`=yes, `DEPENDENCIES`=yes, `CI`=partial (όχι σε PRs)· όλα τα υπόλοιπα (`WEB_UI`, `HTTP_API`, `AUTH`, `SESSIONS`, `TOKENS_OAUTH`, `DB_SQL`, `BAAS`, `FILE_UPLOAD`, `SUBPROCESS_SHELL`, `PAYMENTS`, `LLM_FEATURES`, `BROWSER_EXTENSION`, `DEPLOYED_PUBLIC`, `DB_MIGRATIONS`)=no, `PERSONAL_DATA`=weak/no

## 8. Assumptions and limits

- Αυτόματοι και static έλεγχοι **δεν αποτελούν απόδειξη ασφάλειας** και **δεν είναι penetration test**.
- **Δεν δοκιμάστηκε:** πραγματικό end-to-end run (fetch yfinance/Wikipedia δεδομένα + αποστολή email) — δεν υπάρχει δίκτυο προς το Yahoo Finance εδώ (`curl` → HTTP 429) ούτε access στο `GMAIL_APP_PASSWORD` secret.
- **Δεν δοκιμάστηκε:** συμπεριφορά με πραγματικά NaN values από το yfinance quarterly financials (G4) — χρειάζεται πραγματικό ticker με NaN EBIT για επιβεβαίωση.
- **Δεν δοκιμάστηκε:** πραγματική απόδοση/χρόνος εκτέλεσης σε πλήρη batch των ~2000 tickers (F13) — μόνο στατική ανάλυση του κώδικα.
- Το `detect-secrets`/`bandit`/`pip-audit` εγκαταστάθηκαν στο sandbox για τους σκοπούς αυτού του report (δεν άγγιξαν product code).
- Το full-environment `pip-audit` (χωρίς `-r`) έδειξε πολλά advisories σε πακέτα του **base OS image** (cryptography, urllib3, setuptools, pyjwt, κ.λπ.) που **δεν είναι dependencies του project** — αγνοήθηκαν ως θόρυβο· το ουσιαστικό αποτέλεσμα είναι το `pip-audit -r requirements.txt` (καθαρό).
- Εργαλεία/εκδόσεις: `bandit` (τελευταία διαθέσιμη από pip σε αυτό το sandbox), `pip-audit`, `detect-secrets`, Python 3.11.15. Πρότυπα: OWASP Top 10:2025, OWASP ASVS 5.0.0 (επιβεβαιώθηκε μέσω web search ότι είναι ακόμα η τρέχουσα stable έκδοση, καμία διαφορά από το κατάλογο), OWASP WSTG 4.2 stable.
- Το branch `claude/model-improvement-uhqx76` ήταν ήδη ίσο με `origin/main` τη στιγμή του review (το PR #12 είχε ήδη γίνει merge) — άρα το "diff" αυτού του review είναι ολόκληρο το project, όπως προβλέπει ο κανόνας για πρώτο run χωρίς προηγούμενο report.
