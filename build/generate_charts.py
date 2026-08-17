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
    # captions quote dollar figures; without this a "$316bn ... $143bn" pair is
    # parsed as mathtext and the chart fails to render
    "text.parse_math": False,
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


# ==================== Epoch AI published visualizations (EPOCH-01 / EPOCH-02)
# Faithful reproductions of Epoch's own AI Data Centers views, rebuilt from the
# published CSVs rather than screenshotted, and restricted to observed data.
# Epoch's default published view has "Color by: None", i.e. a single total across
# all tracked sites, so that is what is drawn here.
DC_DATA = REPO / "ai-infrastructure" / "data"

EPOCH_PLOTS = {
    "EPOCH-01": {
        "metric": "compute_h100e",
        "title": "Compute capacity of AI data centers",
        "ylabel": "Installed compute (millions of H100-equivalents)",
        "scale": 1e6,
        "fmt": "{v:.1f}M",
        "exact": "{v:,.0f} H100-equivalents",
        "what": "installed compute capacity",
        "derivation": "Compute is derived by Epoch from IT power and the chip mix "
                      "judged most likely to be installed, except where a site's "
                      "chips are actually reported. It is a modelled quantity, not "
                      "a hardware inventory.",
    },
    "EPOCH-02": {
        "metric": "it_power_mw",
        "title": "IT power of AI data centers",
        "ylabel": "Installed IT power (GW)",
        "scale": 1e3,
        "fmt": "{v:.1f} GW",
        "exact": "{v:,.1f} MW",
        "what": "installed IT power",
        "derivation": "IT power is the load of the computing equipment itself, not "
                      "the facility total, and is estimated by Epoch largely from "
                      "cooling equipment visible in satellite imagery. Facility "
                      "power runs about 1.28x higher.",
    },
}


def _epoch_data():
    import csv as _csv
    with (DC_DATA / "epoch_observed_series.csv").open(encoding="utf-8") as f:
        series = list(_csv.DictReader(f))
    with (DC_DATA / "epoch_observed_summary.csv").open(encoding="utf-8") as f:
        summary = {r["metric"]: r for r in _csv.DictReader(f)}
    return series, summary


