#!/usr/bin/env python3
"""Generate AzureLLMInferenceTrace charts from company-disclosed figures.

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
import math
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


FOOTER_WRAP = 133


def _footer_lines(source, note):
    """The footer as it will actually be drawn, wrapped to the figure width."""
    src = textwrap.wrap(f"Source: {source}", FOOTER_WRAP,
                        subsequent_indent="        ")
    notes = textwrap.wrap(note, FOOTER_WRAP) if note else []
    return src, notes


def _footer_h(source, note):
    """Height the footer needs, in figure fractions.

    frame() draws the footer and _rect() and build_azure() reserve space above
    it, so all three read this one number. A source naming five files wraps to
    three lines; without this the last of them ran off the page.
    """
    src, notes = _footer_lines(source, note)
    return 0.052 + 0.026 * (len(src) + 1 + len(notes))


def frame(fig, ax, plot_id, title, subtitle, source, methodology, note):
    """Apply the standard chart furniture: ID, title, subtitle, footer block."""
    fig.text(0.035, 0.972, plot_id, ha="left", va="top", fontsize=10.5,
             fontweight="bold", color=NAVY, family="monospace")
    fig.text(0.035, 0.928, title, ha="left", va="top", fontsize=15.5,
             fontweight="bold", color=INK)
    for i, line in enumerate(textwrap.wrap(subtitle, 122)):
        fig.text(0.035, 0.882 - i * 0.030, line, ha="left", va="top",
                 fontsize=10.2, color=MUTED)

    src_lines, note_lines = _footer_lines(source, note)
    # footer grows upward from the bottom so long notes never spill off-page
    y = _footer_h(source, note)
    fig.lines.append(plt.Line2D([0.035, 0.965], [y, y], transform=fig.transFigure,
                                color=RULE, linewidth=0.8))
    cur = y - 0.022
    for line in src_lines:
        fig.text(0.035, cur, line, ha="left", va="top", fontsize=8.6, color=MUTED)
        cur -= 0.026
    fig.text(0.035, cur, f"Methodology: {methodology}", ha="left", va="top",
             fontsize=8.6, color=MUTED)
    cur -= 0.026
    for i, line in enumerate(note_lines):
        prefix = "Note: " if i == 0 else "      "
        fig.text(0.035, cur - i * 0.024, prefix + line, ha="left", va="top",
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
    # text.parse_math is off repo-wide, so any tick left on matplotlib's default
    # log formatter renders its mathtext source literally - several overlapping
    # "$\mathdefault{10^{4}}$" strings where the axis labels should be. It is
    # invisible in code review and obvious to a reader, so it fails here instead.
    if "mathdefault" in svg.read_text(encoding="utf-8"):
        raise SystemExit(
            f"{plot_id}: axis labels contain raw mathtext. A log axis was left on "
            f"matplotlib's default formatter - call _plain_log_axis() on it.")
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

# the exact published files each chart is built from, printed on its face. Same
# names summarise_azure_traces.py reads, so a chart never claims a file the
# derivation did not touch.
AZURE_FILES = {
    "conv_2023": "AzureLLMInferenceTrace_conv_2023.csv",
    "code_2023": "AzureLLMInferenceTrace_code_2023.csv",
    "conv_2024": "AzureLLMInferenceTrace_conv_2024.csv",
    "code_2024": "AzureLLMInferenceTrace_code_2024.csv",
    "multimodal_2025": "AzureLMMInferenceTrace_multimodal_2025.csv",
}


def azure_src(plot_id):
    cfg = AZURE_PLOTS[plot_id]
    return (cfg["source"] + " — "
            + " + ".join(AZURE_FILES[t] for t, _ in cfg["traces"])
            + " — github.com/Azure/AzurePublicDataset")


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
    bottom = _footer_h(azure_src(plot_id), note) + 0.055   # clear of the footer rule
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
            _plain_log_axis(ax.xaxis)
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

    frame(fig, axes[0][0], plot_id, cfg["title"], subtitle, azure_src(plot_id),
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

    frame(fig, ax, plot_id, cfg["title"], subtitle, epoch_src(plot_id),
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
          badge_above=False, source=None):
    n_sub = len(textwrap.wrap(subtitle, 122))
    n_note = len(textwrap.wrap(note, 133))
    top = 0.882 - (n_sub - 1) * 0.030 - 0.055 - (0.040 if badge_above else 0.0)
    # a source long enough to wrap makes the footer taller; callers that know
    # their source pass it so the axes clear the extra lines
    bottom = (_footer_h(source, note) if source is not None
              else 0.052 + 0.026 * (2 + n_note)) + xlabel_room
    return [left, bottom, width, top - bottom]


# the exact raw Epoch files each chart is built from, printed on its face so a
# downloaded SVG or PNG still says where every number came from
DC_FILES = {
    "EPOCH-01": ("data_centers.csv", "data_center_timelines.csv"),
    "EPOCH-02": ("data_centers.csv", "data_center_timelines.csv"),
    "EPOCH-03": ("data_centers.csv", "data_center_timelines.csv"),
    "EPOCH-04": ("data_centers.csv", "data_center_timelines.csv"),
    "EPOCH-05": ("data_centers.csv", "data_center_timelines.csv"),
    "DERIVED-01": ("data_centers.csv", "data_center_timelines.csv"),
    "DERIVED-02": ("data_centers.csv", "data_center_timelines.csv"),
    "DERIVED-03": ("data_centers.csv", "data_center_timelines.csv"),
    "DERIVED-04": ("data_center_chip_quantities.csv",),
    "DERIVED-05": ("data_center_cooling_towers.csv", "data_center_chillers.csv"),
    "DERIVED-06": ("data_centers.csv", "data_center_timelines.csv"),
}


def epoch_src(plot_id):
    return ("Epoch AI, AI Data Centers (CC-BY) \u2014 "
            + " + ".join(DC_FILES[plot_id])
            + " \u2014 epoch.ai/data/ai-data-centers")


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

    frame(fig, ax, plot_id, title, subtitle, epoch_src(plot_id), EPOCH_METH, note)
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
          subtitle, epoch_src("DERIVED-01"), EPOCH_METH, note)
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
          subtitle, epoch_src("DERIVED-02"), EPOCH_METH, note)
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
          subtitle, epoch_src("DERIVED-03"), EPOCH_METH, note)
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
          subtitle, epoch_src("DERIVED-04"), EPOCH_METH, note)
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
    _plain_log_axis(ax.xaxis)
    _plain_log_axis(ax.yaxis)
    ax.set_xlabel("Footprint of the unit (m\u00b2, log scale)", fontsize=10)
    ax.set_ylabel("Rated cooling capacity (kW, log scale)", fontsize=10)
    ax.grid(color=RULE, linewidth=0.7, which="major")
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    frame(fig, ax, "DERIVED-05",
          "Cooling hardware size predicts its capacity, and so a site's power",
          subtitle, epoch_src("DERIVED-05"), EPOCH_METH, note)
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
          subtitle, epoch_src("DERIVED-06"), EPOCH_METH, note)
    save(fig, "DERIVED-06", "ai-infrastructure")


# ==================================================== AI Models (Epoch AI)
# Epoch publishes one configurable figure at epoch.ai/data/ai-models: a scatter
# of a chosen metric against publication date, over a chosen release, optionally
# coloured by domain, organization or country, with a fitted trend. The MODELS-*
# charts below are that figure at each of its published settings, rebuilt from
# the downloaded CSVs. The MODELS-D* charts are our own analysis of the same
# files. Both obey the same rule: a model appears in a chart only where Epoch
# records the value being plotted. Nothing is imputed.
MODELS_DATA = REPO / "ai-models" / "data"
MODELS_DOMAIN = "ai-models"

MODELS_SRC = {
    "notable": "notable_ai_models.csv",
    "frontier": "frontier_ai_models.csv",
    "large_scale": "large_scale_ai_models.csv",
    "all": "all_ai_models.csv",
}
MODELS_LABEL = {
    "notable": "notable AI models",
    "frontier": "frontier AI models",
    "large_scale": "large-scale AI models",
    "all": "all AI models",
}
# what each release is, in Epoch's own terms, quoted on the chart that uses it
MODELS_DEF = {
    "notable": "Epoch's notable set: models with a state-of-the-art result on a "
               "recognised benchmark, over 1,000 citations, historical significance "
               "or significant use.",
    "frontier": "Epoch's frontier set: models that were in the top 10 by training "
                "compute at the time of their release.",
    "large_scale": "Epoch's large-scale set: models trained with more than 1e23 FLOP, "
                   "the static threshold used in several AI regulatory frameworks.",
    "all": "Epoch's full database of AI models, notable or not.",
}

MODELS_METH = ("Methodology reference pending final methodology document; derivation "
               "follows Epoch AI's published AI models documentation")

DL_ERA = 2010  # Epoch's Deep Learning Era boundary

SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³"
                                           "⁴⁵⁶⁷⁸⁹")


def models_src(dataset):
    return (f"Epoch AI, Data on AI Models (CC-BY) — {MODELS_SRC[dataset]} "
            f"— epoch.ai/data/ai-models")


def _pow10(v):
    """10^n rendered as text, since mathtext is disabled repo-wide."""
    if v <= 0:
        return ""
    exp = int(round(math.log10(v)))
    if abs(math.log10(v) - exp) > 1e-6:
        return ""
    return "10" + str(exp).translate(SUPERSCRIPT)


def _human(v, prefix="", suffix=""):
    if v <= 0:
        return ""
    for cut, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if v >= cut:
            n = v / cut
            return f"{prefix}{n:,.0f}{unit}{suffix}" if n >= 1 else ""
    return f"{prefix}{v:,.0f}{suffix}"


AXIS_FMT = {
    "pow10": lambda v: _pow10(v),
    "count": lambda v: _human(v),
    "usd": lambda v: _human(v, prefix="$"),
    "watt": lambda v: (_human(v / 1e6, suffix=" MW") if v >= 1e6
                       else _human(v / 1e3, suffix=" kW") if v >= 1e3
                       else f"{v:,.0f} W"),
    "days": lambda v: (f"{v:,.0f}" if v >= 1 else f"{v:g}"),
}


def _plain_log_axis(axis, formatter=None):
    """Label a log axis in plain text.

    text.parse_math is off repo-wide so that dollar figures in captions render
    literally. The side effect is that matplotlib's default log formatter emits
    "$\\mathdefault{10^{4}}$" and, with math parsing disabled, that string is
    drawn verbatim - several of them overlapping into an illegible smear. Any
    log axis therefore has to state its own formatter.
    """
    import matplotlib.ticker as mticker
    formatter = formatter or AXIS_FMT["count"]
    axis.set_major_locator(mticker.LogLocator(base=10.0))
    axis.set_minor_locator(mticker.NullLocator())
    axis.set_major_formatter(plt.FuncFormatter(lambda v, _p: formatter(v)))


def _dec_year(stamp):
    """Decimal year, matching build/summarise_epoch_models.py exactly."""
    return stamp.year + (stamp.timetuple().tm_yday - 1) / 365.25


def _sci(v):
    """2×10¹⁷, for axes too short to be labelled in whole decades."""
    exp = int(math.floor(math.log10(v)))
    mant = v / 10 ** exp
    text = f"{mant:.0f}" if abs(mant - round(mant)) < 1e-9 else f"{mant:g}"
    return ("10" if text == "1" else text + "×10") + str(exp).translate(SUPERSCRIPT)


def _decade_ticks(axis, values, formatter, target=9):
    """Label whole powers of ten, thinned so a 25-decade axis stays readable."""
    import matplotlib.ticker as mticker
    lo = int(math.floor(math.log10(float(values.min()))))
    hi = int(math.ceil(math.log10(float(values.max()))))
    if hi - lo < 3:
        # too few decades to carry the axis on its own: subdivide 1-2-5 instead
        if not formatter(2 * 10.0 ** lo):
            formatter = _sci
        ticks = [m * 10.0 ** e for e in range(lo, hi + 1) for m in (1, 2, 5)]
        ticks = [t for t in ticks
                 if float(values.min()) / 1.6 <= t <= float(values.max()) * 1.6]
        axis.set_major_locator(mticker.FixedLocator(ticks))
        axis.set_minor_locator(mticker.NullLocator())
        axis.set_major_formatter(plt.FuncFormatter(lambda v, _p: formatter(v)))
        return
    stride = max(1, math.ceil((hi - lo + 1) / target))
    ticks = [10.0 ** e for e in range(lo, hi + 1) if (hi - e) % stride == 0]
    axis.set_major_locator(mticker.FixedLocator(ticks))
    axis.set_minor_locator(mticker.NullLocator())
    axis.set_major_formatter(plt.FuncFormatter(lambda v, _p: formatter(v)))


_MODELS_CACHE = {}


def _mpoints(dataset):
    """The derived point table for one Epoch release."""
    import pandas as pd
    if dataset not in _MODELS_CACHE:
        df = pd.read_csv(MODELS_DATA / f"points_{dataset}.csv", low_memory=False)
        df["publication_date"] = pd.to_datetime(df["publication_date"], errors="coerce")
        df = df.dropna(subset=["publication_date"])
        df["year"] = df["publication_date"].dt.year
        df["decyear"] = df["publication_date"].map(_dec_year)
        _MODELS_CACHE[dataset] = df
    return _MODELS_CACHE[dataset]


def _mtable(name):
    import pandas as pd
    return pd.read_csv(MODELS_DATA / name)


def _msummary(dataset):
    t = _mtable("models_summary.csv")
    return t[t["dataset"] == dataset].iloc[0]


def _mtrend(dataset, metric, era="deep learning era"):
    t = _mtable("models_trends.csv")
    hit = t[(t["dataset"] == dataset) & (t["metric"] == metric) & (t["era"] == era)]
    return None if hit.empty else hit.iloc[0]


def _mprov():
    return _mtable("models_provenance.csv").iloc[0]


# Colour assignment for the "colour by" views. The residual group is deliberately
# pale: it is what is left over, not a category anyone chose.
MODELS_PALETTE = ["#1f3864", "#b4763a", "#6b8f71", "#7d5a7d", "#4e8a8b",
                  "#a46b6b", "#4a6fa5", "#8a8f5c", "#9aa9c4"]
RESIDUAL = "#c9ced8"


def _colour_groups(df, column, top_n, residual_label, keep_first=()):
    """Top-N categories by count, everything else pooled into one pale group."""
    counts = df[column].value_counts()
    ordered = [c for c in keep_first if c in counts.index]
    ordered += [c for c in counts.index if c not in ordered][:max(0, top_n - len(ordered))]
    groups = []
    for i, name in enumerate(ordered):
        sub = df[df[column] == name]
        groups.append((name, sub, MODELS_PALETTE[i % len(MODELS_PALETTE)]))
    rest = df[~df[column].isin(ordered) & df[column].notna()]
    if len(rest):
        groups.append((residual_label, rest, RESIDUAL))
    unknown = df[df[column].isna()]
    return groups, unknown


def _short_country(name):
    return {"United States of America": "United States",
            "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
            "Korea (Republic of)": "South Korea",
            "Russian Federation": "Russia",
            "Taiwan, Province of China": "Taiwan",
            "Iran (Islamic Republic of)": "Iran"}.get(name, name)


def _clip(text, width):
    """Shorten to a whole word, so a label never breaks mid-word."""
    if len(text) <= width:
        return text
    cut = text[:width].rsplit(" ", 1)[0]
    return (cut or text[:width]) + "…"


def _record_setters(rows, xcol, ycol):
    """Models that set a new high-water mark for the metric when they appeared.

    Labelling these rather than simply the largest values traces the upper edge
    of the cloud across the whole period instead of crowding the top-right.
    """
    out = []
    best = None
    for _, r in rows.sort_values(xcol).iterrows():
        if best is None or r[ycol] > best:
            best = r[ycol]
            out.append(r)
    return out


def _label_points(ax, rows, xcol, ycol, count, fontsize=8.6):
    """Name a spread of landmark models along the upper edge of the cloud."""
    import matplotlib.patheffects as pe
    records = _record_setters(rows, xcol, ycol)
    if not records:
        return
    span = rows[xcol].max() - rows[xcol].min()
    if ax.get_xscale() == "log":
        span = math.log10(rows[xcol].max() / rows[xcol].min())

    def _pos(v):
        return math.log10(v) if ax.get_xscale() == "log" else v

    # newest first, keeping only records far enough apart to label cleanly
    chosen = []
    for r in reversed(records):
        if all(abs(_pos(r[xcol]) - _pos(c[xcol])) > span * 0.11 for c in chosen):
            chosen.append(r)
        if len(chosen) == count:
            break
    lo = _pos(rows[xcol].min())
    for i, r in enumerate(chosen):
        # points near the left edge get their label on the other side, so it
        # cannot run off the axes
        near_left = (_pos(r[xcol]) - lo) < span * 0.18
        ax.annotate(_clip(str(r["model"]), 26), xy=(r[xcol], r[ycol]),
                    xytext=(8 if near_left else -8, 8 if i % 2 == 0 else -14),
                    textcoords="offset points",
                    ha="left" if near_left else "right",
                    fontsize=fontsize, color=INK, zorder=9,
                    path_effects=[pe.withStroke(linewidth=2.8, foreground="white")])


# ---------------------------------------------------- Epoch's published figure
# One entry per setting of Epoch's own chart. x is publication date unless an
# explicit x_metric is given.
MODEL_PLOTS = {
    "MODELS-01": {
        "dataset": "notable", "metric": "training_compute_flop", "colour": None,
        "title": "Training compute of notable AI models",
        "ylabel": "Training compute (FLOP, log scale)", "fmt": "pow10",
        "unit": "FLOP", "fit": True, "label": 6,
    },
    "MODELS-05": {
        "dataset": "frontier", "metric": "training_compute_flop", "colour": None,
        "title": "Training compute of frontier AI models",
        "ylabel": "Training compute (FLOP, log scale)", "fmt": "pow10",
        "unit": "FLOP", "fit": True, "label": 6,
    },
    "MODELS-06": {
        "dataset": "large_scale", "metric": "training_compute_flop", "colour": None,
        "title": "Training compute of large-scale AI models",
        "ylabel": "Training compute (FLOP, log scale)", "fmt": "pow10",
        "unit": "FLOP", "fit": True, "label": 5,
    },
}


def build_model_scatter(plot_id):
    import matplotlib.ticker as mticker

    cfg = MODEL_PLOTS[plot_id]
    ds = cfg["dataset"]
    df = _mpoints(ds)
    metric = cfg["metric"]
    xmetric = cfg.get("x_metric")
    prov = _mprov()
    summ = _msummary(ds)

    cols = [metric] + ([xmetric] if xmetric else [])
    pts = df.dropna(subset=cols)
    xcol = xmetric if xmetric else "decyear"
    n_plotted, n_total = len(pts), int(summ["models"])

    # ---------------------------------------------------------------- text
    axes_line = (f"{cfg['ylabel'].split(' (')[0]} against "
                 f"{'training compute' if xmetric else 'publication date'}")
    if cfg.get("colour"):
        axes_line += f", coloured by {cfg['colour_label'].lower()}"
    subtitle = (f"What it shows: Epoch AI's published figure at this setting — "
                f"{axes_line}, over {MODELS_LABEL[ds]}, rebuilt from the downloaded "
                f"CSV rather than screenshotted. Every point is one model that Epoch "
                f"records a value for; {n_plotted:,} of the {n_total:,} models in the "
                f"release carry one.")
    coverage = (f"{n_plotted:,} of {n_total:,} models in {MODELS_SRC[ds]} record "
                f"{'both values' if xmetric else 'this value'}; the remaining "
                f"{n_total - n_plotted:,} are absent from the chart rather than "
                f"estimated, so read it as what has been measured and published, not "
                f"as the whole population.")
    note = f"{MODELS_DEF[ds]} {coverage}"

    # ------------------------------------------------------------- figure
    fig = plt.figure(figsize=(12.0, 8.4))
    wide = cfg.get("colour") is None
    rect = _rect(subtitle, "", left=0.082 if wide else 0.078,
                 width=0.882 if wide else 0.700, xlabel_room=0.055)
    rect[1] = 0.052 + 0.026 * (2 + len(textwrap.wrap(note, 133))) + 0.055
    rect[3] = (0.882 - (len(textwrap.wrap(subtitle, 122)) - 1) * 0.030 - 0.055) - rect[1]
    ax = fig.add_axes(rect)

    # deep learning era band, the toggle Epoch's own chart carries. Only worth
    # drawing where a real pre-2010 population sits outside it; with one or two
    # early points the band is just a tint over the whole chart.
    pre_dl = int((pts["year"] < DL_ERA).sum()) if not xmetric else 0
    band = pre_dl >= 10
    if band:
        ax.axvspan(DL_ERA, pts["decyear"].max() + 1.5, color="#1f3864", alpha=0.045,
                   zorder=0, linewidth=0)

    if cfg.get("colour"):
        keep_first = ("Multinational",) if cfg["colour"] == "country" else ()
        groups, unknown = _colour_groups(pts, cfg["colour"], cfg["top_n"],
                                         cfg["residual"], keep_first)
        for name, sub, colour in groups:
            label = _short_country(name) if cfg["colour"] == "country" else name
            ax.scatter(sub[xcol], sub[metric], s=24, facecolor=colour,
                       edgecolor="white", linewidth=0.35, alpha=0.85, zorder=3,
                       label=f"{_clip(label, 26)}  ({len(sub)})")
        if len(unknown):
            ax.scatter(unknown[xcol], unknown[metric], s=20, facecolor="none",
                       edgecolor=MUTED, linewidth=0.5, alpha=0.6, zorder=2,
                       label=f"Not recorded  ({len(unknown)})")
        handles, labels = ax.get_legend_handles_labels()
        ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.015, 1.0),
                  frameon=False, fontsize=8.8, title=cfg["colour_label"],
                  title_fontsize=9.2, handlelength=1.1, borderaxespad=0,
                  labelspacing=0.55)
    else:
        ax.scatter(pts[xcol], pts[metric], s=24, facecolor=SERIES["current"],
                   edgecolor="white", linewidth=0.35, alpha=0.72, zorder=3)

    # ------------------------------------------------------------- trend
    if cfg.get("fit") and not xmetric:
        tr = _mtrend(ds, metric)
        if tr is not None:
            x0, x1 = float(tr["x_min"]), float(tr["x_max"])
            slope, icept = float(tr["oom_per_year"]), float(tr["intercept_log10"])
            ax.plot([x0, x1], [10 ** (slope * x0 + icept), 10 ** (slope * x1 + icept)],
                    color="#b4763a", linewidth=2.0, zorder=6,
                    label="Deep learning era trend")
            ax.text(0.985, 0.035,
                    f"Deep learning era fit ({DL_ERA} onward), n={int(tr['n'])}:  "
                    f"{float(tr['growth_per_year']):.1f}× per year  ·  "
                    f"doubling every {float(tr['doubling_time_months']):.1f} months  "
                    f"·  r² = {float(tr['r_squared']):.2f}",
                    transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
                    color=INK, zorder=8,
                    bbox=dict(boxstyle="round,pad=0.45", facecolor="white",
                              edgecolor=RULE, linewidth=0.8))

    if cfg.get("label"):
        _label_points(ax, pts, xcol, metric, cfg["label"])

    # -------------------------------------------------------------- axes
    ax.set_yscale("log")
    ax.set_ylabel(cfg["ylabel"], fontsize=10)
    _decade_ticks(ax.yaxis, pts[metric], AXIS_FMT[cfg["fmt"]])

    if xmetric:
        ax.set_xscale("log")
        ax.set_xlabel(cfg["xlabel"], fontsize=10)
        _decade_ticks(ax.xaxis, pts[xmetric], AXIS_FMT[cfg["x_fmt"]])
    else:
        span = pts["decyear"].max() - pts["decyear"].min()
        step = 10 if span > 45 else 5 if span > 18 else 2
        ax.set_xlabel("Publication date", fontsize=10)
        ax.xaxis.set_major_locator(mticker.MultipleLocator(step))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{int(v)}"))
        ax.set_xlim(pts["decyear"].min() - span * 0.02,
                    pts["decyear"].max() + span * 0.04)
        if pts["year"].min() < DL_ERA:
            # above the frame, where no data point or label can reach it
            ax.text(DL_ERA + span * 0.008, 1.008, "Deep learning era",
                    transform=ax.get_xaxis_transform(), ha="left", va="bottom",
                    fontsize=8.8, color=NAVY, zorder=4, clip_on=False)

    ax.grid(color=RULE, linewidth=0.7, which="major")
    ax.set_axisbelow(True)

    frame(fig, ax, plot_id, cfg["title"], subtitle, models_src(ds), MODELS_METH, note)
    save(fig, plot_id, MODELS_DOMAIN)


# ============================================== AI Chip Components (Epoch AI)
# Epoch publishes one configurable figure at epoch.ai/data/ai-chip-components: a
# stacked view of what the leading AI chip designers consumed of three supply
# chain components. It carries four tabs - Total cost, Logic, Packaging, Memory -
# and four settings: colour by component or designer, absolute or share, quarterly
# or annual, running or cumulative. The CHIP-* charts below are that figure at
# each of its distinct settings, rebuilt from the downloaded CSVs rather than
# screenshotted. The CHIP-D* charts are our own analysis of the same files.
#
# Two rules hold throughout. A quarter is charted only where the source records
# every designer in it, which excludes the partial Q1 2026 in the download - see
# build/summarise_epoch_chip_components.py. And nothing is projected: Epoch's own
# "Project trend" control is disabled on the published page, and no value here is
# extrapolated, imputed or filled.
CHIP_DOMAIN = "ai-chip-components"
CHIP_DATA = REPO / CHIP_DOMAIN / "data"

CHIP_METH = ("Derivation follows Epoch AI's published AI Chip Components "
             "methodology; every figure is a Monte Carlo median over 10,000 draws")

# the cost stack, in the order Epoch stacks it
CHIP_PARTS = [
    ("logic_cost_usd", "Logic wafers", "#1f3864"),
    ("cowos_cost_usd", "CoWoS packaging", "#4e8a8b"),
    ("hbm_cost_usd", "HBM memory", "#b4763a"),
    ("aux_cost_usd", "Auxiliary", "#9aa9c4"),
]
CHIP_DESIGNERS = [("NVIDIA", "#1f3864"), ("Google", "#4a6fa5"),
                  ("Amazon", "#6b8f71"), ("AMD", "#b4763a")]
CHIP_OTHER = ("Other", "#c3c8d1")   # the residual of the supply denominator

# one entry per tab. "share_col" is the published share-of-supply column, which is
# read straight out of the file and never recomputed here.
CHIP_TABS = {
    "cost": dict(
        label="Total cost", column="total_cost_usd", scale=1e9,
        fmt="${v:,.0f}bn", total_fmt="${v:,.1f}bn",
        ylabel="Component cost (US$ billions)",
        what="what the components inside those chips cost",
        share_col=None, supply_col=None,
        defn="Cost is the sum of the four published parts - logic wafers, CoWoS "
             "packaging, HBM and auxiliary - for the chips whose components were "
             "consumed in the quarter, not the price of the finished accelerator.",
    ),
    "logic": dict(
        label="Logic", column="logic_wafers", scale=1e3,
        fmt="{v:,.0f}k", total_fmt="{v:,.1f}k",
        ylabel="Advanced-node logic wafers consumed (thousands)",
        what="advanced-node logic wafer consumption",
        share_col="logic_share_pct", supply_col="logic_supply_wafers",
        defn="Logic wafers are 12-inch 3-5 nm wafers fabricated at TSMC (N3/N5 "
             "class), which become the silicon dies inside AI accelerators.",
    ),
    "cowos": dict(
        label="Packaging", column="cowos_wafers", scale=1e3,
        fmt="{v:,.0f}k", total_fmt="{v:,.1f}k",
        ylabel="CoWoS packaging wafers consumed (thousands)",
        what="CoWoS advanced packaging consumption",
        share_col="cowos_share_pct", supply_col="cowos_supply_wafers",
        defn="CoWoS is TSMC's chip-on-wafer-on-substrate packaging, which attaches "
             "the logic chiplets and HBM stacks onto one substrate.",
    ),
    "hbm": dict(
        label="Memory", column="hbm_cost_usd", scale=1e9,
        fmt="${v:,.0f}bn", total_fmt="${v:,.1f}bn",
        ylabel="HBM consumed (US$ billions)",
        what="high-bandwidth memory consumption",
        share_col="hbm_share_pct", supply_col="hbm_supply_usd",
        defn="HBM is measured in dollars rather than units, covering the HBM2e, "
             "HBM3 and HBM3e stacks attached to AI accelerators.",
    ),
}

# Epoch offers "Show data as" as a control on one figure. Each entry below is one
# figure carrying both of its settings side by side, rather than two charts that
# share an x axis and a colour key and differ only in normalisation. The
# cumulative and annual settings are gone: cumulative reproduced the quarterly
# series as a running total to within 0.03%, and annual re-bucketed the same file
# into two bars.
CHIP_PLOTS = {
    # colour-by is a control on this figure too, not a second figure: what used
    # to be CHIP-02 is this chart with "Colour by: Designer" on its companion,
    # and CHIP-D02 carries the designer x component cross as a static.
    "CHIP-01": dict(tab="cost", group="component", period="quarterly",
                    modes=["absolute", "share"],
                    title="Cost of AI chip components, by component"),
    "CHIP-09": dict(tab="logic", group="designer", period="quarterly",
                    modes=["absolute", "supply"],
                    title="Advanced-node logic wafers, consumed and as a share of supply"),
    "CHIP-11": dict(tab="cowos", group="designer", period="quarterly",
                    modes=["absolute", "supply"],
                    title="CoWoS packaging wafers, consumed and as a share of supply"),
    "CHIP-13": dict(tab="hbm", group="designer", period="quarterly",
                    modes=["absolute", "supply"],
                    title="HBM memory, consumed and as a share of supply"),
}

# the exact published files each chart is built from, printed on its face
CHIP_FILES = {
    "quarterly": "quarterly_by_designer.csv",
    "cumulative": "cumulative_by_designer.csv",
    "annual": "quarterly_by_designer.csv",
}


def chip_src(files):
    return ("Epoch AI, AI Chip Components (CC-BY) — "
            + " + ".join(files) + " — epoch.ai/data/ai-chip-components")


def _chip_csv(name):
    """Read a derived chip CSV, floating every column that is a number."""
    import csv as _csv
    with (CHIP_DATA / name).open(encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    for r in rows:
        for k, v in list(r.items()):
            try:
                r[k] = float(v)
            except (TypeError, ValueError):
                pass
    return rows


def _chip_meta():
    return _chip_csv("chip_summary.csv")[0]


def _chip_quarters(rows):
    """The charted window, in order, straight off the file."""
    seen = {}
    for r in rows:
        seen[int(r["quarter_index"])] = r["quarter"]
    return [seen[i] for i in sorted(seen)]


def _chip_badge(ax, above=False):
    """The window rule that defines these charts, stated on the plot itself."""
    y, va = (1.030, "bottom") if above else (0.955, "top")
    ax.text(0.0 if above else 0.017, y,
            "  COMPLETE QUARTERS ONLY  ·  partial Q1 2026 excluded  ",
            transform=ax.transAxes, ha="left", va=va, fontsize=9.1,
            fontweight="bold", color="white", zorder=9, clip_on=False,
            bbox=dict(boxstyle="round,pad=0.42", facecolor=SERIES["current"],
                      edgecolor="none"))


def _chip_series(cfg):
    """Build the stack for one setting of Epoch's figure.

    Returns (x labels, [(name, colour, values)], totals, footnotes). Each setting
    reads the file published at its own grain, so no plotted value is re-derived
    by summing a coarser one - with one exception, the annual view, which sums the
    four published quarterly medians and says so on its face.
    """
    tab = CHIP_TABS[cfg["tab"]]
    rows = _chip_csv("chip_" + ("cumulative" if cfg["period"] == "cumulative"
                                else "quarterly") + "_by_designer.csv")
    quarters = _chip_quarters(rows)

    if cfg["period"] == "annual":
        buckets, order = {}, []
        for q in quarters:
            year = q.split()[-1]
            if year not in order:
                order.append(year)
            buckets.setdefault(year, []).append(q)
        xs = order
        member = buckets
    else:
        xs = quarters
        member = {q: [q] for q in quarters}

    def cell(designer, column, x):
        return sum(r[column] for r in rows
                   if r["designer"] == designer and r["quarter"] in member[x])

    if cfg["mode"] == "supply":
        # published share-of-supply columns, read as published, residual included
        names = [d for d, _ in CHIP_DESIGNERS] + [CHIP_OTHER[0]]
        colours = [c for _, c in CHIP_DESIGNERS] + [CHIP_OTHER[1]]
        col = tab["share_col"] + "_p50"
        series = [(n, c, [cell(n, col, x) for x in xs])
                  for n, c in zip(names, colours)]
    elif cfg["group"] == "component":
        series = [(label, colour,
                   [sum(cell(d, f"{part}_p50", x) for d, _ in CHIP_DESIGNERS)
                    for x in xs])
                  for part, label, colour in CHIP_PARTS]
    else:
        col = tab["column"] + "_p50"
        # the residual is not an AI chip designer. It belongs in the share views,
        # where it closes the stack to 100% of supply, and nowhere else: on an
        # absolute chart it is 85-95% of the bar and buries what the chart is of.
        # The component tabs carry the supply denominator as a line instead.
        names = [(d, c) for d, c in CHIP_DESIGNERS]
        series = [(n, c, [cell(n, col, x) for x in xs]) for n, c in names]

    totals = [sum(s[2][i] for s in series) for i in range(len(xs))]

    if cfg["mode"] == "share":
        series = [(n, c, [v / t * 100 if t else 0.0 for v, t in zip(vals, totals)])
                  for n, c, vals in series]
        totals = [100.0] * len(xs)
    elif cfg["mode"] == "absolute":
        series = [(n, c, [v / tab["scale"] for v in vals]) for n, c, vals in series]
        totals = [t / tab["scale"] for t in totals]
    return xs, series, totals


def _chip_panel(ax, cfg, tab, mode, xs, series, totals, legend=False):
    """Draw one setting of the figure into one axes. Returns whether the world
    supply denominator was read, so the source line credits what it used."""
    import matplotlib.ticker as mticker
    pct = mode in ("share", "supply")
    idx = list(range(len(xs)))
    bottom = [0.0] * len(xs)
    ai_top = None
    bar_w = 0.68 if len(xs) > 3 else 0.42
    for name, colour, vals in series:
        ax.bar(idx, vals, bottom=bottom, width=bar_w, color=colour, label=name,
               edgecolor="white", linewidth=0.7, zorder=3)
        # the residual carries the combined-share rule right below it, so labelling
        # it as well would print two numbers on top of each other
        label_seg = pct and not (mode == "supply" and name == CHIP_OTHER[0])
        for i, v in enumerate(vals):
            if label_seg and v >= 10:
                ax.text(i, bottom[i] + v / 2, f"{v:.0f}%", ha="center", va="center",
                        fontsize=8.0, color="white", fontweight="bold", zorder=5)
        bottom = [b + v for b, v in zip(bottom, vals)]
        if name == CHIP_DESIGNERS[-1][0]:
            ai_top = list(bottom)

    head = max(totals)
    used_supply = mode == "supply"
    if mode == "absolute" and tab["supply_col"]:
        # what the tracked designers are drawing down: Epoch's own supply
        # denominator, so the headroom above each bar is legible
        sup = {r["quarter"]: r[tab["supply_col"] + "_p50"] / tab["scale"]
               for r in _chip_csv("chip_supply.csv")}
        ys = [sup[x] for x in xs]
        ax.plot(idx, ys, linestyle=(0, (5, 2.5)), color=MUTED, linewidth=1.5,
                marker="_", markersize=14, markeredgewidth=1.6,
                label="World supply (all users)", zorder=5)
        head = max(head, max(ys))
        used_supply = True
        for i, t in enumerate(totals):
            inside = ys[i] - t < head * 0.075
            ax.text(i, t - head * 0.012 if inside else t + head * 0.018,
                    tab["total_fmt"].format(v=t), ha="center",
                    va="top" if inside else "bottom", fontsize=8.4,
                    fontweight="bold", color="white" if inside else INK, zorder=6)
    elif not pct:
        for i, t in enumerate(totals):
            ax.text(i, t + head * 0.018, tab["total_fmt"].format(v=t), ha="center",
                    va="bottom", fontsize=8.4, fontweight="bold", color=INK, zorder=6)
    elif mode == "supply" and ai_top:
        # the figure this view exists to show: how much of world supply the four
        # tracked designers took, ruled across the top of their part of the stack
        for i, v in enumerate(ai_top):
            ax.plot([i - bar_w * 0.59, i + bar_w * 0.59], [v, v], color=INK,
                    linewidth=1.3, zorder=6)
            ax.text(i, v + 1.8, f"{v:.0f}%", ha="center", va="bottom", fontsize=8.4,
                    fontweight="bold", color=INK, zorder=7)

    ax.set_xticks(idx)
    ax.set_xticklabels([x.replace(" ", "\n") for x in xs], fontsize=8.8)
    ax.set_ylabel("Share of component cost (%)" if mode == "share"
                  else "Share of world supply (%)" if mode == "supply"
                  else tab["ylabel"], fontsize=9.6)
    ax.set_xlabel("Calendar year" if cfg["period"] == "annual"
                  else "Quarter (cumulative through)" if cfg["period"] == "cumulative"
                  else "Quarter", fontsize=9.6)
    ax.set_xlim(-0.6, len(xs) - 0.4)
    ax.set_ylim(0, 112 if mode == "supply" else 100 if pct else head * 1.14)
    if pct:
        ax.set_yticks([0, 20, 40, 60, 80, 100])
    else:
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(
        lambda v, _p: f"{v:.0f}%" if pct else tab["fmt"].format(v=v)))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.set_title({"absolute": "Amount consumed", "share": "Share of cost",
                  "supply": "Share of world supply"}[mode],
                 fontsize=10.4, fontweight="bold", color=INK, pad=8)
    if legend:
        h, l = ax.get_legend_handles_labels()
        ax.legend(h[::-1], l[::-1], loc="upper left", bbox_to_anchor=(1.030, 1.0),
                  frameon=False, fontsize=9,
                  title="Component" if cfg["group"] == "component" else "Designer",
                  title_fontsize=9.2, handlelength=1.5, borderaxespad=0)
    return used_supply


def build_chip(plot_id):
    """Epoch's published figure, with its absolute and share settings side by side.

    Epoch offers "Show data as" as a control on one figure, not as two figures.
    Publishing each setting separately meant two charts that share an x axis, a
    colour key and a caption, and differ only in whether the stack is normalised.
    They are one chart with two panels here, which is also how the source reads.
    """
    cfg = CHIP_PLOTS[plot_id]
    tab = CHIP_TABS[cfg["tab"]]
    meta = _chip_meta()
    modes = cfg["modes"]
    panels = [(m, _chip_series({**cfg, "mode": m})) for m in modes]
    xs = panels[0][1][0]

    mode_words = " + ".join({"absolute": "Absolute", "share": "Share of cost",
                             "supply": "Share of supply"}[m] for m in modes)
    setting = "\n".join([
        "Epoch explorer settings",
        f"Tab:  {tab['label']}",
        f"Colour by:  {'Component' if cfg['group'] == 'component' else 'Designer'}",
        "Show data as:",
        f"    {mode_words}",
        "    (side by side)",
        f"Show time as:  {'Annual' if cfg['period'] == 'annual' else 'Quarterly'}",
        f"Show cumulative:  {'yes' if cfg['period'] == 'cumulative' else 'no'}",
        "Project trend:  off (disabled at source)",
    ])
    if "supply" in modes:
        setting += "\n\nBlack rule:  the four tracked\ndesigners' combined share"

    subtitle = (f"What it shows: Epoch AI's published figure at both of its "
                f"\"show data as\" settings — {tab['what']} by the "
                f"{int(meta['designers_tracked'])} tracked AI chip designers "
                f"({meta['designer_names']}) in each quarter, as an amount and as a "
                f"{'share of world supply' if 'supply' in modes else 'share of the total'}. "
                f"{meta['window_first_quarter']} to {meta['window_last_quarter']}, the "
                f"full window the source covers.")

    note = tab["defn"] + " "
    if "supply" in modes:
        note += (f"Share is of total world supply of the component, not of AI demand: "
                 f"the five bars sum to exactly 100% of the quarterly denominator "
                 f"Epoch publishes, and the identity was checked to "
                 f"{float(meta['share_identity_max_abs_error_pct']):.0e} percentage "
                 f"points. \"Other\" is therefore not a fifth AI chip designer but the "
                 f"residual of that denominator - capacity taken by designers Epoch "
                 f"does not track, stockpiling, idle capacity, or error in the tracked "
                 f"estimates. Epoch itself calls it directional. The dashed line on the "
                 f"left panel is that same denominator, so the two panels are the same "
                 f"quantity read two ways. ")
    else:
        note += (f"\"Other\" - the rest of world supply - carries no AI chips and is "
                 f"excluded from every cost view here. The right panel is the left one "
                 f"normalised to 100%, which is what makes a composition change legible "
                 f"while the total is growing. ")
    if cfg["group"] == "component":
        note += (f"Component totals are sums of the four designers' published medians. "
                 f"Epoch simulates each aggregation separately, so a median never adds "
                 f"exactly: the measured gap at the analogous grain is "
                 f"{float(meta['median_additivity_grain_pct']):.2f}%. Reported, not "
                 f"reconciled. ")
    note += (f"Every value is a Monte Carlo median; the published 5th-95th percentile "
             f"range is wide and is charted separately in CHIP-D04. "
             f"{int(meta['partial_designer_rows_excluded'])} designer rows for "
             f"the partial quarter after the window are excluded.")

    pct_any = all(m in ("share", "supply") for m in modes)
    fig = plt.figure(figsize=(12.0, 8.4))
    rect = _rect(subtitle, note, left=0.068, width=0.700, xlabel_room=0.062,
                 badge_above=True,
                 source=chip_src([CHIP_FILES[cfg["period"]], "supply_denominators.csv"]))
    l, b, w, h = rect
    gap = 0.075
    pw = (w - gap) / 2
    axes = [fig.add_axes([l, b, pw, h]), fig.add_axes([l + pw + gap, b, pw, h])]
    # each panel carries its own title, so the badge sits above both of them
    fig.text(l, b + h + 0.052,
             "  COMPLETE QUARTERS ONLY  \u00b7  partial Q1 2026 excluded  ",
             ha="left", va="bottom", fontsize=9.1, fontweight="bold", color="white",
             zorder=9, bbox=dict(boxstyle="round,pad=0.42",
                                 facecolor=SERIES["current"], edgecolor="none"))

    used_supply = False
    for k, ((mode, (px, series, totals)), ax) in enumerate(zip(panels, axes)):
        used_supply |= _chip_panel(ax, cfg, tab, mode, px, series, totals,
                                   legend=(k == len(axes) - 1))
    axes[-1].text(1.030, 0.98 - 0.062 * (len(panels[-1][1][1]) + 1), setting,
                  transform=axes[-1].transAxes, ha="left", va="top", fontsize=8.3,
                  color=MUTED, linespacing=1.55)

    frame(fig, axes[0], plot_id, cfg["title"], subtitle,
          chip_src([CHIP_FILES[cfg["period"]]]
                   + (["supply_denominators.csv"] if used_supply else [])),
          CHIP_METH, note)
    save(fig, plot_id, CHIP_DOMAIN)


# --------------------------------------------- Derived Analysis (same files)
def build_chip_d01(_r=None):
    """Which of the three components AI actually absorbs - the bottleneck chart."""
    meta = _chip_meta()
    rows = _chip_csv("chip_quarterly_by_designer.csv")
    quarters = _chip_quarters(rows)
    lines = [("Logic wafers", "logic_share_pct_p50", "#1f3864"),
             ("CoWoS packaging", "cowos_share_pct_p50", "#4e8a8b"),
             ("HBM memory", "hbm_share_pct_p50", "#b4763a")]

    def ai_share(col, q):
        return sum(r[col] for r in rows
                   if r["quarter"] == q and r["designer"] != CHIP_OTHER[0])

    subtitle = ("What it shows: how much of the world's supply of each component the "
                "four tracked AI chip designers took, quarter by quarter. The published "
                "views show one component at a time; this puts all three on one axis, "
                "which is where the constraint becomes visible.")
    last = {n: ai_share(c, quarters[-1]) for n, c, _ in lines}
    first = {n: ai_share(c, quarters[0]) for n, c, _ in lines}
    note = (f"Each line is the sum of the four tracked designers' published "
            f"share-of-supply figures, which is exactly 100% minus Epoch's \"Other\" "
            f"residual for that quarter. In {quarters[-1]} AI took "
            f"{last['HBM memory']:.0f}% of world HBM and "
            f"{last['CoWoS packaging']:.0f}% of world CoWoS packaging, but only "
            f"{last['Logic wafers']:.0f}% of advanced-node logic wafers - up from "
            f"{first['Logic wafers']:.0f}% in {quarters[0]}. Logic capacity is shared "
            f"with every other advanced-node customer (phones, PCs, networking) and AI "
            f"is a minority of it; packaging and memory are near-dedicated to AI and "
            f"have far less headroom, which is why they, not the logic dies, set the "
            f"ceiling on chip output. The residual is directional - Epoch notes it can "
            f"absorb untracked designers, stockpiling, idle capacity or its own "
            f"estimation error, and that annual residuals are more reliable than "
            f"quarterly ones. Denominators are Epoch's own supply estimates, not "
            f"measured capacity.")

    fig = plt.figure(figsize=(12.0, 8.0))
    ax = fig.add_axes(_rect(subtitle, note, left=0.078, width=0.700,
                            xlabel_room=0.056))
    idx = list(range(len(quarters)))
    for name, col, colour in lines:
        ys = [ai_share(col, q) for q in quarters]
        ax.plot(idx, ys, marker="o", markersize=5.5, linewidth=2.4, color=colour,
                label=name, zorder=4)
        ax.annotate(f"{ys[-1]:.0f}%", xy=(idx[-1], ys[-1]), xytext=(8, 0),
                    textcoords="offset points", va="center", fontsize=9.6,
                    fontweight="bold", color=colour, zorder=6)

    ax.set_xticks(idx)
    ax.set_xticklabels([q.replace(" ", "\n") for q in quarters], fontsize=9.4)
    ax.set_xlim(-0.35, len(quarters) - 0.35)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Share of world supply taken by AI (%)", fontsize=10)
    ax.set_xlabel("Quarter", fontsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1.045, 1.0), frameon=False,
              fontsize=9, title="Component", title_fontsize=9.2, handlelength=1.6,
              borderaxespad=0)
    _chip_badge(ax)
    frame(fig, ax, "CHIP-D01",
          "Packaging and memory, not logic dies, are the binding constraint",
          subtitle, chip_src(["quarterly_by_designer.csv", "supply_denominators.csv"]),
          CHIP_METH, note)
    save(fig, "CHIP-D01", CHIP_DOMAIN)


def build_chip_d02(_r=None):
    """What each designer's component bill is made of."""
    meta = _chip_meta()
    rows = _chip_csv("chip_cumulative_by_designer.csv")
    last = _chip_quarters(rows)[-1]
    designers = [d for d, _ in CHIP_DESIGNERS]
    cell = {(r["designer"], p): r[f"{p}_p50"] for r in rows if r["quarter"] == last
            for p, _, _ in CHIP_PARTS}
    totals = {d: sum(cell[(d, p)] for p, _, _ in CHIP_PARTS) for d in designers}

    subtitle = ("What it shows: what each designer's component bill is actually made "
                "of, cumulated over the whole window. The published views stack cost "
                "either by component or by designer; this crosses the two, which is "
                "the only way to see that the four designers buy quite different "
                "things.")
    hbm = {d: cell[(d, "hbm_cost_usd")] / totals[d] * 100 for d in designers}
    hi = max(designers, key=lambda d: hbm[d])
    lo = min(designers, key=lambda d: hbm[d])
    note = (f"Cumulative through {last}, read from Epoch's cumulative file. HBM is the "
            f"largest single line for every designer, ranging from {hbm[lo]:.0f}% of "
            f"{lo}'s bill to {hbm[hi]:.0f}% of {hi}'s - memory, not the logic die, is "
            f"what an AI accelerator mostly costs to build. Bars are ordered by total "
            f"spend, printed at the right. Auxiliary is Epoch's own catch-all for the "
            f"remaining package content and carries no wafer or share counterpart in "
            f"the source. These are component costs, not chip prices or revenue: "
            f"margin, board, system assembly, networking and everything above the "
            f"package are outside the dataset entirely.")

    fig = plt.figure(figsize=(12.0, 7.6))
    ax = fig.add_axes(_rect(subtitle, note, left=0.135, width=0.640,
                            xlabel_room=0.056, badge_above=True))
    order = sorted(designers, key=lambda d: totals[d])
    ys = list(range(len(order)))
    left = [0.0] * len(order)
    for part, label, colour in CHIP_PARTS:
        vals = [cell[(d, part)] / totals[d] * 100 for d in order]
        ax.barh(ys, vals, left=left, height=0.62, color=colour, label=label,
                edgecolor="white", linewidth=0.7, zorder=3)
        for y, v, l0 in zip(ys, vals, left):
            if v >= 6:
                ax.text(l0 + v / 2, y, f"{v:.0f}%", ha="center", va="center",
                        fontsize=8.6, color="white", fontweight="bold", zorder=5)
        left = [l0 + v for l0, v in zip(left, vals)]
    for y, d in zip(ys, order):
        ax.text(101.5, y, f"${totals[d]/1e9:,.1f}bn", va="center", fontsize=9.2,
                color=INK, fontweight="bold")

    ax.set_yticks(ys)
    ax.set_yticklabels(order, fontsize=10.5)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of that designer's cumulative component cost (%)", fontsize=10)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h, l, loc="upper left", bbox_to_anchor=(1.075, 1.0), frameon=False,
              fontsize=9, title="Component", title_fontsize=9.2, handlelength=1.5,
              borderaxespad=0)
    _chip_badge(ax, above=True)
    frame(fig, ax, "CHIP-D02", "Memory is the biggest line in every designer's bill",
          subtitle, chip_src(["cumulative_by_designer.csv"]), CHIP_METH, note)
    save(fig, "CHIP-D02", CHIP_DOMAIN)


