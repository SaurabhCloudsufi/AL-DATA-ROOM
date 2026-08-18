#!/usr/bin/env python3
"""Derive the AI Usage tables from the Anthropic Economic Index.

Reads the release exactly as published on Hugging Face into anthropic_aei/:

    aei_claude_ai_2026-06-26.csv    Claude chat and Cowork (Free, Pro, Max)

One row of that file is one metric value for one geography and one category
node - 1.6 million of them, 219 MB. This script reduces it to the small tables
the charts read, and nothing else touches the raw file.

Three things about this dataset drive every decision here:

  It is one provider's own traffic. Claude.ai is not the market. Every share
  here is a share of Claude conversations, never of AI use at large, and the
  charts say so rather than implying a market measurement.

  A missing cell is not a zero. Anthropic publishes a cell only where it clears
  an aggregation threshold and a geography sample floor. An absent country or
  node was suppressed for sparsity, so it is left absent and counted, never
  filled with zero.

  The two time columns are in different units. human_only_time_mean is in
  HOURS and human_with_ai_time_mean is in MINUTES, per the release
  documentation. They are converted to a common unit here, once, rather than in
  each chart, because comparing them raw understates the gap by 60x.

Usage:
    python build/summarise_anthropic_aei.py [source_dir]
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RAW = REPO / "anthropic_aei"
OUT = REPO / "ai-usage" / "data"
SOURCE = "aei_claude_ai_2026-06-26.csv"

# the metrics carried through to the per-node tables, in the order charts read
NODE_METRICS = [
    "pct", "collaboration_bucket_automation_pct", "collaboration_bucket_augmentation_pct",
    "ai_autonomy_mean", "human_only_ability_pct", "multitasking_pct",
    "ai_education_years_mean", "human_education_years_mean",
    "human_only_time_mean", "human_with_ai_time_mean",
    "use_case_work_pct", "use_case_personal_pct", "use_case_coursework_pct",
]

# ISO 3166-1 alpha-3 for the countries that reach the charts. The release
# publishes codes only, with node_name held at "Overall" for every geography.
COUNTRY_NAME = {
    "USA": "United States", "IND": "India", "FRA": "France",
    "GBR": "United Kingdom", "BRA": "Brazil", "JPN": "Japan",
    "KOR": "South Korea", "DEU": "Germany", "AUS": "Australia",
    "CAN": "Canada", "SGP": "Singapore", "CHE": "Switzerland",
    "LUX": "Luxembourg", "NZL": "New Zealand", "NOR": "Norway",
    "ISL": "Iceland", "MLT": "Malta", "NLD": "Netherlands",
    "IRL": "Ireland", "ISR": "Israel", "SWE": "Sweden", "DNK": "Denmark",
    "FIN": "Finland", "AUT": "Austria", "BEL": "Belgium", "ESP": "Spain",
    "ITA": "Italy", "POL": "Poland", "MEX": "Mexico", "IDN": "Indonesia",
    "PHL": "Philippines", "VNM": "Vietnam", "THA": "Thailand",
    "TUR": "Turkey", "ARE": "United Arab Emirates", "SAU": "Saudi Arabia",
    "ZAF": "South Africa", "NGA": "Nigeria", "EGY": "Egypt", "KEN": "Kenya",
    "PAK": "Pakistan", "BGD": "Bangladesh", "CHN": "China", "RUS": "Russia",
    "ARG": "Argentina", "CHL": "Chile", "COL": "Colombia", "PER": "Peru",
    "MYS": "Malaysia", "HKG": "Hong Kong", "TWN": "Taiwan", "PRT": "Portugal",
    "CZE": "Czechia", "GRC": "Greece", "HUN": "Hungary", "ROU": "Romania",
    "UKR": "Ukraine", "MAR": "Morocco", "TZA": "Tanzania",
    "EST": "Estonia", "CYP": "Cyprus", "LVA": "Latvia", "LTU": "Lithuania",
    "SVN": "Slovenia", "SVK": "Slovakia", "HRV": "Croatia", "BGR": "Bulgaria",
    "SRB": "Serbia", "QAT": "Qatar", "KWT": "Kuwait", "BHR": "Bahrain",
    "URY": "Uruguay", "CRI": "Costa Rica", "PAN": "Panama", "LKA": "Sri Lanka",
    "NPL": "Nepal", "GHA": "Ghana", "ETH": "Ethiopia", "UGA": "Uganda",
    "MOZ": "Mozambique", "AGO": "Angola", "MDG": "Madagascar",
}


def wide(df, index=("node_name",)):
    """Long metric rows -> one row per node, one column per metric."""
    t = df.pivot_table(index=list(index), columns="metric_id", values="value",
                       aggfunc="first")
    keep = [m for m in NODE_METRICS if m in t.columns]
    t = t[keep].reset_index()
    # published in hours and minutes respectively; unified once, here
    if {"human_only_time_mean", "human_with_ai_time_mean"} <= set(t.columns):
        t["human_only_minutes"] = t["human_only_time_mean"] * 60
        t["human_with_ai_minutes"] = t["human_with_ai_time_mean"]
        t["time_ratio"] = t["human_only_minutes"] / t["human_with_ai_minutes"]
    return t


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    path = raw / SOURCE
    if not path.exists():
        sys.exit(f"missing {path}\nDownload it from "
                 f"https://huggingface.co/datasets/Anthropic/EconomicIndex "
                 f"(release_2026_06_26/data/) into {raw}/")
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Deriving AI Usage tables from {path.name} ...")
    df = pd.read_csv(path, low_memory=False)
    print(f"  read {len(df):,} rows")

    periods = sorted(df.date_start.unique())
    latest = periods[-1]
    g = df[df.geo_level == "global"]

    # ---- headline metrics, both periods ---------------------------------
    o = g[g.category_name == "overall"]
    overall = o.pivot_table(index="metric_id", columns="date_start",
                            values="value", aggfunc="first").reset_index()
    overall.columns.name = None
    if len(periods) == 2:
        overall["delta"] = overall[periods[1]] - overall[periods[0]]
    overall.to_csv(OUT / "aei_overall.csv", index=False)
    print(f"  wrote aei_overall.csv ({len(overall)} metrics x {len(periods)} periods)")

    # ---- countries -------------------------------------------------------
    c = df[(df.geo_level == "country") & (df.category_name == "overall")
           & (df.date_start == latest)]
    ct = c.pivot_table(index="geo_id", columns="metric_id", values="value",
                       aggfunc="first").reset_index()
    ct.columns.name = None
    ct["country"] = ct["geo_id"].map(lambda x: COUNTRY_NAME.get(x, x))
    cols = ["geo_id", "country"] + [m for m in
            ("usage_pct", "usage_per_capita_index", "collaboration_bucket_automation_pct",
             "use_case_work_pct", "use_case_personal_pct", "use_case_coursework_pct",
             "ai_autonomy_mean") if m in ct.columns]
    ct[cols].sort_values("usage_pct", ascending=False).to_csv(
        OUT / "aei_countries.csv", index=False)
    named = int(ct["geo_id"].isin(COUNTRY_NAME).sum())
    print(f"  wrote aei_countries.csv ({len(ct)} countries, {named} named)")

    # ---- US states (the only subregions carrying the per-capita index) ---
    s = df[(df.geo_level == "subregion") & (df.category_name == "overall")
           & (df.date_start == latest)]
    st = s.pivot_table(index="geo_id", columns="metric_id", values="value",
                       aggfunc="first").reset_index()
    st.columns.name = None
    st = st[st["geo_id"].str.startswith("US-")]
    scols = ["geo_id"] + [m for m in ("usage_per_capita_index", "usage_pct",
                                      "collaboration_bucket_automation_pct")
                          if m in st.columns]
    st = st[scols].dropna(subset=["usage_per_capita_index"])
    st.sort_values("usage_per_capita_index", ascending=False).to_csv(
        OUT / "aei_us_states.csv", index=False)
    print(f"  wrote aei_us_states.csv ({len(st)} states)")

    # ---- the three category hierarchies, at the grain Anthropic charts ---
    for name, cat, lvl in [("aei_soc_major.csv", "soc_occupation", 1),
                           ("aei_onet_gwa.csv", "onet", 3),
                           ("aei_request_major.csv", "request", 2)]:
        sub = g[(g.category_name == cat) & (g.hierarchy_level == lvl)
                & (g.date_start == latest)]
        t = wide(sub)
        t = t.sort_values("pct", ascending=False)
        t.to_csv(OUT / name, index=False)
        print(f"  wrote {name} ({len(t)} nodes, {t['pct'].sum():.1f}% of usage)")

    # ---- artifacts, from the overall row --------------------------------
    a = o[(o.date_start == latest) & o.metric_id.str.startswith("artifact_")]
    art = a[["metric_id", "value"]].copy()
    art["artifact"] = (art["metric_id"].str.replace("^artifact_", "", regex=True)
                       .str.replace("_pct$", "", regex=True).str.replace("_", " "))
    art[["artifact", "value"]].sort_values("value", ascending=False).to_csv(
        OUT / "aei_artifacts.csv", index=False)
    print(f"  wrote aei_artifacts.csv ({len(art)} artifact types)")

    # ---- what the record holds ------------------------------------------
    cov = (df.groupby(["geo_level", "category_name", "hierarchy_level"])
             .agg(rows=("value", "size"), metrics=("metric_id", "nunique"),
                  nodes=("node_name", "nunique"), geos=("geo_id", "nunique"))
             .reset_index())
    cov.to_csv(OUT / "aei_coverage.csv", index=False)
    print(f"  wrote aei_coverage.csv ({len(cov)} slices)")

    # ---- provenance ------------------------------------------------------
    pd.DataFrame([{
        "source_file": SOURCE,
        "rows": int(len(df)),
        "periods": len(periods),
        "period_first": periods[0],
        "period_last": latest,
        "countries": int(df[df.geo_level == "country"].geo_id.nunique()),
        "subregions": int(df[df.geo_level == "subregion"].geo_id.nunique()),
        "us_states_with_index": int(len(st)),
        "metrics": int(df.metric_id.nunique()),
        "categories": int(df.category_name.nunique()),
    }]).to_csv(OUT / "aei_summary.csv", index=False)
    print("  wrote aei_summary.csv")


if __name__ == "__main__":
    main()