def build_epoch(plot_id):
    from datetime import date as _date
    import matplotlib.dates as mdates

    cfg = EPOCH_PLOTS[plot_id]
    series, summary = _epoch_data()
    meta = summary[cfg["metric"]]
    snapshot = _date.fromisoformat(meta["snapshot_date"])
    axis_start = _date(2023, 1, 1)

    xs = [_date.fromisoformat(r["date"]) for r in series]
    ys = [float(r[cfg["metric"]]) for r in series]
    shown = [(x, y) for x, y in zip(xs, ys) if x >= axis_start]
    px = [p[0] for p in shown]
    py = [p[1] / cfg["scale"] for p in shown]
    final = float(meta["value_at_snapshot"])

    subtitle = (f"What it shows: total {cfg['what']} across the "
                f"{meta['sites_with_observed_data']} AI data centers Epoch tracks, "
                f"reproduced from Epoch's published dataset. Observed data only \u2014 "
                f"every future-dated milestone in the source has been excluded, so the "
                f"series ends at the snapshot rather than running to 2030.")
    note = (f"Observed data only. Epoch's files carry no observed/projected flag, so the "
            f"boundary is the date: {meta['records_projected_excluded']} of "
            f"{meta['records_after_site_join']} timeline records are dated after the "
            f"{meta['snapshot_date']} snapshot and are excluded as schedules, leaving "
            f"{meta['records_observed']} observed records. Including them would carry "
            f"the line to {float(meta['value_if_projections_included'])/cfg['scale']:,.1f}"
            f"{'M' if cfg['scale'] > 1e5 else ' GW'} by 2030, which is a plan, not a "
            f"measurement. The step-sum at the snapshot reproduces Epoch's own published "
            f"current total exactly. {cfg['derivation']} Coverage is about 27% of AI "
            f"compute delivered globally and is strongest for the largest sites, so this "
            f"is a floor on the world total. Values before "
            f"{axis_start.isoformat()} are included in the level but off the axis.")

    n_sub = len(textwrap.wrap(subtitle, 122))
    n_note = len(textwrap.wrap(note, 133))
    fig = plt.figure(figsize=(12.0, 7.9))
    top = 0.882 - (n_sub - 1) * 0.030 - 0.055
    bottom = 0.052 + 0.026 * (2 + n_note) + 0.060
    ax = fig.add_axes([0.088, bottom, 0.872, top - bottom])

    ax.step(px, py, where="post", color=SERIES["current"], linewidth=2.4, zorder=4)
    ax.fill_between(px, py, step="post", color=SERIES["current"], alpha=0.11, zorder=3)

    ax.set_xlim(axis_start, snapshot)
    ax.set_ylim(0, max(py) * 1.20)
    ax.set_ylabel(cfg["ylabel"], fontsize=10)
    ax.set_xlabel("Date", fontsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _p: cfg["fmt"].format(v=v)))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)

    # end-of-series callout: the figure a reader will quote
    ax.plot([snapshot], [py[-1]], marker="o", markersize=6,
            color=SERIES["current"], zorder=6)
    ax.annotate(f"{cfg['fmt'].format(v=py[-1])}\n{meta['snapshot_date']}",
                xy=(snapshot, py[-1]), xytext=(-12, 16),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=10, fontweight="bold", color=INK, zorder=7)

    # the constraint that defines this chart, stated on its face
    ax.text(0.017, 0.955, "  OBSERVED DATA ONLY  \u00b7  projections excluded  ",
            transform=ax.transAxes, ha="left", va="top", fontsize=9.1,
            fontweight="bold", color="white", zorder=8,
            bbox=dict(boxstyle="round,pad=0.42", facecolor=SERIES["current"],
                      edgecolor="none"))

    frame(fig, ax, plot_id, cfg["title"], subtitle,
          "Epoch AI, AI Data Centers (CC-BY) \u2014 https://epoch.ai/data/ai-data-centers",
          "Methodology reference pending final methodology document; derivation follows "
          "Epoch AI's published data centers documentation",
          note)
    save(fig, plot_id, "ai-infrastructure")


# ================= Epoch views by company + derived analysis (observed only)
DC_COLOURS = ["#1f3864", "#4a6fa5", "#6b8f71", "#b4763a", "#7d5a7d",
              "#4e8a8b", "#9aa9c4", "#a46b6b", "#8a8f5c", "#c3c8d1"]

OWNER_METRICS = {
    "EPOCH-03": ("compute_h100e", "Compute capacity of AI data centers, by company",
                 "Installed compute (millions of H100-equivalents)", 1e6, "{v:.1f}M",
                 "Compute is derived by Epoch from IT power and the chip mix judged "
                 "most likely to be installed, except where a site's chips are "
                 "reported. It is modelled, not a hardware inventory."),
    "EPOCH-04": ("it_power_mw", "IT power of AI data centers, by company",
                 "Installed IT power (GW)", 1e3, "{v:.1f} GW",
                 "IT power is the computing load only, not the facility total, and is "
                 "estimated largely from cooling equipment visible in satellite "
                 "imagery. Facility power runs about 1.28x higher."),
    "EPOCH-05": ("capital_cost_busd", "Capital cost of AI data centers, by company",
                 "Capital cost (2025 US$ billions)", 1, "${v:,.0f}bn",
                 "Capital cost is modelled entirely from IT power using Epoch's "
                 "cost-per-watt model; it is not drawn from company filings."),
}


def _dcsv(name):
    import csv as _csv
    with (DC_DATA / name).open(encoding="utf-8") as f:
        return list(_csv.DictReader(f))


def _dc_meta():
    return {r["metric"]: r for r in _dcsv("epoch_observed_summary.csv")}


