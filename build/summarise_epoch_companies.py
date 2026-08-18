#!/usr/bin/env python3
"""Derive the AI Companies tables from Epoch AI's published dataset.

Reads the six files exactly as downloaded from epoch.ai/data/ai-companies into
ai_companies/:

    ai_companies.csv                  one row per tracked company
    ai_companies_revenue_reports.csv  revenue observations, dated
    ai_companies_usage_reports.csv    active users, daily tokens, daily messages
    ai_companies_staff_reports.csv    headcount observations
    ai_companies_funding_rounds.csv   equity, debt and post-money valuation
    ai_companies_compute_spend.csv    inference and R&D cloud compute spend

and writes the small derived tables the charts read into ai-companies/data/.

Three rules hold throughout, and they are why a count here differs from a count
on Epoch's own page:

  Epoch's own exclusions are honoured. Rows flagged "Exclude from graph view"
  are dropped from every charted series, because Epoch flagged them as not
  belonging in its figure - superseded restatements, or a scope that would
  double-count. The dropped rows are counted in companies_summary.csv.

  Nothing is projected. Epoch's chart offers a "Project trend" control; no value
  written here is extrapolated, imputed or carried across from another company.

  A company appears in a chart only where Epoch records the value being plotted.
  Absent is left absent. Revenue is recorded for 8 of the 11 tracked companies,
  compute spend for 2 - the rest are missing from those charts, never filled.

Revenue rows typed "Period interpolation" are kept and flagged. They are Epoch
annualising a disclosed period figure (a reported quarter multiplied out), not a
projection - but they are arithmetic on an observation rather than a disclosed
annual rate, so the charts draw them as open markers and state the count.

Usage:
    python build/summarise_epoch_companies.py [source_dir]
"""
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RAW = REPO / "ai_companies"
OUT = REPO / "ai-companies" / "data"

MIN_FIT_POINTS = 12   # below this a growth trend is not fitted at all

FILES = {
    "companies": "ai_companies.csv",
    "revenue": "ai_companies_revenue_reports.csv",
    "usage": "ai_companies_usage_reports.csv",
    "staff": "ai_companies_staff_reports.csv",
    "funding": "ai_companies_funding_rounds.csv",
    "spend": "ai_companies_compute_spend.csv",
}


def read(raw, key):
    path = raw / FILES[key]
    if not path.exists():
        sys.exit(f"missing {path}\nDownload the six files from "
                 f"https://epoch.ai/data/ai-companies into {raw}/")
    return pd.read_csv(path, low_memory=False)


def excluded_mask(df):
    """Epoch's own 'Exclude from graph view' flag, as a real boolean."""
    if "Exclude from graph view" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["Exclude from graph view"].astype(str).str.strip().str.lower() == "true"


def dec_year(stamp):
    """Decimal year, matching build/summarise_epoch_models.py exactly."""
    return stamp.year + (stamp.dayofyear - 1) / 365.25


def least_squares(x, y):
    mx, my = x.mean(), y.mean()
    sxx = float(((x - mx) ** 2).sum())
    sxy = float(((x - mx) * (y - my)).sum())
    slope = sxy / sxx
    return slope, my - slope * mx


