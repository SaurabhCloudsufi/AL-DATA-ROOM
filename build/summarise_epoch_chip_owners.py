#!/usr/bin/env python3
"""Derive the AI Chip Owners tables from Epoch AI's published dataset.

Reads the three files exactly as downloaded from epoch.ai into ai_chip_owners/:

    cumulative_by_designer.csv    installed base by owner and chip manufacturer
    cumulative_by_chip_type.csv   the same, broken out to 25 chip types
    quarters_by_chip_type.csv     what was added in each quarter, not the total

Two rules decide what reaches a chart.

  Incomplete quarters are excluded. Epoch flags rows it considers incomplete,
  and every row in the final quarter of this download carries that flag: it
  holds 8 rows against 19 the quarter before, 7 owners against 10, and the
  cumulative total FALLS from 20.9M H100e to 17.1M. A cumulative series cannot
  fall. Charting it would show deployed compute dropping 18% when what dropped
  is coverage. The window is the last quarter where nothing is flagged.

  Ownership is estimated, not disclosed. Epoch publishes a 5th and 95th
  percentile beside every median because almost none of this is reported by the
  owners. The interval is wide and uneven - nearly twice the median for smuggled
  Chinese capacity, an eighth of it for CoreWeave - so it is carried through
  here and charted directly rather than dropped.

H100e is Epoch's normalising unit: an H100-equivalent of compute, so a TPU and a
Blackwell can be added. It flattens real differences in how those chips serve
inference, which is a limit on every total here.

Usage:
    python build/summarise_epoch_chip_owners.py [source_dir]
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RAW = REPO / "ai_chip_owners"
OUT = REPO / "ai-chip-owners" / "data"

FILES = {
    "designer": "cumulative_by_designer.csv",
    "chip_type": "cumulative_by_chip_type.csv",
    "quarters": "quarters_by_chip_type.csv",
}
MED = "Compute estimate in H100e (median)"
P5 = "H100e (5th percentile)"
P95 = "H100e (95th percentile)"

# owners that are aggregates rather than companies, flagged so no chart implies
# "China" is an organisation the way Meta is
AGGREGATE_OWNERS = {"Other", "China", "China (smuggled)"}


def read(raw, key):
    path = raw / FILES[key]
    if not path.exists():
        sys.exit(f"missing {path}\nDownload the AI Chip Owners files from "
                 f"epoch.ai/data/ai-chip-owners into {raw}/")
    d = pd.read_csv(path, low_memory=False)
    d["quarter"] = pd.to_datetime(d["End date"]).dt.to_period("Q")
    d["incomplete"] = d["Incomplete"].notna()
    return d


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Deriving AI Chip Owners tables from {raw}/ ...")

    des = read(raw, "designer")
    typ = read(raw, "chip_type")
    qtr = read(raw, "quarters")

    # ---- the complete window ---------------------------------------------
    complete = sorted(q for q in des.quarter.unique()
                      if not des[des.quarter == q].incomplete.any())
    last, first = complete[-1], complete[0]
    excluded = sorted(str(q) for q in des.quarter.unique() if q not in complete)
    print(f"  complete window {first} to {last}; excluded {excluded or 'none'}")

    def window(d):
        return d[(d.quarter >= first) & (d.quarter <= last) & (~d.incomplete)].copy()

    des_w, typ_w, qtr_w = window(des), window(typ), window(qtr)

    # ---- installed base by owner, quarter by quarter ----------------------
    by_owner = (des_w.groupby(["quarter", "Owner"], as_index=False)
                     .agg(h100e=(MED, "sum"), h100e_p5=(P5, "sum"),
                          h100e_p95=(P95, "sum"), units=("Number of Units (median)", "sum")))
    by_owner["quarter"] = by_owner["quarter"].astype(str)
    by_owner["is_aggregate"] = by_owner["Owner"].isin(AGGREGATE_OWNERS)
    by_owner = by_owner.rename(columns={"Owner": "owner"})
    by_owner.sort_values(["quarter", "h100e"], ascending=[True, False]).to_csv(
        OUT / "owners_by_owner.csv", index=False, float_format="%.6g")
    print(f"  wrote owners_by_owner.csv ({by_owner.owner.nunique()} owners x "
          f"{by_owner.quarter.nunique()} quarters)")

    # ---- owner x manufacturer, which is what shows vertical integration ---
    cross = (des_w.groupby(["quarter", "Owner", "Chip manufacturer"], as_index=False)
                  .agg(h100e=(MED, "sum")))
    cross["quarter"] = cross["quarter"].astype(str)
    cross = cross.rename(columns={"Owner": "owner", "Chip manufacturer": "manufacturer"})
    cross["own_silicon"] = cross.owner == cross.manufacturer
    cross.to_csv(OUT / "owners_by_manufacturer.csv", index=False, float_format="%.6g")
    print(f"  wrote owners_by_manufacturer.csv ({cross.manufacturer.nunique()} manufacturers)")

    # ---- installed base by chip type -------------------------------------
    by_type = (typ_w.groupby(["quarter", "Chip type"], as_index=False)
                    .agg(h100e=(MED, "sum")))
    by_type["quarter"] = by_type["quarter"].astype(str)
    by_type = by_type.rename(columns={"Chip type": "chip_type"})
    by_type.sort_values(["quarter", "h100e"], ascending=[True, False]).to_csv(
        OUT / "owners_by_chip_type.csv", index=False, float_format="%.6g")
    print(f"  wrote owners_by_chip_type.csv ({by_type.chip_type.nunique()} chip types)")

    # ---- what was added each quarter, not the running total ---------------
    added = (qtr_w.groupby(["quarter", "Owner"], as_index=False).agg(h100e=(MED, "sum")))
    added["quarter"] = added["quarter"].astype(str)
    added = added.rename(columns={"Owner": "owner"})
    added.sort_values(["quarter", "h100e"], ascending=[True, False]).to_csv(
        OUT / "owners_added.csv", index=False, float_format="%.6g")
    print(f"  wrote owners_added.csv ({added.quarter.nunique()} quarters of additions)")

    # ---- provenance -------------------------------------------------------
    tot = by_owner[by_owner.quarter == str(last)]["h100e"].sum()
    pd.DataFrame([{
        "window_first_quarter": str(first), "window_last_quarter": str(last),
        "excluded_quarters": ", ".join(excluded),
        "excluded_rows": int(des.incomplete.sum() + typ.incomplete.sum()
                             + qtr.incomplete.sum()),
        "owners": int(by_owner.owner.nunique()),
        "aggregate_owners": ", ".join(sorted(AGGREGATE_OWNERS)),
        "manufacturers": int(cross.manufacturer.nunique()),
        "chip_types": int(by_type.chip_type.nunique()),
        "total_h100e_last_quarter": float(tot),
        "quarters": int(by_owner.quarter.nunique()),
    }]).to_csv(OUT / "owners_summary.csv", index=False)
    print(f"  wrote owners_summary.csv  ({tot/1e6:.2f}M H100e installed at {last})")


if __name__ == "__main__":
    main()
