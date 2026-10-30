"""Optional database layer. If DB_URL is set (in .env or the environment) the clean data is also loaded into
MySQL or SQL Server so SQL work and Power BI run against a real database. If DB_URL is not set, nothing happens."""
import os
import pandas as pd
from sqlalchemy import create_engine, inspect, text

try:
    from dotenv import load_dotenv
    load_dotenv()                       # reads the .env file in the project root (PyCharm and terminal both work)
except ImportError:
    pass

COLUMNS = ["invoice_id", "invoice_date", "vendor_raw", "vendor_clean", "description", "amount_inr", "cost_center",
           "po_number", "has_po", "payment_terms", "erp_category", "category", "class_source", "confidence", "miscoding_flag"]


def get_engine():
    url = os.getenv("DB_URL")
    if not url:
        return None
    kw = {"fast_executemany": True} if url.startswith("mssql+pyodbc") else {}     # much faster bulk insert on SQL Server
    return create_engine(url, **kw)


def load_clean(df: pd.DataFrame, engine, table="spend") -> int:
    """Full refresh: empty the table, then insert the clean rows (table must already exist - run schema.sql once)."""
    if not inspect(engine).has_table(table):
        raise RuntimeError(f"Table '{table}' not found. Run sql/mysql/schema.sql (MySQL) or sql/sqlserver/schema.sql (SQL Server) once first.")
    out = df[COLUMNS].copy()
    out["invoice_date"] = out["invoice_date"].dt.date
    out["miscoding_flag"] = out["miscoding_flag"].astype(int)
    out = out.astype(object).where(out.notna(), None)                               # NaN -> NULL
    with engine.begin() as con:                                                     # one transaction: all or nothing
        con.execute(text(f"DELETE FROM {table}"))
        out.to_sql(table, con, if_exists="append", index=False, chunksize=1000)
    return len(out)
