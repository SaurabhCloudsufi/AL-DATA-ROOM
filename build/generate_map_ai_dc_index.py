#!/usr/bin/env python3
"""Emit the interactive AI DC INDEX world map as one self-contained HTML file.

Reads ai-dc-index/data/dc_index_sites.csv and build/world_110m.json and writes
ai-dc-index/charts/DCMAP-01.html. No CDN, no tile server, no API key, no network
at view time - the same rule every other chart in this gallery follows.

WHAT IS PORTED FROM EPOCH'S MAP, AND WHY
----------------------------------------
- Area-proportional radius, r = sqrt(MW) * K * shrink(zoom), with the circles
  shrunk to ~45% at world view and full size when zoomed in. Without the shrink
  term a world view of 294 sites is a single blob; with it, the same encoding
  reads at both altitudes.
- Draw order by descending value, so the biggest circles sit underneath and a
  small site inside a large one stays hoverable.
- A translucent uncertainty halo sized in GROUND units, not pixels, so it grows
  as you zoom the way a real radius of confusion does. Epoch uses this for
  location-fuzzed sites; here it carries geo_precision, and it is the honest way
  to draw the 39 rows that resolve only to a region or a country centroid.
- A size legend on nice-number rings, and a colour legend built from what is
  actually inside the viewport, re-derived on every pan.
- Hover bubble on the mark; click to pin a detail card.

Epoch nests its legend circles and culls any whose labels would collide. That
needs 2*(r_i - r_{i+1}) of clear vertical space per label, and under a sqrt scale
at world zoom the smallest ring here is narrower than its own label, so it gets
covered - the cull then drops it and the legend degrades to one ring. These sit
side by side on a shared baseline instead, which holds all three at every zoom.

WHAT IS DELIBERATELY NOT PORTED
-------------------------------
Epoch animates per-site growth because it has 3,209 dated timeline rows. This
dataset has one `start_year` per site and no capacity curve, so the slider is a
cumulative step - "what exists by year Y" - and circles do not grow. Inventing a
growth curve between start_year and today would be fabrication.

74 sites carry no start_year. They are shown at every step rather than hidden,
and the count is stated under the slider, because dropping a real site for a
blank field would understate every year.

52 sites carry no megawatts. A circle has no size without one, so they are not
drawn; the count is stated in the footer.

COLOUR
------
Light-only, matching every other chart in this gallery. The categorical hues are
the first six slots that pass the all-pairs validator on a light surface (a map
is a bubble field - any two marks can end up adjacent, so the adjacent-pair
list does not apply).

Build status is a progression, so it started on a single-hue ordinal ramp. That
was wrong in practice: four steps of one blue are not separable on marks this
small, which is the whole job of the control. It now uses four distinct
validated hues ordered to read intuitively - green running, amber building, blue
committed, violet announced.

Usage:
    python build/generate_map_ai_dc_index.py
"""
import csv
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SITES = REPO / "ai-dc-index" / "data" / "dc_index_sites.csv"
WORLD = REPO / "build" / "world_110m.json"
OUT = REPO / "ai-dc-index" / "charts" / "DCMAP-01.html"

PLOT_ID = "DCMAP-01"
TITLE = "AI data centres worldwide, by announced capacity"
SUBTITLE = ("Every site in the AI DC INDEX, sized by announced IT capacity. "
            "Drag to pan, scroll to zoom, drag the year to see what existed when.")
SOURCE = "AI DC INDEX (compiled from company, regulator and trade-press disclosures)"

YEAR_FLOOR = 2015   # 33 sites predate this; they read as "already there" at step one

# Categorical slots, in assignment order. Validated light-surface, --pairs all:
# worst normal-vision dE 15.6, worst CVD dE 6.1 (slot 6 only) - the warn band is
# carried with direct labels in the legend, hover and card, per the relief rule.
CATEGORICAL = ["#2a78d6", "#eda100", "#008300", "#4a3aa7", "#1baf7a", "#e87ba4"]
NEUTRAL = "#b8b6ae"          # Other / Unknown - never a categorical slot

# Build status. This began as a single-hue ordinal ramp, since the four stages
# are a progression - but four steps of one blue are hard to tell apart on marks
# this small, which is the whole job of the control. Distinct hues instead,
# ordered so the reading is intuitive: green is running, amber is being built,
# blue is committed, violet is only announced. Validated light-surface,
# --pairs all: worst normal-vision dE 16.3, worst CVD dE 13.0.
STATUS_RAMP = {
    "Operational": "#008300",
    "Under construction": "#eda100",
    "Planned": "#2a78d6",
    "Announced": "#4a3aa7",
    "Unknown": NEUTRAL,
}
STATUS_ORDER = ["Operational", "Under construction", "Planned", "Announced", "Unknown"]
ENERGY_ORDER = ["Renewable", "Nuclear", "Gas", "Grid", "Mixed", "Unknown"]
FOCUS_ORDER = ["Training & inference", "Training", "Inference", "HPC",
               "General cloud", "AI (unspecified)", "Unknown"]

# Ground radius, in metres, implied by each geo_precision level.
HALO_M = {"exact": 0, "city": 12000, "region": 120000, "country": 500000}

# Mark geometry. Defined once here and injected into the page script, so the
# static SVG/PNG fallbacks below cannot drift from what the interactive draws.
RADIUS_K = 0.35        # r = sqrt(MW) * K * shrink(zoom)
MIN_R = 2.0            # a 1 MW site still has to be clickable
SHRINK_FLOOR = 0.45    # circle scale at world view
SHRINK_SPAN = 3.0      # zoom doublings over which shrink climbs to 1

STATIC_W, STATIC_H = 1180, 620


def load_sites():
    with SITES.open() as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if not r["lat"] or not r["lng"]:
            continue
        out.append({
            "id": r["id"], "t": r["title"],
            "mw": float(r["megawatts"]) if r["megawatts"] else None,
            "c": r["primary_company"], "cs": r["companies"],
            "co": r["country"], "rg": r["region"], "ci": r["city"],
            "st": r["status_class"], "sr": r["status_raw"],
            "en": r["energy_class"], "er": r["energy_raw"],
            "fo": r["focus_class"], "fr": r["focus_raw"],
            "y": int(r["start_year"]) if r["start_year"] else None,
            "lat": float(r["lat"]), "lng": float(r["lng"]),
            "p": r["geo_precision"], "u": r["source_url"],
        })
    return out


