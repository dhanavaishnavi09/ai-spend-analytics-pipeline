"""Insight generation. Facts are computed in pandas (deterministic); the LLM only NARRATES them (grounded generation).
Without an API key a template narrator is used, so the pipeline never breaks."""
import json
import os
import re
import pandas as pd

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


def compute_facts(d: pd.DataFrame, removed_dupe_value: float) -> dict:
    spend = d["amount_inr"].sum()
    cat = d.groupby("category")["amount_inr"].sum().sort_values(ascending=False)
    ven = d.groupby("vendor_clean")["amount_inr"].sum().sort_values(ascending=False)
    m = d.groupby(d["invoice_date"].dt.to_period("M"))["amount_inr"].sum()
    last, prev = m.iloc[-1], m.iloc[-2]
    cum = ven.cumsum() / spend
    return {
        "total_spend_inr_cr": round(spend / 1e7, 2), "invoice_count": int(len(d)), "vendor_count": int(ven.size),
        "top_category": cat.index[0], "top_category_share_pct": round(100 * cat.iloc[0] / spend, 1),
        "top3_categories": {k: float(round(100 * v / spend, 1)) for k, v in cat.head(3).items()},
        "top10_vendor_share_pct": round(100 * ven.head(10).sum() / spend, 1),
        "vendors_for_80pct_spend": int((cum < .8).sum() + 1),
        "latest_month": str(m.index[-1]), "latest_month_spend_inr_cr": round(last / 1e7, 2),
        "mom_change_pct": round(100 * (last / prev - 1), 1),
        "spend_without_po_pct": round(100 * d.loc[d.po_number.isna(), "amount_inr"].sum() / spend, 1),
        "duplicate_payments_blocked_inr_lakh": round(removed_dupe_value / 1e5, 1),
        "rows_needing_human_review": int((d.category == "Needs Review").sum()),
        "possible_erp_miscoded_invoices": int(d.miscoding_flag.sum()),
    }


def narrate(facts: dict) -> tuple[str, str]:
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model=MODEL, max_tokens=600,
                system=("You are a finance analyst. Write 5 concise bullet insights for the CFO from the JSON facts. "
                        "Use ONLY numbers present in the JSON; never invent or compute new figures. End with 2 recommended actions."),
                messages=[{"role": "user", "content": json.dumps(facts)}])
            text = msg.content[0].text
            allowed = set(re.findall(r"\d+\.?\d*", json.dumps(facts)))
            if all(n in allowed for n in re.findall(r"\d+\.?\d*", text)):      # guardrail: every number must come from the facts
                return text, "Claude (numbers validated against computed facts)"
        except Exception:
            pass
    f = facts
    text = "\n".join([
        f"- Total clean spend is INR {f['total_spend_inr_cr']} Cr across {f['invoice_count']:,} invoices and {f['vendor_count']} vendors.",
        f"- {f['top_category']} is the largest category at {f['top_category_share_pct']}% of spend; top 3: {f['top3_categories']}.",
        f"- Vendor concentration: top 10 vendors = {f['top10_vendor_share_pct']}% of spend; {f['vendors_for_80pct_spend']} vendors make up 80%.",
        f"- {f['latest_month']} spend was INR {f['latest_month_spend_inr_cr']} Cr ({f['mom_change_pct']:+}% vs prior month).",
        f"- {f['spend_without_po_pct']}% of spend has no PO (maverick spend); INR {f['duplicate_payments_blocked_inr_lakh']} lakh of duplicate invoices were blocked.",
        "Actions: (1) enforce PO-before-invoice for non-PO spend; (2) review flagged ERP miscoded invoices and the human-review queue."])
    return text, "Template (set ANTHROPIC_API_KEY to use Claude)"