def build_chip_d03(_r=None):
    """Which individual chips consumed the supply chain."""
    meta = _chip_meta()
    rows = [r for r in _chip_csv("chip_cumulative_by_chip.csv")
            if r["designer"] != CHIP_OTHER[0]]
    # a chip's cumulative series ends in its last active quarter, so its final
    # published cumulative row is its lifetime total
    final = {}
    for r in sorted(rows, key=lambda r: r["quarter_index"]):
        final[(r["designer"], r["chip_type"])] = r
    items = sorted(final.values(), key=lambda r: -r["total_cost_usd_p50"])
    colour = dict(CHIP_DESIGNERS)
    total = sum(r["total_cost_usd_p50"] for r in items)

    subtitle = ("What it shows: every chip type in the source, ranked by the component "
                "cost it consumed over the whole window. Epoch's published figure never "
                "goes below the designer; the chip-level file does, and it is where the "
                "concentration actually lives.")
    top = items[0]
    note = (f"Each bar is that chip's final published cumulative row - a chip's "
            f"cumulative series ends in its last active quarter, so the last row is its "
            f"lifetime total, and nothing is summed across quarters here. "
            f"{int(meta['chip_types_charted'])} chip types across "
            f"{int(meta['designers_tracked'])} designers, cumulative through "
            f"{meta['window_last_quarter']}. {top['chip_type']} alone accounts for "
            f"{top['total_cost_usd_p50']/total*100:.0f}% of tracked component spend, and "
            f"NVIDIA's four chip types account for "
            f"{sum(r['total_cost_usd_p50'] for r in items if r['designer'] == 'NVIDIA')/total*100:.0f}%. "
            f"Chips retired inside the window (H20, MI300A, Trainium1, TPU v5e/v5p) "
            f"stop accumulating where the source stops recording them, which is why "
            f"their totals are small rather than absent. Component cost is not price or "
            f"revenue.")

    fig = plt.figure(figsize=(12.0, 8.6))
    ax = fig.add_axes(_rect(subtitle, note, left=0.175, width=0.700,
                            xlabel_room=0.050, badge_above=True))
    ys = list(range(len(items)))[::-1]
    ax.barh(ys, [r["total_cost_usd_p50"] / 1e9 for r in items], height=0.70,
            color=[colour[r["designer"]] for r in items], edgecolor="white",
            linewidth=0.6, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels([r["chip_type"] for r in items], fontsize=9.6)
    xmax = items[0]["total_cost_usd_p50"] / 1e9
    for y, r in zip(ys, items):
        v = r["total_cost_usd_p50"] / 1e9
        ax.text(v + xmax * 0.012, y,
                f"${v:,.1f}bn  ·  {v*1e9/total*100:.1f}%",
                va="center", fontsize=8.8, color=MUTED)
    ax.set_xlim(0, xmax * 1.22)
    ax.set_xlabel("Cumulative component cost through "
                  f"{meta['window_last_quarter']} (US$ billions)", fontsize=10)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"${v:,.0f}bn"))
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=c) for _, c in CHIP_DESIGNERS],
              [d for d, _ in CHIP_DESIGNERS], loc="lower right", frameon=False,
              fontsize=9, title="Designer", title_fontsize=9.2)
    _chip_badge(ax, above=True)
    frame(fig, ax, "CHIP-D03", "One chip generation dominates the supply chain",
          subtitle, chip_src(["cumulative_by_chip.csv"]), CHIP_METH, note)
    save(fig, "CHIP-D03", CHIP_DOMAIN)


