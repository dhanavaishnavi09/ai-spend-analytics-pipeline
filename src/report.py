"""Automated Excel report. KPIs/tables are LIVE FORMULAS over the Data sheet (SUMIFS etc.), so finance can audit every number."""
import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

F = "Arial"
HDR = PatternFill("solid", start_color="1F3864"); HF = Font(name=F, bold=True, color="FFFFFF")
INR = '#,##0;(#,##0);"-"'; PCT = "0.0%"


def _hdr(ws, row, labels, col=1):
    for i, l in enumerate(labels):
        c = ws.cell(row, col + i, l); c.fill, c.font = HDR, HF; c.alignment = Alignment(horizontal="center", wrap_text=True)


def _widths(ws, w):
    for i, x in enumerate(w, 1): ws.column_dimensions[get_column_letter(i)].width = x


def build_report(clean, dq, queue, facts, insight_text, how, ev, path):
    wb = Workbook()
    # ---------------- Data sheet (source of truth for every formula) ----------------
    wd = wb.active; wd.title = "Data"
    cols = ["invoice_id", "invoice_date", "month", "vendor_clean", "description", "amount_inr", "category", "class_source",
            "confidence", "cost_center", "po_number", "has_po"]
    d = clean.assign(month=clean.invoice_date.dt.strftime("%Y-%m"), invoice_date=clean.invoice_date.dt.date)[cols]
    _hdr(wd, 1, cols)
    for r in d.itertuples(index=False): wd.append([None if pd.isna(x) else x for x in r])
    n = len(d) + 1
    for row in wd.iter_rows(min_row=2, max_row=n):
        for c in row: c.font = Font(name=F, size=10)
        row[5].number_format = INR; row[8].number_format = "0.00"; row[1].number_format = "yyyy-mm-dd"
    wd.freeze_panes = "A2"; wd.auto_filter.ref = f"A1:L{n}"; _widths(wd, [13, 12, 9, 34, 36, 14, 24, 14, 10, 12, 12, 8])
    A = lambda col: f"Data!${col}$2:${col}${n}"          # absolute range helper: A("F") -> amount column

    # ---------------- Summary ----------------
    ws = wb.create_sheet("Summary", 0)
    ws["A1"] = "Procurement Spend Analytics - Automated Report"; ws["A1"].font = Font(name=F, size=16, bold=True)
    ws["A2"] = "Source: ERP invoice extract (synthetic). Amounts in INR. All KPIs are formulas over the Data sheet."; ws["A2"].font = Font(name=F, italic=True, size=9)
    _hdr(ws, 4, ["KPI", "Value", "Note"])
    k = [("Total clean spend (INR)", f"=SUM({A('F')})", INR, "After removing duplicates, future-dated, zero-value, missing-vendor rows"),
         ("Invoices", f"=COUNTA({A('A')})", "#,##0", ""),
         ("Average invoice (INR)", "=IFERROR(B5/B6,0)", INR, ""),
         ("Spend without PO (INR)", f'=SUMIFS({A("F")},{A("L")},"N")', INR, "Maverick / non-PO spend"),
         ("% spend without PO", "=IFERROR(B8/B5,0)", PCT, "Lower is better"),
         ("Invoices needing human classification", f'=COUNTIF({A("G")},"Needs Review")', "#,##0", "AI confidence below threshold"),
         ("Unique standardised vendors", facts["vendor_count"], "#,##0", "Python value (distinct count)"),
         ("Duplicate payments blocked (INR lakh)", facts["duplicate_payments_blocked_inr_lakh"], "#,##0.0", "Python value from DQ engine")]
    for i, (a, b, fmt, note) in enumerate(k, 5):
        ws.cell(i, 1, a); ws.cell(i, 2, b).number_format = fmt; ws.cell(i, 3, note)
    for r in ws.iter_rows(min_row=5, max_row=12):
        for c in r: c.font = Font(name=F, size=10)
    ws["A14"] = "Classification quality (held-out check vs ground truth)"; ws["A14"].font = Font(name=F, bold=True)
    for i, (lab, key) in enumerate([("Auto-classified %", "auto_classified_pct"), ("Accuracy on auto-classified %", "accuracy_on_auto_classified_pct"),
                                    ("Rules-only coverage %", "rule_only_coverage_pct"), ("Rules-only accuracy %", "rule_only_accuracy_pct")], 15):
        ws.cell(i, 1, lab).font = Font(name=F, size=10); ws.cell(i, 2, ev[key]).font = Font(name=F, size=10)
    _widths(ws, [42, 20, 70])

    # ---------------- Category ----------------
    wc = wb.create_sheet("Category Spend"); cats = clean.groupby("category").amount_inr.sum().sort_values(ascending=False).index.tolist()
    _hdr(wc, 1, ["Category", "Spend (INR)", "% of total", "Invoices"])
    for i, c in enumerate(cats, 2):
        wc.cell(i, 1, c); wc.cell(i, 2, f"=SUMIFS({A('F')},{A('G')},A{i})").number_format = INR
        wc.cell(i, 3, f"=IFERROR(B{i}/Summary!$B$5,0)").number_format = PCT; wc.cell(i, 4, f"=COUNTIFS({A('G')},A{i})").number_format = "#,##0"
    e = len(cats) + 1
    wc.cell(e + 1, 1, "Total").font = Font(name=F, bold=True); wc.cell(e + 1, 2, f"=SUM(B2:B{e})").number_format = INR
    wc.cell(e + 1, 3, f"=SUM(C2:C{e})").number_format = PCT; wc.cell(e + 1, 4, f"=SUM(D2:D{e})")
    wc.cell(e + 2, 1, "Reconciles to Summary?").font = Font(name=F, italic=True)
    wc.cell(e + 2, 2, f'=IF(ABS(B{e+1}-Summary!$B$5)<1,"OK","MISMATCH")')
    for r in wc.iter_rows(min_row=2, max_row=e + 1):
        for c in r: c.font = Font(name=F, size=10, bold=c.font.bold)
    ch = BarChart(); ch.type = "bar"; ch.title = "Spend by category (INR)"; ch.legend = None; ch.height, ch.width = 9, 18
    ch.add_data(Reference(wc, min_col=2, min_row=1, max_row=e), titles_from_data=True); ch.set_categories(Reference(wc, min_col=1, min_row=2, max_row=e))
    wc.add_chart(ch, "F2"); _widths(wc, [28, 16, 11, 10])

    # ---------------- Monthly ----------------
    wm = wb.create_sheet("Monthly Trend"); months = sorted(d.month.unique())
    _hdr(wm, 1, ["Month", "Spend (INR)", "MoM %", "3M rolling avg"])
    for i, m in enumerate(months, 2):
        wm.cell(i, 1, m); wm.cell(i, 2, f"=SUMIFS({A('F')},{A('C')},A{i})").number_format = INR
        if i > 2: wm.cell(i, 3, f'=IFERROR(B{i}/B{i-1}-1,"")').number_format = PCT
        if i > 3: wm.cell(i, 4, f"=AVERAGE(B{i-2}:B{i})").number_format = INR
    for r in wm.iter_rows(min_row=2, max_row=len(months) + 1):
        for c in r: c.font = Font(name=F, size=10)
    lc = LineChart(); lc.title = "Monthly spend"; lc.height, lc.width = 9, 20
    lc.add_data(Reference(wm, min_col=2, max_col=2, min_row=1, max_row=len(months) + 1), titles_from_data=True)
    lc.set_categories(Reference(wm, min_col=1, min_row=2, max_row=len(months) + 1)); wm.add_chart(lc, "F2"); _widths(wm, [10, 16, 9, 16])

    # ---------------- Vendors ----------------
    wv = wb.create_sheet("Top Vendors"); top = clean.groupby("vendor_clean").amount_inr.sum().sort_values(ascending=False).head(10).index.tolist()
    _hdr(wv, 1, ["Vendor", "Spend (INR)", "% of total"])
    for i, v in enumerate(top, 2):
        wv.cell(i, 1, v); wv.cell(i, 2, f"=SUMIFS({A('F')},{A('D')},A{i})").number_format = INR
        wv.cell(i, 3, f"=IFERROR(B{i}/Summary!$B$5,0)").number_format = PCT
    wv.cell(12, 1, "Top-10 concentration").font = Font(name=F, bold=True); wv.cell(12, 3, "=SUM(C2:C11)").number_format = PCT
    for r in wv.iter_rows(min_row=2, max_row=11):
        for c in r: c.font = Font(name=F, size=10)
    _widths(wv, [38, 16, 11])

    # ---------------- Data quality ----------------
    wq = wb.create_sheet("Data Quality"); _hdr(wq, 1, list(dq.columns))
    for r in dq.itertuples(index=False): wq.append(list(r))
    for r in wq.iter_rows(min_row=2):
        for c in r: c.font = Font(name=F, size=10)
        s = r[-1]; s.fill = PatternFill("solid", start_color={"PASS": "C6EFCE", "WARN": "FFEB9C", "FAIL": "FFC7CE"}[s.value])
    wq.cell(len(dq) + 3, 1, f"Assumption: invoices above INR 20,000 must carry a PO (src/dq_checks.py PO_THRESHOLD). Outlier rule = log-amount > Q3 + 3*IQR by category.").font = Font(name=F, italic=True, size=9)
    _widths(wq, [24, 62, 10, 12, 12, 9])

    # ---------------- Review queue ----------------
    wr = wb.create_sheet("Review Queue"); qc = ["invoice_id", "invoice_date", "vendor_clean", "description", "amount_inr", "category", "erp_category", "confidence", "reason"]
    _hdr(wr, 1, qc)
    for r in queue[qc].sort_values("amount_inr", key=abs, ascending=False).head(500).itertuples(index=False):
        wr.append([None if pd.isna(x) else (x.date() if hasattr(x, "date") else x) for x in r])
    for r in wr.iter_rows(min_row=2):
        for c in r: c.font = Font(name=F, size=10)
        r[4].number_format = INR
    wr.freeze_panes = "A2"; _widths(wr, [13, 12, 32, 34, 14, 22, 22, 10, 50])

    # ---------------- AI insights ----------------
    wi = wb.create_sheet("AI Insights"); wi["A1"] = "AI-generated insights"; wi["A1"].font = Font(name=F, size=14, bold=True)
    wi["A2"] = f"Generated by: {how}"; wi["A2"].font = Font(name=F, italic=True, size=9)
    for i, line in enumerate(insight_text.split("\n"), 4):
        wi.cell(i, 1, line).font = Font(name=F, size=10); wi.cell(i, 1).alignment = Alignment(wrap_text=True, vertical="top")
    _widths(wi, [140])
    wb.save(path)
