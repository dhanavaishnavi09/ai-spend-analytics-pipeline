"""Spend classification: Rules -> ML (TF-IDF + Logistic Regression) -> LLM fallback -> Human review.
Cheapest/most explainable method first; LLM only for the ambiguous residue (cost + governance control)."""
import os
import re
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict
from sklearn.pipeline import FeatureUnion, Pipeline

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
ML_THRESHOLD = 0.70           # below this confidence the row goes to LLM / human review
MAX_LLM_CALLS = 200           # hard cost cap per run

RULES = {
    "IT Software & SaaS": ["licence", "license", "saas", "subscription", "software", "microsoft 365", "power bi", "jira", "creative cloud"],
    "IT Hardware": ["laptop", "monitor", "server hardware", "switch", "docking", "hardware"],
    "Cloud & Hosting": ["aws", "azure", "gcp", "cloud data", "hosting", "domain", "compute"],
    "Professional Services": ["audit", "legal", "tax", "due diligence", "transfer pricing", "advisory", "consulting"],
    "Marketing & Advertising": ["ads", "advertising", "campaign", "branding", "sponsored", "trade show"],
    "Travel & Expenses": ["flight", "hotel", "cab", "airfare", "offsite", "travel"],
    "Facilities & Utilities": ["electricity", "housekeeping", "rent", "security services", "utilities", "water"],
    "Office Supplies": ["stationery", "chair", "toner", "pantry supplies", "whiteboard", "printer paper"],
    "Logistics & Freight": ["courier", "freight", "warehouse", "cargo", "delivery charges"],
    "Staffing & Contractors": ["contract staff", "recruitment", "temporary", "payroll", "contractor"],
    "Telecom": ["leased line", "postpaid", "bandwidth", "sip trunk", "voice"],
}


def rule_classify(text: str):
    t = text.lower()
    hits = {c: sum(bool(re.search(r"\b" + re.escape(k), t)) for k in kws) for c, kws in RULES.items()}   # word-boundary: "voice" must not match "invoice"
    best = max(hits.values())
    winners = [c for c, h in hits.items() if h == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


def _make_model():
    feats = FeatureUnion([("w", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                          ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True))])
    return Pipeline([("f", feats), ("clf", LogisticRegression(max_iter=2000, C=5))])


def llm_classify(desc, vendor, categories):
    """Claude fallback. Returns None if no API key / SDK -> row stays in the human review queue."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model=MODEL, max_tokens=30,
            system="You classify procurement invoices into a fixed taxonomy. Reply with EXACTLY one category name from the list, or UNSURE. No other text.",
            messages=[{"role": "user", "content": f"Categories: {categories}\nVendor: {vendor}\nDescription: {desc}"}])
        ans = msg.content[0].text.strip()
        return ans if ans in categories else None        # output validation: reject anything outside the taxonomy
    except Exception:
        return None


def classify_spend(df: pd.DataFrame):
    d = df.copy()
    d["text"] = (d["description"].fillna("") + " | " + d["vendor_clean"].fillna("")).str.lower()
    cats = sorted(RULES)
    labelled = d["erp_category"].notna()

    # (a) ML trained on ERP-labelled rows (noisy labels!). Out-of-fold probs also expose probable ERP mis-coding.
    model = _make_model()
    oof = cross_val_predict(model, d.loc[labelled, "text"], d.loc[labelled, "erp_category"], cv=5, method="predict_proba")
    model.fit(d.loc[labelled, "text"], d.loc[labelled, "erp_category"])
    classes = model.named_steps["clf"].classes_
    d["ml_cat"], d["ml_conf"] = None, 0.0
    proba = model.predict_proba(d.loc[~labelled, "text"])
    d.loc[~labelled, "ml_cat"] = classes[proba.argmax(1)]; d.loc[~labelled, "ml_conf"] = proba.max(1)
    d.loc[labelled, "ml_cat"] = classes[oof.argmax(1)]; d.loc[labelled, "ml_conf"] = oof.max(1)
    d["miscoding_flag"] = labelled & (d["ml_cat"] != d["erp_category"]) & (d["ml_conf"] >= 0.80)

    # (b) rules
    d["rule_cat"] = d["text"].map(rule_classify)

    # (c) waterfall for rows with no ERP category
    cat, src, conf = [], [], []
    llm_calls = 0
    for _, r in d.iterrows():
        if pd.notna(r.erp_category):
            cat.append(r.erp_category); src.append("ERP"); conf.append(1.0)
        elif pd.notna(r.rule_cat) and r.rule_cat == r.ml_cat:
            cat.append(r.rule_cat); src.append("Rule+ML agree"); conf.append(max(r.ml_conf, .95))
        elif pd.notna(r.rule_cat) and r.ml_conf < ML_THRESHOLD:   # NaN is truthy in Python - must test with notna
            cat.append(r.rule_cat); src.append("Rule"); conf.append(.80)
        elif r.ml_conf >= ML_THRESHOLD:
            cat.append(r.ml_cat); src.append("ML"); conf.append(r.ml_conf)
        else:
            ans = llm_classify(r.description, r.vendor_clean, cats) if llm_calls < MAX_LLM_CALLS else None
            llm_calls += ans is not None or bool(os.getenv("ANTHROPIC_API_KEY"))
            cat.append(ans or "Needs Review"); src.append("LLM" if ans else "Human review"); conf.append(.75 if ans else 0.0)
    d["category"], d["class_source"], d["confidence"] = cat, src, np.round(conf, 3)
    return d.drop(columns=["text"]), {"llm_calls": llm_calls}


def evaluate(d: pd.DataFrame):
    """Honest evaluation on rows the ERP left blank, against synthetic ground truth."""
    t = d[d["erp_category"].isna()]
    auto = t[t["category"] != "Needs Review"]
    return {"rows_needing_classification": len(t),
            "auto_classified_pct": round(100 * len(auto) / len(t), 1),
            "accuracy_on_auto_classified_pct": round(100 * (auto["category"] == auto["true_category"]).mean(), 1),
            "rule_only_accuracy_pct": round(100 * (t.dropna(subset=["rule_cat"]).eval("rule_cat == true_category")).mean(), 1),
            "rule_only_coverage_pct": round(100 * t["rule_cat"].notna().mean(), 1),
            "needs_human_review": int((t["category"] == "Needs Review").sum())}
