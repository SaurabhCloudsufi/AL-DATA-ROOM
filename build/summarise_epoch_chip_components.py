#!/usr/bin/env python3
"""Derive the AI Chip Components aggregates the gallery reads.

Source: Epoch AI, "AI Chip Components" (CC-BY) - https://epoch.ai/data/ai-chip-components
Raw files are not committed; only the derived series the charts read.

WHAT THE SOURCE CONTAINS
------------------------
Seven files. Six carry numbers:

    quarterly_by_designer.csv            5 designers x 9 quarters
    quarterly_by_chip.csv               17 chip types x the quarters they ship in
    cumulative_by_designer.csv           the same, cumulated from Q1 2024
    cumulative_by_chip.csv               the same, cumulated from Q1 2024
    supply_denominators.csv              total advanced-node supply per quarter
    cumulative_supply_denominators.csv   the same, cumulated

Every quantity is published as three columns - 5th percentile, median, 95th
percentile - because Epoch's figures come out of a Monte Carlo simulation. All
three are carried through here; nothing is collapsed to a point estimate.

MEDIANS DO NOT ADD
------------------
The median of a sum is not the sum of medians, and Epoch simulates each
aggregation separately. So the four published files disagree slightly with each
other by construction:

    sum of chip-type medians   vs  the designer median      up to 0.71%
    running sum of quarterly   vs  the published cumulative up to 0.44%

Neither is an error, and neither is reconciled here. Each chart reads the file
published at its own grain - designer charts read the designer file, cumulative
charts read the cumulative file - so no plotted value is ever re-derived by
summing a coarser one. The two divergences are measured below and recorded in
chip_summary.csv so the charts can state them.

Supply denominators are deterministic, not simulated, and there the running sum
does reproduce the published cumulative exactly. That is asserted.

WHAT "SHARE (%)" MEANS
----------------------
The share columns are share of *supply*, not share of cost: a designer's
consumption divided by that quarter's total advanced-node supply. Checked, not
assumed - the identity holds to 3e-14, and the five designers sum to exactly
100% in all eight complete quarters. Both are asserted below.

"Other" is therefore not a fifth AI chip designer. It is the residual of the
supply denominator - all the leading-edge silicon that is not one of the tracked
AI accelerators - which is why it carries 52-88% of logic wafers. It belongs in
the share-of-supply charts and is kept out of the AI-designer cost charts.

Q1 2026 IS EXCLUDED
-------------------
The download runs to Q1 2026, but that quarter is not comparable to the eight
before it: it holds 3 designers instead of 5 (no NVIDIA, no "Other"), 7 chip
types instead of 17, blank share columns, and no supply denominator row. Charting
it would show a collapse in total spend that is missing coverage, not a fall in
demand. The complete window is Q1 2024 - Q4 2025, which is also the range Epoch's
own published chart covers. The partial rows are counted in chip_summary.csv and
excluded from the derived quarterly and cumulative series.

Usage:
    python build/summarise_epoch_chip_components.py [raw_csv_directory]
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "ai-chip-components" / "data"
DEFAULT_RAW = OUT / "raw"

# The complete-coverage window. Anything outside it is partial - see the header.
QUARTERS = ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024",
            "Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025"]
QI = {q: i for i, q in enumerate(QUARTERS)}

DESIGNERS = ["NVIDIA", "Google", "Amazon", "AMD"]   # the tracked AI chip designers
RESIDUAL = "Other"                                  # the rest of advanced-node supply

PCT = {"5th percentile": "p5", "median": "p50", "95th percentile": "p95"}

# source column stem -> derived column stem. Auxiliary has no wafer or share
# counterpart in the source, so it appears here as cost only.
QUANTITIES = {
    "Logic wafers": "logic_wafers",
    "Logic cost (USD)": "logic_cost_usd",
    "Logic share (%)": "logic_share_pct",
    "CoWoS wafers": "cowos_wafers",
    "CoWoS cost (USD)": "cowos_cost_usd",
    "CoWoS share (%)": "cowos_share_pct",
    "HBM cost (USD)": "hbm_cost_usd",
    "HBM share (%)": "hbm_share_pct",
    "Auxiliary cost (USD)": "aux_cost_usd",
}

SUPPLY = {
    "Logic supply": "logic_supply_wafers",
    "CoWoS supply": "cowos_supply_wafers",
    "HBM supply (USD)": "hbm_supply_usd",
}

# the four cost components, in the order they are stacked on every chart
COST_PARTS = ["logic_cost_usd", "cowos_cost_usd", "hbm_cost_usd", "aux_cost_usd"]


def rename_map(quantities):
    """{'Logic cost (USD) (median)': 'logic_cost_usd_p50', ...}"""
    return {f"{src} ({label})": f"{dst}_{suffix}"
            for src, dst in quantities.items()
            for label, suffix in PCT.items()}


def read(raw, name):
    path = raw / name
    if not path.exists():
        sys.exit(f"missing source file: {path}\n"
                 f"Download the AI Chip Components CSVs from "
                 f"https://epoch.ai/data/ai-chip-components into {raw}")
    return pd.read_csv(path)


def tidy(df, quarter_col, keys, quantities):
    """Rename to snake_case, add a quarter index, keep the complete window."""
    out = df.rename(columns={quarter_col: "quarter",
                             "Designer": "designer",
                             "Chip type": "chip_type",
                             "Start date": "start_date",
                             "Series start date": "start_date",
                             "End date": "end_date"})
    out = out.rename(columns=rename_map(quantities))
    keep = ["quarter", "start_date", "end_date"] + keys + \
           [c for c in rename_map(quantities).values() if c in out.columns]
    out = out[keep].copy()
    out.insert(1, "quarter_index", out["quarter"].map(QI))
    partial = out[out["quarter_index"].isna()]
    out = out[out["quarter_index"].notna()].copy()
    out["quarter_index"] = out["quarter_index"].astype(int)
    return out.sort_values(["quarter_index"] + keys).reset_index(drop=True), partial


def add_total_cost(df):
    """Total component cost = the four published parts, summed within the row.

    A row-wise sum of one simulation's medians, which is exactly what the stack
    on the chart shows. No cross-row aggregation, so nothing is smuggled in.
    """
    for suffix in ("p5", "p50", "p95"):
        cols = [f"{part}_{suffix}" for part in COST_PARTS]
        df[f"total_cost_usd_{suffix}"] = df[cols].sum(axis=1)
    return df


def check_shares(quarterly, supply):
    """The two identities that fix what 'share (%)' means. Checked, not assumed."""
    m = quarterly.merge(supply, on="quarter", suffixes=("", "_sup"))
    pairs = [("logic_wafers_p50", "logic_supply_wafers_p50", "logic_share_pct_p50"),
             ("cowos_wafers_p50", "cowos_supply_wafers_p50", "cowos_share_pct_p50"),
             ("hbm_cost_usd_p50", "hbm_supply_usd_p50", "hbm_share_pct_p50")]
    worst = 0.0
    for used, avail, share in pairs:
        err = (m[used] / m[avail] * 100 - m[share]).abs().max()
        worst = max(worst, err)
        assert err < 1e-9, f"{share} is not {used}/{avail}: max error {err}"

    totals = quarterly.groupby("quarter")[
        ["logic_share_pct_p50", "cowos_share_pct_p50", "hbm_share_pct_p50"]].sum()
    off = (totals - 100).abs().max().max()
    assert off < 1e-9, f"designer shares do not sum to 100%: off by {off}"
    return worst, off


def median_additivity(by_chip, by_designer, quarterly, cumulative):
    """Measure the two divergences the header describes, so charts can state them.

    Reported, never corrected: each is the honest gap between two separate Monte
    Carlo runs, and hiding it would imply a precision the source does not have.
    """
    chip_sum = by_chip.groupby(["quarter", "designer"])["logic_wafers_p50"].sum()
    published = by_designer.set_index(["quarter", "designer"])["logic_wafers_p50"]
    grain = ((chip_sum - published) / published).abs().max()

    ordered = quarterly.sort_values(["designer", "quarter_index"])
    running = ordered[["quarter", "designer"]].copy()
    running["run"] = ordered.groupby("designer")["logic_wafers_p50"].cumsum()
    merged = running.merge(cumulative[["quarter", "designer", "logic_wafers_p50"]],
                           on=["quarter", "designer"])
    cumul = ((merged["run"] - merged["logic_wafers_p50"])
             / merged["logic_wafers_p50"]).abs().max()
    return grain, cumul


def check_supply_cumulates(supply, cum_supply):
    """Denominators are deterministic, so here the running sum must be exact."""
    cols = [f"{stem}_{s}" for stem in SUPPLY.values() for s in ("p5", "p50", "p95")]
    run = supply.sort_values("quarter_index")[cols].cumsum().reset_index(drop=True)
    pub = cum_supply.sort_values("quarter_index")[cols].reset_index(drop=True)
    err = (run - pub).abs().max().max()
    assert err < 1.0, f"cumulative supply is not the running sum: off by {err}"
    return err


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    OUT.mkdir(parents=True, exist_ok=True)

    q_des, q_des_partial = tidy(read(raw, "quarterly_by_designer.csv"),
                                "Quarter", ["designer"], QUANTITIES)
    q_chip, q_chip_partial = tidy(read(raw, "quarterly_by_chip.csv"),
                                  "Quarter", ["designer", "chip_type"], QUANTITIES)
    c_des, _ = tidy(read(raw, "cumulative_by_designer.csv"),
                    "Cumulative through", ["designer"], QUANTITIES)
    c_chip, _ = tidy(read(raw, "cumulative_by_chip.csv"),
                     "Cumulative through", ["designer", "chip_type"], QUANTITIES)
    supply, _ = tidy(read(raw, "supply_denominators.csv"), "Quarter", [], SUPPLY)
    c_supply, _ = tidy(read(raw, "cumulative_supply_denominators.csv"),
                       "Cumulative through", [], SUPPLY)

    share_err, share_sum_err = check_shares(q_des, supply)
    supply_err = check_supply_cumulates(supply, c_supply)
    grain_gap, cumul_gap = median_additivity(q_chip, q_des, q_des, c_des)

    for df in (q_des, q_chip, c_des, c_chip):
        add_total_cost(df)

    named = q_des[q_des["designer"].isin(DESIGNERS)]
    ai_q4 = named[named["quarter"] == QUARTERS[-1]]["total_cost_usd_p50"].sum()
    ai_cum = c_des[(c_des["designer"].isin(DESIGNERS))
                   & (c_des["quarter"] == QUARTERS[-1])]["total_cost_usd_p50"].sum()

    summary = pd.DataFrame([{
        "source": "Epoch AI, AI Chip Components (CC-BY)",
        "source_url": "https://epoch.ai/data/ai-chip-components",
        "window_first_quarter": QUARTERS[0],
        "window_last_quarter": QUARTERS[-1],
        "quarters_charted": len(QUARTERS),
        "designers_tracked": len(DESIGNERS),
        "designer_names": ", ".join(DESIGNERS),
        "chip_types_charted": q_chip[q_chip["designer"].isin(DESIGNERS)]
                                    ["chip_type"].nunique(),
        # what was dropped, so the charts can say so on their face
        "partial_quarter": "Q1 2026",
        "partial_designer_rows_excluded": len(q_des_partial),
        "partial_chip_rows_excluded": len(q_chip_partial),
        "partial_designers_present": ", ".join(sorted(q_des_partial["designer"])),
        "partial_missing_designers": ", ".join(
            sorted(set(DESIGNERS + [RESIDUAL]) - set(q_des_partial["designer"]))),
        # the measured limits of the source, reported not corrected
        "median_additivity_grain_pct": round(grain_gap * 100, 4),
        "median_additivity_cumulative_pct": round(cumul_gap * 100, 4),
        "share_identity_max_abs_error_pct": share_err,
        "share_sum_max_abs_error_pct": share_sum_err,
        "cumulative_supply_max_abs_error": supply_err,
        # headline figures the captions quote
        "ai_total_cost_usd_last_quarter": ai_q4,
        "ai_total_cost_usd_cumulative": ai_cum,
        "nvidia_share_of_ai_cost_last_quarter_pct":
            named[(named["quarter"] == QUARTERS[-1])
                  & (named["designer"] == "NVIDIA")]["total_cost_usd_p50"].sum()
            / ai_q4 * 100,
        "hbm_share_of_ai_cost_last_quarter_pct":
            named[named["quarter"] == QUARTERS[-1]]["hbm_cost_usd_p50"].sum()
            / ai_q4 * 100,
        "ai_logic_share_of_supply_last_quarter_pct":
            100 - q_des[(q_des["quarter"] == QUARTERS[-1])
                        & (q_des["designer"] == RESIDUAL)]["logic_share_pct_p50"].iloc[0],
        "ai_cowos_share_of_supply_last_quarter_pct":
            100 - q_des[(q_des["quarter"] == QUARTERS[-1])
                        & (q_des["designer"] == RESIDUAL)]["cowos_share_pct_p50"].iloc[0],
        "ai_hbm_share_of_supply_last_quarter_pct":
            100 - q_des[(q_des["quarter"] == QUARTERS[-1])
                        & (q_des["designer"] == RESIDUAL)]["hbm_share_pct_p50"].iloc[0],
    }])

    written = {
        "chip_quarterly_by_designer.csv": q_des,
        "chip_quarterly_by_chip.csv": q_chip,
        "chip_cumulative_by_designer.csv": c_des,
        "chip_cumulative_by_chip.csv": c_chip,
        "chip_supply.csv": supply,
        "chip_cumulative_supply.csv": c_supply,
        "chip_summary.csv": summary,
    }
    for name, df in written.items():
        df.to_csv(OUT / name, index=False, float_format="%.10g")
        print(f"  wrote {(OUT / name).relative_to(REPO)}  ({len(df)} rows)")

    print(f"\nwindow {QUARTERS[0]} - {QUARTERS[-1]}; "
          f"{len(q_des_partial)} designer and {len(q_chip_partial)} chip rows "
          f"excluded as partial Q1 2026")
    print(f"share identity holds to {share_err:.1e} pp, shares sum to 100% "
          f"to {share_sum_err:.1e} pp, cumulative supply exact to {supply_err:.1e}")
    print(f"median additivity gap: {grain_gap*100:.2f}% across grain, "
          f"{cumul_gap*100:.2f}% across quarters - reported, not reconciled")


if __name__ == "__main__":
    main()
