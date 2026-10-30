"""Generate a realistic, MESSY procurement/AP dataset (synthetic) so the pipeline has real problems to solve."""
import random
import re
import numpy as np
import pandas as pd

SEED = 42
AS_OF = pd.Timestamp("2026-10-25")

# category -> (vendors, description templates, log-normal mu, sigma)
CATS = {
    "IT Software & SaaS": (["Microsoft India Pvt Ltd", "Salesforce India Pvt Ltd", "Adobe Systems India Pvt Ltd", "Atlassian Pty Ltd", "Zoho Corporation Pvt Ltd"],
        ["Annual Microsoft 365 licence renewal", "SaaS subscription CRM seats", "Jira cloud licences", "Adobe Creative Cloud subscription", "Software licence true-up", "Power BI Pro licences"], 11.2, 0.8),
    "IT Hardware": (["Dell Technologies India Pvt Ltd", "HP India Sales Pvt Ltd", "Lenovo India Pvt Ltd", "Redington India Ltd"],
        ["Laptops for new joiners", "Monitor and docking station purchase", "Server hardware refresh", "Network switches and cables", "Laptop battery replacement"], 11.8, 0.9),
    "Cloud & Hosting": (["Amazon Web Services India Pvt Ltd", "Microsoft India Pvt Ltd", "Google Cloud India Pvt Ltd", "GoDaddy Inc"],
        ["AWS monthly usage charges", "Azure consumption invoice", "GCP compute and storage", "Domain and hosting renewal", "Cloud data transfer charges"], 11.5, 0.8),
    "Professional Services": (["Deloitte Haskins & Sells LLP", "KPMG Assurance Pvt Ltd", "Khaitan & Co LLP", "Grant Thornton Bharat LLP"],
        ["Statutory audit fees", "Legal advisory retainer", "Tax consulting services", "Due diligence support", "Transfer pricing study"], 12.0, 0.8),
    "Marketing & Advertising": (["Google India Pvt Ltd", "Meta Platforms Ireland", "Ogilvy & Mather India", "LinkedIn Singapore Pte Ltd"],
        ["Google Ads campaign spend", "Social media advertising", "Brand campaign creative fees", "LinkedIn sponsored content", "Trade show booth and branding"], 11.4, 0.9),
    "Travel & Expenses": (["MakeMyTrip India Pvt Ltd", "Taj Hotels Ltd", "Air India Ltd", "IndiGo Interglobe Aviation", "Uber India Systems"],
        ["Flight tickets Hyderabad to Mumbai", "Hotel stay client visit", "Corporate cab rides", "Team offsite travel", "Airfare business trip"], 9.8, 0.8),
    "Facilities & Utilities": (["Telangana State Power Distribution", "Sodexo India Services", "CBRE South Asia Pvt Ltd", "Tata Power Co Ltd"],
        ["Office electricity bill", "Housekeeping and pantry services", "Office rent and maintenance", "Security services monthly", "Water and utilities"], 10.6, 0.7),
    "Office Supplies": (["Amazon India Pvt Ltd", "Staples India", "Officeworks Traders", "Flipkart Internet Pvt Ltd"],
        ["Stationery and printer paper", "Office chairs purchase", "Printer toner cartridges", "Pantry supplies", "Whiteboards and markers"], 8.9, 0.8),
    "Logistics & Freight": (["Blue Dart Express Ltd", "DHL Express India", "Delhivery Ltd", "Maersk Line India"],
        ["Courier charges", "Freight forwarding invoice", "Warehouse handling fees", "Air cargo shipment", "Last mile delivery charges"], 10.5, 0.9),
    "Staffing & Contractors": (["Randstad India Pvt Ltd", "TeamLease Services Ltd", "Quess Corp Ltd", "Adecco India Pvt Ltd"],
        ["Contract staff monthly billing", "Recruitment agency fee", "Temporary analyst resources", "Payroll outsourcing fees", "Contractor invoice"], 11.9, 0.7),
    "Telecom": (["Bharti Airtel Ltd", "Reliance Jio Infocomm Ltd", "Vodafone Idea Ltd", "Tata Communications Ltd"],
        ["Leased line charges", "Mobile postpaid corporate plans", "Internet bandwidth monthly", "Voice and SIP trunk charges"], 10.2, 0.6),
}
GENERIC = ["Invoice payment", "Misc charges", "As per quote", "Services rendered", "Monthly invoice", "Payment against PO"]
COST_CENTERS = ["FIN-100", "HR-200", "SALES-300", "IT-400", "OPS-500", "MKT-600"]