def build_chip_d04(_r=None):
    """How wide the published uncertainty actually is."""
    meta = _chip_meta()
    rows = _chip_csv("chip_quarterly_by_designer.csv")
    last = _chip_quarters(rows)[-1]
    cells = {r["designer"]: r for r in rows if r["quarter"] == last}
    # only quantities the source publishes an interval for, each read as published
    quantities = [("logic_wafers", "Logic wafers", "#1f3864"),
                  ("cowos_wafers", "CoWoS wafers", "#4e8a8b"),
                  ("hbm_cost_usd", "HBM ($)", "#b4763a")]
    designers = [d for d, _ in CHIP_DESIGNERS]

    entries = []
    for d in designers:
        for col, label, colour in quantities:
            r = cells[d]
            p50 = r[f"{col}_p50"]
            if p50 <= 0:
                continue
            entries.append((f"{d}  ·  {label}", colour,
                            r[f"{col}_p5"] / p50 * 100, 100.0,
                            r[f"{col}_p95"] / p50 * 100))

    subtitle = ("What it shows: the published 5th-95th percentile range around every "
                "median in the latest quarter, as a percentage of that median. Epoch's "
                "figure plots the medians alone; this is the uncertainty those medians "
                "carry, which is the first thing to know before quoting one.")
    widest = max(entries, key=lambda e: e[4] - e[2])
    tightest = min(entries, key=lambda e: e[4] - e[2])
    note = (f"Every figure in this dataset is a median over 10,000 Monte Carlo draws, "
            f"and the source publishes a 5th and 95th percentile beside it. Read as a "
            f"90% interval, {last} estimates span from "
            f"{tightest[4]-tightest[2]:.0f} percentage points of the median "
            f"({tightest[0]}) to {widest[4]-widest[2]:.0f} points ({widest[0]}). Only "
            f"published intervals are drawn: percentiles are not additive, so no "
            f"interval here is summed across designers or components, and the totals "
            f"printed on the other charts are sums of medians rather than medians of "
            f"sums. Uncertainty enters through three modelling steps Epoch names - "
            f"upstream chip volumes, unit-to-component conversion factors, and "
            f"inventory accounting - and Epoch states quarterly figures carry more of "
            f"it than annual ones. Auxiliary cost and total cost are omitted because "
            f"neither has a simulated interval of its own.")

    fig = plt.figure(figsize=(12.0, 8.8))
    ax = fig.add_axes(_rect(subtitle, note, left=0.245, width=0.700,
                            xlabel_room=0.050, badge_above=True))
    ys = list(range(len(entries)))[::-1]
    for y, (label, colour, lo, mid, hi) in zip(ys, entries):
        ax.plot([lo, hi], [y, y], color=colour, linewidth=3.2, solid_capstyle="round",
                alpha=0.45, zorder=3)
        ax.plot([lo, hi], [y, y], marker="|", markersize=9, linestyle="none",
                color=colour, zorder=4)
        ax.plot([mid], [y], marker="o", markersize=6.5, color=colour, zorder=5)
        ax.text(hi + 1.5, y, f"{lo:.0f}–{hi:.0f}%", va="center", fontsize=8.6,
                color=MUTED)
    ax.axvline(100, color=INK, linewidth=1.0, linestyle="--", alpha=0.5, zorder=2)
    ax.set_yticks(ys)
    ax.set_yticklabels([e[0] for e in entries], fontsize=9.2)
    ax.set_xlabel(f"Published 5th-95th percentile range, {last} "
                  f"(% of the median, marked at 100%)", fontsize=10)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_xlim(min(e[2] for e in entries) - 8, max(e[4] for e in entries) + 14)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _chip_badge(ax, above=True)
    frame(fig, ax, "CHIP-D04",
          "Every number on these charts is a median with a wide interval behind it",
          subtitle, chip_src(["quarterly_by_designer.csv"]), CHIP_METH, note)
    save(fig, "CHIP-D04", CHIP_DOMAIN)


def build_chip_d05(_r=None):
    """How packaging-intensive each designer's silicon is."""
    meta = _chip_meta()
    rows = _chip_csv("chip_quarterly_by_designer.csv")
    quarters = _chip_quarters(rows)
    cell = {(r["designer"], r["quarter"]): r for r in rows}
    designers = [d for d, _ in CHIP_DESIGNERS]
    colour = dict(CHIP_DESIGNERS)

    def ratio(d, q):
        r = cell[(d, q)]
        return (r["cowos_wafers_p50"] / r["logic_wafers_p50"]
                if r["logic_wafers_p50"] > 0 else None)

    subtitle = ("What it shows: CoWoS packaging wafers consumed per logic wafer, by "
                "designer and quarter. Both columns are published side by side and "
                "never plotted against each other; the ratio is a property of the chip "
                "design, and it separates the four designers sharply.")
    lastvals = {d: ratio(d, quarters[-1]) for d in designers}
    hi = max((d for d in designers if lastvals[d]), key=lambda d: lastvals[d])
    lo = min((d for d in designers if lastvals[d]), key=lambda d: lastvals[d])
    note = (f"Ratio of two published medians in the same row, so it inherits their "
            f"uncertainty and is not itself a simulated quantity. In {quarters[-1]} "
            f"{hi} consumed {lastvals[hi]:.2f} CoWoS wafers per logic wafer against "
            f"{lastvals[lo]:.2f} for {lo}. A high ratio means large packages carrying "
            f"many HBM stacks around a relatively small die; a low one means more dies "
            f"per package or smaller packages. Because both series are assigned to the "
            f"quarter the component was consumed rather than the quarter the chip "
            f"shipped, a chip in work-in-process can consume logic with no CoWoS yet, "
            f"which is what pulls a designer's ratio down in a ramp quarter. Every "
            f"designer records logic wafers in all eight quarters, so no line is "
            f"interpolated across a gap.")

    fig = plt.figure(figsize=(12.0, 8.0))
    ax = fig.add_axes(_rect(subtitle, note, left=0.078, width=0.700,
                            xlabel_room=0.056))
    idx = list(range(len(quarters)))
    for d in designers:
        ys = [ratio(d, q) for q in quarters]
        ax.plot(idx, ys, marker="o", markersize=5.2, linewidth=2.2, color=colour[d],
                label=d, zorder=4)
        if ys[-1] is not None:
            ax.annotate(f"{ys[-1]:.2f}", xy=(idx[-1], ys[-1]), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=9.4,
                        fontweight="bold", color=colour[d], zorder=6)
    ax.set_xticks(idx)
    ax.set_xticklabels([q.replace(" ", "\n") for q in quarters], fontsize=9.4)
    ax.set_xlim(-0.35, len(quarters) - 0.35)
    ax.set_ylim(0, max(v for d in designers for v in
                       [ratio(d, q) for q in quarters] if v is not None) * 1.20)
    ax.set_ylabel("CoWoS packaging wafers per logic wafer", fontsize=10)
    ax.set_xlabel("Quarter", fontsize=10)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1.045, 1.0), frameon=False, fontsize=9,
              title="Designer", title_fontsize=9.2, handlelength=1.6, borderaxespad=0)
    _chip_badge(ax)
    frame(fig, ax, "CHIP-D05", "How much packaging each designer's silicon needs",
          subtitle, chip_src(["quarterly_by_designer.csv"]), CHIP_METH, note)
    save(fig, "CHIP-D05", CHIP_DOMAIN)


def build_chip_d06(_r=None):
    """Demand growth against supply growth, component by component."""
    meta = _chip_meta()
    rows = _chip_csv("chip_quarterly_by_designer.csv")
    supply = {r["quarter"]: r for r in _chip_csv("chip_supply.csv")}
    quarters = _chip_quarters(rows)
    pairs = [("Logic wafers", "logic_wafers_p50", "logic_supply_wafers_p50", "#1f3864"),
             ("CoWoS packaging", "cowos_wafers_p50", "cowos_supply_wafers_p50", "#4e8a8b"),
             ("HBM memory", "hbm_cost_usd_p50", "hbm_supply_usd_p50", "#b4763a")]

    def demand(col, q):
        return sum(r[col] for r in rows
                   if r["quarter"] == q and r["designer"] != CHIP_OTHER[0])

    subtitle = ("What it shows: AI demand for each component against total world "
                "supply of it, both indexed to Q1 2024 = 100. Absolute charts make the "
                "two hard to compare because they are orders of magnitude apart; on a "
                "common index the question is simply which line climbs faster.")
    growth = {}
    for name, dcol, scol, _ in pairs:
        growth[name] = (demand(dcol, quarters[-1]) / demand(dcol, quarters[0]),
                        supply[quarters[-1]][scol] / supply[quarters[0]][scol])
    note = ("Solid lines are the four tracked designers' summed consumption; dashed "
            "lines are Epoch's published supply denominator for the same component. "
            "Over the eight quarters "
            + "; ".join(f"{n} demand grew {g[0]:.1f}x against {g[1]:.1f}x supply"
                        for n, g in growth.items())
            + ". Where demand outruns supply the residual has to give, which is the "
              "same fact CHIP-D01 shows as a rising share. Demand is a sum of published "
              "medians across four designers and inherits the non-additivity noted "
              f"there ({float(meta['median_additivity_grain_pct']):.2f}% at the "
              "analogous grain); supply is deterministic in the source, so it carries "
              "no interval at all. An index hides levels by construction: logic supply "
              "is measured in hundreds of thousands of wafers a quarter and CoWoS in "
              "tens of thousands, so equal slopes are not equal volumes.")

    fig = plt.figure(figsize=(12.0, 8.2))
    ax = fig.add_axes(_rect(subtitle, note, left=0.078, width=0.700,
                            xlabel_room=0.056))
    idx = list(range(len(quarters)))
    for name, dcol, scol, colour in pairs:
        d0 = demand(dcol, quarters[0])
        s0 = supply[quarters[0]][scol]
        ax.plot(idx, [demand(dcol, q) / d0 * 100 for q in quarters], marker="o",
                markersize=5.0, linewidth=2.4, color=colour, label=f"{name} — AI demand",
                zorder=4)
        ax.plot(idx, [supply[q][scol] / s0 * 100 for q in quarters], linewidth=1.8,
                linestyle=(0, (5, 2.5)), color=colour, alpha=0.75,
                label=f"{name} — world supply", zorder=3)

    ax.set_xticks(idx)
    ax.set_xticklabels([q.replace(" ", "\n") for q in quarters], fontsize=9.4)
    ax.set_xlim(-0.35, len(quarters) - 0.15)
    ax.set_ylabel(f"Index, {quarters[0]} = 100", fontsize=10)
    ax.set_xlabel("Quarter", fontsize=10)
    ax.axhline(100, color=RULE, linewidth=1.0, zorder=1)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1.015, 1.0), frameon=False,
              fontsize=8.8, title="Series", title_fontsize=9.2, handlelength=2.0,
              borderaxespad=0)
    _chip_badge(ax)
    frame(fig, ax, "CHIP-D06",
          "Demand outgrew supply in logic and memory; packaging kept pace",
          subtitle, chip_src(["quarterly_by_designer.csv", "supply_denominators.csv"]),
          CHIP_METH, note)
    save(fig, "CHIP-D06", CHIP_DOMAIN)


# ------------------------------------------- Derived analysis (same raw files)
def _mfig(plot_id, title, subtitle, note, source_ds, left, width,
          xlabel_room=0.055, figsize=(12.0, 8.4)):
    """Standard figure and axes for a models chart, sized around its own text."""
    fig = plt.figure(figsize=figsize)
    rect = _rect(subtitle, note, left=left, width=width, xlabel_room=xlabel_room)
    ax = fig.add_axes(rect)
    return fig, ax


def _finish(fig, ax, plot_id, title, subtitle, note, datasets):
    src = (", ".join(MODELS_SRC[d] for d in datasets)
           if len(datasets) > 1 else MODELS_SRC[datasets[0]])
    frame(fig, ax, plot_id, title, subtitle,
          f"Epoch AI, Data on AI Models (CC-BY) — {src} — epoch.ai/data/ai-models",
          MODELS_METH, note)
    save(fig, plot_id, MODELS_DOMAIN)


def _year_stack(dataset, dimension, since, top_n, residual, rename=None):
    """Yearly counts by category, top-N kept and the rest pooled."""
    t = _mtable("models_by_year.csv")
    t = t[(t["dataset"] == dataset) & (t["dimension"] == dimension)
          & (t["year"] >= since)]
    if rename:
        t = t.assign(category=t["category"].map(lambda c: rename(c)))
        t = t.groupby(["year", "category"], as_index=False)["models"].sum()
    years = sorted(t["year"].unique())
    totals = t.groupby("category")["models"].sum().sort_values(ascending=False)
    keep = list(totals.index[:top_n])
    rows = {}
    for cat in keep:
        sub = t[t["category"] == cat].set_index("year")["models"]
        rows[cat] = [int(sub.get(y, 0)) for y in years]
    rest = t[~t["category"].isin(keep)]
    if len(rest):
        sub = rest.groupby("year")["models"].sum()
        rows[residual] = [int(sub.get(y, 0)) for y in years]
    return years, rows


def _stacked_years(ax, years, rows, share=False):
    colours = {}
    base = [0.0] * len(years)
    totals = [sum(rows[k][i] for k in rows) for i in range(len(years))]
    for i, (name, vals) in enumerate(rows.items()):
        colour = RESIDUAL if i == len(rows) - 1 and name.startswith(
            ("Other", "All other")) else MODELS_PALETTE[i % len(MODELS_PALETTE)]
        colours[name] = colour
        heights = [(v / t * 100 if t else 0) if share else v
                   for v, t in zip(vals, totals)]
        ax.bar(years, heights, bottom=base, width=0.78, color=colour,
               edgecolor="white", linewidth=0.5, label=name, zorder=3)
        base = [b + h for b, h in zip(base, heights)]
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc="upper left",
              bbox_to_anchor=(1.015, 1.0), frameon=False, fontsize=8.8,
              handlelength=1.1, borderaxespad=0, labelspacing=0.5)
    return totals, colours


