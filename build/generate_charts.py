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


def save(fig, plot_id):
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


# =============================================================== P-59
def build_p59(_rows):
    """Input and output token distributions, log-binned, per service."""
    import csv as _csv
    from collections import defaultdict
    hist = defaultdict(lambda: defaultdict(int))
    with AZURE_HIST.open(encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            hist[(r["trace"], r["kind"])][int(r["bin_low"])] += int(r["count"])

    fig = plt.figure(figsize=(11.0, 7.2))
    axes = [fig.add_axes([0.085, 0.30, 0.40, 0.48]),
            fig.add_axes([0.565, 0.30, 0.40, 0.48])]

    for ax, trace, title in zip(axes, ["conv_2023", "code_2023"],
                                ["Conversation service", "Code service"]):
        for kind, colour in (("input", SERIES["prior"]), ("output", SERIES["current"])):
            d = hist[(trace, kind)]
            if not d:
                continue
            xs = sorted(d)
            total = sum(d.values())
            ys = [d[x] / total * 100 for x in xs]
            ax.step([max(x, 0.5) for x in xs], ys, where="post", color=colour,
                    linewidth=1.9, label=kind.capitalize())
            ax.fill_between([max(x, 0.5) for x in xs], ys, step="post",
                            color=colour, alpha=0.16)
        ax.set_xscale("log")
        ax.set_title(title, fontsize=11, color=INK, pad=8)
        ax.set_xlabel("Tokens per request (log scale)", fontsize=9.5)
        ax.grid(axis="y", color=RULE, linewidth=0.7)
        ax.set_axisbelow(True)
        ax.set_ylim(0, 45)
    axes[0].set_ylabel("Share of requests (%)", fontsize=10)
    axes[1].tick_params(labelleft=False)
    axes[0].legend(frameon=False, fontsize=9.5, loc="upper left")

    frame(fig, axes[0], "P-59",
          "Code requests carry long prompts and return almost nothing",
          "Distribution of input and output tokens per request across the two Azure services, "
          "log-binned.",
          "Microsoft Azure, AzurePublicDataset (2023 release, CC-BY)",
          "\u00a73.2 \u2014 What we measured",
          "The code service has a median input of 1,469 tokens but a median output of 13 "
          "tokens - the signature of inline completion rather than chat. Conversation medians "
          "are 1,020 input and 129 output. This asymmetry, not a difference in volume, is what "
          "drives the gap in output share between the two services.")
    save(fig, "P-59")


BUILDERS = {"P-01": build_p01, "P-03": build_p03,
            "P-58": build_p58, "P-59": build_p59}


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
