#!/usr/bin/env python3
"""Emit self-contained interactive companions for the by-company Epoch charts.

Static SVG/PNG stay the canonical, downloadable deliverable. These add what a
static image cannot do with ten stacked series: read every owner's value at a
given date, and isolate one owner by clicking it out of the stack.

No external scripts, fonts or styles - the page works offline and inside an
iframe on GitHub Pages. Data is the same observed-only derived CSV the static
charts read, inlined as JSON.

The geometry maths lives in GEOMETRY_JS so build/verify_interactive.mjs can run
exactly the same code under Node and assert the output is sane before publishing.

Usage:
    python build/generate_interactive.py
"""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "ai-infrastructure" / "data"
OUT = REPO / "ai-infrastructure" / "charts"

COLOURS = ["#1f3864", "#4a6fa5", "#6b8f71", "#b4763a", "#7d5a7d",
           "#4e8a8b", "#9aa9c4", "#a46b6b", "#8a8f5c", "#c3c8d1"]

CHARTS = {
    "EPOCH-03": ("compute_h100e", "Compute capacity of AI data centers, by company",
                 "Installed compute (H100-equivalents)", 1e6, "M", 1),
    "EPOCH-04": ("it_power_mw", "IT power of AI data centers, by company",
                 "Installed IT power (GW)", 1e3, " GW", 1),
    "EPOCH-05": ("capital_cost_busd", "Capital cost of AI data centers, by company",
                 "Capital cost (2025 US$ billions)", 1, "bn", 0),
}

