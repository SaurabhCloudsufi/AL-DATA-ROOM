#!/usr/bin/env python3
"""Summarise the Epoch AI data centers dataset into small, committable CSVs.

Source: Epoch AI, "AI Data Centers" - https://epoch.ai/data/ai-data-centers
Files (CC-BY) are published at https://epoch.ai/data/data_centers/<name>.csv and
are not duplicated into this repository; only the derived aggregates the charts
read are committed.

    data_centers.csv                 one row per site, with owner and country
    data_center_timelines.csv        dated snapshots per site
    data_center_chip_quantities.csv  dated chip counts per site and chip type
    data_center_cooling_towers.csv   equipment reference table
    data_center_chillers.csv         equipment reference table

Aggregation. Every dated row in the timeline and chip files is a *cumulative*
snapshot of that site, not an increment. A site's value on any date is therefore
its most recent snapshot at or before that date, and zero before its first one.
Summing those step functions across sites reproduces Epoch's own "current"
column exactly - the check is asserted below rather than assumed.

Everything from the snapshot date onward is Epoch's projection from announced
construction schedules, not observation. The split date is carried into the
derived files so the charts can draw it.

Usage:
    python build/summarise_epoch_datacenters.py /path/to/epoch/csv/directory
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "ai-infrastructure" / "data"

# The snapshot these files were downloaded at. Epoch updates the dataset in
# place, so the "current" totals only reconcile against this date.
SNAPSHOT = pd.Timestamp("2026-08-06")

GRID_START, GRID_END = "2023-01-01", "2030-01-01"

METRICS = {
    "compute_h100e": "H100 equivalents",
    "it_power_mw": "IT power (MW)",
    "capital_cost_busd": "Total capital cost (2025 USD billions)",
}


def clean_owner(o):
    """Strip Epoch's confidence tag: 'Google #confident' -> ('Google', 'confident')."""
    if not isinstance(o, str) or not o.strip():
        return "Unknown", ""
    if "#" in o:
        name, _, conf = o.partition("#")
        return name.strip(), conf.strip()
    return o.strip(), ""


def step_sum(df, key, value_col, grid, group):
    """Forward-fill each entity's cumulative snapshots onto grid, then sum by group."""
    out = {}
    for name, g in df.sort_values("Date").groupby(key):
        s = g.set_index("Date")[value_col].astype(float)
        s = s[~s.index.duplicated(keep="last")]
        series = s.reindex(grid.union(s.index)).ffill().reindex(grid).fillna(0.0)
        out.setdefault(group.get(name, "Unknown"), []).append(series)
    return {k: sum(v) for k, v in out.items()}