def build_md01(_r=None):
    """Which of the measured quantities is actually growing fastest."""
    t = _mtable("models_trends.csv")
    t = t[(t["dataset"] == "notable") & (t["era"] == "deep learning era")]
    names = {
        "training_compute_flop": "Training compute (FLOP)",
        "training_dataset_size": "Training dataset size",
        "training_cost_2023usd": "Training cost (2023 US$)",
        "parameters": "Parameters",
        "training_power_draw_w": "Training power draw",
    }
    rows = [t[t["metric"] == m].iloc[0] for m in names if (t["metric"] == m).any()]
    rows.sort(key=lambda r: r["doubling_time_months"])

    subtitle = (f"What it shows: how fast each measured quantity has doubled since "
                f"{DL_ERA}, fitted to the notable models that record it. Compute is "
                f"not simply parameters multiplied by data — the three grow at "
                f"visibly different rates, and the resources bought to produce it "
                f"grow slower still.")
    note = ("Each fit is an ordinary least-squares line through log10 of the metric "
            "against publication date, over exactly the models that record that "
            "metric — a different subset for every bar, from "
            f"{int(min(r['n'] for r in rows))} to {int(max(r['n'] for r in rows))} "
            "models, shown against each bar with its r². The r² values are low for "
            "cost and power, so those two doubling times describe a wide cloud, not "
            "a tight trend. Nothing is extrapolated past the last observation, and "
            "no missing value is filled: a model with no recorded cost is absent "
            "from the cost fit rather than assigned one.")

    fig = plt.figure(figsize=(11.8, 7.6))
    ax = fig.add_axes(_rect(subtitle, note, left=0.255, width=0.700, xlabel_room=0.085))
    ys = list(range(len(rows)))[::-1]
    ax.barh(ys, [r["doubling_time_months"] for r in rows], height=0.62,
            color=[MODELS_PALETTE[i % len(MODELS_PALETTE)] for i in range(len(rows))],
            edgecolor="white", linewidth=0.6, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels([names[r["metric"]] for r in rows], fontsize=10)
    for y, r in zip(ys, rows):
        ax.text(r["doubling_time_months"] + 0.35, y,
                f"{r['doubling_time_months']:.1f} months  ·  "
                f"{r['growth_per_year']:.1f}× per year  ·  n={int(r['n'])}  ·  "
                f"r² = {r['r_squared']:.2f}",
                va="center", fontsize=9.2, color=INK)
    ax.set_xlim(0, max(r["doubling_time_months"] for r in rows) * 1.85)
    ax.set_xlabel("Doubling time (months), deep learning era fit", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _finish(fig, ax, "MODELS-D01",
            "Compute doubles twice as fast as the money and power behind it",
            subtitle, note, ["notable"])


def build_md02(_r=None):
    """Where the notable models are produced."""
    years, rows = _year_stack("notable", "country", 2012, 6, "Other countries",
                              rename=_short_country)
    summ = _msummary("notable")

    subtitle = ("What it shows: notable models published each year by the country of "
                "the organisation that built them. Counts, not compute — one line of "
                "reading for how broadly the capability is distributed.")
    fig = plt.figure(figsize=(12.0, 8.2))
    note = ("Country is recorded per contributing organisation, so a model with "
            "organisations in two countries is counted once as Multinational rather "
            "than split or assigned to the first. Models with no recorded country "
            "are absent. Counts are of models Epoch judged notable, which is an "
            "editorial threshold and not a census of everything published; the "
            "recent years are also the least complete, because notability is "
            "partly assessed with hindsight. "
            f"{int(summ['models']):,} notable models span "
            f"{summ['first_publication'][:4]}–{summ['last_publication'][:4]}; "
            f"{years[0]} onward is shown.")
    ax = fig.add_axes(_rect(subtitle, note, left=0.075, width=0.700))
    totals, _ = _stacked_years(ax, years, rows)
    for x, tot in zip(years, totals):
        ax.text(x, tot + max(totals) * 0.015, f"{tot}", ha="center", va="bottom",
                fontsize=8.4, color=MUTED)
    ax.set_ylim(0, max(totals) * 1.12)
    ax.set_xlabel("Publication year", fontsize=10)
    ax.set_ylabel("Notable models published", fontsize=10)
    ax.set_xticks(years[::1 if len(years) <= 16 else 2])
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _finish(fig, ax, "MODELS-D02",
            "The United States publishes most notable models; China is the only "
            "close second", subtitle, note, ["notable"])


def build_md03(_r=None):
    """Who builds them, and how big their models are."""
    t = _mtable("models_by_organization.csv")
    t = t[t["dataset"] == "notable"].nlargest(20, "models")
    sectors = {"Industry": MODELS_PALETTE[0], "Academia": MODELS_PALETTE[2],
               "Industry-academia collaboration": MODELS_PALETTE[1],
               "Research collective": MODELS_PALETTE[3], "Government": MODELS_PALETTE[4]}

    subtitle = ("What it shows: the 20 organisations credited on the most notable "
                "models, coloured by what kind of organisation they are, with the "
                "largest training run each has on record.")
    note = ("An organisation is credited here when it is listed first on the model. "
            "Models are co-published often enough that this understates university "
            "involvement in particular, and Epoch lists several Google research "
            "groups separately (Google, Google DeepMind, DeepMind, Google Brain, "
            "Google Research), which are not merged here because merging them would "
            "be our judgement rather than the source's. The compute figure beside "
            "each bar is the largest training run that organisation records, over "
            "the subset of its models that record one.")

    fig = plt.figure(figsize=(12.0, 8.8))
    ax = fig.add_axes(_rect(subtitle, note, left=0.285, width=0.560, xlabel_room=0.05))
    ys = list(range(len(t)))[::-1]
    ax.barh(ys, t["models"], height=0.72,
            color=[sectors.get(c, RESIDUAL) for c in t["org_category"]],
            edgecolor="white", linewidth=0.6, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels([_clip(o, 34) for o in t["organization"]], fontsize=9.2)
    for y, (_, r) in zip(ys, t.iterrows()):
        label = f"{int(r['models'])}"
        if r["max_compute_flop"] == r["max_compute_flop"]:  # not NaN
            label += f"   largest run {_pow10(10 ** round(math.log10(r['max_compute_flop'])))} FLOP"
        ax.text(r["models"] + max(t["models"]) * 0.012, y, label, va="center",
                fontsize=8.8, color=INK)
    ax.set_xlim(0, max(t["models"]) * 1.45)
    ax.set_xlabel("Notable models credited", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    handles = [plt.Line2D([0], [0], marker="s", linestyle="none", markersize=8,
                          color=c, label=k) for k, c in sectors.items()
               if k in set(t["org_category"])]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=9)
    _finish(fig, ax, "MODELS-D03",
            "A handful of industry labs account for most notable models",
            subtitle, note, ["notable"])


def build_md04(_r=None):
    """Industry against academia, over time."""
    years, rows = _year_stack("notable", "org_category", 2010, 5, "Other")
    subtitle = ("What it shows: the share of each year's notable models coming from "
                "industry, from academia, and from the two working together. The "
                "handover is the single clearest structural change in the dataset.")
    note = ("Shares of the models published that year that carry an organisation "
            "category, so every column is 100% of a different base — the count "
            "behind each is printed above it, and the composition is what to read "
            "here, not the volume. Category is recorded per "
            "contributing organisation; a model with both an industry and an "
            "academic organisation is counted once as a collaboration rather than "
            "split between the two. The most recent year is partial.")
    fig = plt.figure(figsize=(12.0, 8.2))
    ax = fig.add_axes(_rect(subtitle, note, left=0.075, width=0.700))
    totals, _ = _stacked_years(ax, years, rows, share=True)
    for x, tot in zip(years, totals):
        ax.text(x, 101, f"n={tot}", ha="center", va="bottom", fontsize=7.8, color=MUTED,
                rotation=90)
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_xlabel("Publication year", fontsize=10)
    ax.set_ylabel("Share of that year's notable models", fontsize=10)
    ax.set_xticks(years[::1 if len(years) <= 16 else 2])
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _finish(fig, ax, "MODELS-D04",
            "Notable models moved from academia to industry, and stayed there",
            subtitle, note, ["notable"])


def build_md05(_r=None):
    """How the weights are released."""
    years, rows = _year_stack("notable", "model_accessibility", 2012, 6, "Other")
    subtitle = ("What it shows: how each year's notable models were released — open "
                "weights, behind an API, hosted without an API, or never released at "
                "all. The access question, answered from the record rather than "
                "from impression.")
    note = ("Shares of the models published that year that carry an accessibility "
            "value; models with none are absent from the column entirely, and the "
            "count behind each column is printed above it. Epoch's categories "
            "distinguish unrestricted open weights from non-commercial and "
            "restricted-use releases, and those are kept separate here rather than "
            "collapsed into one open bucket. The final year is partial. "
            "Accessibility is recorded as of "
            "Epoch's last update to the row, so a model whose licence changed later "
            "still shows its recorded state.")
    fig = plt.figure(figsize=(12.0, 8.4))
    ax = fig.add_axes(_rect(subtitle, note, left=0.075, width=0.660))
    totals, _ = _stacked_years(ax, years, rows, share=True)
    for x, tot in zip(years, totals):
        ax.text(x, 101, f"n={tot}", ha="center", va="bottom", fontsize=7.8,
                color=MUTED, rotation=90)
    ax.set_ylim(0, 118)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_xlabel("Publication year", fontsize=10)
    ax.set_ylabel("Share of that year's notable models", fontsize=10)
    ax.set_xticks(years[::1 if len(years) <= 16 else 2])
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _finish(fig, ax, "MODELS-D05",
            "Fewer models stay unreleased; access increasingly runs through an API",
            subtitle, note, ["notable"])


def build_md06(_r=None):
    """What the models were trained on."""
    years, rows = _year_stack("notable", "hardware_family", 2012, 8, "Other hardware")
    cov = _mtable("models_coverage.csv")
    hw = cov[(cov["dataset"] == "notable") & (cov["field"] == "training_hardware")].iloc[0]

    subtitle = ("What it shows: the training hardware recorded for each year's "
                "notable models, grouped into accelerator families. This is the "
                "demand side of the chip market, read off the models themselves.")
    note = (f"Epoch records training hardware for {int(hw['records'])} of "
            f"{int(hw['models_dated'])} notable models — {hw['share_of_dated']*100:.0f}% "
            f"— so this is a sample of the fleet, not a census, and it is biased "
            f"toward models whose builders published their setup. Free-text hardware "
            f"strings are grouped into families by name (every H100, H800 and H200 "
            f"variant into one bar, each TPU generation into its own); anything that "
            f"matches no family keeps its own name and falls into Other hardware. A "
            f"model is counted once against the hardware it names, so a run that "
            f"used two chip types is attributed to the one Epoch recorded. The "
            f"final year is partial, and recent models are the least likely to "
            f"have had their hardware documented yet.")
    fig = plt.figure(figsize=(12.0, 8.6))
    ax = fig.add_axes(_rect(subtitle, note, left=0.075, width=0.640))
    totals, _ = _stacked_years(ax, years, rows)
    ax.set_ylim(0, max(totals) * 1.10)
    ax.set_xlabel("Publication year", fontsize=10)
    ax.set_ylabel("Notable models recording this hardware", fontsize=10)
    ax.set_xticks(years[::1 if len(years) <= 16 else 2])
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _finish(fig, ax, "MODELS-D06",
            "Each accelerator generation carries the frontier for about three years",
            subtitle, note, ["notable"])


def build_md07(_r=None):
    """How many chips a training run actually takes."""
    df = _mpoints("notable")
    pts = df.dropna(subset=["hardware_quantity", "training_compute_flop"])
    groups, unknown = _colour_groups(pts, "hardware_family", 7, "Other hardware")

    subtitle = ("What it shows: the number of accelerators used against the compute "
                "the run produced, for every notable model that records both. The "
                "spread at a given chip count is how much longer runs got, and how "
                "much faster each chip became.")
    note = (f"{len(pts)} of {len(df)} notable models record both a chip count and a "
            f"training compute figure; the rest are absent rather than estimated. "
            f"Chip count is the quantity Epoch records for the run, which for some "
            f"models is the cluster size rather than the number actually used, so "
            f"treat the horizontal axis as an upper bound. Compute is a modelled "
            f"quantity for most rows — the two axes are not independent "
            f"measurements, since a compute figure is sometimes derived from the "
            f"hardware and the training time.")
    fig = plt.figure(figsize=(12.0, 8.4))
    ax = fig.add_axes(_rect(subtitle, note, left=0.082, width=0.645))
    for name, sub, colour in groups:
        ax.scatter(sub["hardware_quantity"], sub["training_compute_flop"], s=28,
                   facecolor=colour, edgecolor="white", linewidth=0.35, alpha=0.85,
                   zorder=3, label=f"{_clip(name, 24)}  ({len(sub)})")
    if len(unknown):
        ax.scatter(unknown["hardware_quantity"], unknown["training_compute_flop"],
                   s=22, facecolor="none", edgecolor=MUTED, linewidth=0.5, alpha=0.6,
                   zorder=2, label=f"Not recorded  ({len(unknown)})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    _decade_ticks(ax.xaxis, pts["hardware_quantity"], AXIS_FMT["count"])
    _decade_ticks(ax.yaxis, pts["training_compute_flop"], AXIS_FMT["pow10"])
    ax.set_xlabel("Accelerators used in the training run (log scale)", fontsize=10)
    ax.set_ylabel("Training compute (FLOP, log scale)", fontsize=10)
    ax.grid(color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1.015, 1.0), frameon=False,
              fontsize=8.8, title="Training hardware", title_fontsize=9.2,
              handlelength=1.1, borderaxespad=0, labelspacing=0.55)
    _label_points(ax, pts, "hardware_quantity", "training_compute_flop", 3)
    _finish(fig, ax, "MODELS-D07",
            "Chip count explains part of the compute gap, but not most of it",
            subtitle, note, ["notable"])


def build_md08(_r=None):
    """What a unit of training compute costs."""
    df = _mpoints("notable")
    pts = df.dropna(subset=["training_cost_2023usd", "training_compute_flop"])
    ratio = (pts["training_compute_flop"] / pts["training_cost_2023usd"]).median()

    subtitle = ("What it shows: recorded training cost against recorded training "
                "compute, for every notable model that carries both. The dashed "
                "line is the median rate, so points below it bought their compute "
                "more cheaply than the typical model in the set.")
    note = (f"{len(pts)} of {len(df)} notable models record both values. The median "
            f"rate is {_pow10(10 ** round(math.log10(ratio)))} FLOP per 2023 dollar, "
            f"which is a summary of the middle of this cloud and not a price: the "
            f"cloud spans several orders of magnitude at any compute level, because "
            f"it mixes rental and amortised-hardware accounting and spans a decade "
            f"of falling hardware prices. Epoch's cost figures are estimates for "
            f"most rows, not disclosed spend, and they cover the training run only "
            f"— no research, salaries, data or failed runs.")
    fig = plt.figure(figsize=(11.8, 8.2))
    ax = fig.add_axes(_rect(subtitle, note, left=0.088, width=0.870))
    ax.scatter(pts["training_compute_flop"], pts["training_cost_2023usd"], s=26,
               facecolor=SERIES["current"], edgecolor="white", linewidth=0.35,
               alpha=0.75, zorder=3)
    xs = [pts["training_compute_flop"].min(), pts["training_compute_flop"].max()]
    ax.plot(xs, [x / ratio for x in xs], linestyle="--", linewidth=1.3, color=MUTED,
            zorder=2, label=f"Median rate: {_pow10(10 ** round(math.log10(ratio)))} "
                            f"FLOP per 2023 dollar")
    ax.set_xscale("log")
    ax.set_yscale("log")
    _decade_ticks(ax.xaxis, pts["training_compute_flop"], AXIS_FMT["pow10"])
    _decade_ticks(ax.yaxis, pts["training_cost_2023usd"], AXIS_FMT["usd"])
    ax.set_xlabel("Training compute (FLOP, log scale)", fontsize=10)
    ax.set_ylabel("Training compute cost (2023 US$, log scale)", fontsize=10)
    ax.grid(color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False, fontsize=9.2)
    _label_points(ax, pts, "training_compute_flop", "training_cost_2023usd", 3)
    _finish(fig, ax, "MODELS-D08",
            "Cost tracks compute, but spans three orders of magnitude at any scale",
            subtitle, note, ["notable"])


def build_md09(_r=None):
    """Hardware price-performance, the one series Epoch publishes directly."""
    t = _mtable("frontier_hardware_price_performance.csv")
    t = t.dropna(subset=["flop_per_dollar", "hardware_release_date"])
    t["release"] = t["hardware_release_date"].map(
        lambda d: int(d[:4]) + (int(d[5:7]) - 1) / 12)
    groups, _ = _colour_groups(t, "hardware_family", 7, "Other hardware")

    subtitle = ("What it shows: compute bought per dollar of hardware, plotted "
                "against the release date of the chip each frontier model trained "
                "on. This is the falling-cost side of the compute story, and it is "
                "the only price series in the dataset that is not modelled from "
                "power.")
    note = (f"{len(t)} of 137 frontier models record both a FLOP-per-dollar figure "
            f"and a hardware release date; the rest are absent. The figure is "
            f"Epoch's own, computed from the chip's peak throughput and its list "
            f"price, so it is a specification ratio rather than realised "
            f"performance — real utilisation is typically 30-50% of peak. Several "
            f"models train on the same chip and therefore sit at the same point.")
    fig = plt.figure(figsize=(11.8, 8.0))
    ax = fig.add_axes(_rect(subtitle, note, left=0.088, width=0.645))
    for name, sub, colour in groups:
        ax.scatter(sub["release"], sub["flop_per_dollar"], s=44, facecolor=colour,
                   edgecolor="white", linewidth=0.4, alpha=0.9, zorder=3,
                   label=f"{_clip(name, 24)}  ({len(sub)})")
    ax.set_yscale("log")
    _decade_ticks(ax.yaxis, t["flop_per_dollar"], AXIS_FMT["pow10"])
    ax.set_xlabel("Release date of the training hardware", fontsize=10)
    ax.set_ylabel("FLOP per dollar of hardware (log scale)", fontsize=10)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{int(v)}"))
    ax.grid(color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", bbox_to_anchor=(1.015, 1.0), frameon=False,
              fontsize=8.8, title="Training hardware", title_fontsize=9.2,
              handlelength=1.1, borderaxespad=0, labelspacing=0.55)
    _finish(fig, ax, "MODELS-D09",
            "Compute per dollar rises with each chip generation, unevenly",
            subtitle, note, ["frontier"])


def build_md10(_r=None):
    """What the models are for."""
    years, rows = _year_stack("notable", "domain", 2012, 7, "Other domains")
    subtitle = ("What it shows: what each year's notable models were built to do. "
                "Vision led the field for most of the last decade; language and "
                "multimodal models displaced it.")
    note = ("Domain is recorded per model and can list several; a model tagged "
            "Multimodal is counted there rather than under each of its component "
            "domains, and any other multi-domain model is counted under the first "
            "domain Epoch lists. Models with no recorded domain are absent. Counts "
            "are of notable models, so the mix reflects what was judged notable in "
            "each year as much as what was built, and the final year is partial.")
    fig = plt.figure(figsize=(12.0, 8.4))
    ax = fig.add_axes(_rect(subtitle, note, left=0.075, width=0.700))
    totals, _ = _stacked_years(ax, years, rows)
    ax.set_ylim(0, max(totals) * 1.10)
    ax.set_xlabel("Publication year", fontsize=10)
    ax.set_ylabel("Notable models published", fontsize=10)
    ax.set_xticks(years[::1 if len(years) <= 16 else 2])
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _finish(fig, ax, "MODELS-D10",
            "Language and multimodal models took over from vision after 2020",
            subtitle, note, ["notable"])


def build_md11(_r=None):
    """What the dataset actually records - the limit on every chart above."""
    cov = _mtable("models_coverage.csv")
    fields = [
        ("training_compute_flop", "Training compute"),
        ("parameters", "Parameters"),
        ("training_dataset_size", "Training dataset size"),
        ("training_hardware", "Training hardware"),
        ("citations", "Citations"),
        ("training_time_hours", "Training time"),
        ("hardware_quantity", "Accelerator count"),
        ("training_power_draw_w", "Training power draw"),
        ("training_cost_2023usd", "Training cost"),
    ]
    order = ["notable", "frontier", "large_scale", "all"]
    labels = {"notable": "Notable", "frontier": "Frontier",
              "large_scale": "Large-scale", "all": "All models"}

    subtitle = ("What it shows: the share of each Epoch release that records each "
                "field. This is the ceiling on every chart in this domain — a chart "
                "of training cost can only ever plot the sliver of models that "
                "carry a cost.")
    note = ("Share of the models in each release that carry a publication date and "
            "a value for the field. Coverage is far higher in the frontier release "
            "because it is small and heavily researched, and lowest in the full "
            "database, which includes thousands of models nobody has documented in "
            "depth. Nothing on this site fills these gaps: a model missing a field "
            "is dropped from that chart, which is why the plotted count differs "
            "from chart to chart and is stated on each one.")

    fig = plt.figure(figsize=(12.0, 8.6))
    ax = fig.add_axes(_rect(subtitle, note, left=0.215, width=0.640, xlabel_room=0.05,
                            source=("Epoch AI, Data on AI Models (CC-BY) — "
                                    + ", ".join(MODELS_SRC[d] for d in
                                                ["notable", "frontier",
                                                 "large_scale", "all"])
                                    + " — epoch.ai/data/ai-models")))
    height = 0.78 / len(order)
    ys = list(range(len(fields)))[::-1]
    for i, ds in enumerate(order):
        sub = cov[cov["dataset"] == ds].set_index("field")
        offs = [y + (len(order) / 2 - 0.5 - i) * height for y in ys]
        vals, absent = [], []
        for (f, _), off in zip(fields, offs):
            published = f in sub.index and bool(sub.loc[f, "field_in_release"])
            vals.append(sub.loc[f, "share_of_dated"] * 100 if published else 0.0)
            if not published:
                absent.append(off)
        ax.barh(offs, vals, height=height * 0.92, color=MODELS_PALETTE[i],
                edgecolor="white", linewidth=0.4, zorder=3,
                label=f"{labels[ds]}  ({int(sub['models_dated'].iloc[0]):,} models)")
        # an empty bar would read as nobody recording it; say what it really is
        for off in absent:
            ax.text(0.6, off, "column not published in this release", va="center",
                    fontsize=7.4, color=MUTED, style="italic", zorder=4)
    ax.set_yticks(ys)
    ax.set_yticklabels([lab for _, lab in fields], fontsize=9.6)
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_xlabel("Share of dated models in the release that record the field",
                  fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    handles, lbls = ax.get_legend_handles_labels()
    ax.legend(handles, lbls, loc="lower right", frameon=False, fontsize=9,
              title="Epoch release", title_fontsize=9.2)
    _finish(fig, ax, "MODELS-D11",
            "Most models record what they are; far fewer record what they cost",
            subtitle, note, ["notable", "frontier", "large_scale", "all"])


MODEL_DERIVED = {
    "MODELS-D01": build_md01, "MODELS-D02": build_md02, "MODELS-D03": build_md03,
    "MODELS-D04": build_md04, "MODELS-D05": build_md05, "MODELS-D06": build_md06,
    "MODELS-D07": build_md07, "MODELS-D08": build_md08, "MODELS-D09": build_md09,
    "MODELS-D10": build_md10, "MODELS-D11": build_md11,
}


# =========================================================== AI COMPANIES
# Epoch AI publishes one configurable figure for AI Companies: a metric against
# date, over a chosen tab (revenue, funding, staff, usage, compute spend), with
# controls for linear/log scale and a fitted growth regression. COMPANIES-01 to
# COMPANIES-10 are that figure at each of its distinct settings; COMPANIES-D01
# onward ask what the explorer's settings cannot.
COMPANIES_DOMAIN = "ai-companies"
COMPANIES_DATA = REPO / COMPANIES_DOMAIN / "data"

# must match summarise_epoch_companies.py, which refuses a fit below it
MIN_C_FIT = 12

COMPANIES_SRC = {
    "revenue": "ai_companies_revenue_reports.csv",
    "usage": "ai_companies_usage_reports.csv",
    "staff": "ai_companies_staff_reports.csv",
    "funding": "ai_companies_funding_rounds.csv",
    "spend": "ai_companies_compute_spend.csv",
    "companies": "ai_companies.csv",
}
COMPANIES_METH = ("Methodology reference pending final methodology document; derivation "
                  "follows Epoch AI's published AI companies documentation")

# One colour per company, held across every chart in the domain, so a reader who
# learns the key on one figure keeps it on all of them.
COMPANY_COLOUR = {
    "OpenAI": "#1f3864",
    "Anthropic": "#b4763a",
    "Google": "#4a6fa5",
    "Meta": "#6b8f71",
    "xAI": "#7d5a7d",
    "DeepSeek": "#4e8a8b",
    "Mistral AI": "#a46b6b",
    "Cohere": "#8a8f5c",
    "Z.ai (Zhipu)": "#9aa9c4",
    "MiniMax": "#55606e",
    "Moonshot AI": "#5f7a99",
}


def companies_src(keys):
    return ("Epoch AI, AI Companies (CC-BY) — "
            + " + ".join(COMPANIES_SRC[k] for k in keys)
            + " — epoch.ai/data/ai-companies")


def _ccsv(name):
    import pandas as pd
    df = pd.read_csv(COMPANIES_DATA / name)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _cmeta():
    return _ccsv("companies_summary.csv").iloc[0]


def _ccolour(name):
    return COMPANY_COLOUR.get(name, RESIDUAL)


def _cfinish(fig, ax, plot_id, title, subtitle, note, keys, badge_above=False):
    _observed_badge(ax, above=badge_above)
    frame(fig, ax, plot_id, title, subtitle, companies_src(keys),
          COMPANIES_METH, note)
    save(fig, plot_id, COMPANIES_DOMAIN)


def _cfig(subtitle, note, left=0.078, width=0.660, xlabel_room=0.055,
          figsize=(12.0, 8.4), badge_above=False, source=None):
    fig = plt.figure(figsize=figsize)
    ax = fig.add_axes(_rect(subtitle, note, left=left, width=width,
                            xlabel_room=xlabel_room, badge_above=badge_above,
                            source=source))
    return fig, ax


def _date_axis(ax, dates, pad_days=120):
    """Year ticks across the observed span, with a little air at each end."""
    import matplotlib.dates as mdates
    from datetime import timedelta
    lo, hi = min(dates), max(dates)
    ax.set_xlim(lo - timedelta(days=pad_days), hi + timedelta(days=pad_days))
    span = (hi - lo).days / 365.25
    ax.xaxis.set_major_locator(mdates.YearLocator(1 if span <= 8 else 2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def _clegend(ax, title="Company"):
    h, l = ax.get_legend_handles_labels()
    if not h:
        return 0
    leg = ax.legend(h, l, loc="upper left", bbox_to_anchor=(1.015, 1.0),
                    frameon=False, fontsize=9, title=title, title_fontsize=9.2,
                    handlelength=1.6, borderaxespad=0)
    ax.add_artist(leg)   # survives the next ax.legend() call
    return len(h) + 1


CAT_MARKER = {"R&D only": "^", "Inference only": "o", "R&D + inference": "s"}


def _cseries(df, value_col, log=True, marker="o", connect=True, open_mask=None,
             marker_col=None):
    """Plot one line-and-marker series per company, largest company first.

    marker_col splits each company's points by a second dimension - used where a
    company reports more than one kind of figure on the same date, which would
    otherwise stack two indistinguishable dots.
    """
    order = (df.groupby("company")[value_col].max()
               .sort_values(ascending=False).index.tolist())
    if marker_col:
        for name in order:
            sub = df[df["company"] == name]
            plt.gca().scatter([], [], s=46, color=_ccolour(name),
                              edgecolor="white", linewidth=0.8,
                              label=f"{name}  (n={len(sub)})")
            for cat, csub in sub.groupby(marker_col):
                plt.gca().scatter(csub["date"], csub[value_col], s=52,
                                  color=_ccolour(name), marker=CAT_MARKER.get(cat, "o"),
                                  edgecolor="white", linewidth=0.8, zorder=4)
        return order
    for name in order:
        sub = df[df["company"] == name].sort_values("date")
        colour = _ccolour(name)
        if connect and len(sub) > 1:
            plt.gca().plot(sub["date"], sub[value_col], color=colour,
                           linewidth=1.4, alpha=0.85, zorder=3)
        if open_mask is not None:
            solid = sub[~sub[open_mask]]
            hollow = sub[sub[open_mask]]
            plt.gca().scatter(solid["date"], solid[value_col], s=46, color=colour,
                              edgecolor="white", linewidth=0.8, zorder=4,
                              label=f"{name}  (n={len(sub)})")
            if len(hollow):
                plt.gca().scatter(hollow["date"], hollow[value_col], s=46,
                                  facecolor="white", edgecolor=colour,
                                  linewidth=1.5, zorder=4)
        else:
            plt.gca().scatter(sub["date"], sub[value_col], s=46, color=colour,
                              marker=marker, edgecolor="white", linewidth=0.8,
                              zorder=4, label=f"{name}  (n={len(sub)})")
    return order


# ------------------------------------------------- Epoch's figure, each setting
CT = {   # one entry per tab/metric the explorer offers
    "revenue": dict(
        table="companies_revenue.csv", col="revenue_usd", keys=["revenue"],
        ylabel="Annualised revenue (USD)", what="annualised revenue", fmt="usd", connect=True,
        open_col="annualised_from_period",
        open_note="Open markers are Epoch annualising a disclosed period figure "
                  "(a reported quarter multiplied out) rather than a disclosed "
                  "annual rate",
        defn="Annualised revenue is the run rate Epoch records at that date - the "
             "most recent period scaled to a year, not audited annual revenue.",
    ),
    "active_users": dict(
        table="companies_usage.csv", col="active_users", keys=["usage"],
        ylabel="Active users", what="active users", fmt="count", connect=True, open_col=None,
        defn="Active users as each company reported them. The averaging window "
             "differs by report - daily, weekly and monthly counts all appear "
             "here and are not interchangeable.",
    ),
    "daily_tokens": dict(
        table="companies_usage.csv", col="daily_tokens", keys=["usage"],
        ylabel="Tokens processed per day", what="tokens processed per day", fmt="count", connect=True, open_col=None,
        defn="Tokens processed per day, as disclosed. Scope differs by company - "
             "some figures are one API, others every surface.",
    ),
    "staff_count": dict(
        table="companies_staff.csv", col="staff_count", keys=["staff"],
        ylabel="Staff count", what="headcount", fmt="count", connect=True, open_col="_division",
        open_note="Open markers count an AI division or a single role rather than "
                  "the whole company - the only figures published for Google and Meta",
        defn="Headcount at the date of the report. For Google and Meta this is the "
             "AI division, not the corporation.",
    ),
    "equity_usd": dict(
        table="companies_funding.csv", col="equity_usd", keys=["funding"],
        ylabel="Equity raised in the round (USD)", what="equity raised per round", fmt="usd", connect=False,
        open_col=None,
        defn="Equity raised in a single closed round. Rounds still in discussion "
             "and the one cancelled round are excluded - they are not raised capital.",
    ),
    "valuation_usd": dict(
        table="companies_funding.csv", col="valuation_usd", keys=["funding"],
        ylabel="Post-money valuation (USD)", what="post-money valuation", fmt="usd", connect=True, open_col=None,
        defn="Post-money valuation set by the round that closed on that date.",
    ),
    "amount_usd": dict(
        table="companies_spend.csv", col="amount_usd", keys=["spend"],
        ylabel="Compute spend (USD)", what="cloud compute spend", fmt="usd", connect=False, open_col=None,
        marker_col="category_short",
        defn="Cloud compute spend for the period, split by Epoch into R&D and "
             "inference. A row may cover one category or both.",
    ),
}

COMPANIES_PLOTS = {
    "COMPANIES-01": dict(metric="revenue", log=True, trend=False,
                         title="Annualised revenue of AI companies"),
    "COMPANIES-02": dict(metric="revenue", log=False, trend=False,
                         title="Annualised revenue of AI companies, linear scale"),
    "COMPANIES-03": dict(metric="revenue", log=True, trend=True,
                         title="Annualised revenue of AI companies, with fitted growth"),
    "COMPANIES-04": dict(metric="active_users", log=True, trend=False,
                         title="Active users of AI products"),
    "COMPANIES-05": dict(metric="daily_tokens", log=True, trend=False,
                         title="Tokens processed per day, by company"),
    "COMPANIES-06": dict(metric="staff_count", log=True, trend=False,
                         title="Staff at AI companies"),
    "COMPANIES-07": dict(metric="staff_count", log=True, trend=True,
                         title="Staff at AI companies, with fitted growth"),
    "COMPANIES-08": dict(metric="equity_usd", log=True, trend=False,
                         title="Equity raised per funding round"),
    "COMPANIES-09": dict(metric="valuation_usd", log=True, trend=False,
                         title="Post-money valuation of AI companies"),
    "COMPANIES-10": dict(metric="amount_usd", log=True, trend=False,
                         title="Cloud compute spend of AI companies"),
}


def _cdata(metric):
    """The plotted frame for one metric, absent values left absent."""
    cfg = CT[metric]
    df = _ccsv(cfg["table"])
    if metric == "equity_usd":
        df = df[df["closed"]]
    if metric == "staff_count":
        df["_division"] = df["scope"].fillna("") != "Full company"
    if metric == "amount_usd":
        def short(c):
            c = str(c)
            has_r, has_i = "R&D" in c, "Inference" in c
            return ("R&D + inference" if has_r and has_i
                    else "R&D only" if has_r else "Inference only")
        df["category_short"] = df["category"].map(short)
    return df.dropna(subset=[cfg["col"]]).copy()


def _ctrend_lines(ax, value_col, log):
    """Overlay Epoch's regression control: log-linear fits, observed span only."""
    from datetime import date, timedelta
    if not log:
        return []
    fits = _ccsv("companies_trends.csv")
    fits = fits[fits["metric"] == value_col]
    drawn = []
    for _, f in fits.iterrows():
        def as_date(y):
            return date(int(y), 1, 1) + timedelta(days=(y - int(y)) * 365.25)
        xs = [f["x_min"], f["x_max"]]
        ys = [10 ** (f["oom_per_year"] * x + f["intercept_log10"]) for x in xs]
        # never drawn past the last observation: no projection, by house rule
        ax.plot([as_date(x) for x in xs], ys, linestyle=(0, (5, 2.5)),
                color=_ccolour(f["company"]), linewidth=1.8, alpha=0.95, zorder=5)
        drawn.append(f)
    return drawn


def build_companies(plot_id):
    cfg = COMPANIES_PLOTS[plot_id]
    metric, tab = cfg["metric"], CT[cfg["metric"]]
    df = _cdata(metric)
    meta = _cmeta()
    # a log axis cannot carry a zero. Those rows are real observations - a
    # secondary sale raises no new equity - so they are dropped and counted,
    # never quietly nudged onto the floor
    zeroed = 0
    if cfg["log"]:
        zeroed = int((df[tab["col"]] <= 0).sum())
        df = df[df[tab["col"]] > 0]
    n, ncomp = len(df), df["company"].nunique()

    setting = (f"Setting:  {tab['what'][0].upper() + tab['what'][1:]}\n"
               f"Scale:  {'logarithmic' if cfg['log'] else 'linear'}\n"
               f"Trend:  {'fitted' if cfg['trend'] else 'off'}\n"
               f"Projection:  off")

    subtitle = (f"What it shows: {tab['what']} for every AI company where "
                f"Epoch records it, plotted at the date of the report. "
                f"{n} observations across {ncomp} companies. {tab['defn']}")

    note_bits = []
    if cfg["log"]:
        note_bits.append("The vertical axis is log-scaled because the values span "
                         "several orders of magnitude; on a linear axis every "
                         "company but the largest collapses onto the floor")
    else:
        note_bits.append("Linear scale, which is what the largest company looks "
                         "like next to the rest - the same data as the log view "
                         "and the reason Epoch defaults to log")
    if tab.get("open_note"):
        note_bits.append(tab["open_note"])
    excl = int(meta[f"excluded_by_epoch_{'usage' if tab['keys'][0]=='usage' else tab['keys'][0]}"]) \
        if f"excluded_by_epoch_{tab['keys'][0]}" in meta.index else 0
    if excl:
        note_bits.append(f"{excl} rows Epoch flagged 'exclude from graph view' are "
                         f"dropped, as they are on Epoch's own figure")
    if zeroed:
        note_bits.append(f"{zeroed} rounds recorded at zero new equity - secondary "
                         f"sales between existing shareholders - cannot sit on a log "
                         f"axis and are dropped rather than floored")
    note_bits.append("A company is absent from a chart wherever Epoch records no "
                     "value - never imputed, back-filled or carried across")
    note = ". ".join(note_bits) + "."

    fig, ax = _cfig(subtitle, note, source=companies_src(tab["keys"]))
    plt.sca(ax)
    _cseries(df, tab["col"], log=cfg["log"], connect=tab["connect"],
             open_mask=tab["open_col"], marker_col=tab.get("marker_col"))

    fits = _ctrend_lines(ax, tab["col"], cfg["log"]) if cfg["trend"] else []

    if cfg["log"]:
        ax.set_yscale("log")
        _decade_ticks(ax.yaxis, df[tab["col"]], AXIS_FMT[tab["fmt"]])
    else:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(
            lambda v, _p: AXIS_FMT[tab["fmt"]](v) or ("0" if v == 0 else "")))
    _date_axis(ax, list(df["date"]))
    ax.set_ylabel(tab["ylabel"], fontsize=10)
    ax.set_xlabel("Date of report", fontsize=10)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.grid(axis="x", color=RULE, linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    rows = _clegend(ax)

    if tab.get("marker_col"):
        from matplotlib.lines import Line2D
        keys = [Line2D([], [], linestyle="none", marker=m, color=MUTED,
                       markersize=7, label=c) for c, m in CAT_MARKER.items()]
        ax.legend(handles=keys, loc="upper left",
                  bbox_to_anchor=(1.015, 1.0 - 0.062 * rows), frameon=False,
                  fontsize=9, title="Spend category", title_fontsize=9.2,
                  borderaxespad=0)
        rows += len(keys) + 1

    lines = [setting]
    if fits:
        lines.append("Fitted growth\n" + "\n".join(
            f"{f['company']}:  {f['growth_per_year']:.1f}x/year\n"
            f"    doubling {f['doubling_time_months']:.1f} mo,  "
            f"r\u00b2={f['r_squared']:.2f},  n={int(f['n'])}"
            for f in fits))
    elif cfg["trend"]:
        lines.append(f"No fit drawn: no company\nreaches the {MIN_C_FIT} observations\n"
                     f"a trend line requires")
    ax.text(1.015, 0.98 - 0.062 * rows, "\n\n".join(lines),
            transform=ax.transAxes, ha="left", va="top", fontsize=8.3,
            color=MUTED, linespacing=1.55)

    _cfinish(fig, ax, plot_id, cfg["title"], subtitle, note, tab["keys"])


# ------------------------------------------- Derived analysis (same raw files)
def _nearest(target, ref, value_col, max_days=365):
    """Attach each target row the closest reference observation in time.

    Used where two Epoch tables are reported on different dates and a ratio only
    means anything if the two sides are close together. Rows with no reference
    inside the window are dropped, never matched to the nearest at any distance.
    """
    import pandas as pd
    out = []
    for company, sub in target.groupby("company"):
        pool = ref[ref["company"] == company].dropna(subset=[value_col])
        if pool.empty:
            continue
        for _, row in sub.iterrows():
            gap = (pool["date"] - row["date"]).abs()
            j = gap.idxmin()
            if gap.loc[j] <= pd.Timedelta(days=max_days):
                r = row.copy()
                r["ref_value"] = pool.loc[j, value_col]
                r["ref_date"] = pool.loc[j, "date"]
                r["gap_days"] = int(gap.loc[j].days)
                out.append(r)
    return pd.DataFrame(out)


def build_c_d01(_r=None):
    """What growth the record can actually carry a trend for."""
    import pandas as pd
    fits = _ccsv("companies_trends.csv").sort_values("doubling_time_months")
    cov = _ccsv("companies_coverage.csv")
    label = {"revenue_usd": "Revenue", "staff_count": "Staff count",
             "active_users": "Active users"}
    short = {"Revenue": "Revenue", "Staff count": "Staff count",
             "Active users": "Active users"}
    below = {}
    for metric, name in label.items():
        c = cov[cov["metric"] == short[name]]
        below[name] = int((c["observations"].between(1, MIN_C_FIT - 1)).sum())

    subtitle = (f"What it shows: the growth rate behind each series Epoch's regression "
                f"control can fit, as an annual multiple and the doubling time it "
                f"implies. Only {len(fits)} of the tracked series reach the "
                f"{MIN_C_FIT} observations a log-linear fit requires; every other "
                f"company is measured too sparsely to carry a trend at all.")
    note = ("Fitted by ordinary least squares through log10 of the metric against "
            "date, over the observed points only and never extended past the last "
            "of them. A doubling time is the fit restated, not a separate "
            "measurement. Anthropic's revenue fit is the steepest series in the "
            "entire dataset. Companies below the threshold are counted, not fitted "
            "- a two-point 'trend' is a line through two points, not a growth rate.")

    fig, ax = _cfig(subtitle, note, left=0.175, width=0.560, badge_above=True,
                    source=companies_src(["revenue", "staff", "usage"]))
    ys = range(len(fits))
    for y, (_, f) in zip(ys, fits.iterrows()):
        ax.barh(y, f["doubling_time_months"], height=0.62,
                color=_ccolour(f["company"]), edgecolor="white", linewidth=0.6,
                zorder=3)
        ax.text(f["doubling_time_months"] + 0.35, y,
                f"{f['growth_per_year']:.1f}x/year   r²={f['r_squared']:.2f}   "
                f"n={int(f['n'])}", va="center", fontsize=9, color=INK, zorder=4)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([f"{f['company']}\n{label[f['metric']]}"
                        for _, f in fits.iterrows()], fontsize=9.4)
    ax.invert_yaxis()
    ax.set_xlabel("Doubling time (months)", fontsize=10)
    ax.set_xlim(0, float(fits["doubling_time_months"].max()) * 1.55)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.text(0.995, 0.985,
            "Series with observations but too few to fit:  "
            + ",  ".join(f"{k} {v}" for k, v in below.items() if v),
            transform=ax.transAxes, ha="right", va="top", fontsize=8.6,
            color=MUTED, style="italic")
    _observed_badge(ax, above=True)
    frame(fig, ax, "COMPANIES-D01",
          "Only four series in the dataset are measured often enough to fit a trend",
          subtitle, companies_src(["revenue", "staff", "usage"]), COMPANIES_METH, note)
    save(fig, "COMPANIES-D01", COMPANIES_DOMAIN)


def build_c_d02(_r=None):
    """Revenue per employee, matched observation to observation."""
    rev = _ccsv("companies_revenue.csv")
    staff = _ccsv("companies_staff.csv")
    staff = staff[staff["scope"] == "Full company"]
    m = _nearest(rev, staff, "staff_count", max_days=365)
    m["rpe"] = m["revenue_usd"] / m["ref_value"]

    subtitle = (f"What it shows: annualised revenue divided by headcount, each revenue "
                f"observation matched to the closest full-company staff figure within "
                f"a year. {len(m)} matched pairs across {m['company'].nunique()} "
                f"companies. Google and Meta are absent: Epoch records no revenue for "
                f"their AI divisions, only headcount.")
    note = (f"Both sides are point observations reported on their own dates, so each "
            f"ratio carries the gap between them - median {int(m['gap_days'].median())} "
            f"days, longest {int(m['gap_days'].max())}. Divisional headcounts are "
            f"excluded because a division's staff against company-wide revenue is not "
            f"a ratio of anything. Revenue is a run rate, so this is revenue per "
            f"employee at an annualised rate, not booked revenue per employee.")

    fig, ax = _cfig(subtitle, note, source=companies_src(["revenue", "staff"]))
    plt.sca(ax)
    _cseries(m, "rpe", connect=True)
    ax.set_yscale("log")
    _decade_ticks(ax.yaxis, m["rpe"], AXIS_FMT["usd"])
    _date_axis(ax, list(m["date"]))
    ax.set_ylabel("Annualised revenue per employee (USD)", fontsize=10)
    ax.set_xlabel("Date of revenue report", fontsize=10)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.grid(axis="x", color=RULE, linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    _clegend(ax)
    _cfinish(fig, ax, "COMPANIES-D02",
             "Revenue per employee has risen roughly a hundredfold at the leaders",
             subtitle, note, ["revenue", "staff"])


def build_c_d03(_r=None):
    """Valuation against the revenue nearest to it."""
    fund = _ccsv("companies_funding.csv")
    fund = fund[fund["closed"] & fund["valuation_usd"].notna()]
    rev = _ccsv("companies_revenue.csv")
    m = _nearest(fund, rev, "revenue_usd", max_days=365)
    m["multiple"] = m["valuation_usd"] / m["ref_value"]

    subtitle = (f"What it shows: post-money valuation divided by the annualised revenue "
                f"recorded nearest to it, so the price of each round is expressed "
                f"against the revenue it was struck on. {len(m)} rounds across "
                f"{m['company'].nunique()} companies where both sides exist within a year.")
    note = (f"A revenue multiple is only as good as the gap between the two dates - "
            f"median {int(m['gap_days'].median())} days here - and at these growth "
            f"rates revenue moves materially inside that gap. Valuations are set by a "
            f"single negotiated round, not a market price. Rounds with no revenue "
            f"observation within a year are dropped rather than matched to a distant one.")

    fig, ax = _cfig(subtitle, note, source=companies_src(["funding", "revenue"]))
    plt.sca(ax)
    _cseries(m, "multiple", connect=True)
    ax.set_yscale("log")
    _decade_ticks(ax.yaxis, m["multiple"], lambda v: f"{v:,.0f}x" if v >= 1 else f"{v:g}x")
    _date_axis(ax, list(m["date"]))
    ax.set_ylabel("Post-money valuation as a multiple of annualised revenue", fontsize=10)
    ax.set_xlabel("Date the round closed", fontsize=10)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.grid(axis="x", color=RULE, linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    _clegend(ax)
    _cfinish(fig, ax, "COMPANIES-D03",
             "Revenue multiples have compressed as revenue caught up with valuations",
             subtitle, note, ["funding", "revenue"])


def build_c_d04(_r=None):
    """Cumulative equity raised, stepped at each closed round."""
    fund = _ccsv("companies_funding.csv")
    fund = fund[fund["closed"] & fund["equity_usd"].notna()].sort_values("date")
    fund["cum"] = fund.groupby("company")["equity_usd"].cumsum()
    totals = fund.groupby("company")["cum"].max().sort_values(ascending=False)

    subtitle = (f"What it shows: equity raised, accumulated round by round, for every "
                f"company Epoch records funding for. {len(fund)} closed rounds across "
                f"{fund['company'].nunique()} companies. The step is the round; the "
                f"height is everything raised to that date.")
    note = ("Closed rounds only - rounds still in discussion and the one cancelled "
            "round are excluded, because announced capital is not raised capital. "
            "Debt is excluded: it is recorded separately by Epoch and is not equity. "
            "Secondary sales appear as flat steps, since they transfer existing shares "
            "between holders and put no new money into the company.")

    fig, ax = _cfig(subtitle, note, source=companies_src(["funding"]))
    for name in totals.index:
        sub = fund[fund["company"] == name]
        ax.step(sub["date"], sub["cum"], where="post", color=_ccolour(name),
                linewidth=1.9, zorder=3,
                label=f"{name}  ({AXIS_FMT['usd'](totals[name])})")
        ax.scatter(sub["date"], sub["cum"], s=26, color=_ccolour(name),
                   edgecolor="white", linewidth=0.7, zorder=4)
    ax.set_yscale("log")
    _decade_ticks(ax.yaxis, fund["cum"], AXIS_FMT["usd"])
    _date_axis(ax, list(fund["date"]))
    ax.set_ylabel("Cumulative equity raised (USD)", fontsize=10)
    ax.set_xlabel("Date the round closed", fontsize=10)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.grid(axis="x", color=RULE, linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    _clegend(ax, title="Company  (total raised)")
    _cfinish(fig, ax, "COMPANIES-D04",
             "Cumulative equity raised, round by round",
             subtitle, note, ["funding"])


def build_c_d05(_r=None):
    """The inference/R&D split, where both sides are recorded for one period."""
    sp = _ccsv("companies_spend.csv")
    # the two sides are usually on separate rows for the same period, so collapse
    # to one row per company-period before pairing them
    per = sp.groupby(["company", "date"], as_index=False).agg(
        inference_usd=("inference_usd", "max"), rnd_usd=("rnd_usd", "max"))
    both = per.dropna(subset=["inference_usd", "rnd_usd"]).copy()
    both["total"] = both["inference_usd"] + both["rnd_usd"]
    both["inf_share"] = both["inference_usd"] / both["total"] * 100
    both = both.sort_values(["date", "company"])
    labels = [f"{r['company']}\n{r['date']:%Y}" for _, r in both.iterrows()]
    idx = list(range(len(both)))

    subtitle = (f"What it shows: cloud compute spend split into training and research "
                f"against serving, for the {len(both)} company-periods where Epoch "
                f"records both sides. This is the split the published figure cannot "
                f"show: its tab plots one amount per row, whichever category the row "
                f"happens to cover.")
    note = ("Only periods recording both an inference and an R&D figure can be split, "
            "which is why so few bars appear - the rest of the compute spend table "
            "gives one side or a combined total. Rows Epoch flags 'exclude from graph "
            "view' are dropped. Inference here is cloud spend on serving, not the cost "
            "of a token, and cannot be divided by token volume without a price.")

    fig, ax = _cfig(subtitle, note, left=0.095, width=0.620, badge_above=True,
                    xlabel_room=0.080, source=companies_src(["spend"]))
    w = 0.56
    ax.bar(idx, both["rnd_usd"] / 1e9, w, color="#1f3864", edgecolor="white",
           linewidth=0.7, label="R&D compute", zorder=3)
    ax.bar(idx, both["inference_usd"] / 1e9, w, bottom=both["rnd_usd"] / 1e9,
           color="#b4763a", edgecolor="white", linewidth=0.7,
           label="Inference compute", zorder=3)
    for i, r in enumerate(both.itertuples()):
        ax.text(i, r.total / 1e9 + 0.35, f"${r.total/1e9:,.1f}bn",
                ha="center", va="bottom", fontsize=9, fontweight="bold", color=INK)
        ax.text(i, r.rnd_usd / 1e9 + r.inference_usd / 2e9,
                f"{r.inf_share:.0f}%", ha="center", va="center", fontsize=8.8,
                color="white", fontweight="bold", zorder=5)
    ax.set_xticks(idx)
    ax.set_xticklabels(labels, fontsize=9.4)
    ax.set_ylabel("Cloud compute spend (US$ billions)", fontsize=10)
    ax.set_xlabel("Company and period", fontsize=10)
    ax.set_xlim(-0.6, len(both) - 0.4)
    ax.set_ylim(0, float(both["total"].max()) / 1e9 * 1.20)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"${v:,.0f}bn"))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h[::-1], l[::-1], loc="upper left", bbox_to_anchor=(1.015, 1.0),
              frameon=False, fontsize=9, title="Category", title_fontsize=9.2,
              borderaxespad=0)
    ax.text(1.015, 0.72, "White figure:  inference\nas a share of the two", 
            transform=ax.transAxes, ha="left", va="top", fontsize=8.3,
            color=MUTED, linespacing=1.55)
    _observed_badge(ax, above=True)
    frame(fig, ax, "COMPANIES-D05",
          "Serving is closing on research as a share of compute spend",
          subtitle, companies_src(["spend"]), COMPANIES_METH, note)
    save(fig, "COMPANIES-D05", COMPANIES_DOMAIN)


def build_c_d06(_r=None):
    """Compute spend against the revenue recorded nearest to it."""
    sp = _ccsv("companies_spend.csv")
    rev = _ccsv("companies_revenue.csv")
    m = _nearest(sp, rev, "revenue_usd", max_days=270)
    m["ratio"] = m["amount_usd"] / m["ref_value"] * 100

    subtitle = (f"What it shows: each recorded compute spend against the annualised "
                f"revenue nearest to it, as a percentage. {len(m)} matched pairs for "
                f"{m['company'].nunique()} companies - the only two for which Epoch "
                f"records compute spend at all.")
    note = ("A spend figure covering one category is being compared with company-wide "
            "revenue, so a bar is a floor on the true ratio wherever the row is not a "
            "combined total. Revenue is an annualised run rate at a point in time and "
            "spend is a period figure, so this is an indicative ratio, not a margin. "
            "It says nothing about total cost: staff, data and non-cloud infrastructure "
            "are outside this table entirely.")

    fig, ax = _cfig(subtitle, note, left=0.095, width=0.620, badge_above=True,
                    xlabel_room=0.080, source=companies_src(["spend", "revenue"]))
    m = m.sort_values(["date", "company"])
    idx = list(range(len(m)))
    for i, r in enumerate(m.itertuples()):
        ax.bar(i, r.ratio, 0.58, color=_ccolour(r.company), edgecolor="white",
               linewidth=0.7, zorder=3)
        ax.text(i, r.ratio + 1.5, f"{r.ratio:.0f}%", ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=INK)
    ax.axhline(100, color=SERIES["scope"], linewidth=1.4, linestyle=(0, (5, 2.5)),
               zorder=4)
    ax.text(len(m) - 0.45, 102, "compute spend equals revenue", ha="right",
            va="bottom", fontsize=8.8, color=SERIES["scope"], style="italic")
    ax.set_xticks(idx)
    ax.set_xticklabels([f"{r.company}\n{r.date:%Y}" for r in m.itertuples()],
                       fontsize=9.2)
    ax.set_ylabel("Compute spend as a share of annualised revenue", fontsize=10)
    ax.set_xlabel("Company and period of the spend figure", fontsize=10)
    ax.set_xlim(-0.6, len(m) - 0.4)
    ax.set_ylim(0, max(float(m["ratio"].max()) * 1.18, 115))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _observed_badge(ax, above=True)
    frame(fig, ax, "COMPANIES-D06",
          "Compute spend against revenue, where both are on the record",
          subtitle, companies_src(["spend", "revenue"]), COMPANIES_METH, note)
    save(fig, "COMPANIES-D06", COMPANIES_DOMAIN)


def build_c_d07(_r=None):
    """What the record actually holds, company by metric."""
    import numpy as np
    cov = _ccsv("companies_coverage.csv")
    grid = cov.pivot(index="company", columns="metric", values="observations")
    metrics = ["Revenue", "Funding rounds", "Valuation", "Staff count",
               "Active users", "Daily tokens", "Compute spend"]
    grid = grid[metrics]
    grid = grid.loc[grid.sum(axis=1).sort_values(ascending=False).index]
    meta = _cmeta()

    filled = int((grid > 0).sum().sum())
    cells = grid.shape[0] * grid.shape[1]
    subtitle = (f"What it shows: how many observations Epoch holds for each company on "
                f"each metric. {filled} of {cells} company-metric cells carry any "
                f"observation at all; the blank cells are why so many of the published "
                f"views plot two or three companies rather than eleven.")
    note = (f"A blank cell is an absence of disclosure, not a zero - the company has "
            f"published nothing Epoch could record, which is not the same as having no "
            f"revenue or no staff. Counts are observations, not companies or dollars, "
            f"and one company disclosing often will outweigh one disclosing once. "
            f"Tracked companies: {int(meta['tracked_companies'])}; "
            f"record observed to {meta['observed_to']}.")

    fig, ax = _cfig(subtitle, note, left=0.135, width=0.600, xlabel_room=0.075,
                    badge_above=True,
                    source=companies_src(["revenue", "funding", "staff", "usage", "spend"]))
    vals = grid.to_numpy(dtype=float)
    shown = np.where(vals > 0, vals, np.nan)
    im = ax.imshow(shown, cmap="Blues", aspect="auto",
                   vmin=0, vmax=float(np.nanmax(shown)))
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = vals[i, j]
            if v > 0:
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=9.4,
                        fontweight="bold",
                        color="white" if v > np.nanmax(shown) * 0.55 else INK)
            else:
                ax.text(j, i, "—", ha="center", va="center", fontsize=9.4,
                        color="#c9ced8")
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics, fontsize=9.2, rotation=22, ha="right")
    ax.set_yticks(range(grid.shape[0]))
    ax.set_yticklabels(grid.index, fontsize=9.4)
    ax.set_xticks([x - 0.5 for x in range(1, len(metrics))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, grid.shape[0])], minor=True)
    ax.grid(which="minor", color="white", linewidth=1.6)
    ax.tick_params(which="minor", length=0)
    ax.grid(which="major", visible=False)
    cb = fig.colorbar(im, ax=ax, fraction=0.028, pad=0.02)
    cb.set_label("Observations recorded", fontsize=9)
    cb.outline.set_visible(False)
    _observed_badge(ax, above=True)
    frame(fig, ax, "COMPANIES-D07",
          "The record is deep on two companies and thin on the other nine",
          subtitle, companies_src(["revenue", "funding", "staff", "usage", "spend"]),
          COMPANIES_METH, note)
    save(fig, "COMPANIES-D07", COMPANIES_DOMAIN)


def build_c_d08(_r=None):
    """Who said it: the provenance of the record itself."""
    import pandas as pd
    frames = {"Revenue": _ccsv("companies_revenue.csv"),
              "Usage": _ccsv("companies_usage.csv"),
              "Staff": _ccsv("companies_staff.csv")}
    order = ["Company disclosure", "Media report", "Other"]
    colour = {"Company disclosure": "#1f3864", "Media report": "#b4763a",
              "Other": "#9aa9c4"}

    def bucket(v):
        v = str(v)
        if v == "nan":
            return "Other"
        if "Company disclosure" in v:
            return "Company disclosure"
        if "Media report" in v:
            return "Media report"
        return "Other"

    rows = []
    for name, df in frames.items():
        b = df["source_type"].map(bucket).value_counts()
        total = int(b.sum())
        rows.append({"dataset": name, "total": total,
                     **{k: int(b.get(k, 0)) for k in order}})
    t = pd.DataFrame(rows)

    disclosed = int(t["Company disclosure"].sum())
    total = int(t["total"].sum())
    subtitle = (f"What it shows: where each observation in the AI Companies record came "
                f"from. {disclosed} of {total} observations across revenue, usage and "
                f"staff are the company's own disclosure; the rest are journalism or "
                f"filings reported at second hand.")
    note = ("This is a chart about the evidence, not about AI. It matters because a "
            "media-reported revenue figure and an audited disclosure carry very "
            "different weight, and the published views plot both as identical dots. "
            "Funding rounds and compute spend are omitted: Epoch does not record a "
            "source type for them in the same form.")

    fig, ax = _cfig(subtitle, note, left=0.115, width=0.620, badge_above=True,
                    xlabel_room=0.068, source=companies_src(["revenue", "usage", "staff"]))
    ys = range(len(t))
    left = [0.0] * len(t)
    for cat in order:
        share = t[cat] / t["total"] * 100
        ax.barh(list(ys), share, 0.56, left=left, color=colour[cat],
                edgecolor="white", linewidth=0.7, label=cat, zorder=3)
        for i, (s, l) in enumerate(zip(share, left)):
            if s >= 8:
                ax.text(l + s / 2, i, f"{s:.0f}%", ha="center", va="center",
                        fontsize=9, color="white", fontweight="bold", zorder=5)
        left = [a + b for a, b in zip(left, share)]
    ax.set_yticks(list(ys))
    ax.set_yticklabels([f"{r.dataset}\n{r.total} obs" for r in t.itertuples()],
                       fontsize=9.6)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of observations in the dataset", fontsize=10)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    h, l = ax.get_legend_handles_labels()
    ax.legend(h, l, loc="upper left", bbox_to_anchor=(1.015, 1.0), frameon=False,
              fontsize=9, title="Source of the figure", title_fontsize=9.2,
              borderaxespad=0)
    _observed_badge(ax, above=True)
    frame(fig, ax, "COMPANIES-D08",
          "Most of the record is the companies' own telling",
          subtitle, companies_src(["revenue", "usage", "staff"]),
          COMPANIES_METH, note)
    save(fig, "COMPANIES-D08", COMPANIES_DOMAIN)


COMPANIES_DERIVED = {
    "COMPANIES-D01": build_c_d01, "COMPANIES-D02": build_c_d02,
    "COMPANIES-D03": build_c_d03, "COMPANIES-D04": build_c_d04,
    "COMPANIES-D05": build_c_d05, "COMPANIES-D06": build_c_d06,
    "COMPANIES-D07": build_c_d07, "COMPANIES-D08": build_c_d08,
}


# ============================================================== AI USAGE (AEI)
# The Anthropic Economic Index publishes one enormous long-format file: a metric
# value per geography per category node. AEI-01 to AEI-10 are the views
# Anthropic's own index and report present; AEI-D01 onward are ours.
AEI_DOMAIN = "ai-usage"
AEI_DATA = REPO / AEI_DOMAIN / "data"
AEI_FILE = "aei_claude_ai_2026-06-26.csv"
AEI_METH = ("Methodology reference pending final methodology document; derivation "
            "follows Anthropic's published Economic Index data documentation")


def aei_src():
    return (f"Anthropic Economic Index (CC-BY) — {AEI_FILE} — "
            f"huggingface.co/datasets/Anthropic/EconomicIndex")


def _acsv(name):
    import pandas as pd
    return pd.read_csv(AEI_DATA / name)


def _ameta():
    return _acsv("aei_summary.csv").iloc[0]


def _aei_badge(ax, above=False):
    """The scope limit that governs every reading of this dataset."""
    y, va = (1.030, "bottom") if above else (0.955, "top")
    ax.text(0.0 if above else 0.017, y,
            "  ONE PROVIDER'S OWN TRAFFIC  ·  not a market measure  ",
            transform=ax.transAxes, ha="left", va=va, fontsize=9.1,
            fontweight="bold", color="white", zorder=9, clip_on=False,
            bbox=dict(boxstyle="round,pad=0.42", facecolor=SERIES["current"],
                      edgecolor="none"))


def _afig(subtitle, note, left=0.300, width=0.560, xlabel_room=0.055,
          figsize=(12.0, 8.4), badge_above=True):
    fig = plt.figure(figsize=figsize)
    ax = fig.add_axes(_rect(subtitle, note, left=left, width=width,
                            xlabel_room=xlabel_room, badge_above=badge_above,
                            source=aei_src()))
    return fig, ax


def _afinish(fig, ax, plot_id, title, subtitle, note, badge_above=True):
    _aei_badge(ax, above=badge_above)
    frame(fig, ax, plot_id, title, subtitle, aei_src(), AEI_METH, note)
    save(fig, plot_id, AEI_DOMAIN)


AEI_SCOPE = ("Claude.ai covers the Free, Pro and Max consumer plans plus Cowork; "
             "Anthropic's API traffic is a separate file and is not included here.")
AEI_ABSENT = ("A cell Anthropic did not publish is absent, not zero: a value is "
              "released only where it clears an aggregation threshold and a "
              "geography sample floor.")


def _abar(ax, labels, values, colours=None, fmt="{v:.1f}%", pad=None,
          headroom=1.16, height=0.72, min_slots=0):
    """Ranked horizontal bars, highest at the top, labelled at the tip."""
    ys = list(range(len(labels)))
    colours = colours or [SERIES["current"]] * len(labels)
    ax.barh(ys, values, height=height, color=colours, edgecolor="white",
            linewidth=0.6, zorder=3)
    span = max(values) if len(values) else 1
    pad = pad if pad is not None else span * 0.014
    for y, v in zip(ys, values):
        ax.text(v + pad, y, fmt.format(v=v), va="center", fontsize=9,
                color=INK, zorder=4)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=9.4)
    ax.invert_yaxis()
    # two or three categories across a full-height axis give absurdly thick
    # bars; padding the y range keeps the canvas and thins the bars instead
    if min_slots and len(labels) < min_slots:
        mid = (len(labels) - 1) / 2
        ax.set_ylim(mid + min_slots / 2, mid - min_slots / 2)
    ax.set_xlim(0, span * headroom)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)


# ---- the ranked views, one config each ------------------------------------
AEI_RANK = {
    "AEI-01": dict(table="aei_countries.csv", label="country", col="usage_per_capita_index",
                   top=20, fmt="{v:.2f}", left=0.235,
                   title="Anthropic AI Usage Index, by country",
                   xlabel="Usage share divided by working-age population share",
                   what="Anthropic's own headline geographic measure: a country's share of "
                        "Claude usage divided by its share of the world's working-age "
                        "(15-64) population. 1.0 means usage exactly proportional to "
                        "population; above 1.0 means Claude is used more than population "
                        "alone would predict.",
                   note="An index above 1.0 is not a statement about a country's AI "
                        "adoption at large - it is Claude usage per working-age person "
                        "relative to the world. Small, rich, English-speaking economies "
                        "index highest, which is what one provider's consumer product "
                        "reaching a wealthy early-adopter population looks like."),
    "AEI-02": dict(table="aei_countries.csv", label="country", col="usage_pct",
                   top=20, fmt="{v:.2f}%", left=0.235,
                   title="Share of Claude usage, by country",
                   xlabel="Share of global Claude conversations",
                   what="Where Claude conversations actually come from, as a share of the "
                        "global total. This is the raw volume view that the usage index "
                        "normalises by population.",
                   note="Volume follows population and market presence, so this ranking "
                        "and the per-capita index answer different questions and should "
                        "not be read as competing."),
    "AEI-03": dict(table="aei_us_states.csv", label="geo_id", col="usage_per_capita_index",
                   top=20, fmt="{v:.2f}", left=0.175,
                   title="Anthropic AI Usage Index, by US state",
                   xlabel="Usage share divided by working-age population share",
                   what="The same index inside the United States, the only country for "
                        "which Anthropic publishes it at subregion level.",
                   note="The District of Columbia sits far above every state, which is "
                        "what a single dense federal-and-professional labour market looks "
                        "like when measured per head of population."),
    "AEI-07": dict(table="aei_request_major.csv", label="node_name", col="pct",
                   top=15, fmt="{v:.1f}%", left=0.315,
                   title="What people ask Claude for, by topic",
                   xlabel="Share of Claude conversations",
                   what="Anthropic's request taxonomy at its major-topic grain: what the "
                        "conversation was actually about.",
                   note="Shares are of classified conversations and do not total 100% "
                        "because the long tail of minor topics is not shown."),
    "AEI-08": dict(table="aei_soc_major.csv", label="node_name", col="pct",
                   top=15, fmt="{v:.1f}%", left=0.345,
                   title="Claude usage mapped to occupation groups",
                   xlabel="Share of Claude conversations",
                   what="Conversations mapped onto the US Bureau of Labor Statistics "
                        "Standard Occupational Classification, at major-group level.",
                   note="This is the occupational character of the work in the "
                        "conversation, not the occupation of the person typing. A "
                        "teacher drafting a spreadsheet formula appears under Computer "
                        "and Mathematical."),
    "AEI-09": dict(table="aei_onet_gwa.csv", label="node_name", col="pct",
                   top=15, fmt="{v:.1f}%", left=0.375,
                   title="Claude usage mapped to work activities",
                   xlabel="Share of Claude conversations",
                   what="Conversations mapped onto O*NET Generalized Work Activities - "
                        "the US Department of Labor's vocabulary for what work consists of.",
                   note="Advice, information-gathering and creative thinking dominate, "
                        "which is the signature of a conversational assistant rather than "
                        "of an autonomous worker."),
    "AEI-10": dict(table="aei_artifacts.csv", label="artifact", col="value",
                   top=16, fmt="{v:.1f}%", left=0.315,
                   title="What Claude actually produced",
                   xlabel="Share of Claude conversations",
                   what="The most prominent concrete output of each conversation, across "
                        "Anthropic's 32 artifact labels.",
                   note="'None' is a real category and a large one: a substantial share of "
                        "conversations produce no artifact at all, which is a conversation "
                        "rather than a piece of work."),
}


def build_aei_rank(plot_id):
    cfg = AEI_RANK[plot_id]
    t = _acsv(cfg["table"]).dropna(subset=[cfg["col"]])
    t = t.sort_values(cfg["col"], ascending=False).head(cfg["top"])
    meta = _ameta()
    total = len(_acsv(cfg["table"]).dropna(subset=[cfg["col"]]))

    subtitle = (f"What it shows: {cfg['what']} {cfg['top']} of {total} shown, "
                f"{meta['period_last'][:7]} data.")
    note = f"{cfg['note']} {AEI_SCOPE} {AEI_ABSENT}"

    fig, ax = _afig(subtitle, note, left=cfg["left"], width=0.955 - cfg["left"] - 0.10)
    labels = [_clip(str(x), 46) for x in t[cfg["label"]]]
    _abar(ax, labels, list(t[cfg["col"]]), fmt=cfg["fmt"])
    ax.set_xlabel(cfg["xlabel"], fontsize=10)
    if cfg["col"] == "usage_per_capita_index":
        ax.axvline(1.0, color=SERIES["scope"], linewidth=1.4,
                   linestyle=(0, (5, 2.5)), zorder=4)
        ax.text(1.0, len(labels) - 0.35, "  1.0 = proportional to population",
                fontsize=8.8, color=SERIES["scope"], style="italic", va="top")
    _afinish(fig, ax, plot_id, cfg["title"], subtitle, note)


# ---- the headline splits, read off the overall row ------------------------
# Automation against augmentation was published here as AEI-05 and withdrawn: two
# bars at 51.4 and 48.6 are two numbers rather than a chart, and AEI-D01 carries
# the same measure at the grain where it actually varies, by 29 points.
AEI_MIX = {
    "AEI-04": dict(prefix="use_case_", strip="_pct",
                   title="Work, personal and study use of Claude",
                   xlabel="Share of Claude conversations",
                   what="Anthropic's own classification of what each conversation was "
                        "for. This is the split that decides whether a usage figure "
                        "belongs in an enterprise demand estimate at all.",
                   note="Only the work share is a candidate for an enterprise measure; "
                        "personal and coursework use is real traffic but not commercial "
                        "workload. The three are mutually exclusive and total 100%."),
    "AEI-06": dict(prefix="collaboration_", strip="_pct", exclude=("bucket",),
                   title="How people work with Claude",
                   xlabel="Share of Claude conversations",
                   what="The interaction pattern underneath the automation split: "
                        "directive requests, back-and-forth iteration, learning, "
                        "validation and feedback loops.",
                   note="Directive and task-iteration together account for most "
                        "conversations - one-shot instructions and refinement loops, "
                        "rather than the model being supervised or checked."),
}


def build_aei_mix(plot_id):
    cfg = AEI_MIX[plot_id]
    o = _acsv("aei_overall.csv")
    meta = _ameta()
    last, first = meta["period_last"], meta["period_first"]
    rows = o[o.metric_id.str.startswith(cfg["prefix"])]
    for bad in cfg.get("exclude", ()):
        rows = rows[~rows.metric_id.str.contains(bad)]
    rows = rows.sort_values(last, ascending=False)
    labels = [m[len(cfg["prefix"]):-len(cfg["strip"])].replace("_", " ").capitalize()
              for m in rows.metric_id]

    subtitle = (f"What it shows: {cfg['what']} {meta['period_last'][:7]} data, "
                f"with the change since {first[:7]} marked.")
    note = f"{cfg['note']} {AEI_SCOPE} {AEI_ABSENT}"

    fig, ax = _afig(subtitle, note, left=0.235, width=0.620)
    vals = list(rows[last])
    _abar(ax, labels, vals, fmt="{v:.1f}%", headroom=1.34, min_slots=7)
    # the only movement the release supports: two consecutive months, set clear
    # of the value label rather than running into it
    for y, (_, r) in enumerate(rows.iterrows()):
        d = r["delta"]
        if abs(d) >= 0.05:
            ax.text(r[last] + max(vals) * 0.165, y,
                    f"({d:+.1f} pt vs {first[:7]})", va="center", fontsize=8.4,
                    color=SERIES["scope"] if d > 0 else MUTED, style="italic")
    ax.set_xlabel(cfg["xlabel"], fontsize=10)
    _afinish(fig, ax, plot_id, cfg["title"], subtitle, note)


# ------------------------------------------------ Derived analysis (same file)
def build_aei_d01(_r=None):
    """Which kinds of work Claude does for you, rather than with you."""
    t = _acsv("aei_soc_major.csv").dropna(
        subset=["collaboration_bucket_automation_pct", "pct"])
    t = t[t["pct"] >= 1.0].sort_values("collaboration_bucket_automation_pct",
                                       ascending=False)
    o = _acsv("aei_overall.csv")
    last = _ameta()["period_last"]
    base = float(o[o.metric_id == "collaboration_bucket_automation_pct"][last].iloc[0])

    subtitle = (f"What it shows: the automation share within each occupation group, "
                f"against the {base:.1f}% global average. The published split is a single "
                f"number for all of Claude; this is the same measure held at the grain "
                f"where it varies. {len(t)} groups shown, each with at least 1% of "
                f"conversations.")
    hi_n = t.iloc[0]["node_name"]
    lo_n = t.iloc[-1]["node_name"]
    note = (f"Deviation from the global average, in percentage points. {hi_n} work is the "
            f"most automated and {lo_n} the least, which is the shape of a model that is "
            f"strong at bounded technical tasks and used as a collaborator where judgement "
            f"and voice carry the work. Automation is a property of the conversation, not "
            f"evidence of a job displaced. {AEI_SCOPE}")

    fig, ax = _afig(subtitle, note, left=0.345, width=0.560, badge_above=True)
    ys = range(len(t))
    devs = [v - base for v in t["collaboration_bucket_automation_pct"]]
    colours = [SERIES["current"] if d >= 0 else SERIES["scope"] for d in devs]
    ax.barh(list(ys), devs, height=0.72, color=colours, edgecolor="white",
            linewidth=0.6, zorder=3)
    lim = max(abs(min(devs)), abs(max(devs))) * 1.30
    for y, (d, v) in enumerate(zip(devs, t["collaboration_bucket_automation_pct"])):
        ax.text(d + (lim * 0.018 if d >= 0 else -lim * 0.018), y, f"{v:.0f}%",
                va="center", ha="left" if d >= 0 else "right", fontsize=9, color=INK)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([_clip(x, 44) for x in t["node_name"]], fontsize=9.4)
    ax.invert_yaxis()
    ax.axvline(0, color=INK, linewidth=1.1, zorder=4)
    ax.set_xlim(-lim, lim)
    ax.set_xlabel(f"Automation share relative to the {base:.1f}% global average "
                  f"(percentage points)", fontsize=10)
    ax.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _p: "0" if abs(v) < 1e-9 else f"{v:+.0f}"))
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    spread = (float(t["collaboration_bucket_automation_pct"].max())
              - float(t["collaboration_bucket_automation_pct"].min()))
    _afinish(fig, ax, "AEI-D01",
             f"The even global split hides a {spread:.0f}-point spread across occupations",
             subtitle, note)


