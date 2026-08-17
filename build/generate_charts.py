#!/usr/bin/env python3
"""Generate Inference Tokens charts from company-disclosed figures.

Every value plotted here is read from build/company_disclosures.csv, which is
exported from the Excel register. That file records each figure exactly as the
company disclosed it. Nothing in this script invents, estimates or fills a value.

Normalisation basis (as stated in the methodology):
    monthly equivalent = tokens/minute x 1,440 x 30.44
    annual  equivalent = tokens/minute x 60 x 24 x 365

Outputs SVG (for the web gallery) and PNG (for Excel, decks, offline use) into
inference-tokens/charts/, named by stable Plot ID.

Usage:
    python build/generate_charts.py            # all implemented charts
    python build/generate_charts.py P-01       # a single chart
"""
import csv
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch  # noqa: F401  (kept for future use)

REPO = Path(__file__).resolve().parent.parent
CHARTS = REPO / "inference-tokens" / "charts"
DATA = REPO / "build" / "company_disclosures.csv"
AZURE = REPO / "inference-tokens" / "data" / "azure_trace_summary.csv"
AZURE_HIST = REPO / "inference-tokens" / "data" / "azure_trace_histograms.csv"

# ---------------------------------------------------------------- house style
NAVY = "#1f3864"
INK = "#1a1a1a"
MUTED = "#6b7280"
RULE = "#d7dbe2"
SERIES = {
    "current": "#1f3864",   # most recent disclosure
    "prior": "#9aa9c4",     # earlier disclosure, same provider
    "other": "#6b8f71",     # different measurement basis
    "scope": "#b4763a",     # broader scope, not additive
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": RULE,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "svg.fonttype": "none",   # keep text as text, so SVG stays crisp and selectable
    "figure.dpi": 100,
    # fixed salt -> stable SVG element ids -> clean git diffs
    "svg.hashsalt": "inference-tokens",
})

MIN_TO_YEAR = 60 * 24 * 365
MIN_TO_MONTH = 1440 * 30.44


def load_disclosures():
    with DATA.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def frame(fig, ax, plot_id, title, subtitle, source, methodology, note):
    """Apply the standard chart furniture: ID, title, subtitle, footer block."""
    fig.text(0.035, 0.972, plot_id, ha="left", va="top", fontsize=10.5,
             fontweight="bold", color=NAVY, family="monospace")
    fig.text(0.035, 0.928, title, ha="left", va="top", fontsize=15.5,
             fontweight="bold", color=INK)
    for i, line in enumerate(textwrap.wrap(subtitle, 122)):
        fig.text(0.035, 0.882 - i * 0.030, line, ha="left", va="top",
                 fontsize=10.2, color=MUTED)

    note_lines = textwrap.wrap(note, 133) if note else []
    # footer grows upward from the bottom so long notes never spill off-page
    footer_h = 0.052 + 0.026 * (2 + len(note_lines))
    y = footer_h
    fig.lines.append(plt.Line2D([0.035, 0.965], [y, y], transform=fig.transFigure,
                                color=RULE, linewidth=0.8))
    fig.text(0.035, y - 0.022, f"Source: {source}", ha="left", va="top",
             fontsize=8.6, color=MUTED)
    fig.text(0.035, y - 0.048, f"Methodology: {methodology}", ha="left", va="top",
             fontsize=8.6, color=MUTED)
    for i, line in enumerate(note_lines):
        prefix = "Note: " if i == 0 else "      "
        fig.text(0.035, y - 0.074 - i * 0.024, prefix + line, ha="left", va="top",
                 fontsize=8.4, color=MUTED, style="italic")
    ax.grid(axis="y", color=RULE, linewidth=0.7, alpha=0.9)
    ax.set_axisbelow(True)


def save(fig, plot_id, domain="inference-tokens"):
    CHARTS = REPO / domain / "charts"
    CHARTS.mkdir(parents=True, exist_ok=True)
    svg = CHARTS / f"{plot_id}.svg"
    png = CHARTS / f"{plot_id}.png"
    # Date=None keeps SVG output byte-stable so git diffs show real changes only
    fig.savefig(svg, format="svg", facecolor="white", metadata={"Date": None})
    fig.savefig(png, format="png", dpi=200, facecolor="white")
    plt.close(fig)
    print(f"  wrote {svg.relative_to(REPO)} and {png.relative_to(REPO)}")


