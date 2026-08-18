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
CHARTS = {
    "MODELS-01": ("notable", "training_compute_flop", None, 0, "",
                  "Training compute of notable AI models",
                  "Training compute (FLOP)", None),
    "MODELS-02": ("notable", "training_compute_flop", "domain", 8, "Other domains",
                  "Training compute of notable AI models, by domain",
                  "Training compute (FLOP)", None),
    "MODELS-03": ("notable", "training_compute_flop", "organization_primary", 9,
                  "All other organizations",
                  "Training compute of notable AI models, by organization",
                  "Training compute (FLOP)", None),
    "MODELS-04": ("notable", "training_compute_flop", "country", 7, "Other countries",
                  "Training compute of notable AI models, by country",
                  "Training compute (FLOP)", None),
    "MODELS-05": ("frontier", "training_compute_flop", None, 0, "",
                  "Training compute of frontier AI models",
                  "Training compute (FLOP)", None),
    "MODELS-13": ("notable", "parameters", "domain", 8, "Other domains",
                  "Parameters against training compute, notable AI models",
                  "Parameters", "training_compute_flop"),
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

function geometry(D, hidden, W, H, M) {
  const shown = [];
  for (let i = 0; i < D.pts.length; i++) if (!hidden.has(D.pts[i][2])) shown.push(i);
  const xs = shown.map(i => D.pts[i][0]), ys = shown.map(i => D.pts[i][1]);
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

function nearest(D, G, px, py, limit) {
  let best = -1, bestD = limit * limit;
  for (const i of G.shown) {
    const dx = G.sx(D.pts[i][0]) - px, dy = G.sy(D.pts[i][1]) - py;
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
function fmtY(v){ return D.yUnit==='count' ? human(v) : fmtLog(v); }
function human(v){
  for(const [c,u] of [[1e12,'T'],[1e9,'B'],[1e6,'M'],[1e3,'k']])
    if(v>=c) return (v/c).toLocaleString('en-US',{maximumFractionDigits:0})+u;
  return v.toLocaleString('en-US',{maximumFractionDigits:0});
}
function fmtX(v){ return D.logX ? fmtLog(v) : String(Math.round(v)); }

function drawLegend(){
  lgw.innerHTML='';
  if(D.groups.length<2) return;
  D.groups.forEach((g,i)=>{
    const b=document.createElement('button');
    b.className='lg'; b.type='button';
    b.setAttribute('aria-pressed', hidden.has(i)?'true':'false');
    b.innerHTML='<span class="sw" style="background:'+g.color+'"></span>'+g.name+' ('+g.n+')';
    // toggle in place rather than rebuilding the legend, so focus and the
    // pressed state survive the click
    b.onclick=()=>{
      if(hidden.has(i)) hidden.delete(i);
      else if(hidden.size < D.groups.length-1) hidden.add(i);
      else return;                       // never leave the chart with nothing on it
      b.setAttribute('aria-pressed', hidden.has(i)?'true':'false');
      draw();
    };
    lgw.appendChild(b);
  });
}

let G=null;
function draw(){
  G=geometry(D,hidden,W,H,M);
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
  yl.textContent=D.yLabel; svg.appendChild(yl);

  G.shown.forEach(i=>{
    const p=D.pts[i];
    svg.appendChild(el('circle',{cx:G.sx(p[0]).toFixed(2),cy:G.sy(p[1]).toFixed(2),r:3.6,
      fill:D.groups[p[2]].color,stroke:'#fff','stroke-width':.6,'fill-opacity':.85}));
  });
  if(D.fit && !D.logX){
    const [x0,x1,slope,icept]=D.fit;
    svg.appendChild(el('line',{x1:G.sx(x0),y1:G.sy(Math.pow(10,slope*x0+icept)),
      x2:G.sx(x1),y2:G.sy(Math.pow(10,slope*x1+icept)),stroke:'#b4763a','stroke-width':2.2}));
  }
  const hl=el('circle',{id:'hl',r:6.5,fill:'none',stroke:'#1a1a1a','stroke-width':1.6,
                        cx:-99,cy:-99}); svg.appendChild(hl);
}

function move(ev){
  if(!G) return;
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W, py=(ev.clientY-r.top)/r.height*H;
  const i=nearest(D,G,px,py,14);
  const hl=document.getElementById('hl');
  if(i<0){ tip.style.opacity=0; hl.setAttribute('cx',-99); return; }
  const p=D.pts[i];
  hl.setAttribute('cx',G.sx(p[0])); hl.setAttribute('cy',G.sy(p[1]));
  tip.innerHTML='<b>'+p[3]+'</b><div class="m">'+p[4]+' &middot; '+p[5]+'</div>'
    +'<div>'+D.yLabel+': '+fmtY(p[1])+'</div>'
    +(D.logX?'<div>'+D.xLabel+': '+fmtLog(p[0])+'</div>':'');
  tip.style.opacity=1;
  const left=G.sx(p[0])/W*r.width, top=G.sy(p[1])/H*r.height;
  tip.style.left=Math.min(Math.max(8,left+14), r.width-tip.offsetWidth-8)+'px';
  tip.style.top=Math.min(Math.max(8,top-10), r.height-tip.offsetHeight-8)+'px';
}
// pointer events rather than mouse events, so touch reads the same as hover
svg.addEventListener('pointermove',move);
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;
  const hl=document.getElementById('hl'); if(hl) hl.setAttribute('cx',-99);});
drawLegend(); draw();

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

    for pid, (ds, metric, colour, top_n, residual, title, ylabel, xmetric) in CHARTS.items():
        rows = [r for r in read(f"points_{ds}.csv")
                if r["publication_date"] and r[metric]
                and (not xmetric or r[xmetric])]

        # group assignment, matching the static chart exactly
        if colour:
            counts = {}
            for r in rows:
                key = r[colour] or ""
                counts[key] = counts.get(key, 0) + 1
            ranked = [k for k in sorted(counts, key=lambda k: -counts[k]) if k]
            if colour == "country" and "Multinational" in ranked:
                ranked.remove("Multinational")
                ranked.insert(0, "Multinational")
            keep = ranked[:top_n]
            names = [SHORT_COUNTRY.get(k, k) for k in keep]
            index = {k: i for i, k in enumerate(keep)}
        else:
            keep, names, index = [], [], {}

        pts, group_n = [], {}
        for r in rows:
            if colour:
                key = r[colour] or ""
                gi = index.get(key, len(keep))
            else:
                gi = 0
            group_n[gi] = group_n.get(gi, 0) + 1
            x = float(r[xmetric]) if xmetric else dec_year(r["publication_date"])
            pts.append([round(x, 4), float(r[metric]), gi, r["model"],
                        r["organization_primary"] or "Organization not recorded",
                        r["publication_date"]])

        if colour:
            labels = names + ([residual] if len(keep) in group_n else [])
        else:
            labels = ["Recorded models"]
        groups = [{"name": lab,
                   "color": RESIDUAL if (colour and i == len(names)) else PALETTE[i % len(PALETTE)],
                   "n": group_n.get(i, 0)}
                  for i, lab in enumerate(labels)]

        fit = None
        if not xmetric:
            for t in trends:
                if (t["dataset"] == ds and t["metric"] == metric
                        and t["era"] == "deep learning era"):
                    fit = [float(t["x_min"]), float(t["x_max"]),
                           float(t["oom_per_year"]), float(t["intercept_log10"])]
        payload = {
            "pts": pts, "groups": groups, "logX": bool(xmetric), "fit": fit,
            "yLabel": ylabel, "yUnit": "count" if metric == "parameters" else "pow10",
            "xLabel": ("Training compute (FLOP)" if xmetric else "Publication date"),
        }
        summ = summary[ds]
        sub = (f"{len(pts):,} of {int(summ['models']):,} models in "
               f"{summ['source_file']} record "
               f"{'both values' if xmetric else 'this value'}; the rest are absent.")
        html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                    .replace("__GEOMETRY__", GEOMETRY_JS)
                    .replace("__TITLE__", title).replace("__PID__", pid)
                    .replace("__SUB__", sub).replace("__FILE__", summ["source_file"]))
        (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
        print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
              f"({len(pts):,} points, {len(groups)} groups)")


if __name__ == "__main__":
    main()
