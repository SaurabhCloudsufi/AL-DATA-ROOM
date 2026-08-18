#!/usr/bin/env python3
"""Derive the AI Models chart tables from Epoch AI's published model CSVs.

Input is the four files Epoch publishes at epoch.ai/data/ai-models, staged in
ai_models/ exactly as downloaded:

    notable_ai_models.csv       models meeting Epoch's notability criteria
    frontier_ai_models.csv      top-10-by-training-compute at their release
    large_scale_ai_models.csv   trained with over 1e23 FLOP
    all_ai_models.csv           the full database

Output is the small derived tables in ai-models/data/ that the charts read.

The rule this script enforces, everywhere: **a model is only counted for a
metric it actually carries.** Epoch records training compute for 534 of 1,043
notable models; the compute charts therefore plot 534 points and say so. No
value is imputed, back-filled, carried across from a related model, or inferred
from a note field. Where a field is absent the row is dropped from that metric
and counted in the coverage table instead, so the gap stays visible rather than
being quietly filled.

Multi-valued fields (Domain, Country, Organization categorization) list one
entry per contributing organization. They are reduced to a single label by
de-duplication, never by picking a winner:

    one distinct value   -> that value
    several distinct     -> "Multinational" / "Industry-academia collaboration"
    contains Multimodal  -> "Multimodal" (Epoch's own composite label)

Usage:
    python build/summarise_epoch_models.py
"""
import math
import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "ai_models"
OUT = REPO / "ai-models" / "data"

# the four Epoch releases, and the label used for them throughout the site
DATASETS = {
    "notable": ("notable_ai_models.csv", "Notable AI models"),
    "frontier": ("frontier_ai_models.csv", "Frontier AI models"),
    "large_scale": ("large_scale_ai_models.csv", "Large-scale AI models"),
    "all": ("all_ai_models.csv", "All AI models"),
}

# metric -> source column. Only columns Epoch actually publishes; a dataset that
# does not carry one simply reports zero coverage for it.
METRICS = {
    "training_compute_flop": "Training compute (FLOP)",
    "parameters": "Parameters",
    "training_dataset_size": "Training dataset size (total)",
    "training_cost_2023usd": "Training compute cost (2023 USD)",
    "training_time_hours": "Training time (hours)",
    "training_power_draw_w": "Training power draw (W)",
    "hardware_quantity": "Hardware quantity",
    "citations": "Citations",
}

ATTRS = {
    "organization": "Organization",
    "org_category": "Organization categorization",
    "country": "Country (of organization)",
    "domain": "Domain",
    "task": "Task",
    "training_hardware": "Training hardware",
    "model_accessibility": "Model accessibility",
    "open_weights": "Open model weights?",
    "training_code_accessibility": "Training code accessibility",
    "confidence": "Confidence",
    "compute_estimation_method": "Training compute estimation method",
    "notability_criteria": "Notability criteria",
}

# accelerator families, matched against Epoch's free-text hardware strings in
# order. Anything unmatched keeps its own name rather than being bucketed into
# an "Other" that hides what it was.
HW_FAMILIES = [
    (r"\bH100\b|\bH800\b|\bH200\b", "NVIDIA H100 / H800 / H200"),
    (r"\bB200\b|\bGB200\b|Blackwell", "NVIDIA Blackwell (B200 / GB200)"),
    (r"\bA100\b|\bA800\b", "NVIDIA A100 / A800"),
    (r"\bV100\b", "NVIDIA V100"),
    (r"\bP100\b|\bP40\b|\bK80\b|\bK40\b|\bM40\b", "NVIDIA datacenter (pre-Volta)"),
    (r"TPU\s*v?7|Ironwood", "Google TPU v7"),
    (r"TPU\s*v?6|Trillium", "Google TPU v6"),
    (r"TPU\s*v?5", "Google TPU v5"),
    (r"TPU\s*v?4", "Google TPU v4"),
    (r"TPU\s*v?3", "Google TPU v3"),
    (r"TPU\s*v?2", "Google TPU v2"),
    (r"TPU", "Google TPU (version unstated)"),
    (r"GeForce|GTX|RTX|TITAN|Quadro", "NVIDIA consumer / workstation GPU"),
    (r"\bMI\d{2,3}\b|Radeon|AMD", "AMD Instinct / Radeon"),
    (r"Trainium|Inferentia", "AWS Trainium / Inferentia"),
    (r"Ascend|Huawei", "Huawei Ascend"),
    (r"Gaudi|Habana", "Intel Gaudi"),
    (r"CPU|Xeon|Opteron|Core i", "CPU only"),
]