def colour_scheme(sites):
    """Build the colour-by schemes, capping categorical dimensions at six hues."""
    def by_capacity(key):
        agg = {}
        for s in sites:
            agg[s[key]] = agg.get(s[key], 0) + (s["mw"] or 0)
        return [k for k, _ in sorted(agg.items(), key=lambda kv: -kv[1])]

    top_companies = [c for c in by_capacity("c") if c and c != "Unknown"][:len(CATEGORICAL)]
    companies = {c: CATEGORICAL[i] for i, c in enumerate(top_companies)}

    def fixed(order):
        out, i = {}, 0
        for name in order:
            if name == "Unknown":
                out[name] = NEUTRAL
            else:
                out[name] = CATEGORICAL[i]
                i += 1
        return out

    return {
        "none": {"label": "None", "colors": {}, "single": CATEGORICAL[0]},
        "c": {"label": "Company", "colors": companies, "single": None},
        "st": {"label": "Build status", "colors": STATUS_RAMP, "single": None,
               "order": STATUS_ORDER},
        "en": {"label": "Energy", "colors": fixed(ENERGY_ORDER), "single": None,
               "order": ENERGY_ORDER},
        "fo": {"label": "AI focus", "colors": fixed(FOCUS_ORDER), "single": None,
               "order": FOCUS_ORDER},
    }


# The dataset's country names against Natural Earth's. Only two disagree; the
# three that are absent from 110m geometry (Singapore, Hong Kong, Bahrain) are
# genuinely too small to carry an outline at this resolution.
GEO_ALIAS = {"United States": "United States of America", "Czech Republic": "Czechia"}


def hot_countries(sites):
    """Geometry country name -> capacity held, so labels follow the data."""
    agg = {}
    for s in sites:
        if not s["mw"]:
            continue
        name = GEO_ALIAS.get(s["co"], s["co"])
        agg[name] = agg.get(name, 0) + s["mw"]
    return {k: round(v, 1) for k, v in agg.items()}


def facets(sites):
    """Filter facets, each counted from the data and ordered by site count."""
    def group(key, order=None):
        counts = {}
        for s in sites:
            counts[s[key]] = counts.get(s[key], 0) + 1
        keys = (order if order else
                sorted(counts, key=lambda k: (-counts[k], k)))
        return [{"id": k, "n": counts[k]} for k in keys if k in counts]

    return [
        {"id": "co", "label": "Country", "options": group("co")},
        {"id": "c", "label": "Company", "options": group("c")},
        {"id": "st", "label": "Build status", "options": group("st", STATUS_ORDER)},
        {"id": "en", "label": "Energy", "options": group("en", ENERGY_ORDER)},
        {"id": "fo", "label": "AI focus", "options": group("fo", FOCUS_ORDER)},
    ]


