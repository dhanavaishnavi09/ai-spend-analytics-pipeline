# AI-Powered Spend Analytics & Automated Finance Reporting Pipeline

A complete, runnable project that turns a messy ERP invoice extract into a trusted Excel report and a BI-ready dataset using
**Python, SQL, machine learning and an LLM (Claude)** - with one command and about 6 seconds of runtime.

This README explains **what was done at each step, how it was done, and why**.

---------------------------------------------------------------------------------------------------

## 1. The problem I am solving (the "why" of the whole project)

Finance and procurement teams receive invoice data from an ERP system that is almost never clean:

- the same vendor appears under many spellings ("Microsoft India Pvt Ltd", "MICROSOFT INDIA PRIVATE LIMITED", "Microsft India")
- 30% of invoices have no spend category, and some categories are wrong
- the same invoice is sometimes entered or paid twice
- some invoices have no purchase order (PO), which means no approval or negotiated price ("maverick spend")
- dates in the future, zero amounts, blank vendors, extreme outliers

Analysts then spend days every month cleaning this by hand and rebuilding reports. This project automates that work, and
shows where AI helps and where it should NOT be used.

The two job descriptions ask for exactly this mix: SQL + Python + data accuracy + automated reports + AI tools
(Copilot / ChatGPT / Claude / Gemini) for data quality checks, spend classification, insight generation + Power BI.

---------------------------------------------------------------------------------------------------

## 2. Project structure

```
Spend-Ai-pipeline/
|-- run_pipeline.py              # the orchestrator: runs every step in order
|-- dashboard/
|    |-- SpendDashboard.pbix
├── docs/
│   └── images/
│       └── dashboard.png
|-- src/
|   |-- generate_data.py         # Step 1: creates messy synthetic invoice data
|   |-- vendor_norm.py           # Step 2: standardises vendor names
|   |-- classify.py              # Step 3: AI spend classification waterfall + evaluation
|   |-- dq_checks.py             # Step 4: data quality checks
|   |-- insights.py              # Step 6: facts + LLM/template narrative
|   |-- report.py                # Step 7: builds the Excel report
|-- sql/                         # Step 5: 7 business SQL queries
│   ├── queries.sql
│   └── sqlserver/
│       ├── queries.sql
│       ├── schema.sql
│       └── views.sql
|-- tests/test_pipeline.py       # unit tests
|-- src/db.py                    # optional MySQL / SQL Server loader
|-- sql/mysql, sql/sqlserver     # database-specific schema, queries, views
|-- data/raw_invoices.csv        # generated raw input
|-- outputs/ 
|     └── Spend_Analytics_Report.xlsx                    # Spend_Analytics_Report.xlsx, 
```


## 3. How to run

```bash
pip install pandas scikit-learn openpyxl pytest        # anthropic is optional
python run_pipeline.py                                  # works with no API key
python -m pytest -q tests                               # 4 tests
# optional - turn on Claude for fallback classification and narrative:
export ANTHROPIC_API_KEY=your_key
# optional - recalculate Excel formulas so cached values exist for viewers that do not calculate
```

Outputs appear in `outputs/`:
- `Spend_Analytics_Report.xlsx` - the finance-facing report
- `clean_spend.csv` - connect Power BI to this
- `sql_*.csv` - results of each SQL query

---------------------------------------------------------------------------------------------------

## 3b. Database edition (MySQL or SQL Server) + PyCharm + Power BI

The default run uses an in-memory SQLite database so the project works anywhere. To use a real database:

| File | Purpose |
|---|---|
| `src/db.py` | Loads clean data into MySQL / SQL Server through SQLAlchemy (only if `DB_URL` is set) |
| `.env.example` | Copy to `.env`, put your connection string in it (never commit `.env`) |
| `sql/mysql/` , `sql/sqlserver/` | `schema.sql` (table), `queries.sql` (7 business queries), `views.sql` (views for Power BI) |
| `docs/DB_POWERBI_PYCHARM_GUIDE.md` | Full step-by-step: install, PyCharm setup, connect, Power BI, dialect differences, troubleshooting |