def build_aei_d02(_r=None):
    """The time claim, with both sides converted to the same unit."""
    t = _acsv("aei_soc_major.csv").dropna(subset=["time_ratio", "pct"])
    t = t[t["pct"] >= 1.0].sort_values("time_ratio", ascending=False)

    subtitle = ("What it shows: Anthropic's two time estimates side by side - how long a "
                "task would take a person alone, against how long it takes with Claude - "
                "for each occupation group. The published file gives the first in hours "
                "and the second in minutes; both are converted to minutes here.")
    note = ("The unit difference is the trap in this dataset: read raw, the two columns "
            "appear to show tasks taking longer with AI. Both are Anthropic's own "
            "model-generated estimates of a hypothetical unaided task, not measurements "
            "of anyone actually working, so the ratio is a property of the classifier as "
            f"much as of the work. {AEI_SCOPE}")

    fig, ax = _afig(subtitle, note, left=0.345, width=0.500, badge_above=True)
    ys = list(range(len(t)))
    h = 0.36
    ax.barh([y - h/2 for y in ys], t["human_only_minutes"], height=h,
            color=SERIES["prior"], edgecolor="white", linewidth=0.5,
            label="Without AI (estimated)", zorder=3)
    ax.barh([y + h/2 for y in ys], t["human_with_ai_minutes"], height=h,
            color=SERIES["current"], edgecolor="white", linewidth=0.5,
            label="With Claude (estimated)", zorder=3)
    top = float(t["human_only_minutes"].max())
    for y, r in zip(ys, t.itertuples()):
        ax.text(r.human_only_minutes + top * 0.012, y - h/2,
                f"{r.human_only_minutes/60:.1f}h", va="center", fontsize=8.4, color=MUTED)
        ax.text(r.human_with_ai_minutes + top * 0.012, y + h/2,
                f"{r.human_with_ai_minutes:.0f}m", va="center", fontsize=8.4, color=INK)
        ax.text(top * 1.30, y, f"{r.time_ratio:.1f}x", va="center", fontsize=9,
                fontweight="bold", color=SERIES["scope"])
    ax.text(top * 1.30, -0.85, "ratio", fontsize=8.6, color=SERIES["scope"],
            style="italic", va="center")
    ax.set_yticks(ys)
    ax.set_yticklabels([_clip(x, 44) for x in t["node_name"]], fontsize=9.4)
    ax.invert_yaxis()
    ax.set_xlim(0, top * 1.42)
    ax.set_xlabel("Estimated task time (minutes)", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    # kept left of the ratio column rather than on top of it
    ax.legend(loc="lower right", bbox_to_anchor=(0.87, 0.01), frameon=False, fontsize=9)
    lo, hi = float(t["time_ratio"].min()), float(t["time_ratio"].max())
    _afinish(fig, ax, "AEI-D02",
             f"Estimated time falls {lo:.0f}- to {hi:.0f}-fold, on Anthropic's own numbers",
             subtitle, note)




def build_aei_d05(_r=None):
    """Volume against intensity, which the published views never cross."""
    t = _acsv("aei_countries.csv").dropna(subset=["usage_pct", "usage_per_capita_index"])

    subtitle = (f"What it shows: each country's share of Claude conversations against its "
                f"usage per working-age person. The index published on its own hides that "
                f"the highest-indexing countries are small; the volume ranking on its own "
                f"hides that the largest are not the most intensive. {len(t)} countries.")
    note = ("Both axes are log-scaled: shares span three orders of magnitude and the index "
            "two. A country high and to the left is small but intensive; low and to the "
            "right is large but thin. The United States is the only country that is both "
            f"large and well above proportional. {AEI_SCOPE} {AEI_ABSENT}")

    fig, ax = _afig(subtitle, note, left=0.085, width=0.640, xlabel_room=0.058,
                    badge_above=True)
    ax.scatter(t["usage_pct"], t["usage_per_capita_index"], s=34,
               color=SERIES["current"], alpha=0.62, edgecolor="white",
               linewidth=0.6, zorder=3)
    show = (set(t.nlargest(6, "usage_pct").geo_id)
            | set(t.nlargest(6, "usage_per_capita_index").geo_id))
    # the labelled countries cluster tightly at the top right, so labels are
    # alternated above and below the marker rather than stacked on each other
    labelled = t[t.geo_id.isin(show)].sort_values("usage_pct")
    offsets = [(0, 10), (0, -18), (0, 23)]
    for i, r in enumerate(labelled.itertuples()):
        dx, dy = offsets[i % len(offsets)]
        ax.annotate(r.country, (r.usage_pct, r.usage_per_capita_index),
                    textcoords="offset points", xytext=(dx, dy), ha="center",
                    va="bottom" if dy > 0 else "top", fontsize=8.2, color=INK)
    ax.set_xscale("log"); ax.set_yscale("log")
    _decade_ticks(ax.xaxis, t["usage_pct"], lambda v: f"{v:g}%")
    _decade_ticks(ax.yaxis, t["usage_per_capita_index"], lambda v: f"{v:g}")
    ax.axhline(1.0, color=SERIES["scope"], linewidth=1.3, linestyle=(0, (5, 2.5)), zorder=2)
    ax.text(float(t["usage_pct"].min()), 1.05, " proportional to population",
            fontsize=8.6, color=SERIES["scope"], style="italic", va="bottom")
    ax.set_xlabel("Share of global Claude conversations", fontsize=10)
    ax.set_ylabel("Usage per working-age person (index, 1.0 = proportional)", fontsize=10)
    ax.grid(color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    _afinish(fig, ax, "AEI-D05",
             "Big markets and intensive ones are mostly different countries",
             subtitle, note, badge_above=True)


def build_aei_d06(_r=None):
    """What the release actually contains, before anyone reads a number off it."""
    import numpy as np
    cov = _acsv("aei_coverage.csv")
    meta = _ameta()
    grid = cov.pivot_table(index="category_name", columns="geo_level",
                           values="rows", aggfunc="sum").fillna(0)
    grid = grid[[c for c in ("global", "country", "subregion") if c in grid.columns]]
    grid = grid.loc[grid.sum(axis=1).sort_values(ascending=False).index]

    subtitle = (f"What it shows: how the {int(meta['rows']):,} published rows are "
                f"distributed across the four category hierarchies and three geographic "
                f"levels. {int(meta['metrics'])} distinct metrics, "
                f"{int(meta['countries'])} countries and {int(meta['subregions'])} "
                f"subregions, over {int(meta['periods'])} months.")
    note = ("Depth is very unevenly distributed, and that governs which charts are "
            "possible: everything is available globally, only shares are published for "
            "most country and subregion breakdowns, and the usage index reaches "
            f"subregion level for US states alone ({int(meta['us_states_with_index'])} of "
            f"them). {AEI_ABSENT} {AEI_SCOPE}")

    fig, ax = _afig(subtitle, note, left=0.215, width=0.560, xlabel_room=0.070,
                    badge_above=True)
    vals = grid.to_numpy(dtype=float)
    shown = np.where(vals > 0, vals, np.nan)
    im = ax.imshow(shown, cmap="Blues", aspect="auto", vmin=0, vmax=float(np.nanmax(shown)))
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = vals[i, j]
            if v > 0:
                ax.text(j, i, f"{int(v):,}", ha="center", va="center", fontsize=9.4,
                        fontweight="bold",
                        color="white" if v > np.nanmax(shown) * 0.55 else INK)
            else:
                ax.text(j, i, "—", ha="center", va="center", fontsize=9.4, color="#c9ced8")
    ax.set_xticks(range(grid.shape[1]))
    ax.set_xticklabels([c.capitalize() for c in grid.columns], fontsize=9.6)
    ax.set_yticks(range(grid.shape[0]))
    ax.set_yticklabels(grid.index, fontsize=9.6)
    ax.set_xticks([x - 0.5 for x in range(1, grid.shape[1])], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, grid.shape[0])], minor=True)
    ax.grid(which="minor", color="white", linewidth=1.6)
    ax.tick_params(which="minor", length=0)
    ax.grid(which="major", visible=False)
    ax.set_xlabel("Geographic level", fontsize=10)
    cb = fig.colorbar(im, ax=ax, fraction=0.030, pad=0.02)
    cb.set_label("Published rows", fontsize=9)
    cb.outline.set_visible(False)
    _afinish(fig, ax, "AEI-D06",
             "Everything globally, shares only almost everywhere else", subtitle, note)