# Pure functions, shared verbatim with the Node verifier.
GEOMETRY_JS = r"""
function niceTicks(max, count) {
  if (!(max > 0)) return [0];
  const raw = max / count, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const out = [];
  for (let v = 0; v <= max * 1.0000001; v += step) out.push(v);
  return out;
}

function geometry(D, hidden, W, H, M) {
  const vis = D.series.filter(s => !hidden.has(s.name));
  const n = D.dates.length;
  const tops = new Array(n).fill(0);
  const bands = [];
  for (const s of vis) {
    const lower = tops.slice();
    for (let i = 0; i < n; i++) tops[i] += s.values[i];
    bands.push({ name: s.name, color: s.color, lower, upper: tops.slice() });
  }
  const yMax = Math.max(1e-9, Math.max.apply(null, tops)) * 1.08;
  const x0 = D.dates[0], x1 = D.dates[n - 1];
  const sx = t => M.l + (t - x0) / (x1 - x0) * (W - M.l - M.r);
  const sy = v => H - M.b - v / yMax * (H - M.t - M.b);

  for (const b of bands) {
    let d = "";
    for (let i = 0; i < n; i++) d += (i ? "L" : "M") + sx(D.dates[i]).toFixed(2) + " " + sy(b.upper[i]).toFixed(2);
    for (let i = n - 1; i >= 0; i--) d += "L" + sx(D.dates[i]).toFixed(2) + " " + sy(b.lower[i]).toFixed(2);
    b.path = d + "Z";
  }
  return { bands, yMax, tops, sx, sy, yTicks: niceTicks(yMax, 5) };
}

function nearestIndex(D, t) {
  let lo = 0, hi = D.dates.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (D.dates[mid] < t) lo = mid + 1; else hi = mid;
  }
  if (lo > 0 && Math.abs(D.dates[lo - 1] - t) <= Math.abs(D.dates[lo] - t)) lo--;
  return lo;
}
"""

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:14px 16px 10px; background:#fff; color:#1a1a1a;
         font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
  .hd {{ display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:2px; }}
  .pid {{ font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; color:#1f3864;
          letter-spacing:.04em; }}
  h1 {{ font-size:15px; margin:0; font-weight:700; }}
  .sub {{ color:#6b7280; font-size:12px; margin:2px 0 8px; }}
  .badge {{ display:inline-block; background:#1f3864; color:#fff; font-weight:700;
            font-size:10.5px; padding:3px 9px; border-radius:999px; letter-spacing:.02em; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:5px 12px; margin:8px 0 4px; }}
  .lg {{ display:inline-flex; align-items:center; gap:6px; cursor:pointer;
         font-size:12px; border:0; background:none; padding:2px 3px; color:#1a1a1a; }}
  .lg .sw {{ width:12px; height:12px; border-radius:2px; flex:none; }}
  .lg[aria-pressed="true"] {{ opacity:.32; text-decoration:line-through; }}
  .lg:focus-visible {{ outline:2px solid #1f3864; outline-offset:2px; }}
  svg {{ width:100%; height:auto; display:block; touch-action:none; }}
  .grid {{ stroke:#d7dbe2; stroke-width:1; }}
  .axis {{ fill:#6b7280; font-size:11px; }}
  .guide {{ stroke:#1a1a1a; stroke-width:1; stroke-dasharray:3 3; }}
  .tip {{ position:absolute; pointer-events:none; background:#fff; border:1px solid #d7dbe2;
          border-radius:6px; padding:8px 10px; font-size:12px; box-shadow:0 4px 14px rgba(0,0,0,.10);
          opacity:0; transition:opacity .08s; max-width:280px; z-index:5; }}
  .tip b {{ display:block; margin-bottom:4px; font-size:11.5px; color:#6b7280; font-weight:600; }}
  .tip .row {{ display:flex; align-items:center; gap:7px; white-space:nowrap; }}
  .tip .row span.sw {{ width:9px; height:9px; border-radius:2px; flex:none; }}
  .tip .row i {{ font-style:normal; margin-left:auto; font-variant-numeric:tabular-nums;
                 padding-left:14px; }}
  .tot {{ border-top:1px solid #d7dbe2; margin-top:5px; padding-top:4px; font-weight:700; }}
  .foot {{ color:#6b7280; font-size:11px; margin-top:6px; }}
</style>
<div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
<div class="sub">__SUB__ <span class="badge">OBSERVED DATA ONLY</span></div>
<div class="legend" id="lg"></div>
<div style="position:relative">
  <svg id="c" viewBox="0 0 1000 470" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">Hover to read every owner at a date; click a legend entry to remove it from
the stack. Source: Epoch AI, AI Data Centers (CC-BY). Observed to __SNAP__; projected
milestones excluded.</div>
<script>
const D = __DATA__;
__GEOMETRY__
const W=1000, H=470, M={{l:74,r:16,t:14,b:34}};
const svg=document.getElementById('c'), tip=document.getElementById('tip'), lgw=document.getElementById('lg');
const hidden=new Set();
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;}};
const fmt=v=>(v/D.scale).toLocaleString('en-US',{{minimumFractionDigits:D.dp,maximumFractionDigits:D.dp}})+D.unit;
const dstr=t=>new Date(t).toISOString().slice(0,10);

function drawLegend(){{
  lgw.innerHTML='';
  D.series.forEach(s=>{{
    const b=document.createElement('button');
    b.className='lg'; b.type='button';
    b.setAttribute('aria-pressed', hidden.has(s.name)?'true':'false');
    b.innerHTML='<span class="sw" style="background:'+s.color+'"></span>'+s.name;
    b.onclick=()=>{{ hidden.has(s.name)?hidden.delete(s.name):hidden.add(s.name); drawLegend(); draw(); }};
    lgw.appendChild(b);
  }});
}}

let G=null;
function draw(){{
  G=geometry(D,hidden,W,H,M);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  G.yTicks.forEach(v=>{{
    const y=G.sy(v);
    svg.appendChild(el('line',{{x1:M.l,x2:W-M.r,y1:y,y2:y,class:'grid'}}));
    const t=el('text',{{x:M.l-8,y:y+4,class:'axis','text-anchor':'end'}});
    t.textContent=fmt(v); svg.appendChild(t);
  }});
  const y0=new Date(D.dates[0]).getUTCFullYear(), y1=new Date(D.dates[D.dates.length-1]).getUTCFullYear();
  for(let y=y0;y<=y1;y++){{
    const t=Date.UTC(y,0,1); if(t<D.dates[0]||t>D.dates[D.dates.length-1]) continue;
    const x=G.sx(t);
    const lab=el('text',{{x:x,y:H-M.b+18,class:'axis','text-anchor':'middle'}});
    lab.textContent=y; svg.appendChild(lab);
  }}
  G.bands.forEach(b=>svg.appendChild(el('path',{{d:b.path,fill:b.color,stroke:'#fff','stroke-width':.4}})));
  svg.appendChild(el('line',{{x1:M.l,x2:W-M.r,y1:H-M.b,y2:H-M.b,class:'grid'}}));
  const g=el('line',{{class:'guide',id:'gd',y1:M.t,y2:H-M.b,x1:-99,x2:-99}}); svg.appendChild(g);
}}

function move(ev){{
  if(!G) return;
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W;
  if(px<M.l||px>W-M.r){{ tip.style.opacity=0; return; }}
  const t=D.dates[0]+(px-M.l)/(W-M.l-M.r)*(D.dates[D.dates.length-1]-D.dates[0]);
  const i=nearestIndex(D,t);
  const gd=document.getElementById('gd'); const gx=G.sx(D.dates[i]);
  gd.setAttribute('x1',gx); gd.setAttribute('x2',gx);
  let rows='', tot=0;
  D.series.forEach(s=>{{
    if(hidden.has(s.name)) return;
    const v=s.values[i]; tot+=v;
    if(v>0) rows+='<div class="row"><span class="sw" style="background:'+s.color+'"></span>'+s.name+'<i>'+fmt(v)+'</i></div>';
  }});
  tip.innerHTML='<b>'+dstr(D.dates[i])+'</b>'+rows+'<div class="row tot">Total<i>'+fmt(tot)+'</i></div>';
  tip.style.opacity=1;
  const left=gx/W*r.width;
  tip.style.left=Math.min(Math.max(8,left+14), r.width-tip.offsetWidth-8)+'px';
  tip.style.top='8px';
}}
svg.addEventListener('mousemove',move);
svg.addEventListener('mouseleave',()=>{{tip.style.opacity=0;}});
drawLegend(); draw();
</script>
"""


def rows_for(metric, top_n=9):
    with (DATA / "epoch_observed_by_owner.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
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
    series = [{"name": o, "values": filled[o]} for o in keep]
    if rest:
        series.append({"name": "Other owners",
                       "values": [sum(filled[o][i] for o in rest) for i in range(len(dates))]})
    # axis starts where Epoch's own published view starts
    keep_idx = [i for i, d in enumerate(dates) if d >= "2023-01-01"]
    dates = [dates[i] for i in keep_idx]
    for s in series:
        s["values"] = [round(s["values"][i], 4) for i in keep_idx]
    return dates, series


def main():
    with (DATA / "epoch_observed_summary.csv").open(encoding="utf-8") as f:
        meta = {r["metric"]: r for r in csv.DictReader(f)}
    import datetime as dt
    for pid, (metric, title, ylabel, scale, unit, dp) in CHARTS.items():
        dates, series = rows_for(metric)
        m = meta[metric]
        for i, s in enumerate(series):
            s["color"] = COLOURS[i % len(COLOURS)]
        payload = {
            "dates": [int(dt.datetime.fromisoformat(d).replace(
                tzinfo=dt.timezone.utc).timestamp() * 1000) for d in dates],
            "series": series, "scale": scale, "unit": unit, "dp": dp, "ylabel": ylabel,
        }
        sub = (f"Observed to {m['snapshot_date']} across "
               f"{m['sites_with_observed_data']} tracked sites; "
               f"{m['records_projected_excluded']} future-dated milestones excluded.")
        html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                    .replace("__GEOMETRY__", GEOMETRY_JS)
                    .replace("__TITLE__", title).replace("__PID__", pid)
                    .replace("__SUB__", sub).replace("__SNAP__", m["snapshot_date"]))
        (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
        print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
              f"({len(dates)} points, {len(series)} series)")

    # emit the shared maths + one payload for the Node verifier
    dates, series = rows_for("compute_h100e")
    for i, s in enumerate(series):
        s["color"] = COLOURS[i % len(COLOURS)]
    (REPO / "build" / "_interactive_geometry.mjs").write_text(
        GEOMETRY_JS + "\nexport {geometry, nearestIndex, niceTicks};\n"
        + "export const SAMPLE = " + json.dumps({
            "dates": [int(dt.datetime.fromisoformat(d).replace(
                tzinfo=dt.timezone.utc).timestamp() * 1000) for d in dates],
            "series": series}, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("wrote build/_interactive_geometry.mjs for verification")


if __name__ == "__main__":
    main()