HTML = r"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    color-scheme: light;
    --surface: #fcfcfb; --plane: #f9f9f7;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --hair: #e1e0d9; --axis: #c3c2b7; --ring: rgba(11,11,11,.10);
    --land: #edece7; --land-line: #d9d7d0;
    --pid: #1f3864;
  }
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; }
  body { background:var(--surface); color:var(--ink);
         font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
  #pg { padding:14px 16px 10px; }

  .hd { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:2px; }
  .pid { font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--pid);
         letter-spacing:.04em; }
  h1 { font-size:15px; margin:0; font-weight:700; }
  .sub { color:var(--ink-2); font-size:12px; margin:2px 0 10px; max-width:88ch; }

  /* ---------------------------------------------------------- controls */
  .ctl { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px; }
  .ctl input[type=search], .ctl button, .ctl select {
    font:inherit; font-size:12.5px; color:var(--ink); background:#fff;
    border:1px solid var(--axis); border-radius:6px; padding:6px 9px; height:30px; }
  .ctl input[type=search] { flex:1 1 260px; min-width:180px; }
  .ctl button { cursor:pointer; }
  .ctl button:hover { border-color:var(--ink-2); }
  .ctl .count { margin-left:auto; color:var(--ink-2); font-size:12px; white-space:nowrap; }
  .badge { display:inline-block; min-width:16px; text-align:center; background:var(--pid);
           color:#fff; border-radius:999px; font-size:10.5px; font-weight:700;
           padding:1px 5px; margin-left:5px; }

  .pop { position:absolute; z-index:40; background:#fff; border:1px solid var(--axis);
         border-radius:8px; box-shadow:0 6px 24px rgba(0,0,0,.13); padding:10px 12px;
         max-height:340px; overflow:auto; min-width:220px; }
  .pop h4 { margin:0 0 6px; font-size:11px; letter-spacing:.04em; text-transform:uppercase;
            color:var(--muted); font-weight:700; }
  .pop label { display:flex; gap:7px; align-items:center; padding:3px 0; font-size:12.5px;
               cursor:pointer; }
  .pop label span.n { margin-left:auto; color:var(--muted); font-size:11px; }
  .pop .grp + .grp { margin-top:10px; border-top:1px solid var(--hair); padding-top:9px; }
  .pop .clear { float:right; font-size:11px; color:var(--pid); background:none; border:none;
                cursor:pointer; padding:0; text-decoration:underline; }

  /* --------------------------------------------------------------- map */
  .wrap { position:relative; border:1px solid var(--hair); border-radius:8px;
          overflow:hidden; background:var(--plane); }
  svg.map { display:block; width:100%; height:520px; touch-action:none; cursor:grab; }
  svg.map.drag { cursor:grabbing; }
  .land { fill:var(--land); stroke:var(--land-line); stroke-width:.6; stroke-linejoin:round; }
  .halo { stroke:none; }
  .dot { stroke:rgba(11,11,11,.45); stroke-width:1; }
  .dot.dim { opacity:.18; }
  .dot.hot { stroke:var(--ink); stroke-width:1.8; }

  /* The legend sits UNDER the map, not floating over it. As an overlay it
     covered live sites - Pacific Northwest and the Nordics both sit exactly
     where a top-left panel lands - and a legend that hides data defeats itself. */
  .legend { display:flex; align-items:flex-end; gap:22px; flex-wrap:wrap;
            padding:9px 2px 0; border-top:1px solid var(--hair); margin-top:8px; }
  .legend .cap { font-size:10.5px; text-transform:uppercase; letter-spacing:.04em;
                 color:var(--muted); font-weight:700; display:block; }
  .legend .blk { display:flex; flex-direction:column; gap:3px; }
  .lg-circ { overflow:visible; }
  .lg-circ circle { fill:none; stroke:var(--muted); stroke-width:1; }
  .lg-circ text { font-size:10px; fill:var(--ink-2); text-anchor:middle; }
  .swatches { display:flex; align-items:center; gap:13px; flex-wrap:wrap; }
  .sw { display:flex; align-items:center; gap:5px; font-size:11.5px; color:var(--ink-2); }
  .sw i { width:11px; height:11px; border-radius:3px; flex:none;
          box-shadow:0 0 0 1px var(--ring) inset; }
  .sw b { font-weight:400; color:var(--ink); }

  /* Country names, drawn under the marks so a label never hides a site. */
  .cname { font-size:10.5px; fill:#8d8b84; text-anchor:middle; pointer-events:none;
           paint-order:stroke; stroke:var(--land); stroke-width:2.5px;
           stroke-linejoin:round; letter-spacing:.02em; }

  .zoom { position:absolute; top:10px; right:10px; display:flex; flex-direction:column;
          gap:4px; }
  .zoom button { width:27px; height:27px; font-size:15px; line-height:1; background:#fff;
                 border:1px solid var(--axis); border-radius:6px; cursor:pointer;
                 color:var(--ink); padding:0; }
  .zoom button:hover { border-color:var(--ink-2); }

  .bub { position:absolute; z-index:20; pointer-events:none; transform:translate(-50%,-100%);
         background:#fff; border:1.5px solid var(--ink); border-radius:5px; padding:4px 7px;
         font-size:11.5px; font-weight:700; white-space:nowrap; }
  .bub:after { content:""; position:absolute; left:50%; top:100%; transform:translateX(-50%);
               border:6px solid transparent; border-top-color:var(--ink); }
  .bub.pin { background:var(--ink); color:#fff; }
  .bub.pin:after { border-top-color:var(--ink); }

  .card { position:absolute; z-index:30; width:290px; background:#fff;
          border:1px solid var(--axis); border-radius:9px; padding:11px 13px;
          box-shadow:0 6px 24px rgba(0,0,0,.16); font-size:12px; }
  .card h3 { margin:0 0 2px; font-size:13.5px; line-height:1.3; }
  .card .loc { color:var(--ink-2); font-size:11.5px; margin-bottom:8px; }
  .card .big { font-size:20px; font-weight:700; line-height:1.1; }
  .card .big span { font-size:12px; font-weight:400; color:var(--ink-2); }
  .card dl { display:grid; grid-template-columns:auto 1fr; gap:3px 9px; margin:9px 0 0; }
  .card dt { color:var(--muted); font-size:11px; }
  .card dd { margin:0; font-size:11.5px; }
  .card .note { margin-top:8px; padding-top:7px; border-top:1px solid var(--hair);
                color:var(--ink-2); font-size:11px; line-height:1.4; }
  .card a { color:var(--pid); }
  .card .x { position:absolute; top:7px; right:9px; border:none; background:none;
             font-size:16px; line-height:1; color:var(--muted); cursor:pointer; padding:2px; }

  /* ---------------------------------------------------------- timeline */
  .tl { display:flex; align-items:center; gap:11px; margin-top:11px; }
  .tl button.play { width:31px; height:31px; flex:none; border-radius:50%; cursor:pointer;
                    border:none; background:var(--pid); color:#fff; font-size:12px; }
  .tl .edge { font-size:11.5px; color:var(--ink-2); white-space:nowrap; }
  .tl .track { position:relative; flex:1; }
  .tl input[type=range] { -webkit-appearance:none; appearance:none; width:100%; height:4px;
    background:linear-gradient(to right,var(--pid) 0,var(--pid) var(--fill,0%),
    var(--axis) var(--fill,0%),var(--axis) 100%); border-radius:2px; display:block;
    cursor:pointer; margin:0; padding-block:9px; background-clip:content-box; }
  .tl input[type=range]::-webkit-slider-thumb { -webkit-appearance:none; width:15px;
    height:15px; border-radius:50%; background:var(--pid); cursor:pointer; border:none; }
  .tl input[type=range]::-moz-range-thumb { width:15px; height:15px; border-radius:50%;
    background:var(--pid); cursor:pointer; border:none; }
  .tl .val { position:absolute; top:-4px; transform:translate(-50%,-100%); font-size:12px;
             font-weight:700; color:var(--ink); pointer-events:none; white-space:nowrap; }
  .tl .marks { position:absolute; top:26px; left:0; right:0; height:14px; pointer-events:none; }
  .tl .yr { position:absolute; transform:translateX(-50%); font-size:10.5px; color:var(--muted); }
  .tl .yr.now { color:var(--ink); font-weight:700; }
  .tl .tick { position:absolute; top:20px; width:1px; height:5px; background:var(--ink);
              transform:translateX(-50%); }

  .foot { margin-top:26px; color:var(--muted); font-size:11px; line-height:1.5;
          border-top:1px solid var(--hair); padding-top:8px; }
  .foot b { color:var(--ink-2); font-weight:600; }
  @media (max-width:640px){ svg.map { height:400px; } .legend { max-width:150px; } }
</style>

<div id="pg">
  <div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
  <p class="sub">__SUBTITLE__</p>

  <div class="ctl">
    <input type="search" id="q" placeholder="Search sites, companies, places...">
    <button id="fbtn" aria-expanded="false">Filter<span class="badge" id="fcount" hidden>0</span></button>
    <select id="cby" aria-label="Colour by"></select>
    <span class="count" id="count"></span>
  </div>

  <div class="wrap" id="wrap">
    <svg class="map" id="map"></svg>
    <div class="zoom">
      <button id="zin"  title="Zoom in">+</button>
      <button id="zout" title="Zoom out">&minus;</button>
      <button id="zfit" title="Reset view" style="font-size:11px">&#9673;</button>
    </div>
  </div>
  <div class="legend" id="legend"></div>

  <div class="tl">
    <button class="play" id="play" title="Play">&#9654;</button>
    <span class="edge" id="e0"></span>
    <div class="track">
      <div class="val" id="tlval"></div>
      <input type="range" id="year" step="1">
      <div class="marks" id="marks"></div>
    </div>
    <span class="edge" id="e1"></span>
  </div>

  <p class="foot" id="foot"></p>
</div>

<script>
const D = __DATA__;
const W = __WORLD__;

/* ============================================================ projection */
const clampLat = l => Math.max(-84, Math.min(84, l));
const mx = lng => (lng + 180) / 360;
const my = lat => { const s = Math.sin(clampLat(lat) * Math.PI / 180);
                    return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); };

const svg   = document.getElementById('map');
const wrap  = document.getElementById('wrap');
const NS    = 'http://www.w3.org/2000/svg';
let   view  = { cx: .5, cy: .42, k: 1 };   // centre in [0,1] mercator units, scale
let   size  = { w: 800, h: 520 };

const worldPx = () => size.w * view.k;
const sx = lng => (mx(lng) - view.cx) * worldPx() + size.w / 2;
const sy = lat => (my(lat) - view.cy) * worldPx() + size.h / 2;

/* Circles shrink at low zoom so a world view of 294 sites is not one blob, then
   reach full size once you are close enough for the area encoding to be read. */
const K = __RADIUS_K__, MINR = __MIN_R__, SFLOOR = __SHRINK_FLOOR__, SSPAN = __SHRINK_SPAN__;
const shrink = () => Math.max(SFLOOR,
  Math.min(1, SFLOOR + (1 - SFLOOR) * Math.log2(view.k) / SSPAN));
const radius = mw => Math.max(MINR, Math.sqrt(mw) * K * shrink());
/* Halo is a ground radius, so it must scale with zoom AND with the Mercator
   stretch at that latitude - the same correction Epoch applies to its fuzz. */
const haloR = s => {
  const m = HALO[s.p] || 0;
  if (!m) return 0;
  return m * worldPx() / (40075017 * Math.cos(clampLat(s.lat) * Math.PI / 180));
};
const HALO = __HALO__;

/* =============================================================== helpers */
const fmtMW = v => v >= 1000 ? (v / 1000).toFixed(v >= 10000 ? 0 : 1) + ' GW'
                             : Math.round(v).toLocaleString('en-US') + ' MW';
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* Nice-number rings for the size legend, largest first, as Epoch does it. */
function niceMax(v) {
  if (v <= 0) return 1;
  const t = Math.pow(10, Math.floor(Math.log10(v)));
  const step = v < 2 * t ? t / 10 : t;
  return parseFloat((Math.ceil(v / step) * step).toFixed(Math.max(0, Math.round(-Math.log10(step)))));
}
const rings = v => { const a = niceMax(v); return [...new Set([niceMax(a / 10), niceMax(a / 2.5), a])]
                       .filter(x => x > 0).sort((p, q) => q - p); };

/* ================================================================= state */
let state = { q: '', filters: {}, colorBy: 'none', year: null, pinned: null, hot: null };

const sites = D.sites;
const YEARS = D.years;
state.year = Math.min(D.today, YEARS[YEARS.length - 1]);

function matches(s) {
  const q = state.q.trim().toLowerCase();
  if (q) {
    const hay = [s.t, s.c, s.cs, s.co, s.rg, s.ci].join(' ').toLowerCase();
    if (!hay.includes(q)) return false;
  }
  for (const [dim, vals] of Object.entries(state.filters)) {
    if (vals.length && !vals.includes(s[dim])) return false;
  }
  // Undated sites stay visible at every step; hiding a real site for a blank
  // field would understate every year on the slider.
  if (s.y != null && s.y > state.year) return false;
  return true;
}

const scheme = () => D.schemes[state.colorBy];
function colourOf(s) {
  const sc = scheme();
  if (sc.single) return sc.single;
  return sc.colors[s[state.colorBy]] || '__NEUTRAL__';
}

/* ================================================================ render */
let layers = {};
/* Ring coordinates stay in this array, paired by index with the <path> nodes.
   Parking them in data- attributes instead would mean JSON.parse-ing all 279
   rings - ~9,900 points - on every drawLand(), and drawLand() runs on every
   pointermove of a drag and every wheel tick. */
let landRings = [];
function initSvg() {
  svg.replaceChildren();
  const g = document.createElementNS(NS, 'g');
  layers.land  = document.createElementNS(NS, 'g');
  layers.names = document.createElementNS(NS, 'g');
  layers.halo  = document.createElementNS(NS, 'g');
  layers.dots  = document.createElementNS(NS, 'g');
  g.append(layers.land, layers.names, layers.halo, layers.dots);
  svg.append(g);
  landRings = [];
  const paths = [];
  for (const f of W) for (const ring of f.r) {
    const p = document.createElementNS(NS, 'path');
    p.setAttribute('class', 'land');
    landRings.push(ring);
    paths.push(p);
  }
  layers.land.append(...paths);
}

function drawLand() {
  const paths = layers.land.children;
  for (let n = 0; n < landRings.length; n++) {
    const ring = landRings[n];
    let d = '';
    for (let i = 0; i < ring.length; i++) {
      d += (i ? 'L' : 'M') + sx(ring[i][0]).toFixed(1) + ' ' + sy(ring[i][1]).toFixed(1);
    }
    paths[n].setAttribute('d', d + 'Z');
  }
}

/* Country names.
   Two rules decide which names appear, and both matter:

   1. ORDER BY THE DATA, NOT BY LANDMASS. Placement is greedy, so whatever is
      tried first wins the space. Sorting by land width alone labelled Mali,
      Niger and the Central African Republic while skipping Germany, the UK and
      Ireland - backwards for a map of AI data centres. Countries that hold
      sites are tried first, heaviest capacity down, and everything else fills
      in behind them.
   2. A NAME NEEDS ROOM. A country is labelled only once it is wide enough on
      screen to carry its own text, so world view names the big landmasses and
      more appear as you zoom - no zoom thresholds to hand-tune. Countries that
      hold sites clear a lower bar, since they are the ones being read.

   Labels are drawn beneath the marks: a basemap label must never hide a site. */
const SHORT = { 'United States of America': 'United States',
                'Dem. Rep. Congo': 'DR Congo', 'Central African Rep.': 'CAR',
                'Bosnia and Herz.': 'Bosnia', 'S. Sudan': 'South Sudan',
                'Korea': 'South Korea', 'Dem. Rep. Korea': 'North Korea' };
const named = W.filter(f => f.l).sort((a, b) => {
  const ha = D.hot[a.n] || 0, hb = D.hot[b.n] || 0;
  return (hb - ha) || (b.w - a.w);
});

function drawNames() {
  const nodes = [], boxes = [];
  for (const f of named) {
    const label = SHORT[f.n] || f.n;
    const need = label.length * 5.6 + 10;
    const px = f.w / 360 * worldPx();
    if (px < need * (D.hot[f.n] ? 0.55 : 1)) continue;
    const x = sx(f.l[0]), y = sy(f.l[1]);
    if (x < 4 || y < 10 || x > size.w - 4 || y > size.h - 4) continue;
    const box = { x0: x - need / 2, x1: x + need / 2, y0: y - 7, y1: y + 7 };
    if (boxes.some(b => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)) continue;
    boxes.push(box);
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('class', 'cname');
    t.setAttribute('x', x.toFixed(1));
    t.setAttribute('y', y.toFixed(1));
    t.textContent = label;
    nodes.push(t);
  }
  layers.names.replaceChildren(...nodes);
}

let visible = [];
function draw() {
  drawLand();
  drawNames();
  visible = sites.filter(matches);
  const marks = visible.filter(s => s.mw)          // no capacity, no circle
                       .sort((a, b) => b.mw - a.mw); // big ones underneath

  const haloNodes = [], dotNodes = [];
  for (const s of marks) {
    const cx = sx(s.lng), cy = sy(s.lat), col = colourOf(s);
    const hr = haloR(s);
    if (hr > 1.5) {
      const h = document.createElementNS(NS, 'circle');
      h.setAttribute('class', 'halo');
      h.setAttribute('cx', cx.toFixed(1)); h.setAttribute('cy', cy.toFixed(1));
      h.setAttribute('r', Math.min(hr, 400).toFixed(1));
      h.setAttribute('fill', col); h.setAttribute('opacity', '.10');
      haloNodes.push(h);
    }
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('class', 'dot' + (state.pinned && state.pinned !== s.id ? ' dim' : '')
                           + (state.hot === s.id || state.pinned === s.id ? ' hot' : ''));
    c.setAttribute('cx', cx.toFixed(1)); c.setAttribute('cy', cy.toFixed(1));
    c.setAttribute('r', radius(s.mw).toFixed(2));
    c.setAttribute('fill', col); c.setAttribute('fill-opacity', '.82');
    c.dataset.id = s.id;
    dotNodes.push(c);
  }
  // One replaceChildren per layer instead of an append per mark: 294 circles
  // reflowed individually on every pan frame is the difference between a map
  // that drags smoothly and one that stutters.
  layers.halo.replaceChildren(...haloNodes);
  layers.dots.replaceChildren(...dotNodes);
  drawLegend(marks);
  const undated = visible.filter(s => s.y == null).length;
  document.getElementById('count').textContent =
    `${visible.length} sites · ${fmtMW(marks.reduce((t, s) => t + s.mw, 0))}`;
  positionOverlays();
}

/* --------------------------------------------------------------- legend */
function drawLegend(marks) {
  const el = document.getElementById('legend');
  const max = marks.length ? Math.max(...marks.map(s => s.mw)) : 0;
  let html = '<div class="blk"><span class="cap">Announced capacity</span>';

  if (max > 0) {
    // Circles sit side by side on a shared baseline with the label under each.
    // Nesting them (as Epoch does) needs 2*(r_i - r_{i+1}) of clear vertical
    // space per label, and under a sqrt scale at world zoom the smallest ring is
    // narrower than its own label - so it gets covered. Side by side has no such
    // constraint and holds all three rings at every zoom.
    const rs = rings(max).map(v => ({ v, r: radius(v), lab: fmtMW(v) })).filter(d => d.r >= 1.5);
    const GAP = 8, PAD = 2, LAB = 13;
    // Each slot is as wide as the circle OR its label, whichever is bigger: the
    // smallest circle carries the longest label ("800 MW"), so spacing on the
    // circle alone runs the bottom row of labels into each other.
    let x = PAD, top = 2 * rs[0].r;
    const parts = [];
    for (const d of rs) {
      const slot = Math.max(2 * d.r, d.lab.length * 5.9);
      const cx = x + slot / 2;
      parts.push(`<circle cx="${cx.toFixed(1)}" cy="${(top - d.r).toFixed(1)}" r="${d.r.toFixed(1)}"/>` +
                 `<text x="${cx.toFixed(1)}" y="${(top + 9).toFixed(1)}">${d.lab}</text>`);
      x += slot + GAP;
    }
    const w = Math.max(x - GAP + PAD, 60), h = top + LAB;
    html += `<svg class="lg-circ" width="${w.toFixed(0)}" height="${h.toFixed(0)}" ` +
            `viewBox="0 0 ${w.toFixed(0)} ${h.toFixed(0)}">${parts.join('')}</svg>`;
  }
  html += '</div>';

  const sc = scheme();
  if (!sc.single) {
    // Viewport-aware, like Epoch's: only categories actually on screen, biggest
    // first, with Other/Unknown pinned last.
    const seen = new Map();
    for (const s of marks) {
      const x = sx(s.lng), y = sy(s.lat);
      if (x < -40 || y < -40 || x > size.w + 40 || y > size.h + 40) continue;
      const k = sc.colors[s[state.colorBy]] ? s[state.colorBy] : 'Other';
      seen.set(k, (seen.get(k) || 0) + s.mw);
    }
    const rank = k => (k === 'Unknown' ? 2 : k === 'Other' ? 1 : 0);
    const items = [...seen.entries()].sort((a, b) => rank(a[0]) - rank(b[0]) || b[1] - a[1]);
    if (items.length) {
      html += `<div class="blk"><span class="cap">${esc(sc.label)}</span>` +
        '<div class="swatches">' +
        items.map(([k]) =>
          `<span class="sw"><i style="background:${sc.colors[k] || '__NEUTRAL__'}"></i>` +
          `<b>${esc(k)}</b></span>`).join('') + '</div></div>';
    }
  }
  el.innerHTML = html;
}

/* ================================================= hover, pin and detail */
const bub = document.createElement('div'); bub.className = 'bub'; bub.hidden = true;
const card = document.createElement('div'); card.className = 'card'; card.hidden = true;
wrap.append(bub, card);

const byId = id => sites.find(s => s.id === id);

function positionOverlays() {
  if (state.hot || state.pinned) {
    const s = byId(state.pinned || state.hot);
    if (s) {
      bub.hidden = false;
      bub.classList.toggle('pin', state.pinned === s.id);
      bub.textContent = s.mw ? fmtMW(s.mw) : 'capacity not disclosed';
      bub.style.left = sx(s.lng) + 'px';
      bub.style.top  = (sy(s.lat) - radius(s.mw || 1) - 6) + 'px';
    }
  } else { bub.hidden = true; }

  if (state.pinned) {
    const s = byId(state.pinned);
    if (s) {
      card.hidden = false;
      const x = sx(s.lng), y = sy(s.lat);
      const left = Math.max(8, Math.min(x - 145, size.w - 298));
      const above = y - radius(s.mw || 1) - 14 - card.offsetHeight;
      card.style.left = left + 'px';
      card.style.top = (above >= 8 ? above : y + radius(s.mw || 1) + 30) + 'px';
    }
  } else { card.hidden = true; }
}

function fillCard(s) {
  const place = [s.ci, s.rg, s.co].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(', ');
  const approx = s.p !== 'exact'
    ? `<div class="note">Location approximate &mdash; resolved to ${esc(s.p)} level. ` +
      `This record names a ${s.p === 'country' ? 'programme or portfolio' : 'district'}, not a single building.</div>` : '';
  const raw = [['Reported status', s.sr], ['Energy', s.er], ['Workload', s.fr]]
    .filter(([, v]) => v).map(([k, v]) =>
      `<div class="note"><b>${esc(k)}:</b> ${esc(v)}</div>`).join('');
  card.innerHTML =
    `<button class="x" id="cx" title="Close">&times;</button>` +
    `<h3>${esc(s.t)}</h3><div class="loc">${esc(place)}</div>` +
    (s.mw ? `<div class="big">${fmtMW(s.mw)} <span>announced capacity</span></div>`
          : `<div class="big" style="font-size:13px">Capacity not disclosed</div>`) +
    `<dl>` +
      `<dt>Company</dt><dd>${esc(s.cs || s.c)}</dd>` +
      `<dt>Status</dt><dd>${esc(s.st)}</dd>` +
      `<dt>Energy</dt><dd>${esc(s.en)}</dd>` +
      `<dt>Focus</dt><dd>${esc(s.fo)}</dd>` +
      `<dt>Start</dt><dd>${s.y == null ? 'not stated' : s.y}</dd>` +
    `</dl>` + approx + raw +
    (s.u ? `<div class="note"><a href="${esc(s.u)}" target="_blank" rel="noopener">Source</a></div>` : '');
}
// Delegated, so it survives every re-render of the card body.
card.addEventListener('click', e => {
  if (e.target && e.target.id === 'cx') { e.stopPropagation(); state.pinned = null; draw(); }
});

svg.addEventListener('mousemove', e => {
  if (dragging) return;
  const t = e.target;
  const id = t.classList && t.classList.contains('dot') ? t.dataset.id : null;
  if (id !== state.hot) { state.hot = id; svg.style.cursor = id ? 'pointer' : ''; positionOverlays(); }
});
svg.addEventListener('mouseleave', () => { state.hot = null; positionOverlays(); });
svg.addEventListener('click', e => {
  if (moved) return;
  const t = e.target;
  const id = t.classList && t.classList.contains('dot') ? t.dataset.id : null;
  state.pinned = (id && id !== state.pinned) ? id : null;
  if (state.pinned) fillCard(byId(state.pinned));
  draw();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && state.pinned) { state.pinned = null; draw(); }
});

