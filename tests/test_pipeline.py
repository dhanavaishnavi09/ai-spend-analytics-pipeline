import pandas as pd
from src.vendor_norm import clean_name, normalise_vendors
from src.dq_checks import run_checks
from src.classify import rule_classify


def test_vendor_variants_collapse():
    s = pd.Series(["Microsoft India Pvt Ltd"] * 5 + ["MICROSOFT INDIA PRIVATE LIMITED", "microsoft india", "Microsoft India Pvt Ltd."])
    _, name = normalise_vendors(s)
    assert name.nunique() == 1


def test_clean_name_strips_suffix():
    assert clean_name("Tata Power Co Ltd.") == "tata power"


def test_rules_unambiguous_and_ambiguous():
    assert rule_classify("aws monthly usage charges") == "Cloud & Hosting"
    assert rule_classify("invoice payment") is None


def test_dq_catches_planted_errors():
    df = pd.DataFrame({"invoice_id": ["A", "A", "B-R", "B", "C", "D"], "vendor_clean": ["x", "x", "y", "y", None, "z"],
                       "cost_center": ["F"] * 6, "po_number": [None] * 6, "category": ["c"] * 6,
                       "amount_inr": [100.0, 100.0, 50000.0, 50000.0, 0.0, -5.0],
                       "invoice_date": pd.to_datetime(["2026-01-01"] * 5 + ["2027-06-01"])})
    summary, f = run_checks(df)
    s = summary.set_index("check").failed_rows
    assert s["duplicate_invoice_id"] == 1 and s["zero_amount"] == 1 and s["missing_vendor"] == 1
    assert s["future_date"] == 1 and s["negative_amount"] == 1 and s["duplicate_payment"] == 1