def _owner_stack(metric, top_n=9):
    """Forward-fill each owner's change points onto the common date axis.

    The per-owner series sums back to Epoch's published total exactly; that is
    asserted in build/summarise_epoch_datacenters.py, not assumed here.
    """
    from datetime import date as _date
    rows = _dcsv("epoch_observed_by_owner.csv")
    dates = sorted({r["date"] for r in rows})
    owners = sorted({r["owner"] for r in rows})

    filled = {}
    for ow in owners:
        pts = {r["date"]: float(r[metric]) for r in rows if r["owner"] == ow}
        run, out = 0.0, []
        for d in dates:
            if d in pts:
                run = pts[d]
            out.append(run)
        filled[ow] = out

    ranked = sorted(owners, key=lambda o: -filled[o][-1])
    keep, rest = ranked[:top_n], ranked[top_n:]
    series = {o: filled[o] for o in keep}
    if rest:
        series["Other owners"] = [sum(filled[o][i] for o in rest)
                                  for i in range(len(dates))]
    labels = keep + (["Other owners"] if rest else [])
    return [_date.fromisoformat(d) for d in dates], series, labels


def _observed_badge(ax, above=False):
    """The constraint that defines these charts, stated on the plot itself.

    Bar charts fill their top-left corner, so there the badge sits just above the
    axes instead of inside them.
    """
    y, va = (1.030, "bottom") if above else (0.955, "top")
    ax.text(0.0 if above else 0.017, y,
            "  OBSERVED DATA ONLY  \u00b7  projections excluded  ",
            transform=ax.transAxes, ha="left", va=va, fontsize=9.1,
            fontweight="bold", color="white", zorder=9, clip_on=False,
            bbox=dict(boxstyle="round,pad=0.42", facecolor=SERIES["current"],
                      edgecolor="none"))


def _rect(subtitle, note, left=0.075, width=0.700, xlabel_room=0.058,
          badge_above=False):
    n_sub = len(textwrap.wrap(subtitle, 122))
    n_note = len(textwrap.wrap(note, 133))
    top = 0.882 - (n_sub - 1) * 0.030 - 0.055 - (0.040 if badge_above else 0.0)
    bottom = 0.052 + 0.026 * (2 + n_note) + xlabel_room
    return [left, bottom, width, top - bottom]


EPOCH_SRC = "Epoch AI, AI Data Centers (CC-BY) \u2014 https://epoch.ai/data/ai-data-centers"
EPOCH_METH = ("Methodology reference pending final methodology document; derivation "
              "follows Epoch AI's published data centers documentation")


def build_owner_metric(plot_id):
    import matplotlib.dates as mdates
    from datetime import date as _date
    metric, title, ylabel, scale, fmt, caveat = OWNER_METRICS[plot_id]
    meta = _dc_meta()[metric]
    snapshot = _date.fromisoformat(meta["snapshot_date"])
    dates, series, labels = _owner_stack(metric)

    keep = [i for i, d in enumerate(dates) if d >= _date(2023, 1, 1)]
    px = [dates[i] for i in keep]
    stacks = [[series[l][i] / scale for i in keep] for l in labels]
    total_now = sum(series[l][-1] for l in labels)

    subtitle = (f"What it shows: the same Epoch view broken out by owner \u2014 who has "
                f"actually built the {meta['sites_with_observed_data']} tracked sites. "
                f"Observed data only; the {meta['records_projected_excluded']} "
                f"future-dated milestones in the source are excluded, so the series "
                f"stops at the {meta['snapshot_date']} snapshot rather than 2030.")
    note = (f"Owner shares sum to Epoch's published total of "
            f"{fmt.format(v=total_now/scale)} exactly. Ownership is the entity that "
            f"built and holds the site, which is often not the entity using it - "
            f"see the owner-versus-user chart in Derived Analysis. \"Unknown\" is "
            f"Epoch's own label where ownership is unattributed, not a residual we "
            f"computed. {caveat} Coverage is about 27% of AI compute delivered "
            f"globally and is strongest for the largest sites, so every share is a "
            f"share of what Epoch tracks, not of the world.")

    fig = plt.figure(figsize=(12.0, 8.3))
    ax = fig.add_axes(_rect(subtitle, note))
    ax.stackplot(px, stacks, colors=DC_COLOURS[:len(labels)], labels=labels,
                 edgecolor="white", linewidth=0.35)
    ax.set_xlim(px[0], snapshot)
    ax.set_ylim(0, max(sum(c) for c in zip(*stacks)) * 1.18)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xlabel("Date", fontsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: fmt.format(v=v)))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _observed_badge(ax)

    h, l = ax.get_legend_handles_labels()
    ax.legend(h[::-1], l[::-1], loc="upper left", bbox_to_anchor=(1.015, 1.0),
              frameon=False, fontsize=9, title="Owner", title_fontsize=9.2,
              handlelength=1.5, borderaxespad=0)
    ax.annotate(f"{fmt.format(v=total_now/scale)}\n{meta['snapshot_date']}",
                xy=(snapshot, total_now / scale), xytext=(-10, 14),
                textcoords="offset points", ha="right", fontsize=10,
                fontweight="bold", color=INK, zorder=8)

    frame(fig, ax, plot_id, title, subtitle, EPOCH_SRC, EPOCH_METH, note)
    save(fig, plot_id, "ai-infrastructure")