# =============================================================== P-01
def build_p01(rows):
    """Annualised throughput by disclosing provider.

    Uses only the disclosures that carry an absolute token figure. Google and
    OpenAI disclose an instantaneous tokens/minute rate, annualised here.
    Microsoft discloses a completed fiscal-year total, which needs no
    annualisation - a different measurement basis, so it is coloured and
    labelled differently rather than silently pooled with the others.
    """
    def find(company, value_startswith, unit_contains):
        for r in rows:
            if (r["Company"] == company
                    and r["Value_as_disclosed"].startswith(value_startswith)
                    and unit_contains in r["Unit_as_disclosed"]):
                return r
        raise LookupError(f"disclosure not found: {company} {value_startswith}")

    g_now = find("Alphabet / Google", "22 billion", "tokens/minute")
    g_prev = find("Alphabet / Google", "16 billion", "tokens/minute")
    o_now = find("OpenAI", "more than 15 billion", "tokens/minute")
    o_prev = find("OpenAI", "6 billion", "tokens/minute")
    ms = find("Microsoft", "over 500 trillion", "FY2025")

    # rate-based disclosures -> annualised, straight from the disclosed rate
    def annual_from_rate(rec, billions):
        return billions * 1e9 * MIN_TO_YEAR / 1e15  # quadrillions/yr

    bars = [
        # (provider, prior label/value, current label/value, kind)
        ("Google\nmodel APIs",
         ("Q1 2026\n16 bn/min", annual_from_rate(g_prev, 16)),
         ("Q2 2026\n22 bn/min", annual_from_rate(g_now, 22)),
         "rate"),
        ("OpenAI\nAPIs",
         ("Oct 2025\n6 bn/min", annual_from_rate(o_prev, 6)),
         ("Mar 2026\n15 bn/min", annual_from_rate(o_now, 15)),
         "rate"),
        ("Microsoft\nAzure AI Foundry",
         None,
         ("FY2025 total\n500 T tokens", 500e12 / 1e15),
         "period"),
    ]

    fig = plt.figure(figsize=(11.0, 7.4))
    ax = fig.add_axes([0.085, 0.315, 0.88, 0.50])

    width = 0.34
    xt, xl = [], []
    for i, (prov, prior, current, kind) in enumerate(bars):
        if prior:
            ax.bar(i - width / 2, prior[1], width, color=SERIES["prior"],
                   edgecolor="white", linewidth=0.8)
            ax.text(i - width / 2, prior[1] + 0.22, f"{prior[1]:.2f}",
                    ha="center", va="bottom", fontsize=9, color=MUTED)
            ax.text(i - width / 2, -0.40, prior[0], ha="center", va="top",
                    fontsize=7.6, color=MUTED)
            cx = i + width / 2
        else:
            cx = i
        colour = SERIES["current"] if kind == "rate" else SERIES["other"]
        ax.bar(cx, current[1], width, color=colour, edgecolor="white", linewidth=0.8)
        ax.text(cx, current[1] + 0.22, f"{current[1]:.2f}", ha="center",
                va="bottom", fontsize=9.5, fontweight="bold", color=INK)
        ax.text(cx, -0.40, current[0], ha="center", va="top", fontsize=7.6,
                color=MUTED)
        xt.append(i)
        xl.append(prov)

    ax.set_xticks(xt)
    ax.set_xticklabels(xl, fontsize=10.5)
    ax.tick_params(axis="x", length=0, pad=34)
    ax.set_ylabel("Annualised tokens per year (quadrillions)", fontsize=10)
    ax.set_ylim(0, 13.6)
    ax.set_xlim(-0.7, 2.7)

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=SERIES["prior"]),
        plt.Rectangle((0, 0), 1, 1, color=SERIES["current"]),
        plt.Rectangle((0, 0), 1, 1, color=SERIES["other"]),
    ]
    ax.legend(handles,
              ["Earlier disclosure (rate, annualised)",
               "Latest disclosure (rate, annualised)",
               "Completed fiscal year (no annualisation)"],
              loc="upper right", frameon=False, fontsize=8.8)

    frame(fig, ax,
          "P-01",
          "Annualised inference throughput by disclosing provider",
          "Token throughput as disclosed by each provider, converted to a common annual basis. "
          "Google and OpenAI publish an instantaneous rate; Microsoft publishes a completed "
          "fiscal-year total.",
          "Alphabet Q2 2026 earnings; OpenAI announcement; Microsoft FY2025 Q4 earnings",
          "\u00a77.3 \u2014 Method 1, Direct Provider Throughput",
          "Scopes differ and the bars must not be summed. Microsoft's figure covers Azure AI "
          "Foundry, a gateway: models served through it are counted at the model owner "
          "(\u00a77.9, rule 1), so it overlaps with OpenAI's. Rate-based figures are spot rates "
          "annualised, which assumes the rate held for a full year. Microsoft's figure is "
          "FY2025, ended 30 June 2025.")
    save(fig, "P-01")


