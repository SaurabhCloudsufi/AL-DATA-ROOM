#!/usr/bin/env python3
"""Generate the AI Data Room site from the Plot Index.

The gallery HTML is never hand-edited. It is rebuilt from build/plot_index.csv
plus whatever chart files actually exist in the domain's charts/ directory.
A plot with no chart file renders as Pending rather than as a broken image, so
the page can never imply a chart exists when it does not.

Adding a new domain (Training Compute, Model Pricing, ...) means appending an
entry to DOMAINS and dropping a plot index CSV in place - the root page and the
per-domain gallery both pick it up without touching any HTML.

Usage:
    python build/build_site.py
"""
import csv
import html
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------- domains
# 'live' domains are built from a plot index; 'planned' render as placeholders
# on the root page only. Nothing is claimed to exist before it does.
DOMAINS = [
    {
        "slug": "inference-tokens",
        "title": "Inference Tokens",
        "blurb": "Total tokens processed when models answer requests, across the US "
                 "enterprise market. Everything except training.",
        "index": "build/plot_index.csv",
        "live": True,
    },
    {"slug": "training-compute", "title": "Training Compute", "live": False},
    {"slug": "model-pricing", "title": "Model Pricing", "live": False},
    {"slug": "ai-infrastructure", "title": "AI Infrastructure", "live": False},
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


def assign(plots):
    """Bucket each plot into a section by its methodology reference."""
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
    parts.append('<div class="chart-head">')
    parts.append(f'<a class="pid" href="#{e(pid)}">{e(pid)}</a>')
    parts.append(f"<h3>{e(title)}</h3>")
    parts.append("</div>")
    if lead:
        parts.append(f'<p class="shows">{e(lead)}</p>')

    if has_svg:
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

    if has_svg or has_png:
        links = []
        if has_svg:
            links.append(f'<a href="charts/{e(pid)}.svg" download>Download SVG</a>')
        if has_png:
            links.append(f'<a href="charts/{e(pid)}.png" download>Download PNG</a>')
        parts.append(f'<p class="downloads">{"".join(links)}</p>')

    parts.append("</section>")
    return "\n".join(parts)


def build_gallery(dom):
    plots = load_plots(dom["index"])
    sections = assign(plots)
    built = sum(1 for p in plots if chart_files(dom["slug"], p["Plot_ID"])[0])

    body = []
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
        body.append(f"<h2>{e(name)}</h2>")
        if blurb:
            body.append(f'<p class="blurb">{e(blurb)}</p>')
        for p in ps:
            body.append(render_chart(dom["slug"], p))
        body.append("</div>")

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(dom['title'])} — Visual Evidence Gallery — AI Data Room</title>
<meta name="description" content="{e(dom['blurb'])}">
<link rel="stylesheet" href="{CSS}">
</head>
<body>
<div class="wrap">

<header class="masthead">
  <p class="eyebrow"><a href="../">AI Data Room</a> &nbsp;/&nbsp; Visual Evidence</p>
  <h1>{e(dom['title'])}</h1>
  <p class="standfirst">{e(dom['blurb'])}</p>
  <dl class="meta">
    <div><dt>Charts catalogued</dt><dd>{len(plots)}</dd></div>
    <div><dt>Charts published</dt><dd>{built}</dd></div>
    <div><dt>Sections</dt><dd>{len(sections)}</dd></div>
    <div><dt>Headline estimate</dt><dd>60–100 quadrillion tokens/yr</dd></div>
  </dl>
</header>

{chr(10).join(body)}

<footer class="foot">
  <p><strong>How to read this gallery.</strong> Every chart carries a stable Plot ID
  matching the Dataset Register. Link straight to any chart by appending its ID, for
  example <code>#P-01</code>. Charts marked Pending are catalogued and specified but not
  yet generated.</p>
  <p><strong>On the headline figure.</strong> The 60–100 quadrillion tokens per year
  range, central scenario approximately 75 quadrillion, is a modelled estimate combining
  four estimation methods. It is not a measured figure — no official global dataset
  exists.</p>
  <p><strong>Methodology references.</strong> Section references shown against each chart
  are taken from the working methodology. They become links once that document is final.</p>
</footer>

</div>
</body>
</html>
"""
    out = REPO / dom["slug"] / "index.html"
    out.write_text(page, encoding="utf-8")
    print(f"  {out.relative_to(REPO)}  —  {len(plots)} plots, {built} published, "
          f"{len(sections)} sections")
    return len(plots), built


def build_root(stats):
    cards = []
    for dom in DOMAINS:
        if dom["live"]:
            total, built = stats[dom["slug"]]
            cards.append(f"""    <div class="domain live">
      <h2>{e(dom['title'])}</h2>
      <p>{e(dom['blurb'])}<br><strong>{built}</strong> of {total} charts published.</p>
      <a class="btn" href="{e(dom['slug'])}/">Open {e(dom['title'])} Gallery</a>
    </div>""")
        else:
            cards.append(f"""    <div class="domain planned">
      <h2>{e(dom['title'])}</h2>
      <p>Not yet published.</p>
      <span class="status">Planned</span>
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
  <p class="standfirst">Visual evidence supporting AI demand research. Each domain below
  holds a catalogue of charts, every one carrying a stable identifier, a named source and
  a methodology reference, so any figure can be traced back to where it came from.</p>
</header>

<div class="domains">
{chr(10).join(cards)}
</div>

<footer class="foot">
  <p>Charts are generated from source data and published here with stable URLs. A chart's
  address does not change as the gallery grows, so a link made today keeps working.</p>
  <p>Domains marked Planned do not yet contain published charts.</p>
</footer>

</div>
</body>
</html>
"""
    (REPO / "index.html").write_text(page, encoding="utf-8")
    print(f"  index.html  —  {sum(1 for d in DOMAINS if d['live'])} live, "
          f"{sum(1 for d in DOMAINS if not d['live'])} planned")


def main():
    print("building site")
    stats = {}
    for dom in DOMAINS:
        if dom["live"]:
            stats[dom["slug"]] = build_gallery(dom)
    build_root(stats)


if __name__ == "__main__":
    main()