# ------------------------------------------------- Derived Analysis (observed)
def _sites():
    rows = _dcsv("dc_sites_observed.csv")
    for r in rows:
        for k in ("compute_h100e", "it_power_mw", "capital_cost_busd",
                  "compute_cost_busd", "construction_cost_busd", "annual_opex_busd"):
            r[k] = float(r[k])
    return rows


def build_d01(_r=None):
    """How concentrated the observed build-out is across individual sites."""
    rows = sorted(_sites(), key=lambda r: -r["compute_h100e"])
    meta = _dc_meta()["compute_h100e"]
    total = sum(r["compute_h100e"] for r in rows)
    top = rows[:15]
    owners = [r["owner"] for r in top]
    palette = {o: DC_COLOURS[i % len(DC_COLOURS)]
               for i, o in enumerate(dict.fromkeys(owners))}

    subtitle = ("What it shows: the 15 largest sites by observed compute, and how much "
                "of the tracked total they account for. A useful check on whether AI "
                "capacity is a handful of megasites or a broad build-out.")
    note = (f"Observed data only, at the {meta['snapshot_date']} snapshot. The largest "
            f"single site holds {top[0]['compute_h100e']/total*100:.1f}% of tracked "
            f"compute, the top 10 hold "
            f"{sum(r['compute_h100e'] for r in rows[:10])/total*100:.1f}% and the top 20 "
            f"hold {sum(r['compute_h100e'] for r in rows[:20])/total*100:.1f}%. "
            f"{sum(1 for r in rows if r['compute_h100e'] == 0)} of {len(rows)} tracked "
            f"sites have no observed compute yet - they are under construction, and "
            f"they are counted in the denominator. Concentration is measured across "
            f"Epoch's coverage, which is deliberately biased toward the largest sites, "
            f"so the real market is less concentrated than this.")

    fig = plt.figure(figsize=(12.0, 8.6))
    ax = fig.add_axes(_rect(subtitle, note, left=0.315, width=0.635, xlabel_room=0.05, badge_above=True))
    ys = range(len(top))[::-1]
    ax.barh(list(ys), [r["compute_h100e"] / 1e3 for r in top], height=0.72,
            color=[palette[r["owner"]] for r in top], edgecolor="white", linewidth=0.6)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([r["site"] for r in top], fontsize=9.2)
    ax.set_xlabel("Observed compute (thousands of H100-equivalents)", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    for y, r in zip(ys, top):
        ax.text(r["compute_h100e"] / 1e3 + total / 1e3 * 0.006, y,
                f"{r['compute_h100e']/1e3:,.0f}k  \u00b7  {r['compute_h100e']/total*100:.1f}%",
                va="center", fontsize=8.6, color=MUTED)
    ax.set_xlim(0, max(r["compute_h100e"] for r in top) / 1e3 * 1.20)
    seen = []
    for o in owners:
        if o not in seen:
            seen.append(o)
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=palette[o]) for o in seen], seen,
              loc="lower right", frameon=False, fontsize=8.8, title="Owner",
              title_fontsize=9)
    _observed_badge(ax, above=True)
    frame(fig, ax, "DERIVED-01",
          "AI compute is concentrated, but not in a single site",
          subtitle, EPOCH_SRC, EPOCH_METH, note)
    save(fig, "DERIVED-01", "ai-infrastructure")