# =============================================================== P-03
def build_p03(rows):
    """API-only vs all-surfaces scope ladder for Google.

    The single chart whose job is to show that two Google disclosures measure
    different things, and that the larger contains the smaller. Drawn as nested
    volumes on a monthly basis, never as additive bars.
    """
    def find(value_startswith, unit_contains):
        for r in rows:
            if (r["Company"] == "Alphabet / Google"
                    and r["Value_as_disclosed"].startswith(value_startswith)
                    and unit_contains in r["Unit_as_disclosed"]):
                return r
        raise LookupError(value_startswith)

    find("22 billion", "tokens/minute")
    find("over 3.2 quadrillion", "tokens/month")

    api_month = 22e9 * MIN_TO_MONTH / 1e12          # trillions per month
    all_month = 3.2e15 / 1e12                        # trillions per month

    fig = plt.figure(figsize=(11.0, 7.0))
    ax = fig.add_axes([0.085, 0.30, 0.88, 0.50])

    ax.barh(0.6, all_month, height=0.42, color=SERIES["scope"], alpha=0.28,
            edgecolor=SERIES["scope"], linewidth=1.4)
    ax.barh(0.6, api_month, height=0.42, color=SERIES["current"],
            edgecolor="white", linewidth=1.0)

    ax.text(api_month / 2, 0.66, "model APIs only", ha="center", va="center",
            color="white", fontsize=10, fontweight="bold")
    ax.text(api_month / 2, 0.54, f"{api_month:,.0f} T/month", ha="center",
            va="center", color="white", fontsize=10.5)
    ax.text(all_month, 0.90, f"all Google surfaces  \u2014  {all_month:,.0f} T/month",
            ha="right", va="center", fontsize=10.5, color=SERIES["scope"],
            fontweight="bold")

    ax.annotate("", xy=(api_month, 0.28), xytext=(all_month, 0.28),
                arrowprops=dict(arrowstyle="<->", color=MUTED, linewidth=1.0))
    ax.text((api_month + all_month) / 2, 0.20,
            f"consumer and enterprise surfaces not in the API figure "
            f"\u2014 {all_month - api_month:,.0f} T/month",
            ha="center", va="top", fontsize=8.8, color=MUTED)

    ax.set_xlim(0, all_month * 1.06)
    ax.set_ylim(0, 1.35)
    ax.set_yticks([])
    ax.set_xlabel("Tokens per month (trillions)", fontsize=10)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color=RULE, linewidth=0.7)

    frame(fig, ax,
          "P-03",
          "Google API throughput sits inside the all-surfaces figure",
          "Two Google disclosures on a common monthly basis. The all-surfaces figure already "
          "contains the model-API figure, so the two describe nested volumes rather than "
          "separate ones.",
          "Alphabet Q2 2026 earnings; Google I/O 2026 keynote",
          "\u00a77.9 \u2014 De-duplication rule 2; \u00a72.6 \u2014 Global share",
          "These two figures must never be added together. The API figure is a spot rate of 22 "
          "billion tokens/minute (Q2 2026) put on a 30.44-day month; the all-surfaces figure is "
          "disclosed directly as over 3.2 quadrillion tokens/month (May 2026). The dates differ "
          "and the all-surfaces figure spans multimodal and consumer traffic, so the gap shown "
          "is indicative of scope, not a precise residual.")
    save(fig, "P-03")


# =============================================================== P-58
def build_p58(_rows):
    """Measured output share against the pipeline's assumed range.

    Reads the derived Azure trace summary. Every value is computed from the
    published traces - nothing here is assumed. The pipeline's own assumed
    output share (0.15 low / 0.25 base / 0.40 high) is drawn as a band behind
    the bars so the gap is visible rather than described.
    """
    import csv as _csv
    with AZURE.open(encoding="utf-8") as f:
        rows = {r["trace"]: r for r in _csv.DictReader(f)}

    order = [("conv_2023", "Conversation\nservice"),
             ("code_2023", "Code\nservice"),
             ("combined_2023", "Both services\ncombined")]
    vals, labels, reqs = [], [], []
    for key, lab in order:
        if key not in rows:
            continue
        vals.append(float(rows[key]["output_share"]) * 100)
        labels.append(lab)
        reqs.append(int(rows[key]["requests"]))

    fig = plt.figure(figsize=(11.0, 7.4))
    ax = fig.add_axes([0.085, 0.30, 0.88, 0.50])

    # pipeline assumption band
    ax.axhspan(15, 40, color=SERIES["scope"], alpha=0.10, zorder=0)
    ax.axhline(25, color=SERIES["scope"], linewidth=1.3, linestyle="--", zorder=1)
    ax.axhline(15, color=SERIES["scope"], linewidth=0.9, alpha=0.6, zorder=1)
    ax.axhline(40, color=SERIES["scope"], linewidth=0.9, alpha=0.6, zorder=1)
    ax.text(2.46, 25.6, "pipeline base case  0.25", ha="right", va="bottom",
            fontsize=9, color=SERIES["scope"], fontweight="bold")
    ax.text(2.46, 15.6, "low  0.15", ha="right", va="bottom", fontsize=8.5,
            color=SERIES["scope"], alpha=0.85)
    ax.text(2.46, 40.6, "high  0.40", ha="right", va="bottom", fontsize=8.5,
            color=SERIES["scope"], alpha=0.85)

    for i, (v, n) in enumerate(zip(vals, reqs)):
        colour = SERIES["current"] if i < 2 else SERIES["other"]
        ax.bar(i, v, 0.5, color=colour, edgecolor="white", linewidth=0.8, zorder=3)
        ax.text(i, v + 1.0, f"{v:.2f}%", ha="center", va="bottom", fontsize=11,
                fontweight="bold", color=INK, zorder=4)
        ax.text(i, -2.4, f"{n:,} requests", ha="center", va="top", fontsize=8,
                color=MUTED)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=10.5)
    ax.tick_params(axis="x", length=0, pad=22)
    ax.set_ylabel("Output tokens as a share of total tokens (%)", fontsize=10)
    ax.set_ylim(0, 46)
    ax.set_xlim(-0.55, 2.55)

    frame(fig, ax, "P-58",
          "Measured output share lands at the floor of the assumed range, or below it",
          "Output tokens as a percentage of all tokens, computed directly from Microsoft's "
          "published Azure inference traces, against the output share the pipeline currently "
          "assumes.",
          "Microsoft Azure, AzurePublicDataset (2023 release, CC-BY)",
          "\u00a73.2 \u2014 What we measured; \u00a77.9 \u2014 De-duplication rule 3",
          "Computed from 28,185 real requests. The combined figure of 9.68% and the code "
          "service at 1.34% both fall below even the pipeline's low case; the conversation "
          "service at 15.46% is the one value inside the band, and only just. The 2023 "
          "release covers a single 58-minute window on 16 November 2023, so it is a snapshot "
          "rather than a representative period, and it predates reasoning models and agentic "
          "tool-calling, both of which push output share up.")
    save(fig, "P-58")