def fit_trend(sub, value_col, date_col, company, metric):
    """Log-linear fit of a metric against date, over the plotted points only.

    Returns growth as orders of magnitude per year with the implied doubling
    time, or None below MIN_FIT_POINTS - a trend is refused rather than drawn
    thin.
    """
    sub = sub.dropna(subset=[value_col, date_col])
    sub = sub[sub[value_col] > 0]
    if len(sub) < MIN_FIT_POINTS:
        return None
    x = sub[date_col].map(dec_year).to_numpy()
    y = sub[value_col].map(math.log10).to_numpy()
    slope, intercept = least_squares(x, y)
    resid = y - (slope * x + intercept)
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "company": company,
        "metric": metric,
        "n": int(len(sub)),
        "oom_per_year": slope,
        "intercept_log10": intercept,
        "growth_per_year": 10 ** slope,
        "doubling_time_months": math.log10(2) / slope * 12 if slope > 0 else float("nan"),
        "r_squared": 1 - ss_res / ss_tot if ss_tot else float("nan"),
        "x_min": float(x.min()),
        "x_max": float(x.max()),
        "y_min_log10": float(y.min()),
        "y_max_log10": float(y.max()),
    }


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Deriving AI Companies tables from {raw}/ ...")
    dropped = {}

    # ---- revenue ---------------------------------------------------------
    rv = read(raw, "revenue")
    rv["date"] = pd.to_datetime(rv["Date"], errors="coerce")
    drop = excluded_mask(rv)
    dropped["revenue"] = int(drop.sum())
    rev = rv[~drop].dropna(subset=["date", "Annualized revenue (USD)"]).copy()
    rev = rev.rename(columns={
        "Company": "company", "Annualized revenue (USD)": "revenue_usd",
        "Annualized revenue type": "revenue_type", "Scope": "scope",
        "Confidence": "confidence", "Source type": "source_type"})
    rev["annualised_from_period"] = rev["revenue_type"] == "Period interpolation"
    rev = rev[["company", "date", "revenue_usd", "revenue_type", "scope",
               "confidence", "source_type", "annualised_from_period"]]
    rev.sort_values(["company", "date"]).to_csv(
        OUT / "companies_revenue.csv", index=False, date_format="%Y-%m-%d")
    print(f"  wrote companies_revenue.csv ({len(rev)} observations, "
          f"{rev['company'].nunique()} companies)")

    # ---- usage -----------------------------------------------------------
    us = read(raw, "usage")
    us["date"] = pd.to_datetime(us["Date"], errors="coerce")
    drop = excluded_mask(us)
    dropped["usage"] = int(drop.sum())
    use = us[~drop].dropna(subset=["date"]).copy()
    use = use.rename(columns={
        "Company": "company", "Active users": "active_users",
        "Active users time period": "active_users_period",
        "Daily tokens": "daily_tokens", "Daily messages": "daily_messages",
        "Product": "product", "Confidence": "confidence",
        "Source type": "source_type"})
    use = use[["company", "date", "product", "active_users", "active_users_period",
               "daily_tokens", "daily_messages", "confidence", "source_type"]]
    use.sort_values(["company", "date"]).to_csv(
        OUT / "companies_usage.csv", index=False, date_format="%Y-%m-%d")
    print(f"  wrote companies_usage.csv ({len(use)} observations, "
          f"{int(use['active_users'].notna().sum())} with active users, "
          f"{int(use['daily_tokens'].notna().sum())} with daily tokens)")

    # ---- staff -----------------------------------------------------------
    st = read(raw, "staff")
    st["date"] = pd.to_datetime(st["Date"], errors="coerce")
    drop = excluded_mask(st)
    dropped["staff"] = int(drop.sum())
    staff = st[~drop].dropna(subset=["date", "Staff count"]).copy()
    staff = staff.rename(columns={
        "Company": "company", "Staff count": "staff_count", "Type": "scope",
        "Division name": "division", "Confidence": "confidence",
        "Source type": "source_type"})
    staff = staff[["company", "date", "staff_count", "scope", "division",
                   "confidence", "source_type"]]
    staff.sort_values(["company", "date"]).to_csv(
        OUT / "companies_staff.csv", index=False, date_format="%Y-%m-%d")
    print(f"  wrote companies_staff.csv ({len(staff)} observations, "
          f"{staff['company'].nunique()} companies)")

    # ---- funding ---------------------------------------------------------
    fd = read(raw, "funding")
    fd["date"] = pd.to_datetime(fd["Close date"], errors="coerce")
    drop = excluded_mask(fd)
    dropped["funding"] = int(drop.sum())
    fund = fd[~drop].dropna(subset=["date"]).copy()
    # only rounds that actually closed carry money; discussions and the one
    # cancelled round are not raised capital and must not enter a total
    fund["closed"] = fund["Status"].astype(str).str.strip() == "Closed"
    fund = fund.rename(columns={
        "Company": "company", "Funding (equity)": "equity_usd",
        "Funding (debt)": "debt_usd", "Valuation (post-money)": "valuation_usd",
        "Status": "status", "Type": "round_type", "Confidence": "confidence"})
    fund = fund[["company", "date", "equity_usd", "debt_usd", "valuation_usd",
                 "status", "closed", "round_type", "confidence"]]
    fund.sort_values(["company", "date"]).to_csv(
        OUT / "companies_funding.csv", index=False, date_format="%Y-%m-%d")
    print(f"  wrote companies_funding.csv ({len(fund)} rounds, "
          f"{int(fund['closed'].sum())} closed)")

    # ---- compute spend ---------------------------------------------------
    cs = read(raw, "spend")
    cs["date"] = pd.to_datetime(cs["Date"], errors="coerce")
    drop = excluded_mask(cs)
    dropped["spend"] = int(drop.sum())
    spend = cs[~drop].dropna(subset=["date"]).copy()
    spend = spend.rename(columns={
        "Company": "company", "Amount": "amount_usd", "Category": "category",
        "Period type": "period_type", "Confidence": "confidence",
        "Inference compute spend": "inference_usd",
        "R&D compute spend": "rnd_usd", "Total compute spend": "total_usd"})
    spend = spend[["company", "date", "amount_usd", "category", "period_type",
                   "inference_usd", "rnd_usd", "total_usd", "confidence"]]
    spend.sort_values(["company", "date"]).to_csv(
        OUT / "companies_spend.csv", index=False, date_format="%Y-%m-%d")
    print(f"  wrote companies_spend.csv ({len(spend)} observations, "
          f"{spend['company'].nunique()} companies)")

    # ---- fitted growth trends -------------------------------------------
    trends = []
    for company, sub in rev.groupby("company"):
        f = fit_trend(sub, "revenue_usd", "date", company, "revenue_usd")
        if f:
            trends.append(f)
    for company, sub in staff[staff["scope"] == "Full company"].groupby("company"):
        f = fit_trend(sub, "staff_count", "date", company, "staff_count")
        if f:
            trends.append(f)
    for company, sub in use.groupby("company"):
        f = fit_trend(sub, "active_users", "date", company, "active_users")
        if f:
            trends.append(f)
    pd.DataFrame(trends).to_csv(OUT / "companies_trends.csv", index=False)
    print(f"  wrote companies_trends.csv ({len(trends)} fits at "
          f"{MIN_FIT_POINTS}+ points)")

    # ---- coverage: which company records which metric, and how often ------
    cov = []
    series = {
        "Revenue": rev.assign(v=rev["revenue_usd"]),
        "Active users": use[use["active_users"].notna()].assign(v=use["active_users"]),
        "Daily tokens": use[use["daily_tokens"].notna()].assign(v=use["daily_tokens"]),
        "Staff count": staff.assign(v=staff["staff_count"]),
        "Funding rounds": fund[fund["closed"]].assign(v=fund["equity_usd"]),
        "Valuation": fund[fund["valuation_usd"].notna()].assign(v=fund["valuation_usd"]),
        "Compute spend": spend.assign(v=spend["amount_usd"]),
    }
    companies = sorted(set().union(*(set(d["company"]) for d in series.values())))
    for company in companies:
        for metric, df in series.items():
            sub = df[df["company"] == company]
            cov.append({
                "company": company, "metric": metric, "observations": int(len(sub)),
                "first": sub["date"].min().date().isoformat() if len(sub) else "",
                "last": sub["date"].max().date().isoformat() if len(sub) else "",
            })
    pd.DataFrame(cov).to_csv(OUT / "companies_coverage.csv", index=False)
    print(f"  wrote companies_coverage.csv ({len(companies)} companies x "
          f"{len(series)} metrics)")

    # ---- provenance and the counts the charts quote ----------------------
    tracked = read(raw, "companies")
    prov = [{
        "tracked_companies": int(len(tracked)),
        "revenue_observations": int(len(rev)),
        "revenue_companies": int(rev["company"].nunique()),
        "revenue_interpolated": int(rev["annualised_from_period"].sum()),
        "usage_observations": int(len(use)),
        "usage_active_users": int(use["active_users"].notna().sum()),
        "usage_daily_tokens": int(use["daily_tokens"].notna().sum()),
        "staff_observations": int(len(staff)),
        "staff_companies": int(staff["company"].nunique()),
        "funding_rounds_closed": int(fund["closed"].sum()),
        "valuation_observations": int(fund["valuation_usd"].notna().sum()),
        "spend_observations": int(len(spend)),
        "spend_companies": int(spend["company"].nunique()),
        "excluded_by_epoch_revenue": dropped["revenue"],
        "excluded_by_epoch_usage": dropped["usage"],
        "excluded_by_epoch_staff": dropped["staff"],
        "excluded_by_epoch_funding": dropped["funding"],
        "excluded_by_epoch_spend": dropped["spend"],
        "observed_to": max(rev["date"].max(), use["date"].max(),
                           staff["date"].max(), fund["date"].max(),
                           spend["date"].max()).date().isoformat(),
    }]
    pd.DataFrame(prov).to_csv(OUT / "companies_summary.csv", index=False)
    print("  wrote companies_summary.csv")
    print(f"  Epoch 'exclude from graph view' rows dropped: "
          + ", ".join(f"{k} {v}" for k, v in dropped.items()))


if __name__ == "__main__":
    main()
