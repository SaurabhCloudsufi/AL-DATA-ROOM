#!/usr/bin/env python3
"""Derive the Tokens Per Day tables from the tokensperday.com extraction.

Reads the extraction exactly as staged into tokensperday/:

    chart_data/   the JavaScript objects that draw the site's own charts
    extraction/normalized/   the ledger, the estimates and the channel inputs
                             behind those charts

tokensperday.com is a static Astro build with no API and no data endpoint. Every
chart it draws comes from an object literal embedded in the homepage HTML, and
the extraction lifted those literals character-for-character. That has one
consequence which governs this whole domain:

  The plotted value is the site's own number. `Value` in chart_data is the
  figure the site's tooltip prints. Nothing here rounds it, interpolates it,
  refits it or recomputes it. Where the ledger holds more precision than the
  chart does — Google plots 105.1, the ledger holds 105.133 — both travel, and
  the chart's own number is the one plotted.

Three further decisions run through every table:

  Measured and modeled are kept apart. The site carries a `real` flag on every
  point. It matters in exactly one place and it matters a lot: the China line in
  the BY COUNTRY tab has 27 plotted points of which 3 are measured disclosures,
  and the other 24 are the site's own curve drawn between them. That flag is
  preserved rather than flattened into "data".

  The floor is six named rows, not a rollup. The disclosed floor is the sum of
  the six ledger rows flagged include_in_floor=yes. It is not the latest figure
  per company: Microsoft's in-floor row is its 2024-12-30 disclosure, while its
  later 2025-12-30 figure is out. Overlaps are marked `contained` — Doubao sits
  inside the China aggregate — and are excluded so nothing is counted twice.

  Estimates are bands, never points. Every per-company figure is a low/mid/high
  reconciliation of up to six channels, and the widths differ by two orders of
  magnitude between companies. Any table here that carries a mid carries its
  band beside it.

Usage:
    python build/summarise_tokensperday.py [source_dir]
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RAW = REPO / "tokensperday"
OUT = REPO / "tokens-per-day" / "data"

# the four regions the site splits the non-China total across; China is measured
# directly and is not part of the split
SPLIT_REGIONS = ["United States", "Europe", "Asia ex-China", "Rest of world"]


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    cd, nz = raw / "chart_data", raw / "extraction" / "normalized"
    if not cd.exists():
        sys.exit(f"missing {cd}\nStage the tokensperday extraction in {raw}/")
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Deriving Tokens Per Day tables from {raw.name}/ ...")

    # ---- the three tabs of the time-series chart, as one long table --------
    frames = []
    for tab, fname, entity_col in (
            ("TOTAL", "tokens_per_day_total.csv", None),
            ("COUNTRY", "tokens_per_day_country.csv", "Country/Region"),
            ("COMPANY", "tokens_per_day_company.csv", "Company")):
        d = pd.read_csv(cd / fname)
        d["tab"] = tab
        d["entity"] = d[entity_col] if entity_col else d["Series"]
        frames.append(d)
    ts = pd.concat(frames, ignore_index=True)
    ts = ts.rename(columns={
        "Date": "date", "Series": "series", "Value": "value", "Unit": "unit",
        "Source Name": "source_name", "Source Link": "source_link",
        "Archive Link": "archive_link", "Ledger Value (full precision)": "ledger_value",
        "Confidence": "confidence", "In Disclosed Floor": "in_floor",
        "Observation Type": "observation_type", "Is Real Observation": "is_real",
        "Series Color": "color"})
    cols = ["tab", "series", "entity", "date", "value", "unit", "is_real",
            "observation_type", "confidence", "in_floor", "ledger_value",
            "color", "source_name", "source_link", "archive_link"]
    ts = ts[cols].sort_values(["tab", "series", "date"])
    ts.to_csv(OUT / "tpd_timeseries.csv", index=False)
    print(f"  wrote tpd_timeseries.csv ({len(ts)} points, "
          f"{ts.series.nunique()} series across 3 tabs, "
          f"{int((~ts.is_real).sum())} modeled)")

    # ---- is the regional split four numbers or one? ------------------------
    # The site allocates non-China tokens across four regions by fixed shares.
    # If those shares are constant then four of the five country lines carry one
    # number's shape, which is a different claim from four measurements.
    ctry = ts[ts.tab == "COUNTRY"].pivot_table(index="date", columns="entity",
                                               values="value")
    have = ctry[SPLIT_REGIONS].dropna()
    non_china = have.sum(axis=1)
    shares = have.div(non_china, axis=0) * 100
    stated = pd.read_csv(nz / "geography" / "geography_allocation_shares.csv")
    stated = stated.set_index("region")["share_pct"]
    rs = pd.DataFrame({
        "region": SPLIT_REGIONS,
        "stated_share_pct": [_num(stated.get(r)) for r in SPLIT_REGIONS],
        "implied_share_mean_pct": [shares[r].mean() for r in SPLIT_REGIONS],
        "implied_share_min_pct": [shares[r].min() for r in SPLIT_REGIONS],
        "implied_share_max_pct": [shares[r].max() for r in SPLIT_REGIONS],
        "dates_checked": len(shares),
    })
    # The site plots to 0.1 T/day, so on a small base the rounding alone moves
    # the implied share by more than the allocation does: at a 3 T/day non-China
    # total, +-0.05 on one region is +-1.7pp. The stability test is therefore run
    # only where the base is large enough for the rounding not to swamp it.
    BASE_MIN = 10.0
    big = shares[non_china >= BASE_MIN]
    rs["spread_all_dates_pp"] = [shares[r].max() - shares[r].min()
                                 for r in SPLIT_REGIONS]
    rs["spread_where_base_over_10T_pp"] = [big[r].max() - big[r].min()
                                           for r in SPLIT_REGIONS]
    rs["dates_over_10T"] = len(big)
    rs["rounding_tolerance_pp"] = 0.05 / non_china[non_china >= BASE_MIN].min() * 100
    rs.to_csv(OUT / "tpd_region_shares.csv", index=False, float_format="%.4f")
    print(f"  wrote tpd_region_shares.csv (4 regions, {len(shares)} dates; "
          f"shares hold to {rs.spread_where_base_over_10T_pp.max():.2f}pp over "
          f"the {int(rs.dates_over_10T.iloc[0])} dates with a base above "
          f"{BASE_MIN:.0f}T/day)")

    # ---- the 24-hour cycle -------------------------------------------------
    h = pd.read_csv(cd / "hourly_tokens.csv").rename(columns={
        "Hour (UTC)": "hour_utc", "Series": "series", "Value": "pct_of_peak",
        "Is Peak Hour": "is_peak", "Series Color": "color",
        "Source Name": "source_name", "Source Link": "source_link",
        "Observation Type": "observation_type"})
    h = h[["series", "hour_utc", "pct_of_peak", "is_peak", "observation_type",
           "color", "source_name", "source_link"]].sort_values(["series", "hour_utc"])
    h.to_csv(OUT / "tpd_hourly.csv", index=False)
    peaks = h[h.is_peak].set_index("series").hour_utc.to_dict()
    print(f"  wrote tpd_hourly.csv ({h.series.nunique()} series x 24 hours; "
          f"peaks {', '.join(f'{k} {v:02d}:00' for k, v in sorted(peaks.items()))})")

    # ---- cumulative, and whether it is the daily estimate added up ---------
    cu = pd.read_csv(cd / "cumulative_tokens.csv").rename(columns={
        "Date": "date", "Value": "cumulative_quadrillions",
        "Value (tokens)": "cumulative_tokens", "Series Since": "series_since"})
    cu = cu[["date", "cumulative_quadrillions", "cumulative_tokens", "series_since"]]
    # trapezoid integral of the plotted daily estimate, in quadrillions:
    # (T/day x days) / 1000
    est = ts[(ts.tab == "TOTAL") & (ts.series == "Estimated total")].copy()
    est["d"] = pd.to_datetime(est.date)
    days = (est.d - est.d.iloc[0]).dt.days.to_numpy()
    v = est.value.to_numpy()
    integral = [0.0]
    for i in range(1, len(v)):
        integral.append(integral[-1] + (days[i] - days[i - 1]) * (v[i] + v[i - 1]) / 2)
    chk = pd.DataFrame({"date": est.date.to_numpy(),
                        "integral_quadrillions": [x / 1000 for x in integral]})
    cu = cu.merge(chk, on="date", how="left")
    cu["integral_diff_pct"] = ((cu.integral_quadrillions - cu.cumulative_quadrillions)
                               / cu.cumulative_quadrillions.replace(0, pd.NA) * 100)
    cu.to_csv(OUT / "tpd_cumulative.csv", index=False, float_format="%.6g")
    worst = cu.integral_diff_pct.abs().max()
    print(f"  wrote tpd_cumulative.csv ({len(cu)} quarters; the published curve is "
          f"the daily estimate integrated, agreeing to {worst:.2f}%)")

    # ---- the quarterly estimate band --------------------------------------
    b = pd.read_csv(cd / "estimate_band_quarterly.csv")
    band = b.pivot_table(index="Date", columns="Series", values="Value").reset_index()
    band.columns.name = None
    band = band.rename(columns={"Date": "date", "Estimated total (low)": "low",
                                "Estimated total (mid)": "mid",
                                "Estimated total (high)": "high"})
    band["band_ratio_high_over_low"] = band.high / band.low
    band["qoq_growth_multiple"] = band["mid"] / band["mid"].shift(1)
    # the TOTAL tab plots this same mid; carrying both proves it rather than
    # asserting it, and the gap is the band table's own rounding to 0.1
    plotted = est.set_index("date").value
    band["total_tab_mid"] = band.date.map(plotted)
    band["mid_diff_pct"] = (band.total_tab_mid - band["mid"]) / band["mid"] * 100
    band.to_csv(OUT / "tpd_estimate_band.csv", index=False, float_format="%.6g")
    print(f"  wrote tpd_estimate_band.csv ({len(band)} quarters; band "
          f"{band.band_ratio_high_over_low.iloc[-1]:.2f}x wide at the end, "
          f"matches the TOTAL tab to {band.mid_diff_pct.abs().max():.2f}%)")

    # ---- the evidence ledger ----------------------------------------------
    led = pd.read_csv(nz / "disclosures" / "evidence_ledger.csv")
    led = led.rename(columns={"tokens_per_day_trillions": "t_per_day",
                              "include_in_floor": "floor_status"})
    keep = ["entity", "region", "observation_scope", "ledger", "t_per_day",
            "as_of_date", "confidence", "floor_status", "source_title",
            "source_url", "archive_url", "archive_status"]
    led = led[keep].sort_values("t_per_day", ascending=False)
    led.to_csv(OUT / "tpd_ledger.csv", index=False)
    floor = led[led.floor_status == "yes"]
    print(f"  wrote tpd_ledger.csv ({len(led)} disclosures, "
          f"{led.entity.nunique()} entities; {len(floor)} sum to the "
          f"{floor.t_per_day.sum():.1f}T/day floor; "
          f"{int((led.archive_status == 'archived').sum())} archived)")

    # ---- the reconciled per-company bands ---------------------------------
    rec = pd.read_csv(nz / "estimates" / "reconciled_company_estimates.csv")
    rec = rec.rename(columns={"low_t_per_day": "low", "mid_t_per_day": "mid",
                              "high_t_per_day": "high",
                              "dispersion_ratio_high_over_low": "dispersion"})
    rec = rec[["entity", "low", "mid", "high", "dispersion", "primary_channel",
               "notes"]]
    rec["in_global_sum"] = [
        "" if e == "GLOBAL" else ("no" if "EXCLUDED" in str(n) else "yes")
        for e, n in zip(rec.entity, rec.notes)]
    rec.to_csv(OUT / "tpd_reconciled.csv", index=False, float_format="%.6g")
    comp = rec[rec.entity != "GLOBAL"]
    print(f"  wrote tpd_reconciled.csv ({len(comp)} companies + GLOBAL; "
          f"dispersion {comp.dispersion.min():.1f}x to {comp.dispersion.max():.1f}x)")

    # ---- the channel fan behind each of those bands ------------------------
    fan = pd.read_csv(nz / "estimates" / "channel_fan_per_company.csv")
    fan = fan.rename(columns={"low_t_per_day": "low", "mid_t_per_day": "mid",
                              "high_t_per_day": "high"})
    fan = fan[["entity", "channel", "low", "mid", "high", "value_kind",
               "confidence", "backtest_ratio", "backtest_verdict",
               "included_in_reconciliation", "formula"]]
    fan.to_csv(OUT / "tpd_channels.csv", index=False, float_format="%.6g")
    print(f"  wrote tpd_channels.csv ({len(fan)} channel estimates over "
          f"{fan.entity.nunique()} entities; "
          f"{int((fan.included_in_reconciliation == 'no').sum())} excluded on backtest)")

    # ---- the hardware-side capacity check ---------------------------------
    cap = pd.read_csv(nz / "channel_inputs" / "capacity_parameters.csv")
    cap = cap.rename(columns={"parameter": "parameter", "unit": "unit"})
    cap = cap[["parameter", "unit", "low", "mid", "high", "basis"]]
    cap.to_csv(OUT / "tpd_capacity.csv", index=False)
    print(f"  wrote tpd_capacity.csv ({len(cap) - 1} parameters + the compounded "
          f"capacity band)")

    # ---- this index against the independent estimates ---------------------
    cmp_ = pd.read_csv(nz / "global" / "comparison_vs_independent_estimates.csv")
    cmp_ = cmp_.rename(columns={"t_per_day": "t_per_day_raw_text"})
    cmp_["t_per_day"] = _num(cmp_.t_per_day_raw_text)
    cmp_ = cmp_[["source", "scope", "t_per_day", "t_per_day_raw_text", "as_of",
                 "confidence", "is_this_index"]]
    cmp_.to_csv(OUT / "tpd_comparison.csv", index=False)
    print(f"  wrote tpd_comparison.csv ({len(cmp_)} estimates, "
          f"{int(cmp_.t_per_day.notna().sum())} with a single plottable figure)")

    # ---- provenance --------------------------------------------------------
    head = pd.read_csv(nz / "global" / "headline_metrics.csv").set_index("metric")
    pd.DataFrame([{
        "source_site": "https://tokensperday.com/",
        "extracted": "2026-08-21",
        "data_last_verified": head.loc["data_last_verified", "value"],
        "chart_points": int(len(ts)),
        "chart_series": int(ts.series.nunique()),
        "modeled_points": int((~ts.is_real).sum()),
        "ledger_rows": int(len(led)),
        "ledger_entities": int(led.entity.nunique()),
        "floor_rows": int(len(floor)),
        "floor_t_per_day": float(floor.t_per_day.sum()),
        "headline_t_per_day": float(head.loc["global_tokens_per_day_today", "value"]),
        "band_low_t_per_day": float(head.loc["estimated_total_band_low", "value"]),
        "band_high_t_per_day": float(head.loc["estimated_total_band_high", "value"]),
        "capacity_mid_t_per_day": float(head.loc["compute_capacity_mid", "value"]),
        "demand_share_of_mid_capacity_pct": float(
            head.loc["demand_share_of_mid_capacity", "value"]),
        "cumulative_quadrillions": float(head.loc["cumulative_all_time", "value"]),
        "cumulative_integral_worst_diff_pct": float(worst),
        "region_share_spread_pp": float(rs.spread_where_base_over_10T_pp.max()),
        "region_share_dates_tested": int(rs.dates_over_10T.iloc[0]),
    }]).to_csv(OUT / "tpd_summary.csv", index=False)
    print("  wrote tpd_summary.csv")


if __name__ == "__main__":
    main()