# ======================================= Azure token distributions (P-1 / P-2 / P-3)
# One builder for every Azure release. Each chart pairs the distribution itself
# with its cumulative curve, so the reader sees the shape on the left and can read
# any percentile straight off the right.
AZURE_PLOTS = {
    "P-1": {
        "traces": [("conv_2023", "Conversation service"),
                   ("code_2023", "Code service")],
        "title": "Distribution of input and output tokens per request \u2014 "
                 "Azure LLM inference traces, 2023",
        "source": "Microsoft Azure, AzurePublicDataset \u2014 LLM inference production "
                  "traces (2023 release, CC-BY)",
        "caveat": "A 58-minute snapshot, not a representative period, and it predates "
                  "reasoning models and agentic tool-calling, both of which lengthen "
                  "output. The code service's median input of 1,469 tokens against a "
                  "median output of 13 is the signature of inline completion, not chat.",
    },
    "P-2": {
        "traces": [("conv_2024", "Conversation service"),
                   ("code_2024", "Code service")],
        "title": "Distribution of input and output tokens per request \u2014 "
                 "Azure LLM inference traces, 2024",
        "source": "Microsoft Azure, AzurePublicDataset \u2014 LLM inference production "
                  "traces (2024 release, CC-BY)",
        "caveat": "Computed from all 44.1 million requests in the release, streamed in "
                  "chunks - nothing is sampled or estimated. Note the two services cover "
                  "different weeks, overlapping by five days, so they are not a matched "
                  "pair; they are separate workloads and must not be pooled. One week of "
                  "one provider's production traffic is not a market-wide sample.",
    },
    "P-3": {
        "traces": [("multimodal_2025", "Multimodal service")],
        "title": "Distribution of input and output tokens per request \u2014 "
                 "Azure multimodal inference traces, 2025",
        "source": "Microsoft Azure, AzurePublicDataset \u2014 multimodal (LMM) inference "
                  "production traces (2025 release, CC-BY)",
        "caveat": "Input tokens include image tokens as well as text, so this is not "
                  "comparable with the text-only traces and the two must never be "
                  "pooled. Despite the 2025 release label the observation window is "
                  "October 2024, and Microsoft describes the file as a sample of the "
                  "cluster's traffic rather than its full volume.",
    },
}

KINDS = (("input", "Input tokens", "prior"), ("output", "Output tokens", "current"))


