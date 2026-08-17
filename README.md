# AI Data Room

Client-facing visual evidence for AI demand research.

Each chart published here carries a stable identifier, a named source and a
methodology reference, so any figure on the site can be traced back to where it
came from. The site is static HTML — no login, no tooling, no code required to
read it.

**Live site:** https://saurabhcloudsufi.github.io/AL-DATA-ROOM/

---

## What is published

One chart, in the Inference Tokens gallery:

| Plot ID | Chart | Dataset |
|---|---|---|
| [`P-59`](https://saurabhcloudsufi.github.io/AL-DATA-ROOM/inference-tokens/#P-59) | Input and output token distributions | Microsoft Azure — LLM inference production traces, 2023 release |

The site shows only charts that have actually been generated. Work that is
catalogued but not yet produced does not appear on the page at all — no Pending
placeholders, no planned-domain cards. Nothing is advertised before it exists.

---

## Inference Tokens

The total number of tokens processed when AI models answer requests, across the
US enterprise market, over a given period. Everything except training.

`build/plot_index.csv` remains the full catalogue of **69 charts**, `P-01`
through `P-69`, grouped into six sections that follow the estimation methods in
the methodology. That catalogue is the working inventory; it is not published to
the site. Setting `PUBLISHED_ONLY = False` in `build/build_site.py` renders the
whole catalogue again, with Pending placeholders for anything not yet generated.

---

## Structure

```
ai-data-room/
├── index.html                  landing page (generated)
├── inference-tokens/
│   ├── index.html              gallery (generated)
│   ├── charts/                 P-59.svg, P-59.png
│   ├── assets/style.css        shared stylesheet
│   └── data/                   derived public data backing the charts
│       ├── azure_trace_summary.csv
│       └── azure_trace_histograms.csv
├── build/
│   ├── export_from_workbook.py  Excel register  →  CSV
│   ├── summarise_azure_traces.py  raw traces  →  derived aggregates
│   ├── generate_charts.py       CSV  →  chart SVG + PNG
│   ├── build_site.py            plot index + charts  →  HTML
│   ├── update_excel_links.py    gallery URLs  →  workbook
│   ├── plot_index.csv           the chart catalogue (69 rows)
│   └── company_disclosures.csv  23 verified company disclosures
├── notebooks/
│   └── Inference_Tokens_Chart_Generation.ipynb
└── README.md
```

### How the pieces relate

```
Excel Dataset Register     the inventory of datasets and charts
        │
        ├─ export_from_workbook.py ─→ build/plot_index.csv
        │
        ├─ summarise_azure_traces.py ─→ inference-tokens/data/*.csv
        │
        ├─ generate_charts.py ──────→ inference-tokens/charts/P-NN.svg + .png
        │
        └─ build_site.py ───────────→ index.html + inference-tokens/index.html
```

The Excel register is the source of truth for which charts exist. The gallery
HTML is generated, never hand-edited.

`build/` holds builders for charts that are not currently published. Running
`python build/generate_charts.py` with no arguments rebuilds all of them, and
they would then reappear on the site at the next `build_site.py`. Pass an
explicit Plot ID to avoid that.

---

## Linking to a chart

Every chart has an anchor matching its Plot ID:

```
https://saurabhcloudsufi.github.io/AL-DATA-ROOM/inference-tokens/#P-59
```

These addresses are stable. Adding charts or new domains does not change them, so
a link made today keeps working.

---

## Rebuilding the site

```bash
python build/summarise_azure_traces.py ~/data/azure-traces   # derive aggregates
python build/generate_charts.py P-59                         # regenerate a chart
python build/build_site.py                                   # rebuild HTML
```

Requires `python3` with `matplotlib`, `pandas` and `openpyxl`.

Chart output is deterministic: re-running `generate_charts.py` on unchanged input
produces byte-identical SVG and PNG, so a git diff only ever shows a real change.

## Adding a chart

1. Confirm the Plot ID exists in `build/plot_index.csv`. Charts are never invented
   outside the catalogue.
2. Add a builder function in `build/generate_charts.py`, or a cell in the
   notebook, that loads the **real** source data. If the data is not available,
   request it rather than substituting another dataset.
3. Save as `P-NN.svg` and `P-NN.png` in the domain's `charts/` directory.
4. Run `build/build_site.py`. The chart appears on the page; nothing else moves.

## Adding a domain

Append an entry to `DOMAINS` in `build/build_site.py` with a slug, title and plot
index path, then create `<slug>/charts/`. The landing page and the new gallery
are generated from there. No existing HTML changes, and no existing URL moves.

---

## Data and disclosure

`inference-tokens/data/` carries only derived aggregates — the small, public,
chart-backing files. The Azure trace summaries are re-derivable byte for byte
from Microsoft's published traces (CC-BY) using
`build/summarise_azure_traces.py`, so every plotted value can be checked against
its source.

`build/company_disclosures.csv` records 23 figures that companies published
themselves — earnings calls, earnings releases, SEC exhibits, official
announcements — each with a link to its primary source.

Working datasets that are not cleared for public release are **not** committed to
this repository. Where a chart depends on one, the chart output is published but
the underlying file stays in the private project store. See `.gitignore`.

---

## Methodology references

Section references shown against each chart (for example `§7.9 — De-duplication
rule 3`) come from the working methodology document. They are plain text for now
and become links once that document is finalised; the HTML already carries a
`data-methodology-ref` attribute on each one so they can be converted in a single
pass.
