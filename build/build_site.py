#!/usr/bin/env python3
"""Generate the AI Data Room site from the Plot Index.

The gallery HTML is never hand-edited. It is rebuilt from build/plot_index.csv
plus whatever chart files actually exist in the domain's charts/ directory, so
the page can never imply a chart exists when it does not.

PUBLISHED_ONLY controls what reaches the page:

    True  - the site carries only plots whose chart files are on disk. The Plot
            Index stays the full catalogue; it simply is not advertised on the
            public page. This is the current setting: the site publishes one
            chart and says nothing about work not yet done.
    False - every catalogued plot renders, with Pending placeholders for those
            not yet generated.

Either way the catalogue in build/plot_index.csv is untouched, so flipping the
flag back restores the full gallery without regenerating anything.

Adding a new domain (Training Compute, Model Pricing, ...) means appending an
entry to DOMAINS and dropping a plot index CSV in place - the root page and the
per-domain gallery both pick it up without touching any HTML. Domains with no
published charts are not rendered at all.

Usage:
    python build/build_site.py
"""
import csv
import html
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Publish only what has actually been generated. See the module docstring.
PUBLISHED_ONLY = True

# --------------------------------------------------------------- domains
# 'live' domains are built from a plot index; 'planned' render as placeholders
# on the root page only. Nothing is claimed to exist before it does.
DOMAINS = [
    {
        # the slug stays "inference-tokens": it is the published address, five
        # other domains load their stylesheet through it, and the site's premise
        # is that a link made today keeps working. Only the display name changes.
        "slug": "inference-tokens",
        "title": "AzureLLMInferenceTrace",
        "blurb": "Microsoft's own production inference traces, released from Azure's "
                 "LLM and multimodal serving fleets: one row per request, with the "
                 "input and output token counts it actually used.",
        # build/plot_index.csv remains the 69-row workbook catalogue for
        # reference; the site is driven by the curated published index
        "index": "build/plot_index_published.csv",
        "live": True,
    },
    {
        "slug": "ai-infrastructure",
        "title": "AI Data Centers",
        "blurb": "The physical build-out behind AI compute: installed capacity, IT power, "
                 "capital cost and hardware across the largest AI data centers worldwide.",
        "index": "build/plot_index_datacenters.csv",
        # one stylesheet for the whole site rather than a copy per domain
        "css": "../inference-tokens/assets/style.css",
        "section_blurbs": {
            "Epoch AI — Published Visualizations":
                "These reproduce Epoch AI's own published views of the AI Data Centers "
                "dataset, rebuilt from the underlying CSVs rather than screenshotted. "
                "Observed data only — every future-dated milestone in the source is "
                "excluded, so nothing here is a projection.",
            "Derived Analysis":
                "Our own analysis of the same underlying Epoch AI files — questions the "
                "published views do not answer. Same observed-only rule throughout.",
        },
        "live": True,
    },
    {
        "slug": "ai-models",
        "title": "AI Models",
        "blurb": "The models themselves: how much compute, data, money, time and power "
                 "went into training them, who built them, and what the record actually "
                 "contains.",
        "index": "build/plot_index_models.csv",
        "css": "../inference-tokens/assets/style.css",
        "section_blurbs": {
            "Epoch AI — Published Visualizations":
                "Epoch publishes one configurable figure on this dataset — a metric "
                "against publication date, over a chosen release, optionally coloured "
                "by domain, organization or country. These are that figure at each of "
                "its settings, rebuilt from the downloaded CSVs rather than "
                "screenshotted, with the point counts stated on every chart.",
            "Derived Analysis":
                "Our own analysis of the same four files — questions the published "
                "figure does not answer. Same rule throughout: a model appears in a "
                "chart only where Epoch records the value being plotted, and nothing "
                "is imputed to fill a gap.",
        },
        "live": True,
    },
    {
        "slug": "ai-chip-components",
        "title": "AI Chip Components",
        "blurb": "The three components AI accelerators are built from — advanced-node logic "
                 "wafers, CoWoS packaging and HBM memory — and how much of the world's "
                 "supply of each the leading AI chip designers consumed.",
        "index": "build/plot_index_chip_components.csv",
        "css": "../inference-tokens/assets/style.css",
        "section_blurbs": {
            "Epoch AI — Published Visualizations":
                "Epoch publishes one configurable figure for this dataset: four tabs "
                "(Total cost, Logic, Packaging, Memory) crossed with colour by component "
                "or designer, absolute or share, quarterly or annual, running or "
                "cumulative. These are that figure at each of its distinct settings, "
                "rebuilt from the published CSVs rather than screenshotted. Complete "
                "quarters only — the partial Q1 2026 in the download is excluded, and "
                "Epoch's own Project trend control is disabled at source, so nothing "
                "here is a projection.",
            "Derived Analysis":
                "Our own analysis of the same published files — questions the explorer's "
                "settings cannot answer, including the uncertainty behind every median. "
                "Same complete-quarters rule throughout.",
        },
        "extra_sections": [{
            "title": "What these components are",
            "body": "An AI accelerator is not one chip. It is a logic die, a stack of "
                    "memory beside it, and a package holding the two together — three "
                    "separate supply chains, each with its own constraint. These are "
                    "the terms used throughout this domain.",
            "terms": [
                ("Wafer",
                 "A disc of silicon, 12 inches across, that chips are made on. Fabs "
                 "sell capacity in wafers rather than chips, so wafers are the unit "
                 "supply is counted in. One wafer yields many dies, and how many "
                 "depends on die size and how many come out working."),
                ("Advanced-node logic",
                 "The processor itself — the part that does the arithmetic. "
                 "\"Advanced-node\" means the 3–5 nanometre class TSMC fabricates "
                 "(N3/N5), the leading edge. Only a handful of fabs in the world can "
                 "make it, which is why the capacity is worth tracking."),
                ("CoWoS packaging",
                 "Chip-on-Wafer-on-Substrate, TSMC's advanced packaging. It mounts the "
                 "logic die and the memory stacks onto one substrate so they sit "
                 "millimetres apart. Without it the memory cannot feed the processor "
                 "fast enough, and it has been the tightest constraint in the chain — "
                 "AI took 88% of all of it produced across 2024–25."),
                ("HBM",
                 "High Bandwidth Memory: DRAM stacked vertically and placed beside the "
                 "logic die rather than out on the board. Bandwidth, not capacity, is "
                 "what training and inference are short of, and HBM is the largest "
                 "single line in every designer's component bill. Epoch measures it in "
                 "dollars rather than units, because stack generations are not "
                 "comparable by count."),
                ("Auxiliary",
                 "Epoch's catch-all for everything else in the bill of materials — "
                 "substrate, power delivery, passives, assembly and test. Small per "
                 "chip, and not broken out further at source."),
                ("Chip designer",
                 "The company that designs the accelerator and buys the capacity: "
                 "NVIDIA, Google (TPUs), Amazon (Trainium) and AMD. None of them owns "
                 "a leading-edge fab, so all four are drawing on the same TSMC and "
                 "memory-vendor capacity."),
                ("World supply",
                 "Epoch's estimate of everything the world produced of that component "
                 "in the period, AI or otherwise. It is the denominator behind every "
                 "share view here, and \"Other\" is its residual — not a fifth "
                 "designer, but the capacity going to phones, laptops, cars and "
                 "everything else, plus stockpiling and estimation error."),
                ("Monte Carlo median",
                 "Every figure Epoch publishes is the middle of 10,000 simulated draws, "
                 "not a measured quantity. Two consequences run through this domain: "
                 "medians do not add, because each aggregation is simulated separately, "
                 "and the 5th–95th interval behind each one is wide — CHIP-D04 plots it."),
            ],
        }],
        "live": True,
    },
    {
        "slug": "ai-companies",
        "title": "AI Companies",
        "blurb": "The companies building the models: what they earn, what they raise, what "
                 "they are worth, who they employ, how much they are used and what they "
                 "spend on compute.",
        "index": "build/plot_index_companies.csv",
        "css": "../inference-tokens/assets/style.css",
        "section_blurbs": {
            "Epoch AI — Published Visualizations":
                "Epoch publishes one configurable figure on this dataset — a metric "
                "against the date it was reported, over a chosen tab, with controls for "
                "linear or log scale and a fitted growth regression. These are that "
                "figure at each of its settings, rebuilt from the downloaded CSVs "
                "rather than screenshotted. Rows Epoch flags 'exclude from graph view' "
                "are dropped here exactly as they are there, and the projection control "
                "is off throughout.",
            "Derived Analysis":
                "Our own analysis of the same six files — questions the tabs cannot "
                "answer, because they need two of them at once: revenue against "
                "headcount, valuation against revenue, serving against training. Where "
                "two observations are paired, each is matched to the nearest in time "
                "within a stated window and unmatched rows are dropped, never stretched "
                "to a convenient partner.",
        },
        "live": True,
    },
    {
        "slug": "ai-usage",
        "title": "AI Usage",
        "blurb": "What people actually do with a frontier model: what they ask for, what "
                 "gets produced, which occupations the work belongs to, and where in the "
                 "world it happens.",
        "index": "build/plot_index_aei.csv",
        "css": "../inference-tokens/assets/style.css",
        "section_blurbs": {
            "Anthropic — Published Visualizations":
                "These reproduce the views Anthropic's own Economic Index presents, "
                "rebuilt from the published file rather than screenshotted. The whole "
                "domain carries one caveat that cannot be repeated often enough: this "
                "is one provider's own consumer traffic, so every share is a share of "
                "Claude conversations and never of AI use at large.",
            "Anthropic — Enterprise API":
                "The same index over Anthropic's other published population: 1P API "
                "traffic, excluding Claude Code. This is programmatic, paid usage "
                "rather than consumer conversation, published globally with no "
                "geographic breakdown. It is the file that speaks to enterprise "
                "workloads, and it behaves nothing like the consumer one.",
            "Derived Analysis":
                "Our own analysis of the same two files — the published views held at "
                "a grain where they vary, and the API set against Claude.ai on the "
                "measures where they diverge. The two are never pooled: they are "
                "different populations, and the gap between them is the finding. A "
                "cell Anthropic did not publish is absent rather than zero, so a "
                "missing country is a suppressed one.",
        },
        "live": True,
    },
    {"slug": "training-compute", "title": "Training Compute", "live": False},
    {"slug": "model-pricing", "title": "Model Pricing", "live": False},
    {"slug": "energy", "title": "Energy", "live": False},
]