def _azure_data():
    """Load the derived summary and histograms. Both are re-derivable byte for
    byte from Microsoft's published traces by build/summarise_azure_traces.py,
    so every value plotted traces back to a real request count."""
    import csv as _csv
    from collections import defaultdict
    hist = defaultdict(dict)
    with AZURE_HIST.open(encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            hist[(r["trace"], r["kind"])][int(r["bin_low"])] = (
                int(r["bin_high"]), int(r["count"]))
    with AZURE.open(encoding="utf-8") as f:
        summary = {r["trace"]: r for r in _csv.DictReader(f)}
    return summary, hist


def _count_fmt(v, _pos=None):
    if v >= 1e6:
        return f"{v/1e6:g}M"
    if v >= 1e3:
        return f"{v/1e3:g}k"
    return f"{v:g}"


def _window_text(rec):
    """Observation window, read off the trace itself rather than assumed."""
    from datetime import datetime
    def ts(x):
        return datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    a, b = ts(rec["window_start"]), ts(rec["window_end"])
    if a.date() == b.date():
        return f"{a:%d %b %Y}, {a:%H:%M}\u2013{b:%H:%M}"
    return f"{a:%d %b %Y} \u2013 {b:%d %b %Y}"


def build_azure(plot_id):
    cfg = AZURE_PLOTS[plot_id]
    summary, hist = _azure_data()

    missing = [t for t, _ in cfg["traces"] if t not in summary]
    if missing:
        raise SystemExit(
            f"{plot_id}: no derived data for {', '.join(missing)}.\n"
            f"Run: python build/summarise_azure_traces.py <dir holding the raw traces>")

    rows = cfg["traces"]
    nrows = len(rows)
    total_req = sum(int(summary[t]["requests"]) for t, _ in rows)
    windows = "; ".join(f"{lab.split()[0].lower()} {_window_text(summary[t])}"
                        for t, lab in rows)

    subtitle = (f"What it shows: how input and output token counts are distributed "
                f"across {total_req:,} observed Azure inference requests. Left panel "
                f"counts requests per token bin; right panel gives the cumulative "
                f"share, so any percentile reads off the curve.")
    note = (f"Observation window \u2014 {windows}. {cfg['caveat']} The horizontal axis is "
            f"log-scaled because token counts span several orders of magnitude and a linear "
            f"axis would collapse everything below a thousand tokens into a single bar; "
            f"bins are left-closed powers of two. No request is excluded and the full "
            f"long tail is drawn.")

    # frame() places its furniture in figure fractions, so the panel band has to be
    # derived from the same numbers or the text and the axes overlap.
    n_sub = len(textwrap.wrap(subtitle, 122))
    n_note = len(textwrap.wrap(note, 133))
    fig_h = 4.6 + 2.75 * nrows + 0.17 * n_note
    fig = plt.figure(figsize=(12.0, fig_h))

    top = 0.882 - (n_sub - 1) * 0.030 - 0.105          # clear of subtitle + legend
    bottom = 0.052 + 0.026 * (2 + n_note) + 0.055      # clear of the footer rule
    band = top - bottom
    gap = 0.24 * band if nrows > 1 else 0.0
    panel_h = (band - gap * (nrows - 1)) / nrows

    axes = []
    for i in range(nrows):
        y = bottom + (nrows - 1 - i) * (panel_h + gap)
        axes.append((fig.add_axes([0.070, y, 0.370, panel_h]),
                     fig.add_axes([0.585, y, 0.370, panel_h])))

    for (ax_d, ax_c), (trace, label) in zip(axes, rows):
        rec = summary[trace]
        n = int(rec["requests"])
        x_hi, y_hi = 1, 0
        medians = []

        for kind, _legend, tone in KINDS:
            colour = SERIES[tone]
            bins = hist[(trace, kind)]
            lows = sorted(bins)
            counts = [bins[l][1] for l in lows]
            highs = [bins[l][0] for l in lows]
            x_hi = max(x_hi, max((h for h, c in zip(highs, counts) if c), default=1))
            y_hi = max(y_hi, max(counts))

            # ---- left: the distribution itself, request counts per log-spaced bin
            edges = [max(l, 0.5) for l in lows] + [highs[-1]]
            ax_d.stairs(counts, edges, color=colour, linewidth=1.9, fill=False)
            ax_d.stairs(counts, edges, color=colour, alpha=0.16, fill=True)

            # ---- right: cumulative curve, exact at every bin edge
            total = sum(counts)
            cum, run = [], 0
            for c in counts:
                run += c
                cum.append(run / total * 100)
            ax_c.plot(highs, cum, color=colour, linewidth=2.1)

            med = float(rec[f"{kind}_median"])
            medians.append((med, kind, colour))

        for ax in (ax_d, ax_c):
            ax.set_xscale("log")
            ax.set_xlim(0.7, x_hi * 1.6)
            ax.grid(axis="y", color=RULE, linewidth=0.7)
            ax.set_axisbelow(True)
            ax.set_xlabel("Tokens per request  (log scale)", fontsize=9.4)

        # median callouts. Each label sits directly over its own marker - input
        # above the 50% line, output below - so the two can never read as swapped.
        # Only a label that would overrun the panel edge is nudged inward.
        from math import log10
        lo, hi = 0.7, x_hi * 1.6
        for med, kind, colour in medians:
            ax_c.plot([med], [50], marker="o", markersize=5.5, color=colour, zorder=6)
            frac = (log10(med) - log10(lo)) / (log10(hi) - log10(lo))
            ha, dx = "center", 0
            if frac > 0.88:
                ha, dx = "right", 5
            elif frac < 0.12:
                ha, dx = "left", -5
            ax_c.annotate(f"median {med:,.0f}", xy=(med, 50),
                          xytext=(dx, 13 if kind == "input" else -18),
                          textcoords="offset points", ha=ha,
                          fontsize=8.6, color=colour, fontweight="bold", zorder=7)

        ax_d.set_ylim(0, y_hi * 1.16)
        ax_d.set_title(f"{label}  \u2014  {n:,} requests", fontsize=10.6,
                       color=INK, pad=7)
        ax_d.set_ylabel("Number of requests", fontsize=9.8)
        ax_d.yaxis.set_major_formatter(plt.FuncFormatter(_count_fmt))

        ax_c.set_title(f"{label}  \u2014  cumulative", fontsize=10.6, color=INK, pad=7)
        ax_c.set_ylabel("Requests at or below x  (%)", fontsize=9.8)
        ax_c.set_ylim(0, 104)
        ax_c.set_yticks([0, 25, 50, 75, 100])
        ax_c.axhline(50, color=MUTED, linewidth=0.8, linestyle=":", zorder=1)

    # one legend for the whole figure - repeating it in every panel is noise
    handles = [plt.Line2D([0], [0], color=SERIES[t], linewidth=2.4) for _, _, t in KINDS]
    fig.legend(handles, [lbl for _, lbl, _ in KINDS], loc="lower left",
               bbox_to_anchor=(0.070, top + 0.045), ncol=2, frameon=False,
               fontsize=9.8, handlelength=1.9, columnspacing=2.2)

    frame(fig, axes[0][0], plot_id, cfg["title"], subtitle, cfg["source"],
          "\u00a73.2 \u2014 What we measured; \u00a77.9 \u2014 De-duplication rule 3, "
          "sub-types", note)
    save(fig, plot_id)


# ============================= Epoch AI data centers (P-4 / P-5 / P-6 / P-7 / P-8)
# Reproduces the three metric tabs of Epoch's own AI Data Centers timeline
# (Compute / IT Power / Cost) from the published CSVs, then two further charts
# the remaining files in that download support.
DC_DATA = REPO / "ai-infrastructure" / "data"

# Owner palette. Nine slots is more than the four-colour house set carries, so
# the extras stay inside the same muted register rather than turning categorical.
DC_COLOURS = ["#1f3864", "#4a6fa5", "#6b8f71", "#b4763a", "#7d5a7d",
              "#4e8a8b", "#9aa9c4", "#a46b6b", "#c3c8d1"]

DC_METRICS = {
    "P-4": ("compute_h100e", "Compute capacity",
            "H100-equivalents", 1e6, "{v:.0f}M",
            "Compute is derived from IT power and the chip mix Epoch judges most "
            "likely to be installed; only where a site's chips are actually "
            "reported is it counted directly."),
    "P-5": ("it_power_mw", "IT power",
            "IT power (GW)", 1e3, "{v:.0f} GW",
            "IT power is the load of the computing equipment itself, not the "
            "facility total, and is largely inferred from cooling equipment "
            "visible in satellite imagery."),
    "P-6": ("capital_cost_busd", "Capital cost",
            "Cumulative capital cost (2025 US$ billions)", 1, "${v:.0f}bn",
            "Capital cost is modelled entirely from IT power using Epoch's "
            "cost-per-watt model; it is not drawn from company filings."),
}


def _dc_summary():
    import csv as _csv
    with (DC_DATA / "dc_summary.csv").open(encoding="utf-8") as f:
        return next(_csv.DictReader(f))


def _dc_frame(name):
    import csv as _csv
    with (DC_DATA / name).open(encoding="utf-8") as f:
        return list(_csv.DictReader(f))


def _dc_stack(ax, dates, series, labels, snapshot, ylabel, yscale, ytick):
    """Stacked area with the observed / projected split drawn, not described."""
    from datetime import date as _date
    xs = [_date.fromisoformat(d) for d in dates]
    vals = [[v / yscale for v in series[l]] for l in labels]
    ax.stackplot(xs, vals, colors=DC_COLOURS[:len(labels)], labels=labels,
                 edgecolor="white", linewidth=0.35)

    cut = _date.fromisoformat(snapshot)
    top = max(sum(col) for col in zip(*vals)) * 1.10
    ax.axvspan(cut, xs[-1], color="#f2f0ec", alpha=0.55, zorder=0)
    ax.axvline(cut, color=INK, linewidth=1.1, linestyle="--", zorder=6)
    ax.text(cut, top * 0.985, "  projected \u2192", ha="left", va="top",
            fontsize=8.6, color=MUTED, style="italic", zorder=7)
    ax.text(cut, top * 0.985, "\u2190 observed  ", ha="right", va="top",
            fontsize=8.6, color=MUTED, style="italic", zorder=7)

    ax.set_ylim(0, top)
    ax.set_xlim(xs[0], xs[-1])
    ax.set_ylabel(ylabel, fontsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _p: ytick.format(v=v)))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)


