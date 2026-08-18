#!/usr/bin/env python3
"""Emit self-contained interactive companions for the AI Models scatter charts.

Epoch's own figure is interactive: you hover a point to find out which model it
is. A static SVG of 534 points cannot do that, and with 534 points it is the
single thing a reader most wants. These pages add it - hover for the model
behind a point, click a legend entry to drop that group - over exactly the same
derived CSVs the static charts read.

No external scripts, fonts or styles: the page works offline and inside an
iframe on GitHub Pages.

Usage:
    python build/generate_interactive_models.py
"""
import csv
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "ai-models" / "data"
OUT = REPO / "ai-models" / "charts"

PALETTE = ["#1f3864", "#b4763a", "#6b8f71", "#7d5a7d", "#4e8a8b",
           "#a46b6b", "#4a6fa5", "#8a8f5c", "#9aa9c4"]
RESIDUAL = "#c9ced8"

# pid -> (dataset, y metric, colour column, top-N groups, residual label,
#         title, y axis label, x metric or None for publication date)
# Epoch's figure takes "colour by" and the metric as controls. The static gallery
# used to publish one chart per setting; the settings live here instead, as the
# selectors above the plot, and the payload carries every setting at once.
COLOUR_DIMS = [
    ("__none__", "No colouring", 0, ""),
    ("domain", "Domain", 8, "Other domains"),
    ("organization_primary", "Organization", 9, "All other organizations"),
    ("country", "Country", 7, "Other countries"),
]

CHARTS = {
    "MODELS-01": dict(dataset="notable", x="publication_date",
                      metrics=[("training_compute_flop", "Training compute (FLOP)", "pow10")],
                      colours=COLOUR_DIMS, fit=True,
                      title="Training compute of notable AI models",
                      xlabel="Publication date"),
    "MODELS-05": dict(dataset="frontier", x="publication_date",
                      metrics=[("training_compute_flop", "Training compute (FLOP)", "pow10")],
                      colours=COLOUR_DIMS[:1], fit=True,
                      title="Training compute of frontier AI models",
                      xlabel="Publication date"),
    "MODELS-06": dict(dataset="large_scale", x="publication_date",
                      metrics=[("training_compute_flop", "Training compute (FLOP)", "pow10")],
                      colours=COLOUR_DIMS[:1], fit=True,
                      title="Training compute of large-scale AI models",
                      xlabel="Publication date"),
    "MODELS-08": dict(dataset="notable", x="publication_date",
                      metrics=[("parameters", "Parameters", "count"),
                               ("training_dataset_size", "Training dataset (datapoints)", "count"),
                               ("training_cost_2023usd", "Training cost (2023 USD)", "usd"),
                               ("training_time_days", "Training time (days)", "days")],
                      colours=COLOUR_DIMS[:1], fit=False,
                      title="What else went into training, over time",
                      xlabel="Publication date"),
    "MODELS-13": dict(dataset="notable", x="training_compute_flop",
                      metrics=[("parameters", "Parameters", "count"),
                               ("hardware_quantity", "Accelerators used", "count"),
                               ("training_cost_2023usd", "Training cost (2023 USD)", "usd")],
                      colours=COLOUR_DIMS[:2], fit=False,
                      title="What training compute buys",
                      xlabel="Training compute (FLOP)"),
    "MODELS-D09": dict(dataset="frontier", x="publication_date",
                       metrics=[("flop_per_dollar", "Compute per dollar of hardware (FLOP/$)", "pow10")],
                       colours=COLOUR_DIMS[:1], fit=False, table="hardware",
                       title="Hardware price-performance behind frontier models",
                       xlabel="Hardware release date"),
}

SHORT_COUNTRY = {
    "United States of America": "United States",
    "United Kingdom of Great Britain and Northern Ireland": "United Kingdom",
    "Korea (Republic of)": "South Korea",
    "Russian Federation": "Russia",
    "Taiwan, Province of China": "Taiwan",
    "Iran (Islamic Republic of)": "Iran",
}