Why: a real database is what companies use, SQL skills are tested on MySQL/SQL Server, and Power BI connects to it directly.
Tested: the Python loader (5,940 rows, unique IDs, totals match, safe re-runs). The MySQL/SQL Server scripts were syntax-checked but not run on a live server.

---------------------------------------------------------------------------------------------------

## 4. Step-by-step: what, how, why

### Step 1 - Create realistic messy data  (`src/generate_data.py`)
**What:** Generates 6,096 invoice rows across 11 spend categories (software, hardware, cloud, legal/audit, marketing, travel,
facilities, office supplies, logistics, staffing, telecom) and 44 real-looking vendors.

**How:** Random but realistic sampling (log-normal amounts so a few invoices are very large, like real spend), then deliberately
injects defects:
| Defect injected | Amount |
|---|---|
| Vendor name variants (case, "Pvt Ltd"/"Private Limited", trailing dot, typos, extra spaces) | ~45% of rows |
| ERP category blank | 30% |
| ERP category wrong (mis-coded) | 4% of the filled ones |
| Generic descriptions ("Misc charges", "As per quote") | 7% |
| No PO | 30% of small invoices, 8% of large |
| Missing cost centre | 4% |
| Negative amounts (credit notes / sign errors) | 0.8% |
| Outliers (amount x15) | 0.5% |
| Future dates (2027) | 0.4% |
| Zero amounts / missing vendor | 0.3% each |
| Exact duplicate invoice IDs | 0.8% |
| Re-keyed duplicates (same invoice, ID + "-R") | 0.8% |

A hidden column `true_category` stores the real category so I can later measure the AI honestly.

**Why:** I cannot use a real company's data. Synthetic data with known defects lets me prove that each check catches what it
should, and lets me measure accuracy against ground truth. **Limitation:** synthetic data is cleaner than real data, so
real-world accuracy would be lower.

### Step 2 - Standardise vendor names  (`src/vendor_norm.py`)
**What:** 488 raw vendor spellings become 50 standardised vendors.

**How:**
1. Clean: lowercase, remove punctuation, strip company suffixes (pvt, ltd, llp, inc, private, limited...).
2. Sort cleaned names by frequency.
3. Greedy fuzzy clustering with `difflib.SequenceMatcher` - a name joins an existing cluster if similarity >= 0.84.
4. The display name is the most common properly-cased spelling in the cluster.

**Why:** Without this, "spend by vendor" is wrong because one vendor is split into many. Fuzzy matching is deterministic, free
and fast; using an LLM for thousands of vendor strings would be slower and costlier for no gain.
**Why 0.84:** 0.88 left typos unmerged; much higher risks merging different vendors (e.g. "Google India" vs "Google Cloud India").
**Known gap:** 50 vs the true 44 - a few typos in short names (GoDaddy, Quess) still split. In production I would add a vendor
master list and sample-review merges.

### Step 3 - AI spend classification  (`src/classify.py`)
**What:** Fills in the category for invoices where the ERP left it blank, and flags invoices where the ERP category looks wrong.

**How - a "waterfall", cheapest and most explainable method first:**
1. **Keep the ERP category** if present.
2. **Rules** - keyword dictionary per category (e.g. "aws", "azure" -> Cloud). Uses word-boundary regex.
3. **ML model** - TF-IDF (word + character n-grams) on `description + vendor`, then Logistic Regression, trained on the
   rows the ERP already labelled. Gives a confidence score.
4. **Decision logic for unlabelled rows:**
   - rule and ML agree -> accept (high confidence)
   - rule found, ML unsure (<0.70) -> use the rule
   - ML confidence >= 0.70 -> use ML
   - otherwise -> **Claude** (if `ANTHROPIC_API_KEY` is set; capped at 200 calls per run)
   - Claude unsure / no key -> **"Needs Review"** (human)
5. **Mis-coding detector:** for already-labelled rows, cross-validated (out-of-fold) predictions are compared with the ERP
   label; confident disagreement (>= 0.80) sets `miscoding_flag`.
6. Every row stores `category`, `class_source` (ERP / Rule+ML agree / Rule / ML / LLM / Human review) and `confidence`.