# AEI-D03 (autonomy against required education) and AEI-D04 (month-on-month
# movement) were published and withdrawn. D03 plotted an autonomy range of 0.34
# on a 1-5 scale, which is noise presented as a relationship; D04 plotted 46
# metrics of which 44 moved by less than a point, median 0.07. Neither is
# rebuildable on purpose.
AEI_DERIVED = {
    "AEI-D01": build_aei_d01, "AEI-D02": build_aei_d02,
    "AEI-D05": build_aei_d05, "AEI-D06": build_aei_d06,
}


# --------------------------------------------------- Enterprise API (1P) file
AEI_API_FILE = "aei_1p_api_2026-06-26.csv"
AEI_API_SCOPE = ("The 1P API file is Anthropic's own API traffic excluding Claude Code, "
                 "published globally with no geographic breakdown. It is a different "
                 "population from Claude.ai and the two are never pooled.")


def aei_api_src(both=False):
    files = f"{AEI_API_FILE} + {AEI_FILE}" if both else AEI_API_FILE
    return (f"Anthropic Economic Index (CC-BY) — {files} — "
            f"huggingface.co/datasets/Anthropic/EconomicIndex")


def _api_badge(ax, above=True):
    y, va = (1.030, "bottom") if above else (0.955, "top")
    ax.text(0.0 if above else 0.017, y,
            "  ENTERPRISE API TRAFFIC  ·  not consumer conversation  ",
            transform=ax.transAxes, ha="left", va=va, fontsize=9.1,
            fontweight="bold", color="white", zorder=9, clip_on=False,
            bbox=dict(boxstyle="round,pad=0.42", facecolor="#6b8f71",
                      edgecolor="none"))