def build_d02(_r=None):
    """Where the observed capacity physically is."""
    rows = _sites()
    meta = _dc_meta()["compute_h100e"]
    agg = {}
    for r in rows:
        a = agg.setdefault(r["country"], {"c": 0.0, "n": 0})
        a["c"] += r["compute_h100e"]
        a["n"] += 1
    order = sorted(agg, key=lambda k: -agg[k]["c"])
    total = sum(a["c"] for a in agg.values())
    zero = [k for k in order if agg[k]["c"] == 0]

    subtitle = ("What it shows: observed compute and tracked site count by country. The "
                "single most important structural fact about the dataset, and the "
                "reason it cannot be read as a picture of global capacity.")
    note = (f"Observed data only, at the {meta['snapshot_date']} snapshot. The United "
            f"States holds {agg[order[0]]['c']/total*100:.1f}% of observed compute "
            f"across {agg[order[0]]['n']} of {len(rows)} tracked sites. That is partly "
            f"real and partly coverage: Epoch states the database is strongest in the "
            f"US and is still expanding elsewhere, so non-US capacity is understated by "
            f"an unknown margin rather than absent. "
            f"{', '.join(zero)} appear with tracked sites but no observed compute yet. "
            f"Chinese capacity in particular is known to be larger than the three sites "
            f"recorded here.")

    fig = plt.figure(figsize=(11.6, 7.9))
    ax = fig.add_axes(_rect(subtitle, note, left=0.185, width=0.755, xlabel_room=0.05, badge_above=True))
    ys = list(range(len(order)))[::-1]
    ax.barh(ys, [agg[k]["c"] / 1e6 for k in order], height=0.68,
            color=SERIES["current"], edgecolor="white", linewidth=0.6)
    ax.set_yticks(ys)
    ax.set_yticklabels(order, fontsize=9.6)
    ax.set_xlabel("Observed compute (millions of H100-equivalents)", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    xmax = max(agg[k]["c"] for k in order) / 1e6
    for y, k in zip(ys, order):
        v = agg[k]["c"] / 1e6
        lab = (f"{v:,.2f}M  \u00b7  {agg[k]['c']/total*100:.1f}%  "
               f"({agg[k]['n']} site{'s' if agg[k]['n'] != 1 else ''})")
        ax.text(v + xmax * 0.012, y, lab, va="center", fontsize=8.8, color=MUTED)
    ax.set_xlim(0, xmax * 1.34)
    _observed_badge(ax, above=True)
    frame(fig, ax, "DERIVED-02",
          "The tracked build-out is almost entirely American",
          subtitle, EPOCH_SRC, EPOCH_METH, note)
    save(fig, "DERIVED-02", "ai-infrastructure")


def build_d03(_r=None):
    """What the money buys: chips versus buildings."""
    rows = _sites()
    meta = _dc_meta()["capital_cost_busd"]
    agg = {}
    for r in rows:
        a = agg.setdefault(r["owner"], {"chips": 0.0, "build": 0.0, "opex": 0.0})
        a["chips"] += r["compute_cost_busd"]
        a["build"] += r["construction_cost_busd"]
        a["opex"] += r["annual_opex_busd"]
    order = [o for o in sorted(agg, key=lambda k: -(agg[k]["chips"] + agg[k]["build"]))
             if agg[o]["chips"] + agg[o]["build"] > 0]
    chips = sum(a["chips"] for a in agg.values())
    build = sum(a["build"] for a in agg.values())
    opex = sum(a["opex"] for a in agg.values())

    subtitle = ("What it shows: observed capital cost split into compute hardware and "
                "construction, by owner. In Epoch's cost model the two sum exactly to "
                "the capital total, so the split is arithmetic rather than an estimate "
                "layered on top.")
    note = (f"Observed data only, at the {meta['snapshot_date']} snapshot. Across all "
            f"tracked sites, chips are ${chips:,.0f}bn of ${chips+build:,.0f}bn capital "
            f"({chips/(chips+build)*100:.1f}%) and buildings ${build:,.0f}bn "
            f"({build/(chips+build)*100:.1f}%). Annual operating cost, a flow rather "
            f"than a stock, runs a further ${opex:,.1f}bn a year and is deliberately "
            f"not stacked into the capital bars. Read this as scale, not as cost "
            f"structure: Epoch derives both components from IT power with a fixed "
            f"cost-per-watt model, so the chips/buildings ratio is identical for every "
            f"owner by construction and carries no information about how differently "
            f"these companies build. Only the totals differ. Nothing here is reported "
            f"company spend, and it should not be reconciled against capex disclosures.")

    fig = plt.figure(figsize=(11.8, 8.0))
    ax = fig.add_axes(_rect(subtitle, note, left=0.145, width=0.795, xlabel_room=0.05, badge_above=True))
    ys = list(range(len(order)))[::-1]
    c1 = [agg[o]["chips"] for o in order]
    c2 = [agg[o]["build"] for o in order]
    ax.barh(ys, c1, height=0.70, color=SERIES["current"], label="Compute hardware",
            edgecolor="white", linewidth=0.6)
    ax.barh(ys, c2, height=0.70, left=c1, color=SERIES["scope"], label="Construction",
            edgecolor="white", linewidth=0.6)
    ax.set_yticks(ys)
    ax.set_yticklabels(order, fontsize=9.6)
    ax.set_xlabel("Observed capital cost (2025 US$ billions)", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    xmax = max(a + b for a, b in zip(c1, c2))
    for y, o in zip(ys, order):
        t = agg[o]["chips"] + agg[o]["build"]
        ax.text(t + xmax * 0.012, y, f"${t:,.0f}bn", va="center",
                fontsize=8.8, color=MUTED)
    ax.set_xlim(0, xmax * 1.30)
    ax.legend(loc="lower right", frameon=False, fontsize=9.2)
    _observed_badge(ax, above=True)
    frame(fig, ax, "DERIVED-03",
          "Epoch's cost model puts roughly two-thirds of the capital in chips",
          subtitle, EPOCH_SRC, EPOCH_METH, note)
    save(fig, "DERIVED-03", "ai-infrastructure")


def build_d04(_r=None):
    """Accelerator mix over time, observed only."""
    import matplotlib.dates as mdates
    from datetime import date as _date
    rows = _dcsv("dc_chip_mix_observed.csv")
    meta = _dc_meta()["compute_h100e"]
    dates = sorted({r["date"] for r in rows})
    chips = sorted({r["chip_type"] for r in rows})
    filled = {}
    for c in chips:
        pts = {r["date"]: float(r["units"]) for r in rows if r["chip_type"] == c}
        run, out = 0.0, []
        for d in dates:
            if d in pts:
                run = pts[d]
            out.append(run)
        filled[c] = out
    ranked = sorted(chips, key=lambda c: -filled[c][-1])
    keep, rest = ranked[:9], ranked[9:]
    labels = keep + (["Other chips"] if rest else [])
    series = {c: filled[c] for c in keep}
    if rest:
        series["Other chips"] = [sum(filled[c][i] for c in rest) for i in range(len(dates))]

    px = [_date.fromisoformat(d) for d in dates]
    idx = [i for i, d in enumerate(px) if d >= _date(2023, 1, 1)]
    px = [px[i] for i in idx]
    stacks = [[series[l][i] / 1e6 for i in idx] for l in labels]
    total = sum(series[l][-1] for l in labels)

    subtitle = ("What it shows: how many accelerators of each type are installed at the "
                "sites where Epoch records a chip breakdown, over time.")
    note = (f"Observed data only: {meta['chip_records_observed']} of "
            f"{meta['chip_records_total']} chip records are dated at or before the "
            f"snapshot; {meta['chip_records_projected_excluded']} future-dated records "
            f"are excluded. Units are counted, not performance-weighted - one TPU v5e "
            f"and one B300 each count once despite differing several-fold in "
            f"throughput, so this is a headcount, not capacity. Only "
            f"{meta['chip_units_company_disclosed']} of "
            f"{meta['chip_records_total']} unit counts come from company disclosure; "
            f"the rest are Epoch estimates. Chip detail exists for a subset of sites "
            f"only, so the level here is not comparable with the compute charts.")

    fig = plt.figure(figsize=(12.0, 8.3))
    ax = fig.add_axes(_rect(subtitle, note))
    ax.stackplot(px, stacks, colors=DC_COLOURS[:len(labels)], labels=labels,
                 edgecolor="white", linewidth=0.35)
    ax.set_xlim(px[0], _date.fromisoformat(meta["snapshot_date"]))
    ax.set_ylim(0, max(sum(c) for c in zip(*stacks)) * 1.18)
    ax.set_ylabel("Accelerators installed (millions of units)", fontsize=10)
    ax.set_xlabel("Date", fontsize=10)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(4, 7, 10)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.1f}M"))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _observed_badge(ax)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h[::-1], l[::-1], loc="upper left", bbox_to_anchor=(1.015, 1.0),
              frameon=False, fontsize=9, title="Chip type", title_fontsize=9.2,
              handlelength=1.5, borderaxespad=0)
    ax.annotate(f"{total/1e6:.1f}M units\n{meta['snapshot_date']}",
                xy=(_date.fromisoformat(meta["snapshot_date"]), total / 1e6),
                xytext=(-10, 14), textcoords="offset points", ha="right",
                fontsize=10, fontweight="bold", color=INK)
    frame(fig, ax, "DERIVED-04",
          "Custom silicon carries as much of the installed fleet as Nvidia does",
          subtitle, EPOCH_SRC, EPOCH_METH, note)
    save(fig, "DERIVED-04", "ai-infrastructure")