**Why this design:**
- **Cost and speed:** rules are free, ML is cheap, an LLM costs money per call. Use the LLM only where needed.
- **Explainability:** finance auditors need to know why a row got a category - `class_source` answers that.
- **Safety:** LLM output is validated (must be exactly one valid category, else rejected). Uncertain rows go to a human instead
  of a guess. Out-of-fold predictions are used for mis-coding because predicting on training rows would just echo the label.
- **Model-agnostic:** only `llm_classify()` touches an LLM, so Claude can be swapped for ChatGPT/Gemini.

**Measured result (against hidden ground truth, on the 1,845 invoices the ERP left blank):**
auto-classified 98.4% | accuracy on those 99.9% | 29 sent to human review | rules alone: 91.6% coverage at 100% precision.
I report both coverage AND accuracy because accuracy alone can be inflated by only answering easy rows.

### Step 4 - Data quality checks  (`src/dq_checks.py`)
**What:** 9 rule-based checks producing a scorecard (check, description, severity, failed rows, %, status) plus row-level flags.

| Check | Rule | Severity |
|---|---|---|
| missing_vendor | vendor blank | High |
| missing_cost_center | cost centre blank | Medium |
| zero_amount | amount = 0 | High |
| negative_amount | amount < 0 (credit note or sign error) | Medium |
| future_date | invoice date after 2026-10-25 | High |
| no_po_above_threshold | no PO and amount > INR 20,000 (maverick spend) | Medium |
| duplicate_invoice_id | same invoice ID again | High |
| duplicate_payment | same invoice re-keyed with "-R" | High |
| amount_outlier | log(amount) > Q3 + 3 x IQR within its category | Medium |

**Why:** "Data accuracy" is a core responsibility in the JD. Severity lets finance prioritise. IQR on the **log** of amounts is used
because spend is heavily right-skewed. The INR 20,000 PO threshold is an **assumption** (configurable constant).
**Why classification runs before DQ:** the outlier check compares an invoice with others in the same category.

### Step 5 - Clean dataset + review queue  (`run_pipeline.py`)
**What:** Removes duplicates, future-dated, zero-amount and missing-vendor rows (156 rows, incl. 96 duplicates worth INR 89 lakh).
Builds a **Review Queue** of everything a human should look at (removed rows, outliers, negatives, Needs Review, suspected ERP
mis-coding) with a plain-English reason.

**Why:** Nothing is silently deleted - every exclusion is traceable. Negatives and outliers are **kept but flagged**, because
credit notes and big purchases can be legitimate.

### Step 6 - SQL analysis  (`sql/queries.sql`)
The clean data is loaded into an in-memory SQLite database and 7 business questions are answered:
1. `spend_by_category` - spend and % of total (`SUM() OVER ()`)
2. `monthly_trend_mom` - month-over-month % (`LAG`) and 3-month rolling average (window frame)
3. `vendor_pareto` - cumulative % of spend (running window sum)
4. `maverick_spend_by_cost_center` - spend without PO (`CASE WHEN` inside `SUM`)
5. `vendors_in_multiple_categories` - `GROUP BY ... HAVING COUNT(DISTINCT ...) > 1` (finds possible mis-coding)
6. `possible_duplicate_payments_same_vendor_amount_30d` - self-join (returns 0 after cleaning, i.e. the control passes)
7. `tail_spend` - vendors making up the last 20% of spend

**Why:** SQL is a mandatory JD skill; these are the exact questions procurement teams ask.

### Step 7 - Insights with AI, safely  (`src/insights.py`)
**What:** Produces 5 bullet insights and 2 recommended actions for a CFO-style reader.

**How:** pandas computes a JSON of facts (total spend, top categories, vendor concentration, MoM change, % without PO,
duplicates blocked). If an API key exists, Claude is asked to narrate **only** those facts. A guardrail then checks that every
number in Claude's text exists in the facts; if not, it falls back to a template. With no key, the template is used.

**Why:** LLMs are good at wording and bad at arithmetic. So the numbers come from code and the LLM only writes. The pipeline
also never breaks if the API is down.

