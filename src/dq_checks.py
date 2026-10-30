"""Data-quality engine: rule-based checks that produce (1) a summary scorecard and (2) row-level flags."""
import numpy as np
import pandas as pd

AS_OF = pd.Timestamp("2026-10-25")
PO_THRESHOLD = 20000          # assumption: invoices above this should have a PO (policy-style rule, configurable)


def run_checks(df: pd.DataFrame):
    d = df.copy()
    f = pd.DataFrame(index=d.index)
    f["missing_vendor"] = d["vendor_clean"].isna()
    f["missing_cost_center"] = d["cost_center"].isna()
    f["zero_amount"] = d["amount_inr"].eq(0)
    f["negative_amount"] = d["amount_inr"].lt(0)
    f["future_date"] = d["invoice_date"].gt(AS_OF)
    f["no_po_above_threshold"] = d["po_number"].isna() & d["amount_inr"].gt(PO_THRESHOLD)
    f["duplicate_invoice_id"] = d.duplicated("invoice_id", keep="first")
    key = d["invoice_id"].str.replace("-R$", "", regex=True)
    f["duplicate_payment"] = (d.assign(k=key).duplicated(["k"], keep="first")) & ~f["duplicate_invoice_id"]   # re-keyed invoice ids
    # outliers: IQR on log(amount) within each vendor-cluster's category group (positive amounts only)
    la = np.log(d["amount_inr"].where(d["amount_inr"] > 0))
    grp = d["category"]
    q1, q3 = la.groupby(grp).transform(lambda s: s.quantile(.25)), la.groupby(grp).transform(lambda s: s.quantile(.75))
    f["amount_outlier"] = la.gt(q3 + 3 * (q3 - q1))
    sev = {"missing_vendor": "High", "missing_cost_center": "Medium", "zero_amount": "High", "negative_amount": "Medium",
           "future_date": "High", "no_po_above_threshold": "Medium", "duplicate_invoice_id": "High", "duplicate_payment": "High",
           "amount_outlier": "Medium"}
    desc = {"missing_vendor": "Vendor name blank", "missing_cost_center": "Cost centre blank", "zero_amount": "Invoice amount = 0",
            "negative_amount": "Negative amount (credit note / sign error)", "future_date": f"Invoice date after {AS_OF.date()}",
            "no_po_above_threshold": f"No PO on invoice > INR {PO_THRESHOLD:,} (maverick spend)", "duplicate_invoice_id": "Same invoice_id appears again",
            "duplicate_payment": "Same invoice re-keyed with -R suffix (possible duplicate payment)", "amount_outlier": "Amount > Q3 + 3*IQR (log scale) in its category"}
    summary = pd.DataFrame({"check": f.columns, "description": [desc[c] for c in f.columns], "severity": [sev[c] for c in f.columns],
                            "failed_rows": f.sum().values, "pct_of_rows": (f.mean().values * 100).round(2)})
    summary["status"] = np.where(summary.failed_rows == 0, "PASS", np.where(summary.severity == "High", "FAIL", "WARN"))
    return summary, f
