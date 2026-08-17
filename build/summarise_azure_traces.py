#!/usr/bin/env python3
"""Summarise the Azure LLM inference traces into a small, committable CSV.

The raw traces are large and are published by Microsoft under CC-BY at
https://github.com/Azure/AzurePublicDataset - they are not duplicated into this
repository. This script reads them from a local path and writes only the derived
aggregates the charts need, so the chart output stays reproducible without
committing the source data.

The 2024 pair is ~1.8 GB combined, so every file is read in chunks and reduced to
an exact integer value-count table as it streams. Nothing is sampled and nothing
is approximated: medians and percentiles are computed from the full value counts
using the same linear interpolation pandas uses, so a chunked run and a
load-it-all run produce identical numbers.

Usage:
    python build/summarise_azure_traces.py /path/to/trace/directory
"""
import sys
from collections import Counter
from math import ceil, floor
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "inference-tokens" / "data" / "azure_trace_summary.csv"
HIST = REPO / "inference-tokens" / "data" / "azure_trace_histograms.csv"

FILES = {
    "conv_2023": "AzureLLMInferenceTrace_conv_2023.csv",
    "code_2023": "AzureLLMInferenceTrace_code_2023.csv",
    "conv_2024": "AzureLLMInferenceTrace_conv_2024.csv",
    "code_2024": "AzureLLMInferenceTrace_code_2024.csv",
    # 2025 release; note the observation window is October 2024, not 2025
    "multimodal_2025": "AzureLMMInferenceTrace_multimodal_2025.csv",
}

SERVICE = {"conv": "conversation", "code": "code", "multimodal": "multimodal"}

# Log-spaced bins for the token distributions. The range has to cover the
# largest request in any trace: the 2025 multimodal file reaches 148,569 input
# tokens, so a table stopping at 65,536 would silently drop its tail. binned()
# is asserted against the request count below, so a future trace that outgrows
# this range fails loudly instead of quietly losing rows.
BINS = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192,
        16384, 32768, 65536, 131072, 262144, 524288, 1048576]

CHUNK = 2_000_000


def quantile(counts: Counter, q: float) -> float:
    """Exact quantile from an integer value-count table.

    Matches pandas' default linear interpolation, so chunked and unchunked runs
    agree to the last digit.
    """
    n = sum(counts.values())
    if n == 0:
        return float("nan")
    pos = q * (n - 1)
    lo_i, hi_i = floor(pos), ceil(pos)
    lo_val = hi_val = None
    seen = 0
    for value in sorted(counts):
        seen += counts[value]
        if lo_val is None and seen > lo_i:
            lo_val = value
        if seen > hi_i:
            hi_val = value
            break
    if hi_val is None:
        hi_val = lo_val
    return float(lo_val) + (float(hi_val) - float(lo_val)) * (pos - lo_i)


def binned(counts: Counter):
    """Fold the exact value counts into the log-spaced display bins."""
    out = []
    for low, high in zip(BINS, BINS[1:]):
        out.append((low, high,
                    sum(n for v, n in counts.items() if low <= v < high)))
    return out


def read_trace(path: Path):
    """Stream one trace file, returning exact value counts and the time window."""
    ctx, gen = Counter(), Counter()
    ts_min = ts_max = None
    rows = 0
    for chunk in pd.read_csv(path, chunksize=CHUNK,
                             usecols=["TIMESTAMP", "ContextTokens", "GeneratedTokens"],
                             dtype={"ContextTokens": "int64", "GeneratedTokens": "int64"}):
        rows += len(chunk)
        ctx.update(chunk.ContextTokens.value_counts().to_dict())
        gen.update(chunk.GeneratedTokens.value_counts().to_dict())
        # ISO-8601 sorts correctly as text, so min/max need no date parsing
        lo, hi = chunk.TIMESTAMP.min(), chunk.TIMESTAMP.max()
        ts_min = lo if ts_min is None else min(ts_min, lo)
        ts_max = hi if ts_max is None else max(ts_max, hi)
    return ctx, gen, pd.Timestamp(ts_min), pd.Timestamp(ts_max), rows


def main(src: str) -> None:
    src = Path(src)
    rows, hists = [], []

    for label, fname in FILES.items():
        path = src / fname
        if not path.exists():
            print(f"  skip {label}: {fname} not present")
            continue
        ctx, gen, t0, t1, n = read_trace(path)
        inp, out = int(sum(v * c for v, c in ctx.items())), \
                   int(sum(v * c for v, c in gen.items()))
        span = t1 - t0
        rows.append({
            "trace": label,
            "service": SERVICE[label.rsplit("_", 1)[0]],
            "release": label.rsplit("_", 1)[1],
            "requests": n,
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": inp + out,
            "output_share": round(out / (inp + out), 6),
            "window_start": t0.isoformat(),
            "window_end": t1.isoformat(),
            "window_minutes": round(span.total_seconds() / 60, 1),
            "input_median": quantile(ctx, 0.5),
            "input_p90": quantile(ctx, 0.9),
            "input_max": int(max(ctx)),
            "output_median": quantile(gen, 0.5),
            "output_p90": quantile(gen, 0.9),
            "output_max": int(max(gen)),
        })
        for counts, kind in ((ctx, "input"), (gen, "output")):
            rows_binned = binned(counts)
            # every request must land in a bin, or the distribution charts would
            # under-report their own tail without saying so
            if sum(c for _, _, c in rows_binned) != n:
                sys.exit(f"{label} {kind}: {n - sum(c for _, _, c in rows_binned)} "
                         f"requests fall outside BINS (max value {max(counts)}). "
                         f"Extend BINS - do not publish a truncated distribution.")
            for low, high, count in rows_binned:
                hists.append({"trace": label, "kind": kind,
                              "bin_low": low, "bin_high": high, "count": count})
        print(f"  {label}: {n:,} requests, output share "
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