### Step 8 - Automated Excel report  (`src/report.py`)
**Sheets:** Summary, Category Spend (+chart), Monthly Trend (+chart), Top Vendors, Data Quality, Review Queue, AI Insights, Data.

**How:** The `Data` sheet holds the clean rows; every KPI and table is a **live formula** (`SUMIFS`, `COUNTIFS`, `COUNTIF`,
`AVERAGE`, `IFERROR`) pointing at it - 127 formulas, 0 errors after recalculation. A reconciliation cell checks that the category
total equals the summary total and shows "OK" or "MISMATCH".

**Why:** Finance users must be able to audit and trust numbers; hardcoded values cannot be audited. Reconciliation is the
accuracy safety net - it is what exposed a real bug (see section 6).

### Step 9 - Power BI  (`docs/POWERBI_GUIDE.md`)
Connect to `outputs/clean_spend.csv`. The guide gives 3 dashboard pages, DAX measures (Total Spend, % No PO, MoM %, Rolling 3M,
Top 10 Vendor Share), plus how to schedule a refresh. **Note:** the guide is written; the dashboard
itself is not built in this repo.

### Step 10 - Tests  (`tests/test_pipeline.py`)
4 tests: vendor variants collapse into one, suffix stripping, rule classifier on clear vs ambiguous text, and the DQ engine
catches planted errors (duplicates, zero, missing vendor, future date, negative, re-keyed duplicate).

---------------------------------------------------------------------------------------------------

## 5. Key design decisions (and the reasons)

| Decision | Reason |
|---|---|
| Cheapest method first, LLM last | Cost, speed, auditability, privacy |
| LLM never calculates numbers | Prevents hallucinated figures in finance reports |
| Validate every LLM output | Reject anything outside the category list or not in the computed facts |
| Confidence + source stored per row | Explainability for auditors |
| Human-review queue | AI should not guess on ambiguous rows (e.g. "Misc charges") |
| Flag, do not delete, negatives and outliers | They may be legitimate |
| Formulas instead of pasted values | Auditable and recalculates when data changes |
| API key optional, call cap | Pipeline never breaks; cost is bounded |

## 6. Bugs found during testing (kept honest)
1. **Substring bug:** the keyword `voice` (Telecom) matched inside `invoice`, mislabelling generic invoices. Fixed with word-boundary regex; a unit test now covers it.
2. **NaN is truthy in Python:** a missing rule result passed an `if` check and left 28 invoices with a blank category. The Excel reconciliation (category total vs summary total) revealed the INR/row gap. Fixed with `pd.notna()`. After the fix totals match and the check shows "OK".

## 7. Results summary (synthetic data)
| Metric | Value |
|---|---|
| Raw rows / clean rows | 6,096 / 5,940 |
| Vendor spellings -> vendors | 488 -> 50 |
| Duplicate invoices blocked | 96 rows, INR 89 lakh |
| Clean spend | INR 61.3 Cr |
| Spend without PO | 8.9% |
| Uncategorised invoices | 1,845 -> 98.4% auto-classified, 99.9% accurate, 29 to human review |
| Excel | 127 formulas, 0 errors, reconciles to source |

## 8. Limitations and next steps
- Data is synthetic; validate accuracy on a hand-labelled sample of real invoices (200-500).
- The Claude path is implemented and validated in code, but the demo run used the rule/ML path and template narration.
- Add schema validation at ingest, logging, and scheduling (cron / GitHub Actions).
- Use a vendor master and a library such as rapidfuzz for better matching.
- Add RAG over the company's category policy for custom taxonomies; monitor override rate and drift after launch.
- Build the Power BI dashboard from the guide.

## 9. Skills demonstrated (maps to the JDs)
SQL (CTEs, window functions) | Python (pandas, scikit-learn, openpyxl) | data cleaning and fuzzy matching | data quality engineering |
NLP classification | LLM prompting with guardrails | cost control | Excel automation | BI (Power BI/DAX) design | testing and reconciliation |
business understanding (maverick spend, tail spend, vendor concentration).
