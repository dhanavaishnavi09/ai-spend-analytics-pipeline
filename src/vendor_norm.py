"""Vendor name standardisation: rule-based cleaning + fuzzy clustering (stdlib difflib, no heavy deps)."""
import re
from difflib import SequenceMatcher
import pandas as pd

SUFFIXES = r"\b(pvt|private|ltd|limited|llp|inc|corp|corporation|pte|pty|co)\b"


def clean_name(s):
    if pd.isna(s): return None
    s = re.sub(r"[^a-z0-9& ]", " ", str(s).lower())
    s = re.sub(SUFFIXES, " ", s)
    return re.sub(r"\s+", " ", s).strip() or None


def normalise_vendors(raw: pd.Series, threshold=0.84):
    """Return (cluster key, display name). Most frequent cleaned spelling becomes the cluster centre."""
    keys = raw.map(clean_name)
    canon, mapping = [], {}
    for k in keys.value_counts().index:
        m = next((c for c in canon if SequenceMatcher(None, k, c).ratio() >= threshold), None)
        if m is None: canon.append(k); m = k
        mapping[k] = m
    ck = keys.map(mapping)
    tmp = pd.DataFrame({"ck": ck, "raw": raw.str.strip().str.rstrip(".")}).dropna()
    mixed = tmp[(tmp.raw != tmp.raw.str.upper()) & (tmp.raw != tmp.raw.str.lower())]   # prefer properly-cased spellings
    best = mixed.groupby("ck")["raw"].agg(lambda x: x.mode().iloc[0])
    fallback = tmp.groupby("ck")["raw"].agg(lambda x: x.mode().iloc[0])
    best = best.combine_first(fallback)
    return ck, ck.map(best)