GEOMETRY_JS = r"""
function decadeTicks(lo, hi, target) {
  const a = Math.floor(Math.log10(lo)), b = Math.ceil(Math.log10(hi));
  if (b - a < 3) {
    const out = [];
    for (let e = a; e <= b; e++) for (const m of [1, 2, 5]) {
      const v = m * Math.pow(10, e);
      if (v >= lo / 1.6 && v <= hi * 1.6) out.push(v);
    }
    return out;
  }
  const stride = Math.max(1, Math.ceil((b - a + 1) / target));
  const out = [];
  for (let e = a; e <= b; e++) if ((b - e) % stride === 0) out.push(Math.pow(10, e));
  return out;
}

function geometry(D, hidden, W, H, M, PTS) {
  const shown = [];
  for (let i = 0; i < PTS.length; i++) if (!hidden.has(PTS[i].g)) shown.push(i);
  const xs = shown.map(i => PTS[i].x), ys = shown.map(i => PTS[i].y);
  const yLo = Math.min.apply(null, ys), yHi = Math.max.apply(null, ys);
  let xLo = Math.min.apply(null, xs), xHi = Math.max.apply(null, xs);
  const sy = v => H - M.b - (Math.log10(v) - Math.log10(yLo))
                  / (Math.log10(yHi) - Math.log10(yLo) || 1) * (H - M.t - M.b);
  let sx;
  if (D.logX) {
    sx = v => M.l + (Math.log10(v) - Math.log10(xLo))
              / (Math.log10(xHi) - Math.log10(xLo) || 1) * (W - M.l - M.r);
  } else {
    const pad = (xHi - xLo) * 0.03;
    xLo -= pad; xHi += pad;
    sx = v => M.l + (v - xLo) / (xHi - xLo || 1) * (W - M.l - M.r);
  }
  return {
    shown, sx, sy, xLo, xHi, yLo, yHi,
    yTicks: decadeTicks(yLo, yHi, 8),
    xTicks: D.logX ? decadeTicks(xLo, xHi, 8) : yearTicks(xLo, xHi),
  };
}

function yearTicks(lo, hi) {
  const span = hi - lo;
  const step = span > 45 ? 10 : span > 18 ? 5 : span > 8 ? 2 : 1;
  const out = [];
  for (let y = Math.ceil(lo / step) * step; y <= hi; y += step) out.push(y);
  return out;
}

function nearest(PTS, G, px, py, limit) {
  let best = -1, bestD = limit * limit;
  for (const i of G.shown) {
    const dx = G.sx(PTS[i].x) - px, dy = G.sy(PTS[i].y) - py;
    const d = dx * dx + dy * dy;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}
"""

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin:0; }
  #pg { padding:14px 16px 10px; background:#fff; color:#1a1a1a;
         font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
  body { background:#fff; color:#1a1a1a; }
  .hd { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:2px; }
  .pid { font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; color:#1f3864;
          letter-spacing:.04em; }
  h1 { font-size:15px; margin:0; font-weight:700; }
  .sub { color:#6b7280; font-size:12px; margin:2px 0 8px; }
  .badge { display:inline-block; background:#1f3864; color:#fff; font-weight:700;
            font-size:10.5px; padding:3px 9px; border-radius:999px; letter-spacing:.02em; }
  .ctl { display:flex; flex-wrap:wrap; gap:14px; margin:8px 0 2px; align-items:center; }
  .ctl .grp { display:flex; gap:6px; align-items:center; }
  .ctl .cap { color:#6b7280; font-size:11.5px; }
  .btn { font-size:12px; border:1px solid #d7dbe2; background:#fff; color:#1a1a1a;
          padding:3px 10px; border-radius:999px; cursor:pointer; }
  .btn[aria-pressed="true"] { background:#1f3864; color:#fff; border-color:#1f3864; }
  .btn:focus-visible { outline:2px solid #1f3864; outline-offset:2px; }
  .legend { display:flex; flex-wrap:wrap; gap:5px 12px; margin:8px 0 4px; }
  .lg { display:inline-flex; align-items:center; gap:6px; cursor:pointer;
         font-size:12px; border:0; background:none; padding:2px 3px; color:#1a1a1a; }
  .lg .sw { width:11px; height:11px; border-radius:999px; flex:none; }
  .lg[aria-pressed="true"] { opacity:.32; text-decoration:line-through; }
  .lg:focus-visible { outline:2px solid #1f3864; outline-offset:2px; }
  svg { width:100%; height:auto; display:block; touch-action:none; }
  .grid { stroke:#d7dbe2; stroke-width:1; }
  .axis { fill:#6b7280; font-size:11px; }
  .axlab { fill:#1a1a1a; font-size:11.5px; }
  .era { fill:#1f3864; opacity:.045; }
  .tip { position:absolute; pointer-events:none; background:#fff; border:1px solid #d7dbe2;
          border-radius:6px; padding:8px 10px; font-size:12px; box-shadow:0 4px 14px rgba(0,0,0,.10);
          opacity:0; transition:opacity .08s; max-width:290px; z-index:5; }
  .tip b { display:block; margin-bottom:3px; font-size:12.5px; }
  .tip .m { color:#6b7280; }
  .foot { color:#6b7280; font-size:11px; margin-top:6px; }
</style>
<div id="pg">
<div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
<div class="sub">__SUB__ <span class="badge">RECORDED VALUES ONLY</span></div>
<div class="ctl" id="ctl"></div>
<div class="legend" id="lg"></div>
<div style="position:relative">
  <svg id="c" viewBox="0 0 1000 520" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">Hover a point to identify the model; click a legend entry to remove that
group. Source: Epoch AI, Data on AI Models (CC-BY) — __FILE__. Only models that record the
plotted value appear; nothing is imputed.</div>
</div>
<script>
const D = __DATA__;
__GEOMETRY__
// the settings Epoch offers as controls: which metric is on y, and what colours
// the points. Changing either re-derives the groups and redraws.
let MI = 0, CI = 0;
function metric(){ return D.metrics[MI]; }
function dim(){ return D.dims[CI]; }
function activePts(){
  const m = metric();
  const out = [];
  for (const p of D.pts) {
    const y = p[2 + MI];
    if (y === null || y === undefined) continue;
    out.push({x:p[0], y:y, g:(dim().perPoint ? p[D.gStart + CI] : 0),
              name:p[1], meta:p[D.metaAt], date:p[D.metaAt+1]});
  }
  return out;
}
const W=1000, H=520, M={l:82,r:18,t:16,b:52};
const svg=document.getElementById('c'), tip=document.getElementById('tip'), lgw=document.getElementById('lg');
const hidden=new Set();
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const SUP={'-':'\\u207B','0':'\\u2070','1':'\\u00B9','2':'\\u00B2','3':'\\u00B3','4':'\\u2074',
           '5':'\\u2075','6':'\\u2076','7':'\\u2077','8':'\\u2078','9':'\\u2079'};
const sup=n=>String(n).split('').map(c=>SUP[c]||c).join('');
function fmtLog(v){
  const e=Math.round(Math.log10(v));
  if(Math.abs(Math.log10(v)-e)<1e-9) return '10'+sup(e);
  const f=Math.floor(Math.log10(v)), m=v/Math.pow(10,f);
  return (Math.round(m*10)/10)+'\\u00D7'+'10'+sup(f);
}
function fmtY(v){ const u=metric()[2];
  return u==='count' ? human(v) : u==='usd' ? '$'+human(v)
       : u==='days' ? (v>=1?human(v):String(+v.toPrecision(2))) : fmtLog(v); }
function human(v){
  for(const [c,u] of [[1e12,'T'],[1e9,'B'],[1e6,'M'],[1e3,'k']])
    if(v>=c) return (v/c).toLocaleString('en-US',{maximumFractionDigits:0})+u;
  return v.toLocaleString('en-US',{maximumFractionDigits:0});
}
function fmtX(v){ return D.logX ? fmtLog(v) : String(Math.round(v)); }

function buildCtl(){
  const ctl=document.getElementById('ctl'); ctl.innerHTML='';
  const add=(cap, opts, cur, onPick)=>{
    if(opts.length<2) return;
    const g=document.createElement('div'); g.className='grp';
    const c=document.createElement('span'); c.className='cap'; c.textContent=cap;
    g.appendChild(c);
    opts.forEach((o,i)=>{
      const b=document.createElement('button');
      b.className='btn'; b.type='button'; b.textContent=o;
      b.setAttribute('aria-pressed', i===cur?'true':'false');
      b.onclick=()=>{ onPick(i); hidden.clear(); buildCtl(); drawLegend(); draw(); reportHeight(); };
      g.appendChild(b);
    });
    ctl.appendChild(g);
  };
  add('Metric', D.metrics.map(m=>m[1]), MI, i=>{MI=i;});
  add('Colour by', D.dims.map(d=>d.label), CI, i=>{CI=i;});
}

function drawLegend(){
  lgw.innerHTML='';
  const gs=dim().groups;
  if(!dim().perPoint || gs.length<2) return;
  gs.forEach((g,i)=>{
    const b=document.createElement('button');
    b.className='lg'; b.type='button';
    b.setAttribute('aria-pressed', hidden.has(i)?'true':'false');
    b.innerHTML='<span class="sw" style="background:'+g.color+'"></span>'+g.name;
    b.onclick=()=>{
      if(hidden.has(i)) hidden.delete(i);
      else if(hidden.size < gs.length-1) hidden.add(i);
      else return;
      b.setAttribute('aria-pressed', hidden.has(i)?'true':'false');
      draw();
    };
    lgw.appendChild(b);
  });
}

let G=null, PTS=[];
function draw(){
  PTS=activePts();
  G=geometry(D,hidden,W,H,M,PTS);
  while(svg.firstChild) svg.removeChild(svg.firstChild);

  if(!D.logX && G.xLo < 2010){
    const x=Math.max(M.l,G.sx(2010));
    svg.appendChild(el('rect',{x:x,y:M.t,width:(W-M.r)-x,height:H-M.b-M.t,class:'era'}));
    const t=el('text',{x:x+6,y:M.t+12,class:'axis'}); t.textContent='Deep learning era';
    svg.appendChild(t);
  }
  G.yTicks.forEach(v=>{
    const y=G.sy(v);
    if(y<M.t-1||y>H-M.b+1) return;
    svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:y,y2:y,class:'grid'}));
    const t=el('text',{x:M.l-8,y:y+4,class:'axis','text-anchor':'end'});
    t.textContent=fmtY(v); svg.appendChild(t);
  });
  G.xTicks.forEach(v=>{
    const x=G.sx(v);
    if(x<M.l-1||x>W-M.r+1) return;
    svg.appendChild(el('line',{x1:x,x2:x,y1:M.t,y2:H-M.b,class:'grid'}));
    const t=el('text',{x:x,y:H-M.b+18,class:'axis','text-anchor':'middle'});
    t.textContent=fmtX(v); svg.appendChild(t);
  });
  const xl=el('text',{x:(M.l+W-M.r)/2,y:H-M.b+40,class:'axlab','text-anchor':'middle'});
  xl.textContent=D.xLabel; svg.appendChild(xl);
  const yl=el('text',{x:0,y:0,class:'axlab','text-anchor':'middle',
                      transform:'translate(16,'+((M.t+H-M.b)/2)+') rotate(-90)'});
  yl.textContent=metric()[1]; svg.appendChild(yl);

  const gs=dim().groups;
  G.shown.forEach(i=>{
    const p=PTS[i];
    svg.appendChild(el('circle',{cx:G.sx(p.x).toFixed(2),cy:G.sy(p.y).toFixed(2),r:3.6,
      fill:(gs[p.g]||gs[0]).color,stroke:'#fff','stroke-width':.6,'fill-opacity':.85}));
  });
  const f=D.fits && D.fits[MI];
  if(f && !D.logX && CI===0){
    svg.appendChild(el('line',{x1:G.sx(f[0]),y1:G.sy(Math.pow(10,f[2]*f[0]+f[3])),
      x2:G.sx(f[1]),y2:G.sy(Math.pow(10,f[2]*f[1]+f[3])),
      stroke:'#b4763a','stroke-width':2.2}));
  }
  const hl=el('circle',{id:'hl',r:6.5,fill:'none',stroke:'#1a1a1a','stroke-width':1.6,
                        cx:-99,cy:-99}); svg.appendChild(hl);
  const cnt=document.getElementById('cnt');
  if(cnt) cnt.textContent=G.shown.length.toLocaleString('en-US')+' models plotted';
}

function move(ev){
  if(!G) return;
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W, py=(ev.clientY-r.top)/r.height*H;
  const i=nearest(PTS,G,px,py,14);
  const hl=document.getElementById('hl');
  if(i<0){ tip.style.opacity=0; hl.setAttribute('cx',-99); return; }
  const p=PTS[i];
  hl.setAttribute('cx',G.sx(p.x)); hl.setAttribute('cy',G.sy(p.y));
  tip.innerHTML='<b>'+p.name+'</b><div class="m">'+p.meta+' &middot; '+p.date+'</div>'
    +'<div>'+metric()[1]+': '+fmtY(p.y)+'</div>'
    +(D.logX?'<div>'+D.xLabel+': '+fmtLog(p.x)+'</div>':'');
  tip.style.opacity=1;
  const left=G.sx(p.x)/W*r.width, top=G.sy(p.y)/H*r.height;
  tip.style.left=Math.min(Math.max(8,left+14), r.width-tip.offsetWidth-8)+'px';
  tip.style.top=Math.min(Math.max(8,top-10), r.height-tip.offsetHeight-8)+'px';
}
// pointer events rather than mouse events, so touch reads the same as hover
svg.addEventListener('pointermove',move);
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;
  const hl=document.getElementById('hl'); if(hl) hl.setAttribute('cx',-99);});
buildCtl(); drawLegend(); draw();

function reportHeight(){
  const h=Math.ceil(document.getElementById('pg').getBoundingClientRect().height)+2;
  if(window.parent!==window) window.parent.postMessage({type:'aidr-height',id:'__PID__',h:h},'*');
}
window.addEventListener('load',reportHeight);
window.addEventListener('resize',reportHeight);
if(window.ResizeObserver) new ResizeObserver(reportHeight).observe(document.body);
reportHeight();
</script>
"""


def read(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def dec_year(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    doy = (__import__("datetime").date(y, m, d)
           - __import__("datetime").date(y, 1, 1)).days
    return y + doy / 365.25


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {r["dataset"]: r for r in read("models_summary.csv")}
    trends = read("models_trends.csv")

    for pid, cfg in CHARTS.items():
        if cfg.get("table") == "hardware":
            rows = read("frontier_hardware_price_performance.csv")
            datecol = "hardware_release_date"
        else:
            rows = read(f"points_{cfg['dataset']}.csv")
            datecol = "publication_date"
        xcol = cfg["x"] if cfg["x"] != "publication_date" else datecol

        # a point survives if it has an x and at least one of the metrics
        keep = []
        for r in rows:
            if not r.get(xcol):
                continue
            if not any(r.get(m) for m, _, _ in cfg["metrics"]):
                continue
            keep.append(r)

        # one group index per colour dimension, assigned exactly as the static
        # charts assign them: top-N by count, the rest pooled into one pale group
        dims = []
        for col, label, top_n, residual in cfg["colours"]:
            if col == "__none__":
                dims.append({"label": label, "perPoint": False,
                             "groups": [{"name": "Recorded models", "color": PALETTE[0]}],
                             "index": {}})
                continue
            counts = {}
            for r in keep:
                k = r.get(col) or ""
                if k:
                    counts[k] = counts.get(k, 0) + 1
            ranked = sorted(counts, key=lambda k: -counts[k])
            if col == "country" and "Multinational" in ranked:
                ranked.remove("Multinational"); ranked.insert(0, "Multinational")
            head = ranked[:top_n]
            names = [SHORT_COUNTRY.get(k, k) for k in head]
            groups = [{"name": n, "color": PALETTE[i % len(PALETTE)]}
                      for i, n in enumerate(names)] + [{"name": residual, "color": RESIDUAL}]
            dims.append({"label": label, "perPoint": True, "groups": groups,
                         "index": {k: i for i, k in enumerate(head)}})

        pts = []
        for r in keep:
            x = float(r[xcol]) if cfg["x"] != "publication_date" else dec_year(r[datecol])
            row = [round(x, 4), r.get("model") or "Model not named"]
            for m, _, _ in cfg["metrics"]:
                v = r.get(m)
                row.append(round(float(v), 6) if v else None)
            for (col, _, _, _), d in zip(cfg["colours"], dims):
                if d["perPoint"]:
                    row.append(d["index"].get(r.get(col) or "", len(d["index"])))
            row.append(r.get("organization_primary") or r.get("training_hardware")
                       or "Organization not recorded")
            row.append(r.get(datecol, ""))
            pts.append(row)

        n_metrics = len(cfg["metrics"])
        n_perpoint = sum(1 for d in dims if d["perPoint"])
        fits = [None] * n_metrics
        if cfg["fit"]:
            for t in trends:
                if (t["dataset"] == cfg["dataset"] and t["era"] == "deep learning era"):
                    for k, (m, _, _) in enumerate(cfg["metrics"]):
                        if t["metric"] == m:
                            fits[k] = [float(t["x_min"]), float(t["x_max"]),
                                       float(t["oom_per_year"]), float(t["intercept_log10"])]

        payload = {
            "pts": pts,
            "metrics": [[m, lab, unit] for m, lab, unit in cfg["metrics"]],
            "dims": [{"label": d["label"], "perPoint": d["perPoint"],
                      "groups": d["groups"]} for d in dims],
            "gStart": 2 + n_metrics,
            "metaAt": 2 + n_metrics + n_perpoint,
            "fits": fits,
            "logX": cfg["x"] != "publication_date",
            "xLabel": cfg["xlabel"],
        }
        summ = summary.get(cfg["dataset"], {})
        total = int(summ.get("models", len(keep)))
        controls = []
        if len(cfg["metrics"]) > 1:
            controls.append(f"{len(cfg['metrics'])} metrics")
        if len(cfg["colours"]) > 1:
            controls.append(f"{len(cfg['colours'])} colourings")
        sub = (f"{len(pts):,} of {total:,} models in "
               f"{summ.get('source_file', 'the release')} carry a plotted value"
               + (f"; switch between {' and '.join(controls)} above." if controls
                  else "; the rest are absent."))

        html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                    .replace("__GEOMETRY__", GEOMETRY_JS)
                    .replace("__TITLE__", cfg["title"]).replace("__PID__", pid)
                    .replace("__SUB__", sub)
                    .replace("__FILE__", summ.get("source_file", "notable_ai_models.csv")))
        (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
        print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
              f"({len(pts):,} points, {n_metrics} metric(s), {len(dims)} colouring(s))")


if __name__ == "__main__":
    main()
