#!/usr/bin/env python3
"""Emit self-contained interactive companions for the AI Companies charts.

Epoch's own figure is interactive: you hover a point to find out which company
and which report it is. The static SVG cannot say that, and with observations
reported on their own dates by eleven companies it is the first thing a reader
asks. These pages add it - hover a point for the company, the date and the
figure behind it, click a legend entry to drop that company - over exactly the
same derived CSVs the static charts read.

Every rule the static charts follow holds here too: Epoch's excluded rows are
already gone from the derived tables, no value is projected, and a fitted line
stops at the last observation.

No external scripts, fonts or styles: the page works offline and inside an
iframe on GitHub Pages.

Usage:
    python build/generate_interactive_companies.py
"""
import csv
import json
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "ai-companies" / "data"
OUT = REPO / "ai-companies" / "charts"

# same assignment as generate_charts.py, so a company keeps its colour across
# the static chart, the interactive companion and every other chart in the domain
COMPANY_COLOUR = {
    "OpenAI": "#1f3864", "Anthropic": "#b4763a", "Google": "#4a6fa5",
    "Meta": "#6b8f71", "xAI": "#7d5a7d", "DeepSeek": "#4e8a8b",
    "Mistral AI": "#a46b6b", "Cohere": "#8a8f5c", "Z.ai (Zhipu)": "#9aa9c4",
    "MiniMax": "#55606e", "Moonshot AI": "#5f7a99",
}
RESIDUAL = "#c9ced8"

SRC_FILE = {
    "revenue": "ai_companies_revenue_reports.csv",
    "usage": "ai_companies_usage_reports.csv",
    "staff": "ai_companies_staff_reports.csv",
    "funding": "ai_companies_funding_rounds.csv",
}