DL_ERA_START = 2010          # Epoch's "Deep Learning Era" boundary
MIN_FIT_POINTS = 12          # below this a trend line is not drawn at all


# ----------------------------------------------------------------- helpers
def _multi(value, joint_label):
    """Collapse a comma-joined per-organization list to one label."""
    if not isinstance(value, str) or not value.strip():
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        return None
    distinct = list(dict.fromkeys(parts))
    return distinct[0] if len(distinct) == 1 else joint_label


def _domain(value):
    """Epoch treats Multimodal as a label in its own right; honour that."""
    if not isinstance(value, str) or not value.strip():
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts:
        return None
    return "Multimodal" if "Multimodal" in parts else parts[0]


def _first_org(value):
    if not isinstance(value, str) or not value.strip():
        return None
    return value.split(",")[0].strip()


def _hw_family(value):
    if not isinstance(value, str) or not value.strip():
        return None
    for pattern, label in HW_FAMILIES:
        if re.search(pattern, value, flags=re.I):
            return label
    return value.strip()


def _numeric(series):
    """Coerce to float, discarding anything that is not a finite number.

    Epoch stores a few of these columns as text; inf appears in FLOP/$ where a
    price is zero. Neither is plottable, and neither is repaired here.
    """
    out = pd.to_numeric(series, errors="coerce")
    return out.where(out.apply(lambda v: isinstance(v, float) and math.isfinite(v)
                               and v > 0))


def load(key):
    """One tidy frame per Epoch release, columns harmonised across releases."""
    filename, _ = DATASETS[key]
    raw = pd.read_csv(RAW / filename, low_memory=False)

    df = pd.DataFrame({"model": raw["Model"].astype(str).str.strip()})
    df["dataset"] = key
    df["publication_date"] = pd.to_datetime(raw["Publication date"], errors="coerce")

    for name, col in METRICS.items():
        df[name] = _numeric(raw[col]) if col in raw.columns else pd.NA
    for name, col in ATTRS.items():
        df[name] = raw[col] if col in raw.columns else pd.NA

    df["organization_primary"] = df["organization"].map(_first_org)
    df["org_category"] = df["org_category"].map(
        lambda v: _multi(v, "Industry-academia collaboration"))
    df["country"] = df["country"].map(lambda v: _multi(v, "Multinational"))
    df["domain"] = df["domain"].map(_domain)
    df["hardware_family"] = df["training_hardware"].map(_hw_family)
    df["training_time_days"] = df["training_time_hours"] / 24.0

    # frontier carries hardware price-performance directly; nothing else does
    if "FLOP/$" in raw.columns:
        df["flop_per_dollar"] = _numeric(raw["FLOP/$"])
        df["hardware_release_date"] = pd.to_datetime(raw["Hardware release date"],
                                                     errors="coerce")
    return df


def fit(df, metric, since=None):
    """Log-linear fit of a metric against publication date.

    Returns the growth rate as orders of magnitude per year and the implied
    doubling time. Fitted to the plotted points only - never to a filled or
    extended series - and refused outright below MIN_FIT_POINTS.
    """
    sub = df.dropna(subset=[metric, "publication_date"])
    if since is not None:
        sub = sub[sub["publication_date"].dt.year >= since]
    if len(sub) < MIN_FIT_POINTS:
        return None

    x = sub["publication_date"].map(lambda d: d.year + (d.dayofyear - 1) / 365.25)
    y = sub[metric].map(math.log10)
    slope, intercept = pd.Series(y).pipe(
        lambda ys: _least_squares(x.to_numpy(), ys.to_numpy()))
    resid = y.to_numpy() - (slope * x.to_numpy() + intercept)
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y.to_numpy() - y.mean()) ** 2).sum())
    return {
        "metric": metric,
        "since": since if since is not None else int(sub["publication_date"].dt.year.min()),
        "n": int(len(sub)),
        "oom_per_year": slope,
        "intercept_log10": intercept,
        "doubling_time_months": math.log10(2) / slope * 12 if slope > 0 else float("nan"),
        "growth_per_year": 10 ** slope,
        "r_squared": 1 - ss_res / ss_tot if ss_tot else float("nan"),
        "x_min": float(x.min()),
        "x_max": float(x.max()),
    }


