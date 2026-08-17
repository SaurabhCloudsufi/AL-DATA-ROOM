#!/usr/bin/env python3
"""Derive the observed-only Epoch AI data centre aggregates the gallery reads.

Source: Epoch AI, "AI Data Centers" (CC-BY) - https://epoch.ai/data/ai-data-centers
Raw files are not committed; only the derived series the charts read.

WHAT COUNTS AS OBSERVED
-----------------------
Epoch's files carry no observed/projected flag. That was checked rather than
assumed: the phrase "estimate" in Construction status does NOT mark projections -
30 rows dated in the past contain it (they are estimates *about* a state already
reached, e.g. "Building 4 operational. Based on our default estimate of
roof-to-operational time"), while 29 future-dated rows omit it despite plainly
being schedules ("Buildings 7-8 assumed operational", "Assuming the foundation
starts at the end of May 2026"). Filtering on that text would keep projections
and drop observations.

The defensible boundary is the date, and the dataset itself fixes it. Step-summing
each site's most recent snapshot reproduces Epoch's own "Current" columns exactly
- 12,934,582 H100-equivalents and 12,115.1 MW IT power - for every cutoff from
2026-08-04 to 2026-08-11, and diverges outside that window. Epoch therefore treats
this snapshot date as "now"; the last milestone actually recorded is 2026-08-02
and the next lands 2026-08-12. Rows dated after the snapshot are future-dated
milestones, i.e. schedules, and are excluded everywhere in this script.

The reconciliation is asserted below, so if a future download shifts the cutoff
this script fails rather than silently publishing projections as observations.

NOT DERIVED
-----------
"Water use (MGD)" is left out. Only 23 sites carry it, 51 of 59 observed rows are
zero, and the one large value (Meta Kuna, 70,000 MGD at 152 MW IT power) is four
orders of magnitude away from comparable sites (Google New Albany, 0.966 MGD at
147 MW). The field is not internally consistent enough to chart.

Usage:
    python build/summarise_epoch_datacenters.py /path/to/epoch/csv/directory
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "ai-infrastructure" / "data"

SNAPSHOT = pd.Timestamp("2026-08-06")    # date this download represents
AXIS_START = pd.Timestamp("2023-01-01")  # Epoch's published axis starts here

# metric key -> (timeline column, published "current" column to reconcile against)
METRICS = {
    "compute_h100e": ("H100 equivalents", "Current H100 equivalents"),
    "it_power_mw": ("IT power (MW)", "Current power (MW)"),
    "capital_cost_busd": ("Total capital cost (2025 USD billions)",
                          "Current total capital cost (2025 USD billions)"),
}

COST_PARTS = {
    "compute_cost_busd": "Compute cost (2025 USD billions)",
    "construction_cost_busd": "Construction cost (2025 USD billions)",
    "annual_opex_busd": "Annual operating cost (2025 USD billions)",
}


def strip_conf(v):
    """'Google #confident' -> ('Google', 'confident'); blank -> ('Unknown', '')."""
    if not isinstance(v, str) or not v.strip():
        return "Unknown", ""
    head = v.split(",")[0]
    if "#" in head:
        name, _, conf = head.partition("#")
        return name.strip(), conf.strip()
    return head.strip(), ""


def last_value(g, col, asof):
    """Site's most recent *recorded* value at or before asof.

    A blank cell means "not restated at this milestone", not zero, so blanks are
    skipped and the previous recorded value carries forward. Taking the last row
    regardless would return NaN and poison every total it feeds.
    """
    hist = g[(g.Date <= asof) & g[col].notna()]
    return float(hist.iloc[-1][col]) if len(hist) else None


def step_total(timelines, col, asof):
    total = 0.0
    for _, g in timelines.sort_values("Date").groupby("Data center"):
        v = last_value(g, col, asof)
        if v is not None:
            total += v
    return total


def main(src: str) -> None:
    src = Path(src)
    need = ["data_centers.csv", "data_center_timelines.csv",
            "data_center_chip_quantities.csv", "data_center_cooling_towers.csv",
            "data_center_chillers.csv"]
    missing = [f for f in need if not (src / f).exists()]
    if missing:
        sys.exit("missing source files: " + ", ".join(missing) +
                 "\ndownload from https://epoch.ai/data/data_centers/")

    centres = pd.read_csv(src / "data_centers.csv")
    raw = pd.read_csv(src / "data_center_timelines.csv", parse_dates=["Date"])

    known = set(centres["Name"])
    excluded_sites = sorted(set(raw["Data center"]) - known)
    tl = raw[raw["Data center"].isin(known)]
    observed = tl[tl.Date <= SNAPSHOT]
    projected = tl[tl.Date > SNAPSHOT]

    owner_of, user_of, country_of = {}, {}, {}
    for _, r in centres.iterrows():
        owner_of[r["Name"]] = strip_conf(r["Owner"])[0]
        user_of[r["Name"]] = strip_conf(r.get("Users"))[0]
        country_of[r["Name"]] = r["Country"]

    # ------------------------------------------------------- reconciliation
    for key, (col, published) in METRICS.items():
        got = step_total(tl, col, SNAPSHOT)
        expected = centres[published].sum()
        if got != got or expected != expected:
            sys.exit(f"{key}: NaN in the totals - blank cells are not carrying forward.")
        if abs(got - expected) > max(0.5, abs(expected) * 1e-6):
            sys.exit(f"{key}: step-sum at {SNAPSHOT.date()} = {got:,.6g} but Epoch's "
                     f"'{published}' totals {expected:,.6g}. The observed cutoff no "
                     f"longer matches Epoch's current figures - re-derive before publishing.")
        print(f"  reconciled {key}: {got:,.6g} == Epoch's '{published}'")

    # cost identity holds exactly in the source, so it is asserted not assumed
    ci = observed.dropna(subset=[METRICS["capital_cost_busd"][0],
                                 COST_PARTS["compute_cost_busd"],
                                 COST_PARTS["construction_cost_busd"]])
    err = (ci[METRICS["capital_cost_busd"][0]] - ci[COST_PARTS["compute_cost_busd"]]
           - ci[COST_PARTS["construction_cost_busd"]]).abs().max()
    if err > 1e-6:
        sys.exit(f"cost identity broken: max |total-(compute+construction)| = {err:.6g}")
    print(f"  cost identity holds: total == compute + construction (max err {err:.2g})")

    # ------------------------------------- observed totals (change points only)
    change_dates = sorted({d for d in observed.Date} | {AXIS_START, SNAPSHOT})
    rows = []
    for d in change_dates:
        if d > SNAPSHOT:
            continue
        row = {"date": d.date().isoformat()}
        for key, (col, _) in METRICS.items():
            row[key] = round(step_total(observed, col, d), 6)
        rows.append(row)
    pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").to_csv(
        OUT / "epoch_observed_series.csv", index=False)

    # -------------------------------- observed series per owner (change points)
    # Only the dates where an owner's own total moved are written; the chart
    # forward-fills, which is the same step semantics used everywhere here.
    orows = []
    for owner in sorted(set(owner_of[n] for n in known)):
        sites = [n for n in known if owner_of[n] == owner]
        sub = observed[observed["Data center"].isin(sites)]
        if sub.empty:
            continue
        dates = sorted({AXIS_START} | set(sub.Date) | {SNAPSHOT})
        prev = None
        for d in dates:
            if d > SNAPSHOT:
                continue
            vals = {k: round(step_total(sub, c, d), 6) for k, (c, _) in METRICS.items()}
            if vals != prev:
                orows.append({"date": d.date().isoformat(), "owner": owner, **vals})
                prev = vals
    pd.DataFrame(orows).to_csv(OUT / "epoch_observed_by_owner.csv", index=False)

    # ------------------------------------------- per-site snapshot (observed)
    srows = []
    for name, g in observed.sort_values("Date").groupby("Data center"):
        rec = {"site": name, "owner": owner_of[name], "primary_user": user_of[name],
               "country": country_of[name]}
        for key, (col, _) in METRICS.items():
            rec[key] = round(last_value(g, col, SNAPSHOT) or 0.0, 6)
        for key, col in COST_PARTS.items():
            rec[key] = round(last_value(g, col, SNAPSHOT) or 0.0, 6)
        rec["buildings_operational"] = last_value(g, "Buildings operational", SNAPSHOT) or 0
        srows.append(rec)
    pd.DataFrame(srows).sort_values("compute_h100e", ascending=False).to_csv(
        OUT / "dc_sites_observed.csv", index=False)

    # ------------------------------------------------ chip mix (observed only)
    chips = pd.read_csv(src / "data_center_chip_quantities.csv", parse_dates=["Date"])
    chips_obs = chips[chips.Date <= SNAPSHOT]
    chips["src_norm"] = (chips["Number of Units source"].astype(str).str.strip()
                         .str.lower().replace({"esimate": "estimate"}))
    pair_last = chips_obs.sort_values("Date").groupby(["Data center", "Chip type"]).tail(1)
    cdates = sorted({AXIS_START} | set(chips_obs.Date) | {SNAPSHOT})
    crows = []
    for chip in sorted(chips_obs["Chip type"].unique()):
        sub = chips_obs[chips_obs["Chip type"] == chip]
        prev = None
        for d in cdates:
            if d > SNAPSHOT:
                continue
            tot = 0.0
            for _, g in sub.sort_values("Date").groupby("Data center"):
                h = g[(g.Date <= d) & g["Number of Units"].notna()]
                if len(h):
                    tot += float(h.iloc[-1]["Number of Units"])
            if tot != prev:
                crows.append({"date": d.date().isoformat(), "chip_type": chip,
                              "units": round(tot, 3)})
                prev = tot
    pd.DataFrame(crows).to_csv(OUT / "dc_chip_mix_observed.csv", index=False)

    # ------------------------------------------------------ cooling equipment
    towers = pd.read_csv(src / "data_center_cooling_towers.csv")
    chillers = pd.read_csv(src / "data_center_chillers.csv")
    eq = [{"equipment": "Cooling tower (wet)", "manufacturer": r["Manufacturer"],
           "area_m2": r["Area (m^2)"],
           "capacity_kw": r["Cooling capacity (central estimate, kW)"]}
          for _, r in towers.iterrows()]
    eq += [{"equipment": f"Chiller ({str(r['Type']).lower()})",
            "manufacturer": r["Manufacturer"], "area_m2": r["Area (m^2)"],
            "capacity_kw": r["Cooling capacity (kW)"]}
           for _, r in chillers.iterrows()]
    eqdf = pd.DataFrame(eq)
    eqdf.to_csv(OUT / "dc_cooling_equipment.csv", index=False)
    usable = eqdf[(eqdf.area_m2 > 0) & (eqdf.capacity_kw > 0)]

    # --------------------------------------------------------------- summary
    meta = []
    for key, (col, published) in METRICS.items():
        meta.append({
            "metric": key, "column": col,
            "unit": {"compute_h100e": "H100-equivalents", "it_power_mw": "MW",
                     "capital_cost_busd": "2025 US$ billions"}[key],
            "records_in_file": len(raw),
            "records_after_site_join": len(tl),
            "records_observed": len(observed),
            "records_projected_excluded": len(projected),
            "sites_total": centres["Name"].nunique(),
            "sites_with_observed_data": observed["Data center"].nunique(),
            "observed_first": observed.Date.min().date().isoformat(),
            "observed_last": observed.Date.max().date().isoformat(),
            "snapshot_date": SNAPSHOT.date().isoformat(),
            "value_at_snapshot": round(step_total(tl, col, SNAPSHOT), 6),
            "value_if_projections_included": round(step_total(tl, col, tl.Date.max()), 6),
            "sites_excluded_no_site_record": "; ".join(excluded_sites),
            "chip_records_total": len(chips),
            "chip_records_observed": len(chips_obs),
            "chip_records_projected_excluded": int((chips.Date > SNAPSHOT).sum()),
            "chip_units_company_disclosed": int((chips["src_norm"] == "company disclosure").sum()),
            "cooling_rows": len(eqdf), "cooling_rows_usable": len(usable),
            "countries": centres["Country"].nunique(),
            "owners": len({owner_of[n] for n in known}),
            "sites_with_primary_user": int(centres["Users"].notna().sum()),
        })
    pd.DataFrame(meta).to_csv(OUT / "epoch_observed_summary.csv", index=False)

    print(f"  timeline: {len(raw)} rows -> {len(tl)} after site join -> "
          f"{len(observed)} observed, {len(projected)} projected excluded")
    print(f"  chips: {len(chips)} rows -> {len(chips_obs)} observed, "
          f"{(chips.Date > SNAPSHOT).sum()} projected excluded")
    print(f"  sites excluded (no site record): {excluded_sites or 'none'}")
    for f in ("epoch_observed_series.csv", "epoch_observed_by_owner.csv",
              "dc_sites_observed.csv", "dc_chip_mix_observed.csv",
              "dc_cooling_equipment.csv", "epoch_observed_summary.csv"):
        print(f"wrote {(OUT / f).relative_to(REPO)}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