/* ================================================== pan, zoom and sizing */
let dragging = false, moved = false, last = null;
svg.addEventListener('pointerdown', e => {
  dragging = true; moved = false; last = { x: e.clientX, y: e.clientY };
  svg.classList.add('drag'); svg.setPointerCapture(e.pointerId);
});
svg.addEventListener('pointermove', e => {
  if (!dragging) return;
  const dx = e.clientX - last.x, dy = e.clientY - last.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
  last = { x: e.clientX, y: e.clientY };
  view.cx -= dx / worldPx(); view.cy -= dy / worldPx();
  clampView(); draw();
});
const endDrag = e => { dragging = false; svg.classList.remove('drag');
                       if (e && e.pointerId != null) { try { svg.releasePointerCapture(e.pointerId); } catch (_) {} } };
svg.addEventListener('pointerup', endDrag);
svg.addEventListener('pointercancel', endDrag);

svg.addEventListener('wheel', e => {
  e.preventDefault();
  const r = svg.getBoundingClientRect();
  zoomAt(e.clientX - r.left, e.clientY - r.top, Math.pow(2, -e.deltaY / 420));
}, { passive: false });

function zoomAt(px, py, factor) {
  const k0 = view.k, k1 = Math.max(1, Math.min(48, k0 * factor));
  if (k1 === k0) return;
  // Keep the point under the cursor fixed while the scale changes.
  const wx = view.cx + (px - size.w / 2) / (size.w * k0);
  const wy = view.cy + (py - size.h / 2) / (size.w * k0);
  view.k = k1;
  view.cx = wx - (px - size.w / 2) / (size.w * k1);
  view.cy = wy - (py - size.h / 2) / (size.w * k1);
  clampView(); draw();
}

