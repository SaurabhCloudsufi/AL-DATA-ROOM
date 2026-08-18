# AI Data Room

Client-facing visual evidence for AI demand research.

Each chart published here carries a stable identifier, a named source and a
methodology reference, so any figure on the site can be traced back to where it
came from. The site is static HTML — no login, no tooling, no code required to
read it.

**Live site:** https://saurabhcloudsufi.github.io/AL-DATA-ROOM/

---

## What is published

The Azure inference token distributions, one chart per trace release:

| Plot ID | Chart | Dataset |
|---|---|---|
| [`P-1`](https://saurabhcloudsufi.github.io/AL-DATA-ROOM/inference-tokens/#P-1) | Input and output tokens per request — 2023 | Azure LLM inference production traces, 2023 release |
| [`P-2`](https://saurabhcloudsufi.github.io/AL-DATA-ROOM/inference-tokens/#P-2) | Input and output tokens per request — 2024 | Azure LLM inference production traces, 2024 release |
| [`P-3`](https://saurabhcloudsufi.github.io/AL-DATA-ROOM/inference-tokens/#P-3) | Input and output tokens per request — 2025 | Azure multimodal (LMM) inference traces, 2025 release |

Each chart pairs the distribution with its cumulative curve, so the shape reads
off the left panel and any percentile off the right.

The published set is driven by `build/plot_index_published.csv`, not by the Excel
workbook. `P-1` was previously published as `P-59`; that anchor is retained on the
page so links already shared keep resolving.

The site shows only charts that have actually been generated. Work that is
catalogued but not yet produced does not appear on the page at all — no Pending
placeholders, no planned-domain cards. Nothing is advertised before it exists.

---

## Inference Tokens

The total number of tokens processed when AI models answer requests, across the
US enterprise market, over a given period. Everything except training.

`build/plot_index.csv` remains the full catalogue of **69 charts**, `P-01`
through `P-69`, grouped into six sections that follow the estimation methods in
the methodology. That catalogue is the working inventory and is no longer what
the site renders — the gallery reads `build/plot_index_published.csv` instead.
Setting `PUBLISHED_ONLY = False` in `build/build_site.py` renders whichever index
is configured in full, with Pending placeholders for anything not yet generated.

### Azure trace releases

| Release | Files | Requests | Observation window |
|---|---|---|---|
| 2023 | conv, code | 28,185 | 16 Nov 2023, a single 58-minute window |
| 2024 | conv, code | see chart | one week, May 2024 |
| 2025 | multimodal | 1,000,000 | 15–22 Oct 2024 (released 2025) |

The 2024 pair is ~1.8 GB. `summarise_azure_traces.py` streams it in chunks and
derives exact quantiles from an integer value-count table, so **nothing is
sampled** — the chunked result is identical to loading the files whole, which is
verified against the 2023 aggregates on every run.

---

## AI Chip Components

Epoch AI's estimates of how much advanced-node logic wafer capacity, CoWoS
packaging and HBM memory the leading AI chip designers — NVIDIA, Google (TPUs),
Amazon (Trainium) and AMD — consumed each quarter, and what share of world supply
that was. Source: [Epoch AI, AI Chip Components](https://epoch.ai/data/ai-chip-components)
(CC-BY).

**20 charts**, in two sections:

| IDs | Section | What they are |
|---|---|---|
| `CHIP-01` – `CHIP-14` | Epoch AI — Published Visualizations | Epoch's own configurable figure at each of its distinct settings: the four tabs (Total cost, Logic, Packaging, Memory) crossed with colour by component or designer, absolute or share, quarterly or annual, running or cumulative |
| `CHIP-D01` – `CHIP-D06` | Derived Analysis | Questions the explorer's settings cannot answer — the three components on one axis, component mix by designer, chip-level concentration, the published uncertainty, packaging intensity, and demand growth against supply growth |

Two rules hold across all 20:

- **Complete quarters only.** The download runs to Q1 2026, but that quarter
  carries 3 designers of 5 and 7 chip types of 17, with no supply denominator.
  Charting it would show a collapse in demand that is missing coverage, not a
  fall. The window is Q1 2024 – Q4 2025, which is also the range Epoch's own
  chart covers. The excluded rows are counted in `chip_summary.csv`.
- **Nothing is projected.** Epoch's own *Project trend* control is disabled at
  source, and no value here is extrapolated, imputed or filled.

Every quantity is published as a 5th percentile, median and 95th percentile,
because Epoch's figures come out of a 10,000-draw Monte Carlo. All three are
carried through `summarise_epoch_chip_components.py`; the charts plot medians and
`CHIP-D04` plots the intervals. Medians do not add — Epoch simulates each
aggregation separately — so each chart reads the file published at its own grain,
and the two measured divergences (0.71% across grain, 0.44% across quarters) are
recorded in `chip_summary.csv` and stated on the charts that are affected.

```bash
python build/summarise_epoch_chip_components.py   # raw CSVs → derived series
python build/generate_charts.py CHIP-01 …          # derived series → SVG + PNG
python build/build_site.py                         # → ai-chip-components/index.html
```

---

## AI Models

Epoch AI's record of the models themselves — how much compute, data, money, time
and power went into training each one, who built it, and how it was released.
Source: [Epoch AI, Data on AI Models](https://epoch.ai/data/ai-models) (CC-BY),
four releases downloaded into `ai_models/`:

| File | Models | What it is |
|---|---|---|
| `notable_ai_models.csv` | 1,043 | Epoch's notability threshold: a state-of-the-art result, over 1,000 citations, historical significance or significant use |
| `frontier_ai_models.csv` | 137 | Top 10 by training compute at the time of release |
| `large_scale_ai_models.csv` | 524 | Trained with more than 1e23 FLOP — the threshold used in several regulatory frameworks |
| `all_ai_models.csv` | 3,574 | The full database, notable or not |

**24 charts**, in two sections:

| IDs | Section | What they are |
|---|---|---|
| `MODELS-01` – `MODELS-13` | Epoch AI — Published Visualizations | Epoch publishes one configurable figure: a metric against publication date, over a chosen release, optionally coloured by domain, organization or country. These are that figure at each of its settings — four releases, six metrics, three colourings, plus the metric-against-metric view |
| `MODELS-D01` – `MODELS-D11` | Derived Analysis | Questions the published figure does not answer — doubling times by metric, where models come from, who builds them, industry against academia, how weights are released, training hardware by year, chips per run, cost against compute, hardware price-performance, domain mix, and what the record actually contains |

One rule holds across all 24, and it is the reason the plotted count differs from
chart to chart:

> **A model appears in a chart only where Epoch records the value being plotted.**
> Training compute is recorded for 534 of the 1,043 notable models, cost for 180.
> The other rows are absent from those charts — never imputed, back-filled, or
> carried across from a related model. Every chart states its own n against the
> release total, and `MODELS-D11` plots the coverage of every field directly.

Multi-valued fields (Domain, Country, Organization categorization) list one entry
per contributing organisation and are collapsed by de-duplication, never by
picking a winner: one distinct value keeps it, several become `Multinational` or
`Industry-academia collaboration`, and a model tagged `Multimodal` is counted
there rather than under each component domain.

Trend lines are fitted by ordinary least squares through log10 of the metric
against publication date, over the deep learning era (2010 onward) and over the
plotted points only. Each is drawn with its n and r² on the chart face, is never
extended past the last observation, and is refused entirely below 12 points. The
frontier fit reproduces Epoch's published finding: 4.6× per year, doubling every
5.4 months, r² = 0.97.

`MODELS-01` to `MODELS-05` and `MODELS-13` also ship an interactive companion —
hover a point to identify the model, click a legend entry to drop that group —
generated by `generate_interactive_models.py` and checked end to end by
`verify_interactive_models.mjs`.

```bash
python build/summarise_epoch_models.py        # ai_models/*.csv → ai-models/data/
python build/generate_charts.py MODELS-01 …   # derived tables → SVG + PNG
python build/generate_interactive_models.py   # → self-contained MODELS-NN.html
python build/build_site.py                    # → ai-models/index.html
node build/verify_interactive_models.mjs      # optional, needs jsdom
```

The four raw Epoch CSVs stay out of the repository, as with every other working
dataset here; `ai-models/data/` carries the derived tables the charts read,
including one row per model with every plotted value, so any figure can be
checked without the download. To rebuild from source, put the four files back in
`ai_models/` from the link above.

---

## Structure

```
ai-data-room/
├── index.html                  landing page (generated)
├── inference-tokens/
│   ├── index.html              gallery (generated)
│   ├── charts/                 P-1.svg, P-1.png, P-2.*, P-3.*
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
│   ├── plot_index.csv           the workbook catalogue (69 rows, unpublished)
│   ├── plot_index_published.csv what the site actually renders
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

The gallery HTML is generated, never hand-edited. The published set is chosen by
`build/plot_index_published.csv`; the Excel register still drives
`build/plot_index.csv`, which is kept for reference.

`build/` holds builders for charts that are not currently published. Running
`python build/generate_charts.py` with no arguments rebuilds all of them, and
they would then reappear on the site at the next `build_site.py`. Pass an
explicit Plot ID to avoid that.

---

## Linking to a chart

Every chart has an anchor matching its Plot ID:

```
https://saurabhcloudsufi.github.io/AL-DATA-ROOM/inference-tokens/#P-1
```

These addresses are stable. Adding charts or new domains does not change them, so
a link made today keeps working.

---

## Rebuilding the site

```bash
python build/summarise_azure_traces.py ~/data/azure-traces   # derive aggregates
python build/generate_charts.py P-1 P-2 P-3                  # regenerate charts
python build/build_site.py                                   # rebuild HTML
```

Requires `python3` with `matplotlib`, `pandas` and `openpyxl`.

Chart output is deterministic: re-running `generate_charts.py` on unchanged input
produces byte-identical SVG and PNG, so a git diff only ever shows a real change.

## Adding a chart

1. Add a row to `build/plot_index_published.csv` with its Plot ID, title, dataset,
   granularity, year, source and methodology reference.
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