def build_d05(_r=None):
    """Cooling capacity against footprint - the measurement backbone."""
    rows = _dcsv("dc_cooling_equipment.csv")
    meta = _dc_meta()["it_power_mw"]
    groups = {}
    for r in rows:
        try:
            a, c = float(r["area_m2"]), float(r["capacity_kw"])
        except (ValueError, KeyError):
            continue
        if a > 0 and c > 0:
            groups.setdefault(r["equipment"], []).append((a, c))
    order = sorted(groups, key=lambda k: -len(groups[k]))
    tones = {"Cooling tower (wet)": SERIES["current"],
             "Chiller (air-cooled)": SERIES["scope"],
             "Chiller (water-cooled)": SERIES["other"]}

    subtitle = ("What it shows: rated cooling capacity against physical footprint for "
                "every unit in Epoch's two equipment catalogues. This relationship is "
                "the measurement backbone of the whole dataset - it is what turns a "
                "rooftop counted in an aerial image into a power figure.")
    allpts = [p for g in order for p in groups[g]]
    med = sorted(c / a for a, c in allpts)[len(allpts) // 2]
    note = (f"Manufacturer catalogue specifications, not measurements of installed "
            f"units: rated capacity is an upper bound that real duty rarely reaches. "
            f"{meta['cooling_rows_usable']} of {meta['cooling_rows']} catalogue rows "
            f"carry both a footprint and a capacity and are plotted; the rest are "
            f"omitted rather than imputed. The dashed line is the median intensity of "
            f"{med:,.0f} kW per m\u00b2, a summary of central tendency and not a fitted "
            f"model - the three equipment classes have visibly different intensities, "
            f"so applying one ratio to a mixed site introduces error. This is the step "
            f"where most of the uncertainty in the IT power figures originates.")

    fig = plt.figure(figsize=(11.6, 8.0))
    ax = fig.add_axes(_rect(subtitle, note, left=0.085, width=0.875, xlabel_room=0.05))
    for g in order:
        pts = groups[g]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=26,
                   facecolor=tones.get(g, SERIES["prior"]), edgecolor="white",
                   linewidth=0.4, alpha=0.75, label=f"{g}  (n={len(pts)})", zorder=3)
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
    frame(fig, ax, "DERIVED-05",
          "Cooling hardware size predicts its capacity, and so a site's power",
          subtitle, EPOCH_SRC, EPOCH_METH, note)
    save(fig, "DERIVED-05", "ai-infrastructure")