function clampView() {
  const halfW = size.w / 2 / worldPx(), halfH = size.h / 2 / worldPx();
  view.cx = Math.max(halfW, Math.min(1 - halfW, view.cx));
  const top = my(84), bot = my(-84);
  view.cy = (bot - top) < 2 * halfH ? (top + bot) / 2
          : Math.max(top + halfH, Math.min(bot - halfH, view.cy));
}

function fit() {
  const pts = sites.filter(s => s.mw);
  const xs = pts.map(s => mx(s.lng)), ys = pts.map(s => my(s.lat));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  view.k = Math.max(1, Math.min(6, .92 / Math.max(x1 - x0, (y1 - y0) * size.w / size.h)));
  view.cx = (x0 + x1) / 2; view.cy = (y0 + y1) / 2;
  clampView();
}

function resize() {
  const r = svg.getBoundingClientRect();
  size = { w: Math.max(320, r.width), h: Math.max(300, r.height) };
  svg.setAttribute('viewBox', `0 0 ${size.w} ${size.h}`);
  clampView(); draw();
}

document.getElementById('zin').onclick  = () => zoomAt(size.w / 2, size.h / 2, 1.6);
document.getElementById('zout').onclick = () => zoomAt(size.w / 2, size.h / 2, 1 / 1.6);
document.getElementById('zfit').onclick = () => { fit(); draw(); };