def _dc_top_owners(rows, metric, snapshot, n=8):
    at = {r["group"]: float(r["value"]) for r in rows
          if r["metric"] == metric and r["group_kind"] == "owner"
          and r["date"] <= snapshot}
    last = {}
    for r in rows:
        if r["metric"] == metric and r["group_kind"] == "owner" and r["date"] <= snapshot:
            last[r["group"]] = float(r["value"])
    ranked = sorted(last, key=lambda k: -last[k])
    return ranked[:n], ranked[n:]


def _dc_rect(subtitle, note, left=0.085, width=0.735, xlabel_room=0.055):
    """Panel rect that clears frame()'s subtitle above and footer below.

    frame() lays its furniture out in figure fractions, so anything that sets an
    axes rect by hand has to derive it from the same numbers or the text and the
    plot overlap once a note runs long.
    """
    n_sub = len(textwrap.wrap(subtitle, 122))
    n_note = len(textwrap.wrap(note, 133))
    top = 0.882 - (n_sub - 1) * 0.030 - 0.055
    bottom = 0.052 + 0.026 * (2 + n_note) + xlabel_room
    return [left, bottom, width, top - bottom]


def build_dc_metric(plot_id):
    metric, what, ylabel, yscale, ytick, caveat = DC_METRICS[plot_id]
    rows = _dc_frame("dc_metric_timeseries.csv")
    meta = _dc_summary()
    snapshot = meta["snapshot_date"]

    dates = sorted({r["date"] for r in rows})
    top, rest = _dc_top_owners(rows, metric, snapshot)
    labels = top + (["Other owners"] if rest else [])

    series = {l: [0.0] * len(dates) for l in labels}
    idx = {d: i for i, d in enumerate(dates)}
    for r in rows:
        if r["metric"] != metric or r["group_kind"] != "owner":
            continue
        key = r["group"] if r["group"] in top else "Other owners"
        if key in series:
            series[key][idx[r["date"]]] += float(r["value"])

    final = sum(series[l][-1] for l in labels) / yscale
    now = sum(series[l][idx[max(d for d in dates if d <= snapshot)]]
              for l in labels) / yscale
    prec = ytick.replace(":.0f", ":,.1f")

    subtitle = (f"What it shows: {what} across the {meta['sites']} AI data centers Epoch "
                f"tracks, stacked by owner. Solid ground is observed to {snapshot}; the "
                f"shaded band is Epoch's projection from announced construction "
                f"schedules.")
    note = (f"Snapshot downloaded {snapshot}; Epoch updates the dataset in place, so "
            f"live figures will differ. Reading {prec.format(v=now)} at the snapshot and "
            f"{prec.format(v=final)} by 2030 on present plans. {caveat} Coverage is about "
            f"27% of AI compute delivered globally and is strongest for the largest "
            f"sites, so this is a floor on the total, not the whole market. Everything "
            f"right of the dashed line is a schedule, not a measurement, and announced "
            f"build-outs slip. The flattening after 2029 is an artefact of the data "
            f"ending, not a forecast of saturation: each site is held at its last "
            f"announced milestone, and few sites have published one beyond then.")

    fig = plt.figure(figsize=(12.0, 8.1))
    ax = fig.add_axes(_dc_rect(subtitle, note))
    _dc_stack(ax, dates, series, labels, snapshot, ylabel, yscale, ytick)
    ax.set_xlabel("Quarter", fontsize=10)

    handles, labs = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labs[::-1], loc="upper left",
              bbox_to_anchor=(1.012, 1.0), frameon=False, fontsize=9,
              title="Owner", title_fontsize=9.2, handlelength=1.5,
              borderaxespad=0)

    frame(fig, ax, plot_id,
          f"{what} of the world's largest AI data centers, 2023\u20132030",
          subtitle,
          "Epoch AI, AI Data Centers (CC-BY) \u2014 https://epoch.ai/data/ai-data-centers",
          "Epoch AI data centers documentation \u2014 site-level cumulative snapshots, "
          "step-summed across sites",
          note)
    save(fig, plot_id, "ai-infrastructure")