AEI_API_RANK = {
    "AEI-11": dict(table="aei_api_soc_major.csv", label="node_name", col="pct",
                   top=15, left=0.345,
                   title="API usage mapped to occupation groups",
                   xlabel="Share of API conversations",
                   what="what enterprise API traffic is doing, mapped onto the US "
                        "Bureau of Labor Statistics occupational classification. This "
                        "is the sector view of paid, programmatic usage rather than of "
                        "consumer chat.",
                   note="Computer and Mathematical work is the largest single group and "
                        "Office and Administrative Support runs well above its consumer "
                        "share, which is what back-office automation looks like when it "
                        "is bought rather than chatted with."),
    "AEI-12": dict(table="aei_api_request_major.csv", label="node_name", col="pct",
                   top=15, left=0.315,
                   title="What API traffic is asked to do",
                   xlabel="Share of API conversations",
                   what="the request topics behind enterprise API calls.",
                   note="Document processing and business-process work lead here and "
                        "barely register on the consumer side, where content creation "
                        "and learning dominate. The API is bought to run pipelines."),
}


def build_aei_api_rank(plot_id):
    cfg = AEI_API_RANK[plot_id]
    full = _acsv(cfg["table"]).dropna(subset=[cfg["col"]])
    t = full.sort_values(cfg["col"], ascending=False).head(cfg["top"])
    meta = _ameta()

    subtitle = (f"What it shows: {cfg['what']} {len(t)} of {len(full)} shown, "
                f"{meta['period_last'][:7]} data.")
    note = f"{cfg['note']} {AEI_API_SCOPE} {AEI_ABSENT}"

    fig, ax = _cfig(subtitle, note, left=cfg["left"], width=0.955 - cfg["left"] - 0.10,
                    badge_above=True, source=aei_api_src())
    _abar(ax, [_clip(str(x), 46) for x in t[cfg["label"]]], list(t[cfg["col"]]),
          colours=["#6b8f71"] * len(t), fmt="{v:.1f}%")
    ax.set_xlabel(cfg["xlabel"], fontsize=10)
    _api_badge(ax, above=True)
    frame(fig, ax, plot_id, cfg["title"], subtitle, aei_api_src(), AEI_METH, note)
    save(fig, plot_id, AEI_DOMAIN)


# ------------------------------- the pair, which is what the two files are for
API_COL, CAI_COL = "#6b8f71", "#1f3864"


def _paired(plot_id, dimension, title, headline, what, note_extra, top=12,
            left=0.335, fmt="{v:.1f}%", label_clip=44):
    """One horizontal pair per node: API against Claude.ai, biggest gaps first."""
    c = _acsv("aei_compare.csv")
    d = c[c.dimension == dimension].copy()
    d["gap"] = d["diff"].abs()
    d = d.sort_values("gap", ascending=False).head(top).sort_values("diff")
    meta = _ameta()

    subtitle = (f"What it shows: {what} The {len(d)} largest gaps of "
                f"{int((c.dimension == dimension).sum())} shared categories, "
                f"{meta['period_last'][:7]} data.")
    # AEI_API_SCOPE already states that the two are never pooled, so this only
    # adds what the pairing does: sets them side by side, never combines them
    note = (f"{note_extra} The chart sets the two files side by side and does not "
            f"combine them. {AEI_API_SCOPE} {AEI_ABSENT}")

    fig, ax = _cfig(subtitle, note, left=left, width=0.955 - left - 0.135,
                    badge_above=True, source=aei_api_src(both=True))
    ys = list(range(len(d)))
    h = 0.36
    ax.barh([y - h / 2 for y in ys], d["api"], height=h, color=API_COL,
            edgecolor="white", linewidth=0.5, label="1P API", zorder=3)
    ax.barh([y + h / 2 for y in ys], d["claude_ai"], height=h, color=CAI_COL,
            edgecolor="white", linewidth=0.5, label="Claude.ai", zorder=3)
    hi = float(max(d["api"].max(), d["claude_ai"].max()))
    for y, r in zip(ys, d.itertuples()):
        ax.text(r.api + hi * 0.012, y - h / 2, fmt.format(v=r.api), va="center",
                fontsize=8.4, color=INK)
        ax.text(r.claude_ai + hi * 0.012, y + h / 2, fmt.format(v=r.claude_ai),
                va="center", fontsize=8.4, color=INK)
        ax.text(hi * 1.30, y, f"{r.diff:+.0f}", va="center", ha="center", fontsize=9,
                fontweight="bold", color=API_COL if r.diff > 0 else CAI_COL)
    ax.text(hi * 1.30, -0.9, "gap (pt)", fontsize=8.4, color=MUTED, style="italic",
            ha="center", va="center")
    ax.set_yticks(ys)
    ax.set_yticklabels([_clip(str(x), label_clip) for x in d["node"]], fontsize=9.4)
    ax.invert_yaxis()
    ax.set_xlim(0, hi * 1.40)
    ax.set_xlabel("Share of conversations in that file", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", bbox_to_anchor=(0.88, 0.01), frameon=False, fontsize=9)
    _api_badge(ax, above=True)
    frame(fig, ax, plot_id, headline, subtitle, aei_api_src(both=True), AEI_METH, note)
    save(fig, plot_id, AEI_DOMAIN)


def build_aei_d07(_r=None):
    """The headline difference between the two populations."""
    c = _acsv("aei_compare.csv")
    d = c[c.dimension == "overall"].copy()
    # shares only, and behaviour rather than output: the means in years, hours
    # and index points share no axis with a percentage, and the artifact split
    # is its own dimension rather than a measure of how the model was used
    keep = [n for n in d.node if n.endswith("_pct")
            and n != "usage_pct" and not n.startswith("artifact_")]
    d = d[d.node.isin(keep)].copy()
    d["gap"] = d["diff"].abs()
    d = d.sort_values("gap", ascending=False).head(10).sort_values("diff")
    meta = _ameta()

    subtitle = ("What it shows: the same measures over Anthropic's two published "
                "populations — programmatic API traffic against consumer Claude.ai. "
                "These are the ten largest gaps, and they are not small: the API is "
                "automated, directive and almost entirely work, where the consumer "
                "product is collaborative, iterative and half personal.")
    note = ("This is the chart that decides whether a Claude.ai figure may stand in "
            "for enterprise behaviour. It may not. Automation runs 94% on the API "
            "against 49% on Claude.ai, and directive single-shot requests 83% against "
            "31%. Anything estimated from consumer conversation and applied to "
            f"enterprise workloads inherits that gap. {AEI_API_SCOPE}")

    fig, ax = _cfig(subtitle, note, left=0.335, width=0.485, badge_above=True,
                    source=aei_api_src(both=True))
    ys = list(range(len(d)))
    h = 0.36
    ax.barh([y - h / 2 for y in ys], d["api"], height=h, color=API_COL,
            edgecolor="white", linewidth=0.5, label="1P API", zorder=3)
    ax.barh([y + h / 2 for y in ys], d["claude_ai"], height=h, color=CAI_COL,
            edgecolor="white", linewidth=0.5, label="Claude.ai", zorder=3)
    for y, r in zip(ys, d.itertuples()):
        ax.text(r.api + 1.2, y - h / 2, f"{r.api:.0f}%", va="center", fontsize=8.6, color=INK)
        ax.text(r.claude_ai + 1.2, y + h / 2, f"{r.claude_ai:.0f}%", va="center",
                fontsize=8.6, color=INK)
        ax.text(126, y, f"{r.diff:+.0f}", va="center", ha="center", fontsize=9.2,
                fontweight="bold", color=API_COL if r.diff > 0 else CAI_COL)
    ax.text(126, -0.9, "gap (pt)", fontsize=8.4, color=MUTED, style="italic",
            ha="center", va="center")
    pretty = {"collaboration_bucket_automation_pct": "Automation",
              "collaboration_bucket_augmentation_pct": "Augmentation",
              "collaboration_directive_pct": "Directive requests",
              "collaboration_task_iteration_pct": "Task iteration",
              "collaboration_learning_pct": "Learning",
              "collaboration_feedback_loop_pct": "Feedback loop",
              "collaboration_validation_pct": "Validation",
              "collaboration_none_pct": "No collaboration",
              "use_case_work_pct": "Used for work",
              "use_case_personal_pct": "Used personally",
              "use_case_coursework_pct": "Used for coursework",
              "multitasking_pct": "More than one task",
              "human_only_ability_pct": "A human could do it unaided"}
    ax.set_yticks(ys)
    ax.set_yticklabels([pretty.get(n, n.replace("_", " ")) for n in d["node"]], fontsize=9.6)
    ax.invert_yaxis()
    ax.set_xlim(0, 138)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_xlabel("Share of conversations in that file", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    # top rows are short bars, so the key sits clear of every label
    ax.legend(loc="upper right", bbox_to_anchor=(0.82, 0.99), frameon=False, fontsize=9)
    _api_badge(ax, above=True)
    frame(fig, ax, "AEI-D07",
          "API traffic is automated and directive; consumer traffic is neither",
          subtitle, aei_api_src(both=True), AEI_METH, note)
    save(fig, "AEI-D07", AEI_DOMAIN)


def build_aei_d08(_r=None):
    _paired("AEI-D08", "onet_gwa",
            "What kind of work each population is doing",
            "The API processes information; people ask Claude.ai for advice",
            "the O*NET work activities where the two files diverge most.",
            "Providing Consultation and Advice is the single largest activity on "
            "Claude.ai and almost absent from the API, which instead processes and "
            "analyses information. That is the clearest statement in the dataset of "
            "what changes when a model is called by software rather than typed at.",
            left=0.375, label_clip=42)


def build_aei_d09(_r=None):
    _paired("AEI-D09", "request",
            "What each population asks for",
            "Enterprises buy document processing; people ask for content",
            "the request topics where the two files diverge most.",
            "Document processing, business process work and data analysis lead the "
            "API and barely register on Claude.ai, where content creation, learning "
            "and hobbies dominate. The same model, bought two different ways.",
            left=0.335, label_clip=40)


AEI_API_DERIVED = {
    "AEI-D07": build_aei_d07, "AEI-D08": build_aei_d08, "AEI-D09": build_aei_d09,
}


# ------------------------------- merged small-multiples, replacing four figures
# Epoch's figure takes the metric as a control. Publishing one chart per metric
# gave four scatters that share an x axis, a colour and a caption and differ only
# in the y column. They are one figure with one panel per metric here, and the
# interactive companion carries the selector Epoch actually offers.
MODELS_PANELS = {
    "MODELS-08": dict(
        x="publication_date", xlabel="Publication date",
        title="What else went into training, over time",
        headline="Every input grows, none as fast as compute",
        metrics=[("parameters", "Parameters", "count"),
                 ("training_dataset_size", "Training dataset (datapoints)", "count"),
                 ("training_cost_2023usd", "Training cost (2023 USD)", "usd"),
                 ("training_time_days", "Training time (days)", "days")],
        what="the other three quantities Epoch records against publication date, "
             "beside the parameter count. One panel per metric, on the axes the "
             "published figure uses for each.",
        note="Coverage differs sharply by metric and each panel states its own n: "
             "Epoch records parameters for 714 of the 1,043 notable models and cost "
             "for 180. A model missing the value is absent from that panel, never "
             "imputed. Growth rates differ too, which is the point of seeing them "
             "together - MODELS-D01 fits and compares them directly."),
    "MODELS-13": dict(
        x="training_compute_flop", xlabel="Training compute (FLOP)",
        title="What training compute buys",
        headline="Compute explains part of every other input, and all of none",
        metrics=[("parameters", "Parameters", "count"),
                 ("hardware_quantity", "Accelerators used", "count"),
                 ("training_cost_2023usd", "Training cost (2023 USD)", "usd")],
        what="the three quantities Epoch records against training compute rather "
             "than against time. Both axes are log-scaled on every panel.",
        note="Each panel is the subset recording both values, so the counts fall well "
             "below the 1,043 in the release and differ panel to panel. A relationship "
             "here is association within one published record, not a cost model: "
             "spend at any given compute level spans three orders of magnitude."),
}


def build_models_panels(plot_id):
    import pandas as pd
    cfg = MODELS_PANELS[plot_id]
    df = _mpoints("notable")
    logx = cfg["x"] != "publication_date"
    n_panels = len(cfg["metrics"])
    cols = 2 if n_panels == 4 else n_panels
    rows = (n_panels + cols - 1) // cols
    total = int(_msummary("notable")["models"])

    subtitle = (f"What it shows: {cfg['what']} Notable AI models, {total:,} in the "
                f"release; each panel plots only the models recording both of its "
                f"values.")
    note = cfg["note"]

    fig = plt.figure(figsize=(12.0, 8.6 if rows > 1 else 6.8))
    l, b, w, h = _rect(subtitle, note, left=0.072, width=0.905, xlabel_room=0.060,
                       badge_above=True, source=models_src("notable"))
    # every panel carries its own title, so the badge goes above all of them
    fig.text(l, b + h + 0.050,
             "  OBSERVED DATA ONLY  \u00b7  projections excluded  ",
             ha="left", va="bottom", fontsize=9.1, fontweight="bold", color="white",
             zorder=9, bbox=dict(boxstyle="round,pad=0.42",
                                 facecolor=SERIES["current"], edgecolor="none"))
    gx, gy = 0.085, 0.115
    pw = (w - gx * (cols - 1)) / cols
    ph = (h - gy * (rows - 1)) / rows

    for k, (metric, label, fmt) in enumerate(cfg["metrics"]):
        r, c = divmod(k, cols)
        ax = fig.add_axes([l + c * (pw + gx), b + (rows - 1 - r) * (ph + gy), pw, ph])
        sub = df.dropna(subset=[metric, cfg["x"]])
        sub = sub[sub[metric] > 0]
        if logx:
            sub = sub[sub[cfg["x"]] > 0]
        xs = (sub["decyear"] if cfg["x"] == "publication_date" else sub[cfg["x"]])
        ax.scatter(xs, sub[metric], s=13, color=SERIES["current"], alpha=0.55,
                   edgecolor="none", zorder=3)
        ax.set_yscale("log")
        _decade_ticks(ax.yaxis, sub[metric], AXIS_FMT[fmt], target=5)
        if logx:
            ax.set_xscale("log")
            _decade_ticks(ax.xaxis, sub[cfg["x"]], AXIS_FMT["pow10"], target=5)
        else:
            span = xs.max() - xs.min()
            step = 10 if span > 45 else 5 if span > 18 else 2
            import matplotlib.ticker as mticker
            ax.xaxis.set_major_locator(mticker.MultipleLocator(step))
            ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{int(v)}"))
            ax.set_xlim(xs.min() - span * 0.03, xs.max() + span * 0.04)
        ax.set_title(f"{label}    n={len(sub):,}", fontsize=10.2, fontweight="bold",
                     color=INK, pad=7)
        ax.grid(color=RULE, linewidth=0.7)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8.8)
        if r == rows - 1:
            ax.set_xlabel(cfg["xlabel"], fontsize=9.6)

    frame(fig, fig.axes[0], plot_id, cfg["headline"], subtitle,
          models_src("notable"), MODELS_METH, note)
    save(fig, plot_id, MODELS_DOMAIN)


def build_chip_d07(_r=None):
    """The generation handover, which only the quarterly by-chip file carries."""
    rows = _chip_csv("chip_quarterly_by_chip.csv")
    quarters = sorted({r["quarter"] for r in rows},
                      key=lambda q: (int(q.split()[1]), int(q.split()[0][1])))
    qi = {q: i for i, q in enumerate(quarters)}

    # "Other" is Epoch's untracked residual, not a chip generation, so it has no
    # place in a chart about generations handing over
    tracked = [d for d, _ in CHIP_DESIGNERS]
    by_designer = {d: {} for d in tracked}
    for r in rows:
        d, c = r["designer"], r["chip_type"]
        if d not in by_designer:
            continue
        v = r.get("total_cost_usd_p50")
        if not isinstance(v, float):
            continue
        by_designer[d].setdefault(c, [0.0] * len(quarters))[qi[r["quarter"]]] += v / 1e9

    # generations ordered by first appearance, then shaded oldest-pale to newest-dark
    # so the handover reads as the dark band displacing the pale one
    RAMPS = {"NVIDIA": ["#c3cddf", "#8fa3c4", "#4a6fa5", "#1f3864"],
             "Google": ["#cfd9e8", "#93a9cd", "#4a6fa5", "#22406f"],
             "Amazon": ["#c8dbcb", "#94b79a", "#6b8f71", "#3f6247"],
             "AMD": ["#e8d3bd", "#d6b083", "#b4763a", "#7d4f22"]}

    def first_seen(vals):
        return next((i for i, v in enumerate(vals) if v > 0), len(quarters))

    subtitle = ("What it shows: quarterly component cost by individual chip, one panel "
                "per designer, over the eight complete quarters. Every designer is "
                "running the same transition at the same time: the previous generation "
                "falls away as the next one takes over. This is the only view in the "
                "domain at chip grain over time — the published figure stops at "
                "designer, and CHIP-D03 accumulates the generations into one total.")
    note = ("Shading runs pale to dark by first appearance, so a handover reads as the "
            "dark band displacing the pale one. Epoch's \"Other\" residual is excluded: "
            "it is the untracked remainder of world supply, not a chip generation, and "
            "at $18.7bn in the last quarter it would dwarf every panel. A chip absent "
            "from a quarter was not published for it, which for a retiring part is not "
            "the same as zero. Every value is a Monte Carlo median and medians do not "
            "add, because Epoch simulates each aggregation separately.")

    fig = plt.figure(figsize=(12.0, 8.6))
    l, b, w, h = _rect(subtitle, note, left=0.070, width=0.900, xlabel_room=0.058,
                       badge_above=True,
                       source=chip_src(["quarterly_by_chip.csv"]))
    fig.text(l, b + h + 0.050,
             "  COMPLETE QUARTERS ONLY  ·  partial Q1 2026 excluded  ",
             ha="left", va="bottom", fontsize=9.1, fontweight="bold", color="white",
             zorder=9, bbox=dict(boxstyle="round,pad=0.42",
                                 facecolor=SERIES["current"], edgecolor="none"))
    gx, gy = 0.085, 0.115
    pw, ph = (w - gx) / 2, (h - gy) / 2
    idx = list(range(len(quarters)))

    for k, designer in enumerate(tracked):
        r, c = divmod(k, 2)
        ax = fig.add_axes([l + c * (pw + gx), b + (1 - r) * (ph + gy), pw, ph])
        chips = sorted(by_designer[designer].items(), key=lambda kv: first_seen(kv[1]))
        ramp = RAMPS[designer]
        bottom = [0.0] * len(quarters)
        for j, (chip, vals) in enumerate(chips):
            colour = ramp[min(j, len(ramp) - 1)] if len(chips) <= len(ramp) else \
                ramp[min(int(j * len(ramp) / len(chips)), len(ramp) - 1)]
            ax.bar(idx, vals, bottom=bottom, width=0.72, color=colour, label=chip,
                   edgecolor="white", linewidth=0.6, zorder=3)
            bottom = [a + v for a, v in zip(bottom, vals)]
        top = max(bottom) if max(bottom) else 1
        for i, t in enumerate(bottom):
            if t > 0:
                ax.text(i, t + top * 0.03, f"${t:,.1f}bn", ha="center", va="bottom",
                        fontsize=7.8, color=INK, fontweight="bold")
        ax.set_xticks(idx)
        ax.set_xticklabels([q.replace(" ", "\n") for q in quarters], fontsize=8.2)
        ax.set_xlim(-0.6, len(quarters) - 0.4)
        # headroom scales with the legend, which sits inside the panel and would
        # otherwise sit on top of the early bars
        ax.set_ylim(0, top * (1.30 + 0.09 * min(4, max(0, len(chips) - 2))))
        # a panel topping out near $2bn needs a decimal, or 1.5 and 2.0 both
        # print as "$2bn" and the axis repeats itself
        dp = 0 if top >= 5 else 1
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _p, _d=dp: f"${v:,.{_d}f}bn"))
        ax.set_title(designer, fontsize=10.6, fontweight="bold", color=INK, pad=7)
        ax.grid(axis="y", color=RULE, linewidth=0.7)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8.4)
        if r == 1:
            ax.set_xlabel("Quarter", fontsize=9.6)
        if c == 0:
            ax.set_ylabel("Component cost (US$ bn)", fontsize=9.4)
        hh, ll = ax.get_legend_handles_labels()
        # AMD runs six generations; a single column of keys reaches the bars
        ax.legend(hh[::-1], ll[::-1], loc="upper left", frameon=False, fontsize=8.2,
                  handlelength=1.1, labelspacing=0.32, borderaxespad=0.3,
                  ncol=2 if len(chips) > 4 else 1, columnspacing=1.1)

    frame(fig, fig.axes[0], "CHIP-D07",
          "Every designer is handing over to a new generation at once",
          subtitle, chip_src(["quarterly_by_chip.csv"]), CHIP_METH, note)
    save(fig, "CHIP-D07", CHIP_DOMAIN)