# Gallery sections, keyed off the methodology reference already recorded against
# each plot in the workbook. Order here is the order on the page.
SECTIONS = [
    ("Provider throughput",
     "Charts built from figures companies disclosed themselves. The highest-confidence "
     "route, because a disclosed number needs no assumption beyond unit conversion.",
     [r"^\u00a77\.3"]),
    ("Pricing and model economics",
     "The price side of the revenue-to-tokens conversion, and the spend-side route that "
     "sizes a market segment rather than a single company.",
     [r"^\u00a77\.4", r"^\u00a77\.5"]),
    ("Capacity and infrastructure",
     "The hardware ceiling: installed accelerators, their measured throughput, and the "
     "upper bound they imply.",
     [r"^\u00a77\.6"]),
    ("Coverage gaps",
     "Providers that publish neither tokens nor revenue. The largest unresolved gap in "
     "the estimate.",
     [r"^\u00a77\.7"]),
    ("Validation and cross-check",
     "Independent evidence used to test the bottom-up total from a different direction.",
     [r"^\u00a77\.11", r"^\u00a72\.5", r"^\u00a77\.14"]),
    ("Composition of the total",
     "How the total divides into input, output, cached, reasoning and agentic tokens - "
     "sub-types inside the total, never additions to it.",
     [r"^\u00a77\.9", r"^\u00a710\.1"]),
]