def _least_squares(x, y):
    n = len(x)
    mx, my = x.mean(), y.mean()
    sxx = float(((x - mx) ** 2).sum())
    sxy = float(((x - mx) * (y - my)).sum())
    slope = sxy / sxx
    return slope, my - slope * mx


# -------------------------------------------------------------------- main
POINT_COLS = [
    "dataset", "model", "publication_date", "organization_primary", "organization",
    "org_category", "country", "domain", "task", "training_compute_flop",
    "parameters", "training_dataset_size", "training_cost_2023usd",
    "training_time_hours", "training_time_days", "training_power_draw_w",
    "hardware_quantity", "citations", "training_hardware", "hardware_family",
    "model_accessibility", "open_weights", "training_code_accessibility",
    "confidence", "compute_estimation_method",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = {k: load(k) for k in DATASETS}

    # ---- the plotted points, one file per Epoch release ------------------
    for key, df in frames.items():
        out = df.reindex(columns=POINT_COLS).copy()
        out["publication_date"] = out["publication_date"].dt.strftime("%Y-%m-%d")
        out = out.sort_values(["publication_date", "model"], na_position="last")
        out.to_csv(OUT / f"points_{key}.csv", index=False)
        print(f"  wrote points_{key}.csv ({len(out):,} models)")

    # ---- coverage: what each release actually records --------------------
    cov = []
    columns = {k: set(pd.read_csv(RAW / f, nrows=0).columns)
               for k, (f, _) in DATASETS.items()}
    sources = dict(METRICS, **ATTRS)
    for key, df in frames.items():
        dated = df["publication_date"].notna()
        for metric in list(METRICS) + ["training_hardware", "org_category",
                                       "country", "domain", "open_weights"]:
            present = int((df[metric].notna() & dated).sum())
            cov.append({
                "dataset": key,
                "dataset_label": DATASETS[key][1],
                "field": metric,
                # a release that does not publish the column at all is a
                # different thing from one that publishes it and leaves it empty
                "field_in_release": sources[metric] in columns[key],
                "models": int(len(df)),
                "models_dated": int(dated.sum()),
                "records": present,
                "share_of_dated": present / int(dated.sum()) if dated.sum() else 0.0,
            })
    pd.DataFrame(cov).to_csv(OUT / "models_coverage.csv", index=False)
    print(f"  wrote models_coverage.csv ({len(cov)} rows)")

    # ---- per-release summary --------------------------------------------
    summary = []
    for key, df in frames.items():
        dated = df.dropna(subset=["publication_date"])
        withc = df.dropna(subset=["training_compute_flop", "publication_date"])
        summary.append({
            "dataset": key,
            "dataset_label": DATASETS[key][1],
            "source_file": DATASETS[key][0],
            "models": len(df),
            "models_dated": len(dated),
            "models_with_compute": len(withc),
            "first_publication": dated["publication_date"].min().date().isoformat(),
            "last_publication": dated["publication_date"].max().date().isoformat(),
            "max_compute_flop": float(withc["training_compute_flop"].max())
            if len(withc) else float("nan"),
            "max_compute_model": withc.loc[withc["training_compute_flop"].idxmax(), "model"]
            if len(withc) else "",
            "organizations": int(df["organization_primary"].nunique()),
            "countries": int(df["country"].nunique()),
        })
    pd.DataFrame(summary).to_csv(OUT / "models_summary.csv", index=False)
    print(f"  wrote models_summary.csv ({len(summary)} releases)")

    # ---- fitted trends, per release and metric ---------------------------
    trends = []
    for key, df in frames.items():
        for metric in ("training_compute_flop", "parameters", "training_dataset_size",
                       "training_cost_2023usd", "training_power_draw_w"):
            for since in (None, DL_ERA_START):
                f = fit(df, metric, since)
                if f:
                    f.update(dataset=key, dataset_label=DATASETS[key][1],
                             era="deep learning era" if since else "all records")
                    trends.append(f)
    pd.DataFrame(trends).to_csv(OUT / "models_trends.csv", index=False)
    print(f"  wrote models_trends.csv ({len(trends)} fits)")

    # ---- yearly composition, long format --------------------------------
    rows = []
    for key, df in frames.items():
        dated = df.dropna(subset=["publication_date"]).copy()
        dated["year"] = dated["publication_date"].dt.year
        for dim in ("country", "domain", "org_category", "model_accessibility",
                    "hardware_family", "open_weights", "confidence"):
            grouped = (dated.dropna(subset=[dim])
                       .groupby(["year", dim]).size().reset_index(name="models"))
            for _, r in grouped.iterrows():
                rows.append({"dataset": key, "dimension": dim, "year": int(r["year"]),
                             "category": r[dim], "models": int(r["models"])})
    pd.DataFrame(rows).to_csv(OUT / "models_by_year.csv", index=False)
    print(f"  wrote models_by_year.csv ({len(rows):,} rows)")

    # ---- organization league table --------------------------------------
    org_rows = []
    for key, df in frames.items():
        g = df.dropna(subset=["organization_primary"]).groupby("organization_primary")
        for name, sub in g:
            compute = sub["training_compute_flop"].dropna()
            org_rows.append({
                "dataset": key,
                "organization": name,
                "models": int(len(sub)),
                "models_with_compute": int(len(compute)),
                "median_compute_flop": float(compute.median()) if len(compute) else "",
                "max_compute_flop": float(compute.max()) if len(compute) else "",
                "org_category": sub["org_category"].mode().iat[0]
                if sub["org_category"].notna().any() else "",
                "country": sub["country"].mode().iat[0]
                if sub["country"].notna().any() else "",
                "first_publication": sub["publication_date"].min().date().isoformat()
                if sub["publication_date"].notna().any() else "",
                "last_publication": sub["publication_date"].max().date().isoformat()
                if sub["publication_date"].notna().any() else "",
            })
    (pd.DataFrame(org_rows).sort_values(["dataset", "models"], ascending=[True, False])
     .to_csv(OUT / "models_by_organization.csv", index=False))
    print(f"  wrote models_by_organization.csv ({len(org_rows):,} rows)")

    # ---- hardware price-performance, frontier only ----------------------
    fr = frames["frontier"]
    if "flop_per_dollar" in fr.columns:
        hw = fr.dropna(subset=["flop_per_dollar", "hardware_release_date"])[
            ["model", "training_hardware", "hardware_family",
             "hardware_release_date", "flop_per_dollar", "publication_date"]].copy()
        hw["hardware_release_date"] = hw["hardware_release_date"].dt.strftime("%Y-%m-%d")
        hw["publication_date"] = hw["publication_date"].dt.strftime("%Y-%m-%d")
        hw.sort_values("hardware_release_date").to_csv(
            OUT / "frontier_hardware_price_performance.csv", index=False)
        print(f"  wrote frontier_hardware_price_performance.csv ({len(hw)} models)")

    # ---- provenance ------------------------------------------------------
    last_modified = pd.to_datetime(
        pd.read_csv(RAW / "all_ai_models.csv", low_memory=False)["Last modified"],
        errors="coerce", utc=True).max()
    pd.DataFrame([{
        "source": "Epoch AI - Data on AI Models",
        "source_url": "https://epoch.ai/data/ai-models",
        "licence": "CC-BY 4.0",
        "files": " + ".join(f for f, _ in DATASETS.values()),
        "latest_record_modified": last_modified.date().isoformat(),
        "latest_publication_date": max(s["last_publication"] for s in summary),
        "imputation": "none - a model is plotted for a metric only where Epoch records it",
    }]).to_csv(OUT / "models_provenance.csv", index=False)
    print("  wrote models_provenance.csv")


if __name__ == "__main__":
    print("Deriving AI Models tables from ai_models/ ...")
    main()