# pid -> table, value column, connect points, trend metric, title, y label,
#        y unit and the fields quoted in the tooltip
CHARTS = {
    "COMPANIES-01": dict(
        table="companies_revenue.csv", col="revenue_usd", src="revenue",
        connect=True, trend="revenue_usd", unit="usd", scale_toggle=True,
        title="Annualised revenue of AI companies",
        ylabel="Annualised revenue (USD)", value="Annualised revenue",
        ctx=("revenue_type", "source_type"), open_col="annualised_from_period"),
    "COMPANIES-04": dict(
        table="companies_usage.csv", col="active_users", src="usage",
        connect=True, trend="active_users", unit="count",
        title="Active users of AI products",
        ylabel="Active users", value="Active users",
        ctx=("product", "active_users_period"), open_col=None),
    "COMPANIES-05": dict(
        table="companies_usage.csv", col="daily_tokens", src="usage",
        connect=True, trend=None, unit="count",
        title="Tokens processed per day, by company",
        ylabel="Tokens processed per day", value="Tokens per day",
        ctx=("product", "source_type"), open_col=None),
    "COMPANIES-06": dict(
        table="companies_staff.csv", col="staff_count", src="staff",
        connect=True, trend="staff_count", unit="count", scale_toggle=True,
        title="Staff at AI companies",
        ylabel="Staff count", value="Staff count",
        ctx=("scope", "division"), open_col="_division"),
    "COMPANIES-08": dict(
        table="companies_funding.csv", col="equity_usd", src="funding",
        connect=False, trend=None, unit="usd",
        title="Equity raised per funding round",
        ylabel="Equity raised in the round (USD)", value="Equity raised",
        ctx=("round_type", "status"), open_col=None),
    "COMPANIES-09": dict(
        table="companies_funding.csv", col="valuation_usd", src="funding",
        connect=True, trend=None, unit="usd",
        title="Post-money valuation of AI companies",
        ylabel="Post-money valuation (USD)", value="Post-money valuation",
        ctx=("round_type", "status"), open_col=None),
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

function yearTicks(lo, hi) {
  const span = hi - lo;
  const step = span > 45 ? 10 : span > 18 ? 5 : span > 8 ? 2 : 1;
  const out = [];
  for (let y = Math.ceil(lo / step) * step; y <= hi; y += step) out.push(y);
  return out;
}

function geometry(D, hidden, W, H, M) {
  const shown = [];
  for (let i = 0; i < D.pts.length; i++) if (!hidden.has(D.pts[i][2])) shown.push(i);
  const xs = shown.map(i => D.pts[i][0]), ys = shown.map(i => D.pts[i][1]);
  const yLo = Math.min.apply(null, ys), yHi = Math.max.apply(null, ys);
  let xLo = Math.min.apply(null, xs), xHi = Math.max.apply(null, xs);
  const pad = Math.max((xHi - xLo) * 0.04, 0.15);
  xLo -= pad; xHi += pad;
  const sy = LOGY
    ? v => H - M.b - (Math.log10(v) - Math.log10(yLo))
             / (Math.log10(yHi) - Math.log10(yLo) || 1) * (H - M.t - M.b)
    : v => H - M.b - (v - 0) / (yHi - 0 || 1) * (H - M.t - M.b);
  const sx = v => M.l + (v - xLo) / (xHi - xLo || 1) * (W - M.l - M.r);
  return {
    shown, sx, sy, xLo, xHi, yLo, yHi,
    yTicks: LOGY ? decadeTicks(yLo, yHi, 8) : linearTicks(yHi, 6),
    xTicks: yearTicks(xLo, xHi),
  };
}

function linearTicks(hi, n) {
  const raw = hi / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || 10 * mag;
  const out = []; for (let v = 0; v <= hi * 1.0001; v += step) out.push(+v.toFixed(6));
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
  body { margin:0; background:#fff; color:#1a1a1a; }
  #pg { padding:14px 16px 10px; background:#fff; color:#1a1a1a;
         font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
  .hd { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:2px; }
  .pid { font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; color:#1f3864;
          letter-spacing:.04em; }
  h1 { font-size:15px; margin:0; font-weight:700; }
  .sub { color:#6b7280; font-size:12px; margin:2px 0 8px; }
  .badge { display:inline-block; background:#1f3864; color:#fff; font-weight:700;
            font-size:10.5px; padding:3px 9px; border-radius:999px; letter-spacing:.02em; }
  .ctl { display:flex; flex-wrap:wrap; gap:14px; margin:8px 0 2px; align-items:center; }
  .grp { display:flex; gap:6px; align-items:center; }
  .cap { color:#6b7280; font-size:11.5px; }
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
  .tip { position:absolute; pointer-events:none; background:#fff; border:1px solid #d7dbe2;
          border-radius:6px; padding:8px 10px; font-size:12px; box-shadow:0 4px 14px rgba(0,0,0,.10);
          opacity:0; transition:opacity .08s; max-width:290px; z-index:5; }
  .tip b { display:block; margin-bottom:3px; font-size:12.5px; }
  .tip .m { color:#6b7280; }
  .foot { color:#6b7280; font-size:11px; margin-top:6px; }
</style>
<div id="pg">
<div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
<div class="sub">__SUB__ <span class="badge">OBSERVED DATA ONLY</span></div>
<div class="ctl" id="ctl"></div>
<div class="legend" id="lg"></div>
<div style="position:relative">
  <svg id="c" viewBox="0 0 1000 520" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">Hover a point for the company and the report behind it; click a legend
entry to remove that company. Source: Epoch AI, AI Companies (CC-BY) — __FILE__ —
epoch.ai/data/ai-companies. A company appears only where Epoch records the plotted value;
nothing is imputed and no line is drawn past the last observation.</div>
</div>
<script>
const D = __DATA__;
__GEOMETRY__
const W=1000, H=520, M={l:86,r:18,t:16,b:52};
const svg=document.getElementById('c'), tip=document.getElementById('tip'), lgw=document.getElementById('lg');
const hidden=new Set();
// Epoch offers scale and the growth regression as controls; they live here
// rather than as separate charts
let LOGY=true, TREND=false;
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};

function human(v){
  for(const [c,u] of [[1e12,'T'],[1e9,'B'],[1e6,'M'],[1e3,'k']])
    if(v>=c) return (v/c).toLocaleString('en-US',{maximumFractionDigits:v/c<10?1:0})+u;
  return v.toLocaleString('en-US',{maximumFractionDigits:0});
}
const fmtY = v => (D.unit==='usd' ? '$' : '') + human(v);
const fmtX = v => String(Math.round(v));

function buildCtl(){
  const ctl=document.getElementById('ctl'); if(!ctl) return;
  ctl.innerHTML='';
  const add=(cap,opts,cur,pick)=>{
    const g=document.createElement('div'); g.className='grp';
    const c=document.createElement('span'); c.className='cap'; c.textContent=cap;
    g.appendChild(c);
    opts.forEach((o,i)=>{
      const b=document.createElement('button'); b.className='btn'; b.type='button';
      b.textContent=o; b.setAttribute('aria-pressed', i===cur?'true':'false');
      b.onclick=()=>{ pick(i); buildCtl(); draw(); reportHeight(); };
      g.appendChild(b);
    });
    ctl.appendChild(g);
  };
  if(D.scaleToggle) add('Scale',['Logarithmic','Linear'],LOGY?0:1,i=>{LOGY=i===0;});
  if(D.fits && D.fits.length) add('Growth trend',['Off','Fitted'],TREND?1:0,i=>{TREND=i===1;});
}

function drawLegend(){
  lgw.innerHTML='';
  D.groups.forEach((g,i)=>{
    const b=document.createElement('button');
    b.className='lg'; b.type='button';
    b.setAttribute('aria-pressed', hidden.has(i)?'true':'false');
    b.innerHTML='<span class="sw" style="background:'+g.color+'"></span>'+g.name+' ('+g.n+')';
    // toggled in place, so focus and the pressed state survive the click
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

  // one polyline per visible company, in the order the observations were reported
  if(D.connect){
    D.groups.forEach((g,gi)=>{
      if(hidden.has(gi)) return;
      const seq=D.pts.map((p,i)=>[p,i]).filter(([p])=>p[2]===gi)
                     .sort((a,b)=>a[0][0]-b[0][0]);
      if(seq.length<2) return;
      svg.appendChild(el('polyline',{
        points:seq.map(([p])=>G.sx(p[0]).toFixed(2)+','+G.sy(p[1]).toFixed(2)).join(' '),
        fill:'none',stroke:g.color,'stroke-width':1.6,'stroke-opacity':.85}));
    });
  }

  // fitted growth, dashed, stopping at the last observation - never projected
  (TREND ? (D.fits||[]) : []).forEach(f=>{
    if(hidden.has(f[0])) return;
    const [gi,x0,x1,slope,icept]=f;
    svg.appendChild(el('line',{x1:G.sx(x0),y1:G.sy(Math.pow(10,slope*x0+icept)),
      x2:G.sx(x1),y2:G.sy(Math.pow(10,slope*x1+icept)),
      stroke:D.groups[gi].color,'stroke-width':2.1,'stroke-dasharray':'6 3'}));
  });

  G.shown.forEach(i=>{
    const p=D.pts[i], g=D.groups[p[2]];
    // hollow markers carry the same caveat as the static chart
    svg.appendChild(el('circle',{cx:G.sx(p[0]).toFixed(2),cy:G.sy(p[1]).toFixed(2),r:4,
      fill:p[5]?'#fff':g.color,stroke:p[5]?g.color:'#fff','stroke-width':p[5]?1.6:.7,
      'fill-opacity':p[5]?1:.9}));
  });
  const hl=el('circle',{id:'hl',r:7,fill:'none',stroke:'#1a1a1a','stroke-width':1.6,
                        cx:-99,cy:-99}); svg.appendChild(hl);
}

function move(ev){
  if(!G) return;
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W, py=(ev.clientY-r.top)/r.height*H;
  const i=nearest(D,G,px,py,16);
  const hl=document.getElementById('hl');
  if(i<0){ tip.style.opacity=0; hl.setAttribute('cx',-99); return; }
  const p=D.pts[i];
  hl.setAttribute('cx',G.sx(p[0])); hl.setAttribute('cy',G.sy(p[1]));
  tip.innerHTML='<b>'+D.groups[p[2]].name+'</b>'
    +'<div>'+D.value+': '+fmtY(p[1])+'</div>'
    +'<div class="m">'+p[3]+(p[4]?' &middot; '+p[4]:'')+'</div>';
  tip.style.opacity=1;
  const left=G.sx(p[0])/W*r.width, top=G.sy(p[1])/H*r.height;
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
    return y + (date(y, m, d) - date(y, 1, 1)).days / 365.25


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trends = read("companies_trends.csv")
    meta = read("companies_summary.csv")[0]

    for pid, cfg in CHARTS.items():
        rows = [r for r in read(cfg["table"]) if r.get(cfg["col"])]
        if cfg["table"] == "companies_funding.csv":
            rows = [r for r in rows if r["closed"].strip().lower() == "true"]
        # a log axis cannot carry a zero, exactly as on the static chart
        rows = [r for r in rows if float(r[cfg["col"]]) > 0]
        if cfg["col"] == "staff_count":
            for r in rows:
                r["_division"] = str((r.get("scope") or "") != "Full company")

        # companies ordered by peak value, so the legend reads top-down like the chart
        peak = {}
        for r in rows:
            v = float(r[cfg["col"]])
            peak[r["company"]] = max(peak.get(r["company"], 0), v)
        order = sorted(peak, key=lambda c: -peak[c])
        index = {c: i for i, c in enumerate(order)}

        pts, group_n = [], {}
        for r in rows:
            gi = index[r["company"]]
            group_n[gi] = group_n.get(gi, 0) + 1
            ctx = " · ".join(x for x in (r.get(c) or "" for c in cfg["ctx"]) if x)
            is_open = bool(cfg["open_col"]) and \
                str(r.get(cfg["open_col"], "")).strip().lower() == "true"
            pts.append([round(dec_year(r["date"]), 4), float(r[cfg["col"]]), gi,
                        r["date"], ctx, 1 if is_open else 0])

        groups = [{"name": c, "color": COMPANY_COLOUR.get(c, RESIDUAL),
                   "n": group_n.get(index[c], 0)} for c in order]

        fits = []
        if cfg["trend"]:
            for t in trends:
                if t["metric"] == cfg["trend"] and t["company"] in index:
                    fits.append([index[t["company"]], float(t["x_min"]),
                                 float(t["x_max"]), float(t["oom_per_year"]),
                                 float(t["intercept_log10"])])

        payload = {"pts": pts, "groups": groups, "connect": cfg["connect"],
                   "fits": fits, "unit": cfg["unit"], "value": cfg["value"],
                   "scaleToggle": bool(cfg.get("scale_toggle")),
                   "yLabel": cfg["ylabel"], "xLabel": "Date of report"}

        sub = (f"{len(pts):,} observations across {len(groups)} companies, "
               f"of {int(meta['tracked_companies'])} Epoch tracks. "
               f"Observed to {meta['observed_to']}.")
        bits = []
        if cfg.get("scale_toggle"):
            bits.append("switch the scale")
        if fits:
            bits.append(f"turn on the growth fit for {len(fits)} "
                        f"{'company' if len(fits) == 1 else 'companies'}")
        if bits:
            sub += " Above, " + " or ".join(bits) + "."

        html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                    .replace("__GEOMETRY__", GEOMETRY_JS)
                    .replace("__TITLE__", cfg["title"]).replace("__PID__", pid)
                    .replace("__SUB__", sub)
                    .replace("__FILE__", SRC_FILE[cfg["src"]]))
        (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
        print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
              f"({len(pts):,} points, {len(groups)} companies, {len(fits)} fits)")


if __name__ == "__main__":
    main()
