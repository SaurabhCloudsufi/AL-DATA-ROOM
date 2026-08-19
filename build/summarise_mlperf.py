#!/usr/bin/env python3
"""Derive the MLPerf Inference tables from the MLCommons results export.

Reads the benchmark export exactly as downloaded into mlperf/:

    MLPerf_Inference_Hardware_Performance_Benchmarks.csv

One row is one submitted result: a system, a workload, a scenario and a number.
MLCommons publishes a results table rather than a figure, so everything here is
a reading of that table rather than a reproduction of a published chart.

Four decisions govern the whole domain:

  A result is a system, not a chip. "Result" is the throughput of the whole
  submitted system, which may hold anything from one accelerator to 288. Nothing
  is comparable until it is divided by the accelerator count, so per-accelerator
  throughput is computed once, here, and it is what every chart plots.

  Mixed-accelerator systems are dropped from per-chip views. One submission
  pairs MI300X, MI325X and MI355X in a single system; its throughput cannot be
  attributed to any one of them.

  Configuration variants collapse to the chip. Submissions annotated (x87),
  (x94) or (Power Cap 1000 W) are the same silicon under a different setup, so
  they are folded into the base chip and the best submitted result is taken.

  These are benchmark-tuned figures, not production serving. Vendors optimise
  hard for MLPerf, the closed division fixes the model and the accuracy target,
  and real deployments run below this. Every chart says so.

Usage:
    python build/summarise_mlperf.py [source_dir]
"""
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_RAW = REPO / "mlperf"
OUT = REPO / "mlperf-inference" / "data"
SOURCE = "MLPerf_Inference_Hardware_Performance_Benchmarks.csv"

# workloads measured in tokens per second, which is the only unit that makes
# systems comparable for an inference-demand question
TOKEN_UNIT = "Tokens/s"

# vendor families, for the generation view
FAMILY = [
    (r"^NVIDIA GB300", "NVIDIA", "GB300", 5),
    (r"^NVIDIA B300", "NVIDIA", "B300", 4),
    (r"^NVIDIA GB200", "NVIDIA", "GB200", 3),
    (r"^NVIDIA B200", "NVIDIA", "B200", 2),
    (r"^NVIDIA H200", "NVIDIA", "H200", 1),
    (r"^NVIDIA H100", "NVIDIA", "H100", 0),
    (r"^AMD Instinct MI355X", "AMD", "MI355X", 4),
    (r"^AMD Instinct MI350X", "AMD", "MI350X", 3),
    (r"^AMD Instinct MI325X", "AMD", "MI325X", 2),
    (r"^AMD Instinct MI300X", "AMD", "MI300X", 1),
]


def base_chip(name):
    """Fold configuration variants into the chip they ran on.

    "(x87)", "(x94)" and "(Power Cap 1000 W)" are the same silicon set up
    differently; "(R)" is a trademark mark inside Intel's product names and is
    noise either way.
    """
    n = str(name).replace("(R)", "").replace("(TM)", "")
    n = re.sub(r"\s*\((?:x\d+|Power Cap[^)]*)\)", "", n)
    return " ".join(n.split())


def family_of(chip):
    for pattern, vendor, gen, order in FAMILY:
        if re.match(pattern, chip):
            return vendor, gen, order
    return "", "", -1


def main():
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RAW
    path = raw / SOURCE
    if not path.exists():
        sys.exit(f"missing {path}\nPut the MLCommons export in {raw}/")
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Deriving MLPerf Inference tables from {path.name} ...")

    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    total = len(df)
    print(f"  read {total} submitted results, MLPerf {df['Version'].iloc[0]}, "
          f"{df['Division'].iloc[0]} division")

    d = df.rename(columns={
        "Organization": "organization", "Accelerator Model Name": "accelerator",
        "Model MLC": "workload", "Scenario": "scenario", "Units": "units",
        "Result": "result", "Total Accelerators": "accelerators",
        "Availability": "availability", "System Name (click + for details)": "system"})

    dropped = {
        "not tokens/s": int((d.units != TOKEN_UNIT).sum()),
        "no accelerator count": 0, "mixed accelerators": 0, "unnamed accelerator": 0}
    t = d[d.units == TOKEN_UNIT].copy()
    before = len(t)
    t = t[t.accelerator.notna()]
    dropped["unnamed accelerator"] = before - len(t)
    before = len(t)
    t = t[t.accelerators > 0]
    dropped["no accelerator count"] = before - len(t)
    before = len(t)
    # one submission pairs three Instinct generations in a single system; its
    # throughput belongs to no single chip
    t = t[~t.accelerator.str.contains(" and ", na=False)]
    dropped["mixed accelerators"] = before - len(t)

    t["chip"] = t.accelerator.map(base_chip)
    t["per_accelerator"] = t.result / t.accelerators
    fam = t.chip.map(family_of)
    t["vendor"] = [f[0] for f in fam]
    t["generation"] = [f[1] for f in fam]
    t["generation_order"] = [f[2] for f in fam]

    cols = ["organization", "system", "chip", "accelerator", "vendor", "generation",
            "generation_order", "workload", "scenario", "accelerators", "result",
            "per_accelerator", "availability"]
    t[cols].sort_values(["workload", "scenario", "per_accelerator"],
                        ascending=[True, True, False]).to_csv(
        OUT / "mlperf_results.csv", index=False, float_format="%.6g")
    print(f"  wrote mlperf_results.csv ({len(t)} token-throughput results, "
          f"{t.chip.nunique()} chips, {t.workload.nunique()} workloads)")

    # ---- best submitted result per chip, workload and scenario --------------
    best = (t.groupby(["chip", "vendor", "generation", "generation_order",
                       "workload", "scenario"], as_index=False)
             .agg(per_accelerator=("per_accelerator", "max"),
                  submissions=("per_accelerator", "size"),
                  best_system_result=("result", "max"),
                  max_accelerators=("accelerators", "max")))
    best.sort_values(["workload", "scenario", "per_accelerator"],
                     ascending=[True, True, False]).to_csv(
        OUT / "mlperf_by_chip.csv", index=False, float_format="%.6g")
    print(f"  wrote mlperf_by_chip.csv ({len(best)} chip-workload-scenario cells)")

    # ---- coverage: which chip was submitted on which workload --------------
    cov = (t.groupby(["chip", "workload"], as_index=False)
            .agg(submissions=("per_accelerator", "size"),
                 scenarios=("scenario", "nunique")))
    cov.to_csv(OUT / "mlperf_coverage.csv", index=False)
    print(f"  wrote mlperf_coverage.csv ({cov.chip.nunique()} chips x "
          f"{cov.workload.nunique()} workloads)")

    # ---- provenance --------------------------------------------------------
    pd.DataFrame([{
        "source_file": SOURCE,
        "version": str(df["Version"].iloc[0]),
        "division": str(df["Division"].iloc[0]),
        "system_type": str(df["System Type"].iloc[0]),
        "submitted_results": total,
        "token_results_used": int(len(t)),
        "chips": int(t.chip.nunique()),
        "workloads": int(t.workload.nunique()),
        "organizations": int(t.organization.nunique()),
        "scenarios": ", ".join(sorted(t.scenario.unique())),
        **{f"excluded_{k.replace(' ', '_')}": v for k, v in dropped.items()},
    }]).to_csv(OUT / "mlperf_summary.csv", index=False)
    print("  wrote mlperf_summary.csv")
    print("  excluded: " + ", ".join(f"{k} {v}" for k, v in dropped.items()))


if __name__ == "__main__":
    main()
