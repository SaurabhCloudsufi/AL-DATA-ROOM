#!/usr/bin/env python3
"""Derive the observed-only Epoch AI data centre series the gallery reproduces.

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
milestones, i.e. schedules, and are excluded here.

The reconciliation is asserted below, so if a future download shifts the cutoff
this script fails rather than silently publishing projections as observations.

Usage:
    python build/summarise_epoch_datacenters.py /path/to/epoch/csv/directory
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "ai-infrastructure" / "data"

SNAPSHOT = pd.Timestamp("2026-08-06")   # date this download represents
AXIS_START = pd.Timestamp("2023-01-01")  # Epoch's published axis starts here

METRICS = {
    "compute_h100e": ("H100 equivalents", "Current H100 equivalents"),
    "it_power_mw": ("IT power (MW)", "Current power (MW)"),
}


def step_total(timelines, col, asof):
    """Total across sites of each site's most recent cumulative snapshot.

    A few timeline rows leave a metric blank. Blank means "not restated at this
    milestone", not zero, so the site's most recent *recorded* value is carried
    forward. Taking the last row regardless would turn those into NaN and poison
    the total; treating them as zero would silently delete real capacity.
    """
    total = 0.0
    for _, g in timelines.sort_values("Date").groupby("Data center"):
        hist = g[(g.Date <= asof) & g[col].notna()]
        if len(hist):
            total += float(hist.iloc[-1][col])
    return total


def main(src: str) -> None:
    src = Path(src)
    for f in ("data_centers.csv", "data_center_timelines.csv"):
        if not (src / f).exists():
            sys.exit(f"missing {f} in {src}\n"
                     f"download from https://epoch.ai/data/data_centers/{f}")

    centres = pd.read_csv(src / "data_centers.csv")
    raw = pd.read_csv(src / "data_center_timelines.csv", parse_dates=["Date"])

    # sites in the timeline but absent from the site table cannot be reconciled
    # against Epoch's published totals, so they are excluded
    known = set(centres["Name"])
    excluded_sites = sorted(set(raw["Data center"]) - known)
    tl = raw[raw["Data center"].isin(known)]

    observed = tl[tl.Date <= SNAPSHOT]
    projected = tl[tl.Date > SNAPSHOT]

    # ------------------------------------------------------- reconciliation
    for key, (col, published) in METRICS.items():
        got = step_total(tl, col, SNAPSHOT)
        expected = centres[published].sum()
        # NaN fails every inequality, so test for it explicitly rather than
        # letting a poisoned total slip through the tolerance check
        if got != got or expected != expected:
            sys.exit(f"{key}: step-sum or published total is NaN - blank metric "
                     f"values are not being carried forward correctly.")
        if abs(got - expected) > max(0.5, abs(expected) * 1e-6):
            sys.exit(f"{key}: step-sum at {SNAPSHOT.date()} = {got:,.6g} but Epoch's "
                     f"'{published}' totals {expected:,.6g}. The observed cutoff no "
                     f"longer matches Epoch's own current figures - re-derive the "
                     f"snapshot date before publishing.")
        print(f"  reconciled {key}: {got:,.6g} == Epoch's '{published}'")

    # -------------------------------------------------- observed step series
    # A step function is fully described by its change points, so only the dates
    # where a site actually reported a milestone are written out.
    change_dates = sorted(set(observed.Date.tolist()) | {AXIS_START, SNAPSHOT})
    rows = []
    for d in change_dates:
        if d > SNAPSHOT:
            continue
        row = {"date": d.date().isoformat()}
        for key, (col, _) in METRICS.items():
            row[key] = round(step_total(observed, col, d), 6)
        rows.append(row)
    series = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date")
    series.to_csv(OUT / "epoch_observed_series.csv", index=False)

    # ---------------------------------------------------------------- summary
    meta = []
    for key, (col, published) in METRICS.items():
        meta.append({
            "metric": key,
            "column": col,
            "unit": "H100-equivalents" if key == "compute_h100e" else "MW",
            "records_in_file": len(raw),
            "records_after_site_join": len(tl),
            "records_observed": len(observed),
            "records_projected_excluded": len(projected),
            "sites_total": centres["Name"].nunique(),
            "sites_with_observed_data": observed["Data center"].nunique(),
            "observed_first": observed.Date.min().date().isoformat(),
            "observed_last": observed.Date.max().date().isoformat(),
            "projected_first_excluded": (projected.Date.min().date().isoformat()
                                         if len(projected) else ""),
            "projected_last_excluded": (projected.Date.max().date().isoformat()
                                        if len(projected) else ""),
            "snapshot_date": SNAPSHOT.date().isoformat(),
            "value_at_snapshot": round(step_total(tl, col, SNAPSHOT), 6),
            "value_if_projections_included": round(step_total(tl, col, tl.Date.max()), 6),
            "sites_excluded_no_site_record": "; ".join(excluded_sites),
        })
    pd.DataFrame(meta).to_csv(OUT / "epoch_observed_summary.csv", index=False)

    print(f"  records in file {len(raw)} -> after site join {len(tl)} -> "
          f"observed {len(observed)}, projected excluded {len(projected)}")
    print(f"  observed range {observed.Date.min().date()} .. {observed.Date.max().date()}")
    print(f"  sites excluded (no site record): {excluded_sites or 'none'}")
    print(f"  change points written: {len(series)}")
    for f in ("epoch_observed_series.csv", "epoch_observed_summary.csv"):
        print(f"wrote {(OUT / f).relative_to(REPO)}")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