def vendor_variant(name, rng):
    r = rng.random()
    if r < 0.55: return name
    if r < 0.65: return name.upper()
    if r < 0.72: return name.lower()
    if r < 0.80: return name.replace("Pvt Ltd", "Private Limited")
    if r < 0.86: return name.replace(" Pvt Ltd", "").replace(" Ltd", "")
    if r < 0.91: return name + "."
    if r < 0.96:
        base = len(re.sub(r" (Pvt Ltd|Pty Ltd|Pte Ltd|Ltd|LLP|Inc)$", "", name))   # typos happen in the name, not the suffix
        i = rng.randrange(2, max(3, base - 2)); return name[:i] + name[i + 1] + name[i] + name[i + 2:]
    return "  " + name + "  "


def build(n=6000, seed=SEED):
    rng = random.Random(seed); np.random.seed(seed)
    cats = list(CATS)
    rows = []
    for i in range(n):
        cat = rng.choices(cats, weights=[14, 8, 9, 6, 10, 15, 8, 9, 7, 8, 6])[0]
        vendors, descs, mu, sg = CATS[cat]
        vendor = rng.choice(vendors)
        desc = rng.choice(GENERIC) if rng.random() < 0.07 else rng.choice(descs)
        if rng.random() < 0.3: desc += f" {rng.choice(['Q1','Q2','Q3','Q4','Jan','Mar','Jun','Sep'])}"
        amt = round(float(np.random.lognormal(mu, sg)), 2)
        date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=rng.randint(0, 637))
        po = f"PO{rng.randint(100000, 999999)}" if rng.random() > (0.30 if amt < 20000 else 0.08) else None
        erp = cat if rng.random() > 0.30 else None            # 30% blank in ERP
        if erp and rng.random() < 0.04: erp = rng.choice([c for c in cats if c != cat])  # 4% mis-coded
        rows.append(dict(invoice_id=f"INV-{100000 + i}", po_number=po, invoice_date=date, vendor_raw=vendor_variant(vendor, rng),
                         description=desc, amount_inr=amt, cost_center=None if rng.random() < 0.04 else rng.choice(COST_CENTERS),
                         payment_terms=rng.choice(["Net30", "Net45", "Net60"]), erp_category=erp, true_category=cat))
    df = pd.DataFrame(rows)
    # --- inject data problems ---
    idx = df.sample(frac=0.008, random_state=1).index; df.loc[idx, "amount_inr"] *= -1
    idx = df.sample(frac=0.005, random_state=2).index; df.loc[idx, "amount_inr"] *= 15
    idx = df.sample(frac=0.004, random_state=3).index; df.loc[idx, "invoice_date"] = pd.Timestamp("2027-03-15")
    idx = df.sample(frac=0.003, random_state=4).index; df.loc[idx, "amount_inr"] = 0
    idx = df.sample(frac=0.003, random_state=5).index; df.loc[idx, "vendor_raw"] = None
    d1 = df.sample(frac=0.008, random_state=6).copy()                                   # exact duplicate invoice ids
    d2 = df.sample(frac=0.008, random_state=7).copy(); d2["invoice_id"] += "-R"         # re-keyed duplicate payments
    return pd.concat([df, d1, d2], ignore_index=True).sample(frac=1, random_state=9).reset_index(drop=True)


if __name__ == "__main__":
    out = build(); out.to_csv("data/raw_invoices.csv", index=False)
    print(f"Generated {len(out):,} rows -> data/raw_invoices.csv")
