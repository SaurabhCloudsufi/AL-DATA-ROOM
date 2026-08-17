#!/usr/bin/env python3
"""Summarise the Azure LLM inference traces into a small, committable CSV.

The raw traces are large and are published by Microsoft under CC-BY at
https://github.com/Azure/AzurePublicDataset - they are not duplicated into this
repository. This script reads them from a local path and writes only the derived
aggregates the charts need, so the chart output stays reproducible without
committing the source data.

Usage:
    python build/summarise_azure_traces.py /path/to/trace/directory
"""
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "inference-tokens" / "data" / "azure_trace_summary.csv"
HIST = REPO / "inference-tokens" / "data" / "azure_trace_histograms.csv"

FILES = {
    "conv_2023": "AzureLLMInferenceTrace_conv_2023.csv",
    "code_2023": "AzureLLMInferenceTrace_code_2023.csv",
    # 2024 pair is ~1.8 GB combined; add here once staged locally
    "conv_2024": "AzureLLMInferenceTrace_conv_2024.csv",
    "code_2024": "AzureLLMInferenceTrace_code_2024.csv",
}

# log-spaced bins for the token distributions
BINS = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192,
        16384, 32768, 65536]


def main(src: str) -> None:
    src = Path(src)
    rows, hists = [], []

    for label, fname in FILES.items():
        path = src / fname
        if not path.exists():
            print(f"  skip {label}: {fname} not present")
            continue
        df = pd.read_csv(path, parse_dates=["TIMESTAMP"])
        inp = int(df.ContextTokens.sum())
        out = int(df.GeneratedTokens.sum())
        span = df.TIMESTAMP.max() - df.TIMESTAMP.min()
        rows.append({
            "trace": label,
            "service": "conversation" if "conv" in label else "code",
            "release": label.split("_")[1],
            "requests": len(df),
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": inp + out,
            "output_share": round(out / (inp + out), 6),
            "window_start": df.TIMESTAMP.min().isoformat(),
            "window_end": df.TIMESTAMP.max().isoformat(),
            "window_minutes": round(span.total_seconds() / 60, 1),
            "input_median": float(df.ContextTokens.median()),
            "input_p90": float(df.ContextTokens.quantile(0.9)),
            "input_max": int(df.ContextTokens.max()),
            "output_median": float(df.GeneratedTokens.median()),
            "output_p90": float(df.GeneratedTokens.quantile(0.9)),
            "output_max": int(df.GeneratedTokens.max()),
        })
        for field, kind in (("ContextTokens", "input"), ("GeneratedTokens", "output")):
            counts = pd.cut(df[field], bins=BINS, right=False).value_counts().sort_index()
            for interval, n in counts.items():
                hists.append({"trace": label, "kind": kind,
                              "bin_low": int(interval.left),
                              "bin_high": int(interval.right),
                              "count": int(n)})
        print(f"  {label}: {len(df):,} requests, output share "
              f"{out/(inp+out)*100:.2f}%, window {span.total_seconds()/60:.1f} min")

    if not rows:
        sys.exit("no trace files found - pass the directory containing them")

    # combined figure per release, since that is what the methodology quotes
    summary = pd.DataFrame(rows)
    for release, grp in summary.groupby("release"):
        if len(grp) < 2:
            continue
        inp, out = grp.input_tokens.sum(), grp.output_tokens.sum()
        summary.loc[len(summary)] = {
            "trace": f"combined_{release}", "service": "combined", "release": release,
            "requests": int(grp.requests.sum()), "input_tokens": int(inp),
            "output_tokens": int(out), "total_tokens": int(inp + out),
            "output_share": round(out / (inp + out), 6),
            "window_start": grp.window_start.min(), "window_end": grp.window_end.max(),
            "window_minutes": float(grp.window_minutes.max()),
            "input_median": float("nan"), "input_p90": float("nan"),
            "input_max": int(grp.input_max.max()), "output_median": float("nan"),
            "output_p90": float("nan"), "output_max": int(grp.output_max.max()),
        }
        print(f"  combined_{release}: output share {out/(inp+out)*100:.2f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT, index=False)
    pd.DataFrame(hists).to_csv(HIST, index=False)
    print(f"wrote {OUT.relative_to(REPO)} ({len(summary)} rows)")
    print(f"wrote {HIST.relative_to(REPO)} ({len(hists)} rows)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