/* ============================================================== controls */
const q = document.getElementById('q');
q.oninput = () => { state.q = q.value; state.pinned = null; draw(); };

const cby = document.getElementById('cby');
cby.innerHTML = Object.entries(D.schemes)
  .map(([k, v]) => `<option value="${k}">${k === 'none' ? 'Colour by' : 'Colour: ' + esc(v.label)}</option>`).join('');
cby.onchange = () => { state.colorBy = cby.value; draw(); };

/* Facet panel: options and counts come from the data, never hardcoded. */
const fbtn = document.getElementById('fbtn');
const panel = document.createElement('div');
panel.className = 'pop'; panel.hidden = true;
fbtn.parentNode.appendChild(panel);
panel.innerHTML = '<h4>Filter by<button class="clear" id="fclear">Clear all</button></h4>' +
  D.facets.map(g => `<div class="grp"><h4>${esc(g.label)}</h4>` +
    g.options.map(o =>
      `<label><input type="checkbox" data-dim="${g.id}" value="${esc(o.id)}">` +
      `<span>${esc(o.id || 'Unknown')}</span><span class="n">${o.n}</span></label>`).join('') +
    '</div>').join('');

function syncFilterCount() {
  const n = Object.values(state.filters).reduce((t, v) => t + v.length, 0);
  const b = document.getElementById('fcount');
  b.hidden = !n; b.textContent = n;
}
panel.addEventListener('change', e => {
  const cb = e.target;
  if (!cb.dataset || !cb.dataset.dim) return;
  const dim = cb.dataset.dim;
  const cur = state.filters[dim] || [];
  state.filters[dim] = cb.checked ? [...cur, cb.value] : cur.filter(v => v !== cb.value);
  state.pinned = null; syncFilterCount(); draw();
});
panel.addEventListener('click', e => {
  if (!e.target || e.target.id !== 'fclear') return;
  state.filters = {};
  panel.querySelectorAll('input').forEach(i => { i.checked = false; });
  state.pinned = null; syncFilterCount(); draw();
});
fbtn.onclick = e => {
  e.stopPropagation();
  panel.hidden = !panel.hidden;
  fbtn.setAttribute('aria-expanded', String(!panel.hidden));
  if (!panel.hidden) {
    const r = fbtn.getBoundingClientRect(), p = fbtn.offsetParent.getBoundingClientRect();
    panel.style.left = Math.max(0, r.left - p.left) + 'px';
    panel.style.top  = (r.bottom - p.top + 5) + 'px';
  }
};
document.addEventListener('click', e => {
  if (!panel.hidden && !panel.contains(e.target) && e.target !== fbtn) {
    panel.hidden = true; fbtn.setAttribute('aria-expanded', 'false');
  }
});

/* ============================================================== timeline */
const yr = document.getElementById('year'), marks = document.getElementById('marks');
yr.min = 0; yr.max = YEARS.length - 1;
document.getElementById('e0').textContent = YEARS[0];
document.getElementById('e1').textContent = YEARS[YEARS.length - 1];

const pos = i => `calc((100% - 15px) * ${i / (YEARS.length - 1)} + 7.5px)`;
marks.innerHTML = YEARS.map((y, i) =>
  (y % 5 === 0 || y === D.today)
    ? `<span class="yr${y === D.today ? ' now' : ''}" style="left:${pos(i)}">${y === D.today ? 'today' : y}</span>`
    : '').join('') +
  `<span class="tick" style="left:${pos(YEARS.indexOf(D.today))}"></span>`;