def main(src: str) -> None:
    src = Path(src)
    need = ["data_centers.csv", "data_center_timelines.csv",
            "data_center_chip_quantities.csv", "data_center_cooling_towers.csv",
            "data_center_chillers.csv"]
    missing = [f for f in need if not (src / f).exists()]
    if missing:
        sys.exit("missing source files: " + ", ".join(missing) +
                 f"\ndownload them from https://epoch.ai/data/data_centers/ into {src}")

    centres = pd.read_csv(src / "data_centers.csv")
    timelines = pd.read_csv(src / "data_center_timelines.csv", parse_dates=["Date"])

    # sites present in the timeline but absent from the site table are excluded,
    # so the totals reconcile against Epoch's own "current" columns
    known = set(centres["Name"])
    dropped = sorted(set(timelines["Data center"]) - known)
    timelines = timelines[timelines["Data center"].isin(known)]

    owner_of, conf_of = {}, {}
    for _, r in centres.iterrows():
        name, conf = clean_owner(r["Owner"])
        owner_of[r["Name"]] = name
        conf_of[r["Name"]] = conf
    country_of = dict(zip(centres["Name"], centres["Country"]))

    grid = pd.date_range(GRID_START, GRID_END, freq="QS")

    # ---------------------------------------------------------- reconciliation
    checks = {
        "compute_h100e": centres["Current H100 equivalents"].sum(),
        "capital_cost_busd": centres["Current total capital cost (2025 USD billions)"].sum(),
    }
    asof = pd.DatetimeIndex([SNAPSHOT])
    for key, expected in checks.items():
        got = sum(step_sum(timelines, "Data center", METRICS[key], asof,
                           {n: "all" for n in known}).get("all", pd.Series([0.0])))
        if abs(got - expected) > max(1.0, abs(expected) * 1e-6):
            sys.exit(f"{key}: step-sum at {SNAPSHOT.date()} = {got:,.6g} but the site "
                     f"table says {expected:,.6g}. The aggregation no longer matches "
                     f"Epoch's own totals - do not publish until this reconciles.")
        print(f"  reconciled {key}: {got:,.6g} matches the site table")

    # ------------------------------------------------- metric series by owner
    rows = []
    for key, col in METRICS.items():
        by_owner = step_sum(timelines, "Data center", col, grid, owner_of)
        for owner, series in by_owner.items():
            for date, value in series.items():
                rows.append({"metric": key, "group_kind": "owner", "group": owner,
                             "date": date.date().isoformat(), "value": round(float(value), 6)})
        by_country = step_sum(timelines, "Data center", col, grid, country_of)
        for country, series in by_country.items():
            for date, value in series.items():
                rows.append({"metric": key, "group_kind": "country", "group": country,
                             "date": date.date().isoformat(), "value": round(float(value), 6)})
    pd.DataFrame(rows).to_csv(OUT / "dc_metric_timeseries.csv", index=False)

    # ------------------------------------------------------------- chip mix
    chips = pd.read_csv(src / "data_center_chip_quantities.csv", parse_dates=["Date"])
    chips["pair"] = chips["Data center"] + " || " + chips["Chip type"]
    chip_of = dict(zip(chips["pair"], chips["Chip type"]))
    by_chip = step_sum(chips, "pair", "Number of Units", grid, chip_of)
    crows = [{"date": d.date().isoformat(), "chip_type": c, "units": round(float(v), 3)}
             for c, s in by_chip.items() for d, v in s.items()]
    pd.DataFrame(crows).to_csv(OUT / "dc_chip_mix.csv", index=False)
    disclosed = (chips["Number of Units source"].str.strip().str.lower()
                 == "company disclosure").sum()

    # ------------------------------------------------------ cooling equipment
    towers = pd.read_csv(src / "data_center_cooling_towers.csv")
    chillers = pd.read_csv(src / "data_center_chillers.csv")
    eq = []
    for _, r in towers.iterrows():
        eq.append({"equipment": "Cooling tower (wet)", "manufacturer": r["Manufacturer"],
                   "area_m2": r["Area (m^2)"],
                   "capacity_kw": r["Cooling capacity (central estimate, kW)"]})
    for _, r in chillers.iterrows():
        eq.append({"equipment": f"Chiller ({str(r['Type']).lower()})",
                   "manufacturer": r["Manufacturer"], "area_m2": r["Area (m^2)"],
                   "capacity_kw": r["Cooling capacity (kW)"]})
    eqdf = pd.DataFrame(eq)
    usable = eqdf[(eqdf.area_m2 > 0) & (eqdf.capacity_kw > 0)]
    eqdf.to_csv(OUT / "dc_cooling_equipment.csv", index=False)

    # --------------------------------------------------------------- headline
    pd.DataFrame([{
        "snapshot_date": SNAPSHOT.date().isoformat(),
        "sites": len(centres),
        "owners": len({owner_of[n] for n in known}),
        "countries": centres["Country"].nunique(),
        "current_h100e": round(float(centres["Current H100 equivalents"].sum()), 3),
        "current_capital_cost_busd": round(
            float(centres["Current total capital cost (2025 USD billions)"].sum()), 6),
        "chip_rows": len(chips),
        "chip_rows_company_disclosed": int(disclosed),
        "cooling_equipment_rows": len(eqdf),
        "cooling_equipment_usable": len(usable),
        "timeline_sites_excluded": "; ".join(dropped),
    }]).to_csv(OUT / "dc_summary.csv", index=False)

    print(f"  excluded from timeline (not in site table): {dropped or 'none'}")
    print(f"  chip rows: {len(chips)}, of which company-disclosed: {disclosed}")
    print(f"  cooling equipment: {len(eqdf)} rows, {len(usable)} usable on log axes")
    for f in ["dc_metric_timeseries.csv", "dc_chip_mix.csv",
              "dc_cooling_equipment.csv", "dc_summary.csv"]:
        print(f"wrote {(OUT / f).relative_to(REPO)}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