CSS = "assets/style.css"


def e(s):
    return html.escape(str(s or "").strip())


def load_plots(path):
    with (REPO / path).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def assign(plots, blurbs=None):
    """Bucket each plot into a section.

    A plot index may name its own sections in a Section column, which takes
    precedence and preserves the order the sections first appear. Otherwise
    plots are bucketed by methodology reference against SECTIONS.
    """
    if any((p.get("Section") or "").strip() for p in plots):
        blurbs = blurbs or {}
        order, grouped = [], {}
        for p in plots:
            name = (p.get("Section") or "Other").strip()
            if name not in grouped:
                order.append(name)
                grouped[name] = []
            grouped[name].append(p)
        return [(n, blurbs.get(n, ""), grouped[n]) for n in order]

    out = [(name, blurb, []) for name, blurb, _ in SECTIONS]
    leftover = []
    for p in plots:
        ref = (p["Methodology_reference"] or "").split("\n")[0].strip()
        for i, (_, _, pats) in enumerate(SECTIONS):
            if any(re.match(pat, ref) for pat in pats):
                out[i][2].append(p)
                break
        else:
            leftover.append(p)
    if leftover:
        out.append(("Other", "", leftover))
    return [s for s in out if s[2]]



def svg_size(slug, pid):
    """Intrinsic size of the chart, so the browser reserves layout space.

    Without this, lazily-loaded images have zero height until they load, the
    page reflows, and an anchor link scrolls to the wrong place.
    """
    f = REPO / slug / "charts" / f"{pid}.svg"
    if not f.exists():
        return None
    head = f.read_text(encoding="utf-8", errors="ignore")[:600]
    m = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', head)
    if m:
        return float(m.group(1)), float(m.group(2))
    w = re.search(r'width="([\d.]+)pt"', head)
    h = re.search(r'height="([\d.]+)pt"', head)
    return (float(w.group(1)), float(h.group(1))) if w and h else None