function setYear(i, redraw = true) {
  i = Math.max(0, Math.min(YEARS.length - 1, i));
  yr.value = i;
  state.year = YEARS[i];
  yr.style.setProperty('--fill', pos(i));
  const v = document.getElementById('tlval');
  v.textContent = YEARS[i]; v.style.left = pos(i);
  if (redraw) { state.pinned = null; draw(); }
}
yr.oninput = () => setYear(+yr.value);

let timer = null;
const play = document.getElementById('play');
play.onclick = () => {
  if (timer) { clearInterval(timer); timer = null; play.innerHTML = '&#9654;'; return; }
  if (+yr.value >= YEARS.length - 1) setYear(0);
  play.innerHTML = '&#10073;&#10073;';
  timer = setInterval(() => {
    if (+yr.value >= YEARS.length - 1) { clearInterval(timer); timer = null; play.innerHTML = '&#9654;'; return; }
    setYear(+yr.value + 1);
  }, 750);
};

/* ================================================================== boot */
document.getElementById('foot').innerHTML = D.footnote;
initSvg();
fit();
setYear(YEARS.indexOf(state.year), false);
syncFilterCount();
resize();
// Registered only after the layers exist: a ResizeObserver fires on observe(),
// and wiring it earlier leaves drawLand() reaching into an empty layer set.
new ResizeObserver(resize).observe(svg);

/* Report our height so the gallery iframe can size itself, as the other
   interactive companions in this data room do. */
