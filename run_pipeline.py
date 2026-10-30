"""End-to-end pipeline:  raw CSV -> clean -> vendor normalise -> DQ checks -> AI classification -> SQL -> insights -> Excel report."""
import json, sqlite3, time
from pathlib import Path
import pandas as pd
from src import generate_data, vendor_norm, dq_checks, classify, insights, report, db

OUT = Path("outputs"); OUT.mkdir(exist_ok=True); Path("data").mkdir(exist_ok=True)
t0 = time.time()
raw_path = Path("data/raw_invoices.csv")
if not raw_path.exists(): generate_data.build().to_csv(raw_path, index=False)
df = pd.read_csv(raw_path, parse_dates=["invoice_date"])
print(f"[1] Loaded {len(df):,} raw rows")

df["vendor_key"], df["vendor_clean"] = vendor_norm.normalise_vendors(df["vendor_raw"])
print(f"[2] Vendors: {df.vendor_raw.nunique()} raw spellings -> {df.vendor_clean.nunique()} standardised")

# classification needs vendor_clean; DQ outlier check needs category -> classify first, then DQ
df, llm_stats = classify.classify_spend(df)
ev = classify.evaluate(df); print("[3] Classification:", json.dumps(ev))

summary, flags = dq_checks.run_checks(df)
print("[4] Data quality:\n", summary[["check", "failed_rows", "status"]].to_string(index=False))

dupes = flags["duplicate_invoice_id"] | flags["duplicate_payment"]
bad = dupes | flags["future_date"] | flags["zero_amount"] | flags["missing_vendor"]
clean = df[~bad].copy()
removed_dupe_value = df.loc[dupes, "amount_inr"].sum()
# review queue = everything a human should look at
q = df.join(flags.drop(columns=[]).add_prefix("f_"))
queue = q[bad | flags["amount_outlier"] | flags["negative_amount"] | (df.category == "Needs Review") | df.miscoding_flag].copy()
queue["reason"] = queue.filter(like="f_").apply(lambda r: ", ".join(c[2:] for c in r.index if r[c]), axis=1)
queue.loc[queue.category == "Needs Review", "reason"] += " needs_review"
queue.loc[queue.miscoding_flag, "reason"] += " erp_miscoding_suspected"
clean["has_po"] = clean.po_number.notna().map({True: "Y", False: "N"})
print(f"[5] Clean rows: {len(clean):,} | removed {int(bad.sum())} bad rows | review queue {len(queue)}")

engine = db.get_engine()                      # MySQL / SQL Server if DB_URL is set, else None
if engine is not None:
    print(f"[5b] Loaded {db.load_clean(clean, engine):,} rows into the database (table: spend)")

con = sqlite3.connect(":memory:")
clean.assign(invoice_date=clean.invoice_date.dt.strftime("%Y-%m-%d")).to_sql("spend", con, index=False)
for block in Path("sql/queries.sql").read_text().split("-- name: ")[1:]:
    name, sql = block.split("\n", 1)
    res = pd.read_sql(sql, con); res.to_csv(OUT / f"sql_{name.strip()}.csv", index=False)
    print(f"[6] SQL {name.strip():<55} -> {len(res)} rows")

facts = insights.compute_facts(clean, removed_dupe_value)
text, how = insights.narrate(facts)
print(f"[7] Insights via: {how}\n{text}")

report.build_report(clean, summary, queue, facts, text, how, ev, OUT / "Spend_Analytics_Report.xlsx")
clean.to_csv(OUT / "clean_spend.csv", index=False)       # <- this is the file Power BI / Tableau connects to
print(f"[8] Report written. Total runtime {time.time() - t0:.1f}s")