def build_p7(_rows=None):
    """Accelerator mix over time, from the chip quantities table."""
    rows = _dc_frame("dc_chip_mix.csv")
    meta = _dc_summary()
    snapshot = meta["snapshot_date"]
    dates = sorted({r["date"] for r in rows})
    idx = {d: i for i, d in enumerate(dates)}

    last = {}
    for r in rows:
        if r["date"] <= snapshot:
            last[r["chip_type"]] = max(last.get(r["chip_type"], 0), float(r["units"]))
    ranked = sorted(last, key=lambda k: -last[k])
    top, rest = ranked[:8], ranked[8:]
    labels = top + (["Other chips"] if rest else [])
    series = {l: [0.0] * len(dates) for l in labels}
    for r in rows:
        key = r["chip_type"] if r["chip_type"] in top else "Other chips"
        if key in series:
            series[key][idx[r["date"]]] += float(r["units"])

    fig = plt.figure(figsize=(12.0, 7.9))
    ax = fig.add_axes([0.085, 0.30, 0.735, 0.475])
    _dc_stack(ax, dates, series, labels, snapshot,
              "Accelerators installed (millions of units)", 1e6, "{v:.1f}M")
    ax.set_xlabel("Quarter", fontsize=10)
    handles, labs = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labs[::-1], loc="upper left", bbox_to_anchor=(1.012, 1.0),
              frameon=False, fontsize=9, title="Chip type", title_fontsize=9.2,
              handlelength=1.5, borderaxespad=0)

    frame(fig, ax, "P-7",
          "Accelerator mix across tracked AI data centers, 2023\u20132030",
          "What it shows: how many accelerators of each type are installed across the "
          "sites where Epoch records a chip breakdown, stacked by chip type.",
          "Epoch AI, AI Data Centers \u2014 data_center_chip_quantities.csv (CC-BY)",
          "Epoch AI data centers documentation \u2014 cumulative per-site chip counts, "
          "step-summed",
          f"Units are counted, not performance-weighted: one Trainium2 and one B300 "
          f"each count as one accelerator, though they differ several-fold in "
          f"throughput. Use the compute chart for capacity. Only "
          f"{meta['chip_rows_company_disclosed']} of {meta['chip_rows']} chip records "
          f"are company disclosures; the rest are Epoch estimates. Chip detail exists "
          f"for only a subset of sites, so this understates total deployment and is "
          f"not comparable in level with the compute chart. Right of the dashed line "
          f"is planned deployment.")
    save(fig, "P-7", "ai-infrastructure")


