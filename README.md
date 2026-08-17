# AI Data Room

Client-facing visual evidence for AI demand research.

Each chart published here carries a stable identifier, a named source and a
methodology reference, so any figure on the site can be traced back to where it
came from. The site is static HTML — no login, no tooling, no code required to
read it.

**Live site:** https://saurabhcloudsufi.github.io/AL-DATA-ROOM/

---

## Domains

| Domain | Status | Gallery |
|---|---|---|
| **Inference Tokens** | Published | [`/inference-tokens/`](inference-tokens/) |
| Training Compute | Planned | — |
| Model Pricing | Planned | — |
| AI Infrastructure | Planned | — |
| Energy | Planned | — |

Domains marked Planned have no published charts. They appear on the landing page
as placeholders so the structure is visible, not to imply work that does not exist.

---

## Inference Tokens

The total number of tokens processed when AI models answer requests, across the
US enterprise market, over a given period. Everything except training.

The gallery catalogues **69 charts**, identified `P-01` through `P-69`, grouped
into six sections that follow the estimation methods in the methodology:
provider throughput, pricing and model economics, capacity and infrastructure,
coverage gaps, validation and cross-check, and composition of the total.

Charts that have been generated appear as images. Charts that are catalogued and
specified but not yet produced render as **Pending** placeholders — the gallery
never shows an image for a chart that does not exist.

### Headline figure

60–100 quadrillion tokens per year, central scenario approximately 75
quadrillion. This is a modelled estimate combining four estimation methods, not a
measured figure — no official global dataset exists. Every chart that carries it
says so.

---

## Structure

```
ai-data-room/
├── index.html                  landing page (generated)
├── inference-tokens/
│   ├── index.html              gallery (generated)
│   ├── charts/                 P-01.svg, P-01.png, ...
│   ├── assets/style.css        shared stylesheet
│   └── data/                   public source data for reproducibility
├── build/
│   ├── export_from_workbook.py Excel register  →  CSV
│   ├── generate_charts.py      CSV  →  chart SVG + PNG
│   ├── build_site.py           plot index + charts  →  HTML
│   └── plot_index.csv          the chart catalogue
├── notebooks/
│   └── Inference_Tokens_Chart_Generation.ipynb
└── README.md
```

### How the pieces relate

```
Excel Dataset Register     the inventory of datasets and charts
        │
        ├─ export_from_workbook.py ─→ build/plot_index.csv
        │                             inference-tokens/data/*.csv
        │
        ├─ generate_charts.py ──────→ inference-tokens/charts/P-NN.svg + .png
        │
        └─ build_site.py ───────────→ index.html + inference-tokens/index.html
```

The Excel register is the source of truth for which charts exist. The gallery
HTML is generated, never hand-edited, so the site cannot drift out of step with
the catalogue.

---

## Linking to a chart

Every chart has an anchor matching its Plot ID:

```
https://saurabhcloudsufi.github.io/AL-DATA-ROOM/inference-tokens/#P-01
```

These addresses are stable. Adding charts or new domains does not change them, so
a link made today keeps working.

---

## Rebuilding the site

```bash
python build/export_from_workbook.py path/to/register.xlsx   # refresh catalogue
python build/generate_charts.py                              # regenerate charts
python build/generate_charts.py P-01                         # or just one
python build/build_site.py                                   # rebuild HTML
```

Requires `python3` with `matplotlib`, `pandas` and `openpyxl`.

## Adding a chart

1. Confirm the Plot ID exists in `build/plot_index.csv`. Charts are never invented
   outside the catalogue.
2. Add a builder function in `build/generate_charts.py`, or a cell in the
   notebook, that loads the **real** source data. If the data is not available,
   request it rather than substituting another dataset.
3. Save as `P-NN.svg` and `P-NN.png` in the domain's `charts/` directory.
4. Run `build/build_site.py`. The chart replaces its Pending placeholder.

## Adding a domain

Append an entry to `DOMAINS` in `build/build_site.py` with a slug, title and plot
index path, then create `<slug>/charts/`. The landing page and the new gallery
are generated from there. No existing HTML changes, and no existing URL moves.

---

## Data and disclosure

`inference-tokens/data/company_disclosures.csv` contains figures that companies
published themselves — earnings calls, earnings releases, SEC exhibits, official
announcements — each with a link to its primary source. It is committed so the
charts are reproducible.

Working datasets that are not cleared for public release are **not** committed to
this repository. Where a chart depends on one, the chart output is published but
the underlying file stays in the private project store. See `.gitignore`.

---

## Methodology references

Section references shown against each chart (for example `§7.3 — Method 1,
Direct Provider Throughput`) come from the working methodology document. They are
plain text for now and become links once that document is finalised; the HTML
already carries a `data-methodology-ref` attribute on each one so they can be
converted in a single pass.