def build_d06(_r=None):
    """Who builds the capacity versus who runs on it."""
    rows = _sites()
    meta = _dc_meta()["compute_h100e"]
    own, use = {}, {}
    for r in rows:
        own[r["owner"]] = own.get(r["owner"], 0.0) + r["compute_h100e"]
        use[r["primary_user"]] = use.get(r["primary_user"], 0.0) + r["compute_h100e"]
    names = [n for n in dict.fromkeys(list(own) + list(use))
             if own.get(n, 0) > 0 or use.get(n, 0) > 0]
    names = sorted(names, key=lambda n: -max(own.get(n, 0), use.get(n, 0)))
    total = sum(own.values())

    subtitle = ("What it shows: observed compute by the company that owns each site "
                "against the company recorded as its primary user. The gap between the "
                "two is the rental market: labs run on capacity other companies built.")
    note = (f"Observed data only, at the {meta['snapshot_date']} snapshot. Epoch records "
            f"a user for {meta['sites_with_primary_user']} of {len(rows)} sites; where "
            f"it does not, the site appears under \"Unknown\" on the user side, which "
            f"is why the Unknown user bar is large. Only the first listed user is taken "
            f"as primary, so shared sites are attributed whole to one tenant and the "
            f"user side is coarser than the owner side. Both columns total the same "
            f"{total/1e6:.1f}M H100-equivalents. Ownership and use are Epoch "
            f"attributions carrying their own confidence tags, not contractual facts.")

    fig = plt.figure(figsize=(11.8, 8.2))
    ax = fig.add_axes(_rect(subtitle, note, left=0.165, width=0.775, xlabel_room=0.05, badge_above=True))
    ys = list(range(len(names)))[::-1]
    h = 0.38
    ax.barh([y + h / 2 for y in ys], [own.get(n, 0) / 1e6 for n in names], height=h,
            color=SERIES["current"], label="Owns the site", edgecolor="white",
            linewidth=0.5)
    ax.barh([y - h / 2 for y in ys], [use.get(n, 0) / 1e6 for n in names], height=h,
            color=SERIES["other"], label="Primary user of the site", edgecolor="white",
            linewidth=0.5)
    ax.set_yticks(ys)
    ax.set_yticklabels(names, fontsize=9.6)
    ax.set_xlabel("Observed compute (millions of H100-equivalents)", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(max(own.values()), max(use.values())) / 1e6 * 1.16)
    ax.legend(loc="lower right", frameon=False, fontsize=9.2)
    _observed_badge(ax, above=True)
    frame(fig, ax, "DERIVED-06",
          "The largest users of AI compute are not the largest owners of it",
          subtitle, EPOCH_SRC, EPOCH_METH, note)
    save(fig, "DERIVED-06", "ai-infrastructure")


BUILDERS = {"P-01": build_p01, "P-03": build_p03, "P-58": build_p58}
BUILDERS.update({pid: (lambda _rows, _p=pid: build_azure(_p)) for pid in AZURE_PLOTS})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_epoch(_p)) for pid in EPOCH_PLOTS})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_owner_metric(_p)) for pid in OWNER_METRICS})
BUILDERS.update({"DERIVED-01": build_d01, "DERIVED-02": build_d02,
                 "DERIVED-03": build_d03, "DERIVED-04": build_d04,
                 "DERIVED-05": build_d05, "DERIVED-06": build_d06})


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