def chart_files(slug, pid):
    base = REPO / slug / "charts"
    return ((base / f"{pid}.svg").exists(), (base / f"{pid}.png").exists())


def has_interactive(slug, pid):
    """A self-contained interactive companion, if one was generated."""
    return (REPO / slug / "charts" / f"{pid}.html").exists()


def render_chart(slug, p):
    pid = p["Plot_ID"]
    has_svg, has_png = chart_files(slug, pid)
    title = p["Chart_title"]
    # the workbook appends the chart type in brackets; keep the title clean here
    title = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip() or title

    shows = (p["What_the_chart_shows"] or "").split("\n")
    lead = shows[0].strip() if shows else ""
    note = ""
    for line in shows:
        if line.strip().startswith("Note"):
            note = line.split("\u2014", 1)[-1].strip().rstrip(".")

    parts = [f'<section class="chart" id="{e(pid)}">']
    # an ID this chart used to carry, kept as an invisible anchor so links
    # already shared against the old identifier keep resolving
    if p.get("Legacy_anchor"):
        parts.append(f'<span id="{e(p["Legacy_anchor"])}" class="legacy-anchor"></span>')
    parts.append('<div class="chart-head">')
    parts.append(f'<a class="pid" href="#{e(pid)}">{e(pid)}</a>')
    parts.append(f"<h3>{e(title)}</h3>")
    parts.append("</div>")
    if lead:
        parts.append(f'<p class="shows">{e(lead)}</p>')

    if has_interactive(slug, pid):
        # the interactive build is the figure where one exists; it reports its own
        # height on load, so the fallback here only has to be close
        parts.append('<div class="figure figure-live">')
        parts.append(f'<iframe class="live" src="charts/{e(pid)}.html" '
                     f'title="{e(title)} (interactive)" height="620" loading="lazy"></iframe>')
        parts.append("</div>")
    elif has_svg:
        parts.append('<div class="figure">')
        dims = svg_size(slug, pid)
        sz = f' width="{dims[0]:.0f}" height="{dims[1]:.0f}"' if dims else ""
        parts.append(f'<img src="charts/{e(pid)}.svg" alt="{e(title)}"{sz} loading="lazy">')
        parts.append("</div>")
    else:
        parts.append('<div class="pending">')
        parts.append('<span class="tag">Pending</span>')
        parts.append("<p>This chart is catalogued in the Plot Index and specified, but has "
                     "not yet been generated. It will appear here once produced from its "
                     "source dataset.</p>")
        parts.append("</div>")

    parts.append('<dl class="facts">')
    if p.get("Owning_dataset"):
        parts.append(f'<div><dt>Dataset</dt><dd>{e(p["Owning_dataset"])}</dd></div>')
    if p.get("Granularity"):
        parts.append(f'<div><dt>Granularity</dt><dd>{e(p["Granularity"])}</dd></div>')
    if p.get("Year"):
        parts.append(f'<div><dt>Year</dt><dd>{e(p["Year"])}</dd></div>')
    if p.get("Coverage"):
        parts.append(f'<div><dt>Coverage</dt><dd>{e(p["Coverage"])}</dd></div>')
    if p.get("Source_files"):
        parts.append('<div><dt>Source files</dt>'
                     f'<dd class="files">{e(p["Source_files"])}</dd></div>')
    if p.get("Data_treatment"):
        parts.append('<div><dt>Data treatment</dt>'
                     f'<dd class="treatment">{e(p["Data_treatment"])}</dd></div>')
    if p.get("Source_name"):
        src = e(p["Source_name"])
        url = (p.get("Source_url") or "").strip()
        val = f'<a href="{e(url)}" rel="noopener">{src}</a>' if url else src
        parts.append(f"<div><dt>Source</dt><dd>{val}</dd></div>")
    if p.get("Methodology_reference"):
        ref = " · ".join(x.strip() for x in p["Methodology_reference"].split("\n") if x.strip())
        # methodology document not yet final - plain text now, hyperlink later
        parts.append(f'<div><dt>Methodology</dt><dd data-methodology-ref>{e(ref)}</dd></div>')
    if note:
        parts.append(f"<div><dt>Note</dt><dd>{e(note)}</dd></div>")
    parts.append("</dl>")

    if has_svg or has_png or has_interactive(slug, pid):
        links = []
        if has_interactive(slug, pid):
            links.append(f'<a class="interactive" href="charts/{e(pid)}.html" '
                         f'target="_blank" rel="noopener">Open full screen &#8599;</a>')
        if has_svg:
            links.append(f'<a href="charts/{e(pid)}.svg" download>Download SVG</a>')
        if has_png:
            links.append(f'<a href="charts/{e(pid)}.png" download>Download PNG</a>')
        parts.append(f'<p class="downloads">{"".join(links)}</p>')

    parts.append("</section>")
    return "\n".join(parts)