def build_chip_d08(_r=None):
    """The window total, which the quarterly series never states."""
    tracked = [d for d, _ in CHIP_DESIGNERS]
    cd = _chip_csv("chip_cumulative_by_designer.csv")
    cs = {r["quarter"]: r for r in _chip_csv("chip_cumulative_supply.csv")}
    q = _chip_csv("chip_quarterly_by_designer.csv")
    sq = {r["quarter"]: r for r in _chip_csv("chip_supply.csv")}
    quarters = sorted({r["quarter"] for r in q},
                      key=lambda s: (int(s.split()[1]), int(s.split()[0][1])))
    first, last = quarters[0], quarters[-1]

    parts = [("Logic wafers", "logic_wafers_p50", "logic_supply_wafers_p50", "#1f3864"),
             ("CoWoS packaging", "cowos_wafers_p50", "cowos_supply_wafers_p50", "#4e8a8b"),
             ("HBM memory", "hbm_cost_usd_p50", "hbm_supply_usd_p50", "#b4763a")]

    def share(rows, supply_row, ai_col, sup_col, quarter):
        # the four tracked designers only: Epoch's "Other" row IS the residual of
        # the denominator, so including it returns 100% by construction
        ai = sum(r[ai_col] for r in rows
                 if r["quarter"] == quarter and r["designer"] in tracked)
        return ai / float(supply_row[quarter][sup_col]) * 100

    data = [(lab, share(cd, cs, a, s, last), share(q, sq, a, s, last), col)
            for lab, a, s, col in parts]

    hi = max(d[1] for d in data)
    subtitle = (f"What it shows: the share of world supply the four tracked designers "
                f"took across the whole window, against the share they took in {last} "
                f"alone. The published figure and CHIP-D01 both answer the second "
                f"question quarter by quarter; only Epoch's cumulative file answers the "
                f"first, and it is the one a capacity question actually asks.")
    note = (f"Cumulative share is everything the tracked designers consumed from {first} "
            f"to {last} over everything the world produced in the same window - not an "
            f"average of the quarterly shares, which would weight a small quarter like a "
            f"large one. The gap between the two bars is the direction of travel: HBM at "
            f"{data[2][1]:.0f}% cumulative against {data[2][2]:.0f}% in the final quarter "
            f"is concentration still building, while logic sits near a tenth of supply on "
            f"both measures. Epoch's \"Other\" designer row is excluded from the "
            f"numerator throughout: it is the residual of the denominator, so including "
            f"it returns 100% by construction. Every value is a Monte Carlo median.")

    fig, ax = plt.figure(figsize=(12.0, 7.4)), None
    ax = fig.add_axes(_rect(subtitle, note, left=0.215, width=0.640,
                            xlabel_room=0.062, badge_above=True,
                            source=chip_src(["cumulative_supply_denominators.csv",
                                             "supply_denominators.csv"])))
    ys = list(range(len(data)))
    h = 0.34
    for y, (lab, cum, qtr, col) in zip(ys, data):
        ax.barh(y - h / 2, cum, height=h, color=col, edgecolor="white", linewidth=0.6,
                zorder=3)
        ax.barh(y + h / 2, qtr, height=h, color=col, alpha=0.42, edgecolor="white",
                linewidth=0.6, zorder=3)
        ax.text(cum + hi * 0.014, y - h / 2, f"{cum:.1f}%", va="center", fontsize=9.4,
                fontweight="bold", color=INK)
        ax.text(qtr + hi * 0.014, y + h / 2, f"{qtr:.1f}%", va="center", fontsize=9.0,
                color=MUTED)
    ax.set_yticks(ys)
    ax.set_yticklabels([d[0] for d in data], fontsize=10.4)
    ax.invert_yaxis()
    ax.set_xlim(0, min(100, hi * 1.22))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.set_xlabel("Share of world supply taken by the four tracked AI chip designers",
                  fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    # each row has its own colour, so the key is neutral: solid means cumulative,
    # faded means the final quarter, whatever the component
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=MUTED, label="Whole window, cumulative"),
                       Patch(facecolor=MUTED, alpha=0.42, label=f"{last} alone")],
              loc="upper right", bbox_to_anchor=(1.0, 0.62), frameon=False, fontsize=9)
    _chip_badge(ax, above=True)
    frame(fig, ax, "CHIP-D08",
          "AI took most of the world's packaging and memory, and a tenth of its logic",
          subtitle,
          chip_src(["cumulative_supply_denominators.csv", "supply_denominators.csv"]),
          CHIP_METH, note)
    save(fig, "CHIP-D08", CHIP_DOMAIN)


# ========================================================= MLPERF INFERENCE
# MLCommons publishes a results table, not a figure, so every chart here is a
# reading of that table. The quantity that makes submissions comparable is
# throughput per accelerator: "Result" is the whole system, and systems in this
# release run from 1 accelerator to 288.
MLPERF_DOMAIN = "mlperf-inference"
MLPERF_DATA = REPO / MLPERF_DOMAIN / "data"
MLPERF_FILE = "MLPerf_Inference_Hardware_Performance_Benchmarks.csv"
MLPERF_METH = ("Methodology reference pending final methodology document; derivation "
               "follows MLCommons' published MLPerf Inference rules")
HEADLINE = "llama2-70b-99"

VENDOR_COLOUR = {"NVIDIA": "#1f3864", "AMD": "#b4763a", "": "#6b8f71"}


def mlperf_src():
    return (f"MLCommons, MLPerf Inference v6.0 closed division — {MLPERF_FILE} — "
            f"mlcommons.org/benchmarks/inference-datacenter")


def _mlcsv(name):
    import pandas as pd
    return pd.read_csv(MLPERF_DATA / name)


def _mlmeta():
    return _mlcsv("mlperf_summary.csv").iloc[0]


def _ml_badge(ax, above=True):
    """The caveat that governs every number in this domain."""
    y, va = (1.030, "bottom") if above else (0.955, "top")
    ax.text(0.0 if above else 0.017, y,
            "  BENCHMARK CONDITIONS  ·  not production serving  ",
            transform=ax.transAxes, ha="left", va=va, fontsize=9.1,
            fontweight="bold", color="white", zorder=9, clip_on=False,
            bbox=dict(boxstyle="round,pad=0.42", facecolor=SERIES["current"],
                      edgecolor="none"))


MLPERF_SCOPE = ("Every figure is a vendor-tuned submission to the closed division, "
                "where the model and the accuracy target are fixed and the system is "
                "optimised hard for the benchmark. Production serving runs below this, "
                "so these are ceilings rather than expected throughput.")
MLPERF_NORM = ("Throughput is per accelerator: the published result is the whole "
               "system, and systems here run from 1 accelerator to 288.")


def _mlfig(subtitle, note, left, width, xlabel_room=0.058, figsize=(12.0, 8.4)):
    fig = plt.figure(figsize=figsize)
    ax = fig.add_axes(_rect(subtitle, note, left=left, width=width,
                            xlabel_room=xlabel_room, badge_above=True,
                            source=mlperf_src()))
    return fig, ax


def _mlfinish(fig, ax, pid, title, subtitle, note):
    _ml_badge(ax, above=True)
    frame(fig, ax, pid, title, subtitle, mlperf_src(), MLPERF_METH, note)
    save(fig, pid, MLPERF_DOMAIN)


def _tok(v):
    return f"{v/1000:,.1f}k" if v >= 1000 else f"{v:,.0f}"


def build_mlperf_01(_r=None):
    """The headline comparison: what one accelerator does on the common workload."""
    b = _mlcsv("mlperf_by_chip.csv")
    d = b[(b.workload == HEADLINE) & (b.scenario == "Offline")].copy()
    d = d.sort_values("per_accelerator", ascending=False)
    meta = _mlmeta()

    subtitle = (f"What it shows: the best submitted throughput per accelerator on "
                f"{HEADLINE}, the workload with the most submissions in the release, "
                f"in the offline scenario. {len(d)} chips from "
                f"{int(meta['organizations'])} submitting organisations. "
                f"{MLPERF_NORM}")
    note = (f"Offline is the batch scenario: requests are all available at once and the "
            f"system may reorder them freely, which is the most favourable condition "
            f"the benchmark offers. {MLPERF_SCOPE} A chip absent here was not submitted "
            f"on this workload, which is not a statement about what it can do.")

    fig, ax = _mlfig(subtitle, note, left=0.310, width=0.560)
    ys = list(range(len(d)))
    colours = [VENDOR_COLOUR.get(v if isinstance(v, str) else "", "#6b8f71")
               for v in d["vendor"].fillna("")]
    ax.barh(ys, d["per_accelerator"], height=0.70, color=colours,
            edgecolor="white", linewidth=0.6, zorder=3)
    hi = float(d["per_accelerator"].max())
    for y, r in zip(ys, d.itertuples()):
        ax.text(r.per_accelerator + hi * 0.012, y, _tok(r.per_accelerator),
                va="center", fontsize=9, fontweight="bold", color=INK)
    ax.set_yticks(ys)
    ax.set_yticklabels([_clip(c, 42) for c in d["chip"]], fontsize=9.2)
    ax.invert_yaxis()
    ax.set_xlim(0, hi * 1.16)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: _tok(v)))
    ax.set_xlabel("Tokens per second, per accelerator (offline scenario)", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=VENDOR_COLOUR["NVIDIA"], label="NVIDIA"),
                       Patch(facecolor=VENDOR_COLOUR["AMD"], label="AMD"),
                       Patch(facecolor=VENDOR_COLOUR[""], label="Other vendor")],
              loc="lower right", frameon=False, fontsize=9)
    top = d.iloc[0]
    _mlfinish(fig, ax, "MLPERF-01",
              f"{top['chip'].replace('NVIDIA ', '')} leads at {_tok(top['per_accelerator'])} "
              f"tokens/s per accelerator",
              subtitle, note)


def build_mlperf_02(_r=None):
    """What interactive serving costs, which a single headline number hides."""
    b = _mlcsv("mlperf_by_chip.csv")
    d = b[b.workload == HEADLINE]
    piv = d.pivot_table(index="chip", columns="scenario", values="per_accelerator")
    piv = piv.dropna(subset=["Offline", "Server", "Interactive"])
    piv = piv.sort_values("Offline", ascending=False)
    piv["penalty"] = (1 - piv["Interactive"] / piv["Offline"]) * 100

    subtitle = (f"What it shows: the same chips on {HEADLINE} across all three serving "
                f"scenarios. Offline batches everything; server holds a latency target "
                f"under a Poisson arrival pattern; interactive tightens that target "
                f"further. {len(piv)} chips submitted all three. {MLPERF_NORM}")
    note = (f"The gap between the bars is the price of responsiveness, and it is the "
            f"reason an offline figure must never be quoted as serving capacity: it "
            f"assumes every request is already waiting. Interactive costs "
            f"{piv['penalty'].min():.0f}% to {piv['penalty'].max():.0f}% of offline "
            f"throughput across these chips. {MLPERF_SCOPE}")

    fig, ax = _mlfig(subtitle, note, left=0.300, width=0.520)
    ys = list(range(len(piv)))
    h = 0.26
    for off, (scen, colour) in enumerate([("Offline", "#1f3864"),
                                          ("Server", "#4e8a8b"),
                                          ("Interactive", "#b4763a")]):
        ax.barh([y + (off - 1) * h for y in ys], piv[scen], height=h, color=colour,
                edgecolor="white", linewidth=0.5, label=scen, zorder=3)
    hi = float(piv["Offline"].max())
    for y, r in zip(ys, piv.itertuples()):
        ax.text(hi * 1.19, y, f"−{r.penalty:.0f}%", va="center", ha="center",
                fontsize=9.2, fontweight="bold", color="#b4763a")
    ax.text(hi * 1.19, -0.85, "interactive\nvs offline", ha="center", va="center",
            fontsize=8.2, color=MUTED, style="italic", linespacing=1.4)
    ax.set_yticks(ys)
    ax.set_yticklabels([_clip(c, 40) for c in piv.index], fontsize=9.2)
    ax.invert_yaxis()
    ax.set_xlim(0, hi * 1.30)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: _tok(v)))
    ax.set_xlabel("Tokens per second, per accelerator", fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    hh, ll = ax.get_legend_handles_labels()
    ax.legend(hh, ll, loc="lower right", bbox_to_anchor=(0.86, 0.02), frameon=False,
              fontsize=9, title="Scenario", title_fontsize=9.2)
    lo, hi_p = piv["penalty"].min(), piv["penalty"].max()
    _mlfinish(fig, ax, "MLPERF-02",
              f"Interactive serving costs {lo:.0f}% to {hi_p:.0f}% of batch throughput",
              subtitle, note)


def build_mlperf_03(_r=None):
    """What the model itself costs to serve, which dwarfs the chip choice."""
    b = _mlcsv("mlperf_by_chip.csv")
    d = b[b.scenario == "Offline"]
    best = (d.groupby("workload", as_index=False)
             .agg(per_accelerator=("per_accelerator", "max"),
                  chips=("chip", "nunique")))
    best = best.sort_values("per_accelerator", ascending=False)

    subtitle = (f"What it shows: the best per-accelerator throughput any submitted chip "
                f"reached on each of the {len(best)} token-generating workloads, offline. "
                f"The spread across workloads is far wider than the spread across chips "
                f"on any one of them — what is being served matters more than what it "
                f"is served on.")
    note = (f"Each bar is a different model, so the bars are not alternatives to one "
            f"another: they show what a fixed amount of silicon yields depending on the "
            f"workload put through it. llama3.1-405b sits roughly two orders of "
            f"magnitude below llama3.1-8b on the same hardware. Accuracy targets differ "
            f"between the -99 and -99.9 variants of llama2-70b and are not "
            f"interchangeable. {MLPERF_SCOPE}")

    fig, ax = _mlfig(subtitle, note, left=0.235, width=0.620)
    ys = list(range(len(best)))
    # dots, not bars: a bar on a log axis reads as proportional length when it is
    # not — llama3.1-405b is 77x below llama3.1-8b and a bar would show a quarter
    ax.set_xscale("log")
    lo = float(best["per_accelerator"].min()) * 0.55
    for y, r in zip(ys, best.itertuples()):
        ax.plot([lo, r.per_accelerator], [y, y], color=RULE, linewidth=1.2, zorder=2)
        ax.plot([r.per_accelerator], [y], marker="o", markersize=11,
                color=SERIES["current"], markeredgecolor="white",
                markeredgewidth=1.0, zorder=4)
    _plain_log_axis(ax.xaxis, lambda v: _tok(v) if v >= 1 else "")
    for y, r in zip(ys, best.itertuples()):
        ax.text(r.per_accelerator * 1.10, y,
                f"{_tok(r.per_accelerator)}   ({r.chips} chips submitted)",
                va="center", fontsize=8.8, color=INK)
    ax.set_yticks(ys)
    ax.set_yticklabels(best["workload"], fontsize=9.6)
    ax.invert_yaxis()
    ax.set_xlim(lo, best["per_accelerator"].max() * 7)
    ax.set_xlabel("Best tokens per second, per accelerator (offline, log scale)",
                  fontsize=10)
    ax.grid(axis="x", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ratio = float(best["per_accelerator"].max() / best["per_accelerator"].min())
    ax.text(0.995, 0.03, f"top to bottom: {ratio:.0f}x", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8.8, color=MUTED, style="italic")
    _mlfinish(fig, ax, "MLPERF-03",
              "The workload swings throughput far harder than the chip does",
              subtitle, note)


def build_mlperf_d01(_r=None):
    """Generation over generation, which the ranking flattens into one list."""
    b = _mlcsv("mlperf_by_chip.csv")
    d = b[(b.workload == HEADLINE) & (b.scenario == "Offline")
          & b["generation"].notna() & (b["generation_order"] >= 0)]
    d = d.sort_values("generation_order")

    fig, ax = None, None
    lines = []
    for vendor in ("NVIDIA", "AMD"):
        sub = d[d.vendor == vendor]
        if len(sub) >= 2:
            lines.append((vendor, sub))

    gains = []
    for vendor, sub in lines:
        first, last = sub.iloc[0], sub.iloc[-1]
        gains.append(f"{vendor} {first['generation']} to {last['generation']} "
                     f"{last['per_accelerator']/first['per_accelerator']:.1f}x")

    subtitle = (f"What it shows: per-accelerator throughput on {HEADLINE} by chip "
                f"generation, one line per vendor. The ranking in MLPERF-01 puts every "
                f"chip in one list; this is the same numbers read as a succession. "
                f"{'; '.join(gains)}.")
    note = (f"Generations are ordered by release, not by submission date, and each "
            f"point is the best submitted result for that generation. The two lines are "
            f"not directly comparable to each other beyond their shape: the systems, "
            f"software stacks and submitting organisations differ. {MLPERF_SCOPE}")

    fig, ax = _mlfig(subtitle, note, left=0.088, width=0.640)
    # the two lines converge at several points, so one vendor labels above the
    # marker and the other below rather than writing over each other
    for k, (vendor, sub) in enumerate(lines):
        colour = VENDOR_COLOUR[vendor]
        xs = list(range(len(sub)))
        ax.plot(xs, sub["per_accelerator"], marker="o", markersize=8, linewidth=2.4,
                color=colour, label=vendor, zorder=4)
        above = k == 0
        for x, r in zip(xs, sub.itertuples()):
            ax.annotate(f"{r.generation}\n{_tok(r.per_accelerator)}",
                        (x, r.per_accelerator), textcoords="offset points",
                        xytext=(0, 14 if above else -34), ha="center", fontsize=8.8,
                        color=colour, fontweight="bold", linespacing=1.35)
    ax.set_xticks(range(max(len(s) for _, s in lines)))
    ax.set_xticklabels([f"generation {i+1}" for i in range(max(len(s) for _, s in lines))],
                       fontsize=9.4)
    ax.set_xlim(-0.35, max(len(s) for _, s in lines) - 0.65)
    ax.set_ylim(0, float(d["per_accelerator"].max()) * 1.30)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: _tok(v)))
    ax.set_ylabel("Tokens per second, per accelerator", fontsize=10)
    ax.set_xlabel("Successive generations submitted, oldest first", fontsize=10)
    ax.grid(axis="y", color=RULE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False, fontsize=9.4, title="Vendor",
              title_fontsize=9.4)
    _mlfinish(fig, ax, "MLPERF-D01",
              "Both vendors gained about four-fold across their submitted generations",
              subtitle, note)


def build_mlperf_d02(_r=None):
    """What the benchmark actually contains, before anyone reads a ranking off it."""
    import numpy as np
    cov = _mlcsv("mlperf_coverage.csv")
    grid = cov.pivot_table(index="chip", columns="workload", values="submissions",
                           aggfunc="sum")
    order = grid.notna().sum(axis=1).sort_values(ascending=False).index
    grid = grid.loc[order]
    meta = _mlmeta()
    filled = int(grid.notna().sum().sum())
    cells = grid.shape[0] * grid.shape[1]

    subtitle = (f"What it shows: how many results each chip carries on each workload. "
                f"{filled} of {cells} chip-workload cells hold any submission at all, "
                f"which is why a like-for-like comparison is only possible on a couple "
                f"of workloads and why {HEADLINE} carries the headline charts.")
    note = (f"A blank cell means nothing was submitted, not that the chip cannot run "
            f"the workload — submitting is voluntary and costly, and vendors pick their "
            f"battles. Of {int(meta['submitted_results'])} results in the release, "
            f"{int(meta['token_results_used'])} are token throughput with an "
            f"attributable accelerator count and reach these charts; the rest are other "
            f"units, unnamed accelerators, or one mixed-accelerator system. "
            f"{MLPERF_SCOPE}")

    fig, ax = _mlfig(subtitle, note, left=0.300, width=0.560, xlabel_room=0.086)
    vals = grid.to_numpy(dtype=float)
    im = ax.imshow(np.where(np.isnan(vals), np.nan, vals), cmap="Blues", aspect="auto",
                   vmin=0, vmax=float(np.nanmax(vals)))
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = vals[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{int(v)}", ha="center", va="center", fontsize=9,
                        fontweight="bold",
                        color="white" if v > np.nanmax(vals) * 0.55 else INK)
            else:
                ax.text(j, i, "—", ha="center", va="center", fontsize=9, color="#c9ced8")
    ax.set_xticks(range(grid.shape[1]))
    ax.set_xticklabels(grid.columns, fontsize=8.8, rotation=28, ha="right")
    ax.set_yticks(range(grid.shape[0]))
    ax.set_yticklabels([_clip(c, 40) for c in grid.index], fontsize=8.8)
    ax.set_xticks([x - 0.5 for x in range(1, grid.shape[1])], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, grid.shape[0])], minor=True)
    ax.grid(which="minor", color="white", linewidth=1.6)
    ax.tick_params(which="minor", length=0)
    ax.grid(which="major", visible=False)
    cb = fig.colorbar(im, ax=ax, fraction=0.026, pad=0.02)
    cb.set_label("Results submitted", fontsize=9)
    cb.outline.set_visible(False)
    _mlfinish(fig, ax, "MLPERF-D02",
              "The benchmark is dense on one workload and sparse everywhere else",
              subtitle, note)


MLPERF_BUILDERS = {
    "MLPERF-01": build_mlperf_01, "MLPERF-02": build_mlperf_02,
    "MLPERF-03": build_mlperf_03, "MLPERF-D01": build_mlperf_d01,
    "MLPERF-D02": build_mlperf_d02,
}


BUILDERS = {"P-01": build_p01, "P-03": build_p03, "P-58": build_p58}
BUILDERS.update({pid: (lambda _rows, _p=pid: build_azure(_p)) for pid in AZURE_PLOTS})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_epoch(_p)) for pid in EPOCH_PLOTS})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_owner_metric(_p)) for pid in OWNER_METRICS})
BUILDERS.update({"DERIVED-01": build_d01, "DERIVED-02": build_d02,
                 "DERIVED-03": build_d03, "DERIVED-04": build_d04,
                 "DERIVED-05": build_d05, "DERIVED-06": build_d06})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_model_scatter(_p))
                 for pid in MODEL_PLOTS})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_models_panels(_p))
                 for pid in MODELS_PANELS})
BUILDERS.update({pid: (lambda _rows, _b=fn: _b()) for pid, fn in MODEL_DERIVED.items()})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_chip(_p)) for pid in CHIP_PLOTS})
BUILDERS.update({"CHIP-D01": build_chip_d01, "CHIP-D02": build_chip_d02,
                 "CHIP-D03": build_chip_d03, "CHIP-D04": build_chip_d04,
                 "CHIP-D05": build_chip_d05, "CHIP-D06": build_chip_d06,
                 "CHIP-D07": build_chip_d07,
                 "CHIP-D08": build_chip_d08})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_companies(_p))
                 for pid in COMPANIES_PLOTS})
BUILDERS.update({pid: (lambda _rows, _b=fn: _b())
                 for pid, fn in COMPANIES_DERIVED.items()})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_aei_rank(_p)) for pid in AEI_RANK})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_aei_mix(_p)) for pid in AEI_MIX})
BUILDERS.update({pid: (lambda _rows, _b=fn: _b()) for pid, fn in AEI_DERIVED.items()})
BUILDERS.update({pid: (lambda _rows, _p=pid: build_aei_api_rank(_p)) for pid in AEI_API_RANK})
BUILDERS.update({pid: (lambda _rows, _b=fn: _b()) for pid, fn in AEI_API_DERIVED.items()})
BUILDERS.update({pid: (lambda _rows, _b=fn: _b()) for pid, fn in MLPERF_BUILDERS.items()})


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