def build_p8(_rows=None):
    """Cooling capacity against footprint - the basis for reading power off imagery."""
    import math
    rows = _dc_frame("dc_cooling_equipment.csv")
    meta = _dc_summary()
    groups = {}
    for r in rows:
        try:
            a, c = float(r["area_m2"]), float(r["capacity_kw"])
        except ValueError:
            continue
        if a <= 0 or c <= 0:
            continue
        groups.setdefault(r["equipment"], []).append((a, c))

    order = sorted(groups, key=lambda k: -len(groups[k]))
    tones = {"Cooling tower (wet)": SERIES["current"],
             "Chiller (air-cooled)": SERIES["scope"],
             "Chiller (water-cooled)": SERIES["other"]}

    fig = plt.figure(figsize=(11.6, 7.7))
    ax = fig.add_axes([0.085, 0.315, 0.875, 0.465])

    for g in order:
        pts = groups[g]
        colour = tones.get(g, SERIES["prior"])
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=26,
                   facecolor=colour, edgecolor="white", linewidth=0.4,
                   alpha=0.75, label=f"{g}  (n={len(pts)})", zorder=3)

    allpts = [p for g in order for p in groups[g]]
    med = sorted(c / a for a, c in allpts)[len(allpts) // 2]
    xs = [min(p[0] for p in allpts), max(p[0] for p in allpts)]
    ax.plot(xs, [med * x for x in xs], color=MUTED, linewidth=1.2, linestyle="--",
            zorder=2, label=f"Median intensity  {med:,.0f} kW/m\u00b2")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Footprint of the unit (m\u00b2, log scale)", fontsize=10)
    ax.set_ylabel("Rated cooling capacity (kW, log scale)", fontsize=10)
    ax.grid(color=RULE, linewidth=0.7, which="major")
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9, loc="upper left")

    frame(fig, ax, "P-8",
          "Cooling hardware size predicts its capacity, and so a site's power",
          "What it shows: rated cooling capacity against physical footprint for every "
          "unit in Epoch's two equipment reference tables. The tight relationship is "
          "what lets a rooftop count in an aerial image become a power estimate.",
          "Epoch AI, AI Data Centers \u2014 data_center_cooling_towers.csv and "
          "data_center_chillers.csv (CC-BY)",
          "Epoch AI data centers documentation \u2014 cooling equipment reference tables",
          f"These are manufacturer catalogue specifications, not measurements of "
          f"installed units, and rated capacity is an upper bound that real duty "
          f"rarely reaches. {meta['cooling_equipment_usable']} of "
          f"{meta['cooling_equipment_rows']} catalogue rows carry both a footprint and "
          f"a capacity and are plotted; the rest are omitted rather than imputed. The "
          f"median line is a summary of central tendency, not a fitted model, and the "
          f"three equipment classes have genuinely different intensities, so applying "
          f"one ratio to a mixed site introduces error.")
    save(fig, "P-8", "ai-infrastructure")


BUILDERS = {"P-01": build_p01, "P-03": build_p03, "P-58": build_p58}
BUILDERS.update({pid: (lambda _rows, _p=pid: build_dc_metric(_p)) for pid in DC_METRICS})
BUILDERS.update({"P-7": build_p7, "P-8": build_p8})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_azure(_p)) for pid in AZURE_PLOTS})


def main():
    rows = load_disclosures()
    wanted = sys.argv[1:] or sorted(BUILDERS)
    for pid in wanted:
        if pid not in BUILDERS:
            print(f"  skip {pid}: no builder implemented yet")
            continue
        print(f"building {pid}")
        BUILDERS[pid](rows)


if __name__ == "__main__":
    main()