def build_gallery(dom):
    catalogued = load_plots(dom["index"])
    plots = ([p for p in catalogued if chart_files(dom["slug"], p["Plot_ID"])[0]]
             if PUBLISHED_ONLY else catalogued)
    sections = assign(plots, dom.get("section_blurbs"))
    named = any((p.get("Section") or "").strip() for p in plots)
    built = sum(1 for p in plots if chart_files(dom["slug"], p["Plot_ID"])[0])

    body = []
    # a contents list earns its place only once there is more than one section
    if len(sections) > 1:
        body.append('<div class="toc"><h2>Contents</h2><ol>')
        for name, _, ps in sections:
            live = sum(1 for p in ps if chart_files(dom["slug"], p["Plot_ID"])[0])
            anchor = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            body.append(f'<li><a href="#{anchor}">{e(name)}</a> '
                        f'<span class="count">{live} of {len(ps)} published</span></li>')
        body.append("</ol></div>")

    for name, blurb, ps in sections:
        anchor = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        body.append(f'<div class="section" id="{anchor}">')
        # a named section is part of the page structure, so it always shows;
        # an inferred one only earns a heading when there is more than one
        if named or len(sections) > 1:
            body.append(f"<h2>{e(name)}</h2>")
            if blurb:
                body.append(f'<p class="blurb">{e(blurb)}</p>')
        for p in ps:
            body.append(render_chart(dom["slug"], p))
        body.append("</div>")

    for extra in dom.get("extra_sections", []):
        anchor = re.sub(r"[^a-z0-9]+", "-", extra["title"].lower()).strip("-")
        body.append(f'<div class="section" id="{anchor}">')
        body.append(f"<h2>{e(extra['title'])}</h2>")
        body.append(f'<p class="blurb">{e(extra["body"])}</p>')
        # a glossary is a definition list, not a paragraph: terms have to be
        # scannable, because a reader looks one up rather than reading it through
        if extra.get("terms"):
            body.append('<dl class="glossary">')
            for term, meaning in extra["terms"]:
                body.append(f"<div><dt>{e(term)}</dt><dd>{e(meaning)}</dd></div>")
            body.append("</dl>")
        body.append("</div>")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(dom['title'])} — Visual Evidence Gallery — AI Data Room</title>