function reportHeight() {
  const h = Math.ceil(document.getElementById('pg').getBoundingClientRect().height) + 2;
  if (window.parent !== window) window.parent.postMessage({ type: 'aidr-height', id: '__PID__', h }, '*');
}
window.addEventListener('load', reportHeight);
window.addEventListener('resize', reportHeight);
if (window.ResizeObserver) new ResizeObserver(reportHeight).observe(document.body);
reportHeight();
</script>
"""


# ----------------------------------------------------- static SVG / PNG twin
# The gallery publishes a chart once a static SVG exists beside it, and offers
# SVG/PNG downloads for every figure. These render the map's default view from
# the same constants the page script is given, so the fallback is the same
# picture rather than a second implementation of it.
def _mx(lng):
    return (lng + 180) / 360


def _my(lat):
    lat = max(-84, min(84, lat))
    s = math.sin(lat * math.pi / 180)
    return 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def default_view(marks, w, h):
    """The same fit() and clampView() the page runs on load."""
    xs = [_mx(s["lng"]) for s in marks]
    ys = [_my(s["lat"]) for s in marks]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    k = max(1, min(6, .92 / max(x1 - x0, (y1 - y0) * w / h)))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half_w, half_h = w / 2 / (w * k), h / 2 / (w * k)
    cx = max(half_w, min(1 - half_w, cx))
    top, bot = _my(84), _my(-84)
    cy = ((top + bot) / 2 if (bot - top) < 2 * half_h
          else max(top + half_h, min(bot - half_h, cy)))
    return cx, cy, k


def static_geometry(sites, w=STATIC_W, h=STATIC_H):
    marks = sorted([s for s in sites if s["mw"]], key=lambda s: -s["mw"])
    cx, cy, k = default_view(marks, w, h)
    world_px = w * k
    shrink = max(SHRINK_FLOOR,
                 min(1, SHRINK_FLOOR + (1 - SHRINK_FLOOR) * math.log2(k) / SHRINK_SPAN))

    def sx(lng):
        return (_mx(lng) - cx) * world_px + w / 2

    def sy(lat):
        return (_my(lat) - cy) * world_px + h / 2

    def radius(mw):
        return max(MIN_R, math.sqrt(mw) * RADIUS_K * shrink)

    def halo(s):
        m = HALO_M.get(s["p"], 0)
        if not m:
            return 0.0
        lat = max(-84, min(84, s["lat"]))
        return min(m * world_px / (40075017 * math.cos(lat * math.pi / 180)), 400)

    return marks, sx, sy, radius, halo, shrink, world_px


SHORT_NAME = {"United States of America": "United States", "Dem. Rep. Congo": "DR Congo",
              "Central African Rep.": "CAR", "Bosnia and Herz.": "Bosnia",
              "S. Sudan": "South Sudan", "Korea": "South Korea",
              "Dem. Rep. Korea": "North Korea"}


def place_names(world, hot, sx, sy, world_px, w, h):
    """The page's own label rule, so the static twin names the same countries.

    Data first (countries holding capacity, heaviest down), then the rest by
    landmass; a name needs room to fit; greedy overlap culling.
    """
    order = sorted((f for f in world if f.get("l")),
                   key=lambda f: (-hot.get(f["n"], 0), -f["w"]))
    placed, boxes = [], []
    for f in order:
        label = SHORT_NAME.get(f["n"], f["n"])
        need = len(label) * 5.6 + 10
        if f["w"] / 360 * world_px < need * (0.55 if hot.get(f["n"]) else 1):
            continue
        x, y = sx(f["l"][0]), sy(f["l"][1])
        if x < 4 or y < 10 or x > w - 4 or y > h - 4:
            continue
        box = (x - need / 2, x + need / 2, y - 7, y + 7)
        if any(box[0] < b[1] and box[1] > b[0] and box[2] < b[3] and box[3] > b[2]
               for b in boxes):
            continue
        boxes.append(box)
        placed.append((x, y, label))
    return placed


def legend_rings(marks, radius):
    """Nice-number rings for the static legend: the same max and max/10 the page
    settles on once collision culling has run at world zoom."""
    top = max(s["mw"] for s in marks)
    step = 10 ** math.floor(math.log10(top))
    step = step / 10 if top < 2 * step else step
    nice = math.ceil(top / step) * step
    def nice_to(v):
        if v <= 0:
            return 0
        t = 10 ** math.floor(math.log10(v))
        st = t / 10 if v < 2 * t else t
        return math.ceil(v / st) * st

    out = []
    for v in dict.fromkeys((nice, nice_to(nice / 2.5), nice_to(nice / 10))):
        if v > 0:
            label = f"{v / 1000:.0f} GW" if v >= 1000 else f"{v:.0f} MW"
            out.append((v, label, radius(v)))
    return out


def write_static_svg(sites, path, w=STATIC_W, h=STATIC_H):
    marks, sx, sy, radius, halo, _, world_px = static_geometry(sites, w, h)
    world = json.loads(WORLD.read_text())
    single = CATEGORICAL[0]

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
           f'viewBox="0 0 {w} {h}" font-family="Helvetica,Arial,sans-serif">',
           f'<rect width="{w}" height="{h}" fill="#f9f9f7"/>',
           '<g fill="#edece7" stroke="#d9d7d0" stroke-width=".6" stroke-linejoin="round">']
    for f in world:
        for ring in f["r"]:
            d = "".join(("L" if i else "M") + f"{sx(p[0]):.1f} {sy(p[1]):.1f}"
                        for i, p in enumerate(ring))
            out.append(f'<path d="{d}Z"/>')
    out.append("</g>")

    out.append('<g fill="#8d8b84" font-size="10.5" text-anchor="middle" '
               'paint-order="stroke" stroke="#edece7" stroke-width="2.5" '
               'stroke-linejoin="round">')
    for x, y, label in place_names(world, hot_countries(sites), sx, sy, world_px, w, h):
        out.append(f'<text x="{x:.1f}" y="{y:.1f}">{label}</text>')
    out.append("</g>")

    out.append(f'<g fill="{single}" opacity=".10">')
    for s in marks:
        r = halo(s)
        if r > 1.5:
            out.append(f'<circle cx="{sx(s["lng"]):.1f}" cy="{sy(s["lat"]):.1f}" r="{r:.1f}"/>')
    out.append("</g>")

    out.append(f'<g fill="{single}" fill-opacity=".82" stroke="rgba(11,11,11,.45)" stroke-width="1">')
    for s in marks:
        out.append(f'<circle cx="{sx(s["lng"]):.1f}" cy="{sy(s["lat"]):.1f}" '
                   f'r="{radius(s["mw"]):.2f}"/>')
    out.append("</g>")

    # Slot width is the circle or its label, whichever is wider - the smallest
    # circle carries the longest label, so spacing on the circle alone collides.
    rings = legend_rings(marks, radius)
    slots, x = [], 16.0
    for value, label, r in rings:
        slot = max(2 * r, len(label) * 5.6)
        slots.append((x + slot / 2, label, r))
        x += slot + 8
    base_y = h - 34
    out.append('<g fill="none" stroke="#898781" stroke-width="1">')
    for cx, _, r in slots:
        out.append(f'<circle cx="{cx:.1f}" cy="{base_y - r:.1f}" r="{r:.1f}"/>')
    out.append("</g>")
    out.append('<g font-size="9.5" fill="#52514e" text-anchor="middle">')
    for cx, label, _ in slots:
        out.append(f'<text x="{cx:.1f}" y="{base_y + 11:.1f}">{label}</text>')
    out.append("</g>")
    out.append(f'<text x="16" y="{h - 6}" font-size="10.5" fill="#898781">'
               f'Circle area = announced capacity</text>')
    out.append("</svg>")
    path.write_text("\n".join(out))


def write_static_png(sites, path, w=STATIC_W, h=STATIC_H):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    from matplotlib.patches import Circle

    marks, sx, sy, radius, halo, _, world_px = static_geometry(sites, w, h)
    world = json.loads(WORLD.read_text())
    single = CATEGORICAL[0]

    fig, ax = plt.subplots(figsize=(w / 100, h / 100), dpi=200)
    fig.patch.set_facecolor("#f9f9f7")
    ax.set_facecolor("#f9f9f7")
    for f in world:
        for ring in f["r"]:
            ax.fill([sx(p[0]) for p in ring], [sy(p[1]) for p in ring],
                    facecolor="#edece7", edgecolor="#d9d7d0", linewidth=.6, zorder=1)
    for x, y, label in place_names(world, hot_countries(sites), sx, sy, world_px, w, h):
        ax.text(x, y, label, fontsize=5.2, color="#8d8b84", ha="center", va="center",
                zorder=2, path_effects=[pe.withStroke(linewidth=1.6, foreground="#edece7")])
    for s in marks:
        r = halo(s)
        if r > 1.5:
            ax.add_patch(Circle((sx(s["lng"]), sy(s["lat"])), r,
                                facecolor=single, alpha=.10, lw=0, zorder=3))
        ax.add_patch(Circle((sx(s["lng"]), sy(s["lat"])), radius(s["mw"]),
                            facecolor=single, alpha=.82,
                            edgecolor=(11 / 255, 11 / 255, 11 / 255, .45), lw=1, zorder=4))
    base_y, x = h - 34, 16.0
    for _, label, r in legend_rings(marks, radius):
        slot = max(2 * r, len(label) * 5.6)
        cx = x + slot / 2
        ax.add_patch(Circle((cx, base_y - r), r, facecolor="none",
                            edgecolor="#898781", lw=1, zorder=6))
        ax.text(cx, base_y + 11, label, fontsize=4.8, color="#52514e",
                ha="center", va="center", zorder=7)
        x += slot + 8
    ax.text(16, h - 6, "Circle area = announced capacity", fontsize=5.2,
            color="#898781", ha="left", va="center", zorder=7)

    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    plt.subplots_adjust(0, 0, 1, 1)
    fig.savefig(path, dpi=200, facecolor="#f9f9f7")
    plt.close(fig)


def main():
    sites = load_sites()
    schemes = colour_scheme(sites)
    years = list(range(YEAR_FLOOR, max(s["y"] for s in sites if s["y"]) + 1))

    no_mw = sum(1 for s in sites if not s["mw"])
    undated = sum(1 for s in sites if s["y"] is None)
    approx = sum(1 for s in sites if s["p"] != "exact")
    total_mw = sum(s["mw"] for s in sites if s["mw"])

    footnote = (
        f"<b>{len(sites)}</b> sites, <b>{total_mw:,.0f} MW</b> of announced capacity across "
        f"<b>{len({s['co'] for s in sites})}</b> countries. "
        f"Circle area is proportional to announced IT capacity; {no_mw} sites disclose no "
        f"capacity figure and are searchable but not drawn. "
        f"{undated} sites state no start year and are shown at every step of the slider. "
        f"{approx} sites resolve only to a district or country centroid rather than a "
        f"building and carry a shaded uncertainty halo. "
        f"The slider is cumulative &mdash; it shows what had started by each year, not how "
        f"capacity grew within a site. "
        f"Source: {SOURCE}."
    )

    data = {
        "sites": sites,
        "schemes": schemes,
        "facets": facets(sites),
        "hot": hot_countries(sites),
        "years": years,
        "today": min(2026, years[-1]),
        "footnote": footnote,
    }

    html = (HTML
            .replace("__PID__", PLOT_ID)
            .replace("__TITLE__", TITLE)
            .replace("__SUBTITLE__", SUBTITLE)
            .replace("__NEUTRAL__", NEUTRAL)
            .replace("__RADIUS_K__", str(RADIUS_K))
            .replace("__MIN_R__", str(MIN_R))
            .replace("__SHRINK_FLOOR__", str(SHRINK_FLOOR))
            .replace("__SHRINK_SPAN__", str(SHRINK_SPAN))
            .replace("__HALO__", json.dumps(HALO_M))
            .replace("__WORLD__", WORLD.read_text())
            .replace("__DATA__", json.dumps(data, separators=(",", ":"))))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"wrote {OUT.relative_to(REPO)}  ({len(html):,} bytes, "
          f"{len(sites)} sites, {len(sites) - no_mw} drawn)")

    svg_path = OUT.with_suffix(".svg")
    png_path = OUT.with_suffix(".png")
    write_static_svg(sites, svg_path)
    write_static_png(sites, png_path)
    print(f"wrote {svg_path.relative_to(REPO)}  ({svg_path.stat().st_size:,} bytes)")
    print(f"wrote {png_path.relative_to(REPO)}  ({png_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