<meta name="description" content="{e(dom['blurb'])}">
<link rel="stylesheet" href="{dom.get('css', CSS)}">
</head>
<body>
<div class="wrap">

<header class="masthead">
  <p class="eyebrow"><a href="../">AI Data Room</a> &nbsp;/&nbsp; Visual Evidence</p>
  <h1>{e(dom['title'])}</h1>
  <p class="standfirst">{e(dom['blurb'])}</p>
  <dl class="meta">
    <div><dt>Charts published</dt><dd>{built}</dd></div>
  </dl>
</header>

{chr(10).join(body)}

<footer class="foot">
  <p><strong>How to read this gallery.</strong> Every chart carries a stable Plot ID
  matching the Dataset Register. Link straight to any chart by appending its ID, for
  example <code>#P-59</code>. That address does not change as the gallery grows.</p>
  <p><strong>Methodology references.</strong> Section references shown against each chart
  are taken from the working methodology. They become links once that document is final.</p>
</footer>

</div>
<script>
// embedded charts post their rendered height; without this the iframe would
// either clip the legend or leave a gap at some widths
addEventListener('message', function (ev) {{
  var d = ev.data;
  if (!d || d.type !== 'aidr-height' || !d.id) return;
  var f = document.querySelector('iframe.live[src="charts/' + d.id + '.html"]');
  // ignore implausible measurements rather than collapsing the frame to a sliver
  if (f && d.h > 200 && d.h < 4000) f.style.height = d.h + 'px';
}});
</script>
</body>
</html>
"""
    out = REPO / dom["slug"] / "index.html"
    out.write_text(page, encoding="utf-8")
    print(f"  {out.relative_to(REPO)}  —  {len(plots)} plots, {built} published, "
          f"{len(sections)} sections")
    return len(plots), built


def build_root(stats):
    # only domains that actually carry published charts appear; nothing is
    # advertised before it exists
    cards = []
    for dom in DOMAINS:
        if not dom["live"]:
            continue
        _total, built = stats[dom["slug"]]
        cards.append(f"""    <div class="domain live">
      <h2>{e(dom['title'])}</h2>
      <p>{e(dom['blurb'])}<br><strong>{built}</strong> chart{'' if built == 1 else 's'} published.</p>
      <a class="btn" href="{e(dom['slug'])}/">Open {e(dom['title'])} Gallery</a>
    </div>""")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Data Room</title>
<meta name="description" content="Visual evidence galleries supporting AI demand research.">
<link rel="stylesheet" href="inference-tokens/assets/style.css">
</head>
<body>
<div class="wrap">

<header class="masthead">
  <p class="eyebrow">Research Data Room</p>
  <h1>AI Data Room</h1>
  <p class="standfirst">Visual evidence supporting AI demand research. Every chart carries a
  stable identifier, a named source and a methodology reference, so any figure can be
  traced back to where it came from.</p>
</header>

<div class="domains">
{chr(10).join(cards)}
</div>

<footer class="foot">
  <p>Charts are generated from source data and published here with stable URLs. A chart's
  address does not change as the gallery grows, so a link made today keeps working.</p>
</footer>

</div>
</body>
</html>
"""
    (REPO / "index.html").write_text(page, encoding="utf-8")
    print(f"  index.html  —  {len(cards)} domain card(s)")


def main():
    print("building site")
    stats = {}
    for dom in DOMAINS:
        if dom["live"]:
            stats[dom["slug"]] = build_gallery(dom)
    build_root(stats)


if __name__ == "__main__":
    main()
