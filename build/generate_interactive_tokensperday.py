#!/usr/bin/env python3
"""Emit self-contained interactive companions for the Tokens Per Day charts.

Two pages, for the two things a printed figure cannot carry here.

    TPD-01   The site's tooltip is not a lookup of the point under the cursor.
    TPD-02   Reading its move() handler: the cursor pixel becomes a continuous
    TPD-03   timestamp, and each series then reports its last observation at or
             before that timestamp, carried forward, with the rows sorted by
             value. Series step on different dates, so the same month shows
             different numbers depending on where in it the cursor sits. These
             pages replay that rule exactly, and add the one thing the site
             leaves implicit: the date each carried-forward value was actually
             disclosed on.

             One page per tab, rather than one page with the site's three-way
             switch, because a companion may not carry a file its static chart
             does not read — and each of TPD-01, TPD-02 and TPD-03 is one tab.
             The tabs are different decompositions of different totals, not
             three views of one, so switching between them was never a
             comparison in the first place.

    TPD-D04  The static chart orders the reconciled bands one way — by width,
             which is the finding. Ordering by size is the other reading and is
             the one a client asks for first; this page carries both.

    TPD-D05  The static chart can only show companies estimated by more than one
             route, because a single route has nothing to cross. This page
             carries every entity the reconciliation touched, filterable, so the
             ones estimated from one number are visible as such.

No external scripts, fonts or styles. Runs offline and inside an iframe.

Usage:
    python build/generate_interactive_tokensperday.py
"""
import csv
import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "tokens-per-day" / "data"
OUT = REPO / "tokens-per-day" / "charts"

# tab -> the plot ID whose static chart plots it, the file it comes from, and
# what the reader needs told about that tab specifically
TABS = [
    ("TOTAL", "TPD-01", "tokens_per_day_total.csv",
     "The estimate and the disclosed floor beneath it. The floor steps on each "
     "new disclosure and is carried forward between them; the estimate is "
     "re-evaluated quarterly."),
    ("COUNTRY", "TPD-02", "tokens_per_day_country.csv",
     "Five regional series that sum to the disclosed floor rather than to the "
     "estimate. Only China is measured, and only at 3 of its 27 points — the "
     "hollow markers are the site's own modelled ones."),
    ("COMPANY", "TPD-03", "tokens_per_day_company.csv",
     "Every company-level disclosure the index holds. The series are not a "
     "partition of anything: Doubao sits inside China's national aggregate, and "
     "Anthropic never disclosed a token figure at all."),
]
# the house palette, used where the site's own colours collide (its Global and
# US blues are three hex digits apart and unreadable side by side)
PALETTE = ["#1f3864", "#b4763a", "#6b8f71", "#7d5a7d", "#4e8a8b", "#a46b6b",
           "#8a8f5c", "#4a6fa5", "#9aa9c4", "#c3c8d1"]

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin:0; background:#fff; color:#1a1a1a; }
  #pg { padding:14px 16px 10px;
         font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
  .hd { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:2px; }
  .pid { font:700 11px/1 ui-monospace,SFMono-Regular,Menlo,monospace; color:#1f3864;
          letter-spacing:.04em; }
  h1 { font-size:15px; margin:0; font-weight:700; }
  .sub { color:#6b7280; font-size:12px; margin:2px 0 8px; }
  .badge { display:inline-block; background:#7d5a7d; color:#fff; font-weight:700;
            font-size:10.5px; padding:3px 9px; border-radius:999px; }
  .ctl { display:flex; flex-wrap:wrap; gap:14px; margin:8px 0 2px; align-items:center; }
  .grp { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
  .cap { color:#6b7280; font-size:11.5px; }
  .btn { font-size:12px; border:1px solid #d7dbe2; background:#fff; color:#1a1a1a;
          padding:3px 10px; border-radius:999px; cursor:pointer; }
  .btn[aria-pressed="true"] { background:#1f3864; color:#fff; border-color:#1f3864; }
  .btn[disabled] { opacity:.35; cursor:not-allowed; }
  .btn:focus-visible { outline:2px solid #1f3864; outline-offset:2px; }
  .legend { display:flex; flex-wrap:wrap; gap:5px 12px; margin:8px 0 4px; }
  .lg { display:inline-flex; align-items:center; gap:6px; font-size:12px; }
  .lg .sw { width:11px; height:11px; border-radius:2px; flex:none; }
  svg { width:100%; height:auto; display:block; touch-action:none; }
  .grid { stroke:#d7dbe2; stroke-width:1; }
  .rule { stroke:#1f3864; stroke-width:1; stroke-dasharray:3 3; }
  .axis { fill:#6b7280; font-size:11px; }
  .axlab { fill:#1a1a1a; font-size:11.5px; }
  .rowlab { fill:#1a1a1a; font-size:11px; }
  .tip { position:absolute; pointer-events:none; background:#fff; border:1px solid #d7dbe2;
          border-radius:6px; padding:8px 10px; font-size:12px;
          box-shadow:0 4px 14px rgba(0,0,0,.10); opacity:0; transition:opacity .08s;
          max-width:340px; z-index:5; }
  .tip b { display:block; margin-bottom:3px; font-size:12.5px; }
  .tip .m { color:#6b7280; }
  .tip .row { display:flex; gap:8px; align-items:baseline; }
  .tip .row i { font-style:normal; margin-left:auto; font-variant-numeric:tabular-nums;
                 font-weight:700; }
  .tip .row s { text-decoration:none; color:#6b7280; font-size:10.5px; }
  .foot { color:#6b7280; font-size:11px; margin-top:6px; }
  .empty { fill:#6b7280; font-size:12px; }
</style>
<div id="pg">
<div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
<div class="sub">__SUB__ <span class="badge">__BADGE__</span></div>
<div class="ctl" id="ctl"></div>
<div class="legend" id="lg"></div>
<div style="position:relative">
  <svg id="c" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">__HINT__ Source: Tokens Per Day (tokensperday.com) — __FILE__ —
chartData objects and evidence ledger as extracted 2026-08-21. Values are the site's own,
copied verbatim. The disclosed floor is measured; everything above it is triangulated from
revenue, hardware, users and telemetry by parties who do not have the numbers.</div>
</div>
<script>
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip');
const ctl=document.getElementById('ctl'), lgw=document.getElementById('lg');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000;
__BODY__
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

# ------------------------------------------------------------- the tab chart
LINES_JS = """
let LOG=0;
const MM={l:62,r:170,t:16,b:42}, H=470;
const ser=()=>D.series;
function fmt(v){ return v>=100? v.toFixed(0) : v>=10? v.toFixed(1) : v.toFixed(2); }
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function my(ms){ const d=new Date(ms); return MON[d.getUTCMonth()]+' '+d.getUTCFullYear(); }
function dmy(ms){ const d=new Date(ms);
  return d.getUTCDate()+' '+MON[d.getUTCMonth()]+' '+d.getUTCFullYear(); }

function buildCtl(){
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
  add('Scale', ['Linear','Log'], LOG, i=>{LOG=i;});
  const s=document.createElement('span'); s.className='cap';
  s.textContent=ser().length+' series, '
    +ser().reduce((a,x)=>a+x.pts.length,0)+' observations';
  ctl.appendChild(s);
}

let SX, SY, YMAX;
function draw(){
  const S=ser();
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  let hi=0; S.forEach(s=>s.pts.forEach(p=>{ if(p[1]>hi) hi=p[1]; }));
  YMAX=hi*1.10;
  const lo=LOG? D.floorLog : 0;
  SX=t=>MM.l+(t-D.x0)/(D.x1-D.x0)*(W-MM.l-MM.r);
  SY=v=>{ if(!LOG) return H-MM.b-v/YMAX*(H-MM.t-MM.b);
    const a=Math.log10(Math.max(v,lo)), b0=Math.log10(lo), b1=Math.log10(YMAX);
    return H-MM.b-(a-b0)/(b1-b0)*(H-MM.t-MM.b); };

  // y grid
  const ticks=[];
  if(LOG){ for(let e=Math.floor(Math.log10(lo)); Math.pow(10,e)<=YMAX; e++) ticks.push(Math.pow(10,e)); }
  else { const step=Math.pow(10,Math.floor(Math.log10(YMAX/5)));
    const st=[1,2,2.5,5,10].map(m=>m*step).find(x=>x>=YMAX/5)||10*step;
    for(let v=0; v<=YMAX; v+=st) ticks.push(v); }
  ticks.forEach(v=>{
    const y=SY(v);
    svg.appendChild(el('line',{x1:MM.l,x2:W-MM.r,y1:y,y2:y,class:'grid'}));
    const t=el('text',{x:MM.l-8,y:y+3.6,class:'axis','text-anchor':'end'});
    t.textContent=v>=1?String(+v.toFixed(0)):String(v); svg.appendChild(t);
  });
  // x ticks, every six months
  for(let y=2024;y<=2026;y++) for(const m of [0,6]){
    const ms=Date.UTC(y,m,15); if(ms<D.x0||ms>D.x1) continue;
    const x=SX(ms);
    svg.appendChild(el('line',{x1:x,x2:x,y1:MM.t,y2:H-MM.b,class:'grid'}));
    const t=el('text',{x:x,y:H-MM.b+16,class:'axis','text-anchor':'middle'});
    t.textContent=MON[m]+' '+y; svg.appendChild(t);
  }
  const yl=el('text',{x:14,y:H/2,class:'axlab','text-anchor':'middle',
    transform:'rotate(-90 14 '+(H/2)+')'});
  yl.textContent='Trillion tokens per day'+(LOG?' (log)':''); svg.appendChild(yl);

  S.forEach(s=>{
    let d='';
    s.pts.forEach((p,i)=>{ d+=(i?'L':'M')+SX(p[0]).toFixed(2)+' '+SY(p[1]).toFixed(2); });
    if(s.pts.length>1) svg.appendChild(el('path',{d:d,fill:'none',stroke:s.c,
      'stroke-width':2.2,'stroke-dasharray':s.est?'7 3':'none'}));
    s.pts.forEach(p=>svg.appendChild(el('circle',{cx:SX(p[0]),cy:SY(p[1]),
      r:p[2]?3.2:2.0,fill:p[2]?s.c:'#fff',stroke:s.c,'stroke-width':1.4})));
    const last=s.pts[s.pts.length-1];
    const t=el('text',{x:SX(last[0])+7,y:SY(last[1])+3.6,class:'axis',
      style:'fill:'+s.c+';font-weight:700'});
    t.textContent=s.n; svg.appendChild(t);
  });
  svg.appendChild(el('line',{id:'rule',x1:-9,x2:-9,y1:MM.t,y2:H-MM.b,class:'rule'}));
  lgw.innerHTML='';
  S.forEach(s=>{ const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:'+s.c+'"></span>'+s.n
      +(s.est?' <span class="m">(est.)</span>':''); lgw.appendChild(d); });
  const h=document.createElement('span'); h.className='lg m';
  h.innerHTML='hollow point = the site\\u2019s own \\u201cnot a real observation\\u201d flag';
  lgw.appendChild(h);
}

svg.addEventListener('pointermove',ev=>{
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W;
  if(px<MM.l||px>W-MM.r){ tip.style.opacity=0; return; }
  // the site's own rule: the cursor pixel is a continuous timestamp, and each
  // series reports its last observation at or before it, carried forward
  const ms=D.x0+(D.x1-D.x0)*(px-MM.l)/(W-MM.l-MM.r);
  const rows=[];
  ser().forEach(s=>{ let pt=null;
    for(const p of s.pts) if(p[0]<=ms) pt=p;
    if(pt) rows.push({n:s.n,c:s.c,v:pt[1],t:pt[0],real:pt[2]}); });
  if(!rows.length){ tip.style.opacity=0; return; }
  rows.sort((a,b)=>b.v-a.v);
  const rule=document.getElementById('rule');
  if(rule){ rule.setAttribute('x1',px); rule.setAttribute('x2',px); }
  let h='<b>'+my(ms)+'</b>';
  rows.forEach(x=>{ h+='<div class="row"><span class="sw" style="display:inline-block;'
    +'width:9px;height:9px;border-radius:2px;background:'+x.c+'"></span>'+x.n
    +'<i>'+fmt(x.v)+'</i></div>'
    +'<div class="row m"><s>&nbsp;&nbsp;&nbsp;as disclosed '+dmy(x.t)
    +(x.real?'':' \\u00b7 modelled point')+'</s></div>'; });
  h+='<div class="m" style="margin-top:4px">trillion tokens / day \\u00b7 '
    +'each series at its most recent disclosure on or before the cursor</div>';
  tip.innerHTML=h; tip.style.opacity=1;
  const w=tip.offsetWidth||300;
  tip.style.left=Math.min(Math.max(8,(px/W*r.width)+16), r.width-w-8)+'px';
  tip.style.top=Math.min(24, r.height-tip.offsetHeight-8)+'px';
});
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;
  const rule=document.getElementById('rule');
  if(rule){ rule.setAttribute('x1',-9); rule.setAttribute('x2',-9); }});

buildCtl(); draw();
"""

# ------------------------------------------------------ the bands / channels
BANDS_JS = """
let MODE=0;
const MM={l:210,r:190,t:16,b:52}, RH=30;
function rows(){ return D.sets[MODE]; }
function fmt(v){ return v>=100? v.toFixed(0) : v>=10? v.toFixed(1)
  : v>=1? v.toFixed(1) : v.toFixed(2); }

function buildCtl(){
  ctl.innerHTML='';
  const g=document.createElement('div'); g.className='grp';
  const c=document.createElement('span'); c.className='cap'; c.textContent='Show';
  g.appendChild(c);
  D.modes.forEach((o,i)=>{
    const b=document.createElement('button'); b.className='btn'; b.type='button';
    b.textContent=o; b.setAttribute('aria-pressed', i===MODE?'true':'false');
    b.onclick=()=>{ MODE=i; buildCtl(); draw(); reportHeight(); };
    g.appendChild(b);
  });
  ctl.appendChild(g);
  const s=document.createElement('span'); s.className='cap';
  s.textContent=rows().length+' rows';
  ctl.appendChild(s);
}

let SX, RR=[], HH;
function draw(){
  const R=rows(); RR=R;
  HH=MM.t+MM.b+R.length*RH;
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute('viewBox','0 0 '+W+' '+HH);
  const lo=D.lo, hi=D.hi;
  SX=v=>MM.l+(Math.log10(Math.max(v,lo))-Math.log10(lo))
    /(Math.log10(hi)-Math.log10(lo))*(W-MM.l-MM.r);
  for(let e=Math.floor(Math.log10(lo)); Math.pow(10,e)<=hi; e++){
    const v=Math.pow(10,e), x=SX(v);
    svg.appendChild(el('line',{x1:x,x2:x,y1:MM.t,y2:HH-MM.b,class:'grid'}));
    const t=el('text',{x:x,y:HH-MM.b+17,class:'axis','text-anchor':'middle'});
    t.textContent=v>=1?String(v):String(v); svg.appendChild(t);
  }
  R.forEach((r,i)=>{
    const y=MM.t+i*RH+RH/2;
    svg.appendChild(el('rect',{x:SX(r.lo),y:y-5,width:Math.max(2,SX(r.hi)-SX(r.lo)),
      height:10,fill:r.c,opacity:r.faded?0.20:0.42,rx:2}));
    svg.appendChild(el('circle',{cx:SX(r.mid),cy:y,r:5,fill:r.c,
      opacity:r.faded?0.35:1}));
    const lab=el('text',{x:MM.l-8,y:y+3.6,class:'rowlab','text-anchor':'end'});
    lab.textContent=r.label; svg.appendChild(lab);
    const val=el('text',{x:SX(r.hi)+8,y:y+3.6,class:'axis'});
    val.textContent=fmt(r.lo)+' \\u2013 '+fmt(r.hi)+(r.disp?'   \\u00d7'+r.disp:'');
    svg.appendChild(val);
  });
  const xl=el('text',{x:(MM.l+W-MM.r)/2,y:HH-MM.b+38,class:'axlab','text-anchor':'middle'});
  xl.textContent='Trillion tokens per day, low to high (log scale)'; svg.appendChild(xl);
  lgw.innerHTML='';
  D.kinds.forEach(k=>{ const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:'+k[1]+'"></span>'+k[0];
    lgw.appendChild(d); });
}

svg.addEventListener('pointermove',ev=>{
  if(!RR.length){ tip.style.opacity=0; return; }
  const r=svg.getBoundingClientRect();
  const py=(ev.clientY-r.top)/r.width*W;
  const i=Math.floor((py-MM.t)/RH);
  if(i<0||i>=RR.length){ tip.style.opacity=0; return; }
  const x=RR[i];
  let h='<b>'+x.label+'</b>';
  h+='<div class="row">Low<i>'+fmt(x.lo)+'</i></div>';
  h+='<div class="row">Published figure<i>'+fmt(x.mid)+'</i></div>';
  h+='<div class="row">High<i>'+fmt(x.hi)+'</i></div>';
  if(x.disp) h+='<div class="row m">Width<i>\\u00d7'+x.disp+'</i></div>';
  if(x.note) h+='<div class="m" style="margin-top:4px">'+x.note+'</div>';
  tip.innerHTML=h; tip.style.opacity=1;
  const w=tip.offsetWidth||300;
  tip.style.left=Math.min(Math.max(8,(MM.l/W*r.width)+20), r.width-w-8)+'px';
  tip.style.top=Math.min(Math.max(8,(MM.t+i*RH)/W*r.width), r.height-tip.offsetHeight-8)+'px';
});
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;});

buildCtl(); draw();
"""


def read(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ms(date):
    """Epoch milliseconds at UTC midnight, matching the site's own timestamps.

    Parsed as UTC explicitly: a naive strptime would take the build machine's
    timezone and shift every point by hours, which on a monthly axis is enough
    to move an observation into the previous month.
    """
    return int(datetime.strptime(date + " +0000", "%Y-%m-%d %z").timestamp() * 1000)


def emit(pid, title, sub, badge, hint, files, body, payload):
    html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                .replace("__BODY__", body)
                .replace("__TITLE__", title).replace("__PID__", pid)
                .replace("__SUB__", sub).replace("__BADGE__", badge)
                .replace("__HINT__", hint).replace("__FILE__", " + ".join(files)))
    (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
    print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)}")


def build_lines():
    ts = read("tpd_timeseries.csv")
    # the axis domain is shared across all three pages, so a reader moving down
    # the gallery reads the same x scale on each
    every = [ms(r["date"]) for r in ts]
    lows = [float(r["value"]) for r in ts if float(r["value"]) > 0]
    for tab, pid, src, blurb in TABS:
        rows = [r for r in ts if r["tab"] == tab]
        names = []
        for r in rows:
            if r["series"] not in names:
                names.append(r["series"])
        # largest last value first, so the legend reads in the order the chart does
        def lastv(nm):
            pts = [r for r in rows if r["series"] == nm]
            return float(pts[-1]["value"])
        names.sort(key=lambda nm: -lastv(nm))
        series = []
        for i, nm in enumerate(names):
            pts = [[ms(r["date"]), float(r["value"]),
                    1 if r["is_real"].lower() == "true" else 0]
                   for r in rows if r["series"] == nm]
            pts.sort()
            series.append({
                "n": nm, "c": PALETTE[i % len(PALETTE)], "pts": pts,
                # the site draws its modeled series dashed; so does this
                "est": 1 if ("est." in nm or nm == "Estimated total") else 0})
        n_pts = sum(len(s["pts"]) for s in series)
        emit(pid,
             f"Tokens per day over time — {tab.lower()}, with the site's own tooltip",
             f"{blurb} All {len(series)} series and {n_pts} observations, with the "
             f"tooltip replaying the site's own rule: each series at its most recent "
             f"disclosure on or before the cursor, carried forward.",
             "MEASURED FLOOR vs MODELED ESTIMATE" if tab == "TOTAL"
             else ("DISCLOSED FLOOR · company statements" if tab == "COMPANY"
                   else "MEASURED FLOOR vs MODELED ESTIMATE"),
             "Move the cursor across the chart for every series at that date, and "
             "the date each figure was actually disclosed on.",
             [src], LINES_JS,
             {"series": series, "x0": min(every), "x1": max(every),
              "floorLog": min(lows) * 0.7})


DEMAND, CEIL, OUT_C = "#1f3864", "#b4763a", "#9aa9c4"


def build_bands():
    rec = read("tpd_reconciled.csv")
    bands = []
    for r in rec:
        excluded = r["in_global_sum"] == "no"
        bands.append({
            "label": r["entity"] + ("  (excluded)" if excluded else ""),
            "lo": float(r["low"]), "mid": float(r["mid"]), "hi": float(r["high"]),
            "disp": r["dispersion"], "faded": bool(excluded),
            "c": CEIL if r["entity"] == "GLOBAL" else (OUT_C if excluded else DEMAND),
            "note": r["notes"]})
    by_width = sorted(bands, key=lambda b: float(b["disp"]))
    by_size = sorted(bands, key=lambda b: -b["mid"])
    lo = min(b["lo"] for b in bands) * 0.6
    hi = max(b["hi"] for b in bands) * 1.6
    emit("TPD-D04",
         "What each company's estimate is actually worth",
         f"The reconciled low-to-high band behind each of {len(bands) - 1} company "
         f"figures and the global total. The site publishes the middle of each as a "
         f"single number; the bar is what the method supports.",
         "MODELED ESTIMATE · not a measurement",
         "Order by width or by size; hover a row for the band and the site's own "
         "note on it.",
         ["reconciled_company_estimates.csv"],
         BANDS_JS,
         {"modes": ["By width", "By size"], "sets": [by_width, by_size],
          "lo": lo, "hi": hi,
          "kinds": [["In the global sum", DEMAND],
                    ["The global total", CEIL],
                    ["Excluded from the global sum", OUT_C]]})


def build_channels():
    fan = read("tpd_channels.csv")
    channels = []
    for r in fan:
        faded = r["included_in_reconciliation"] == "no"
        channels.append({
            "entity": r["entity"],
            "label": f"{r['entity']}  ·  {r['channel']}",
            "lo": float(r["low"]), "mid": float(r["mid"]), "hi": float(r["high"]),
            "disp": "", "faded": faded,
            "c": OUT_C if faded else (
                CEIL if r["value_kind"] == "capacity_ceiling" else DEMAND),
            "note": (("EXCLUDED — back-tested "
                      f"{r['backtest_ratio']}x against its own anchor. " if faded else "")
                     + ("A ceiling, not a demand estimate. "
                        if r["value_kind"] == "capacity_ceiling" else "")
                     + r["formula"])})
    # the static chart can only carry entities with more than one route; here
    # the single-route ones are shown too, marked as what they are
    multi = sorted({c["entity"] for c in channels
                    if sum(1 for x in channels if x["entity"] == c["entity"]) > 1})
    sets = [[c for c in channels if c["entity"] in multi], channels]
    lo = min(c["lo"] for c in channels) * 0.6
    hi = max(c["hi"] for c in channels) * 1.6
    emit("TPD-D05",
         "Every route behind every estimate",
         f"All {len(channels)} channel estimates the reconciliation ran, across "
         f"{len({c['entity'] for c in channels})} entities. A demand channel asks how "
         f"many tokens were wanted; a hardware channel asks how many could have been "
         f"served, and is a ceiling rather than an estimate.",
         "MODELED ESTIMATE · not a measurement",
         "Show only the companies with more than one route, or all of them; hover a "
         "row for the formula and the back-test.",
         ["channel_fan_per_company.csv"],
         BANDS_JS,
         {"modes": [f"Cross-checked ({len(multi)} companies)",
                    f"All routes ({len(channels)})"],
          "sets": sets, "lo": lo, "hi": hi,
          "kinds": [["Demand estimate", DEMAND],
                    ["Hardware ceiling", CEIL],
                    ["Excluded on back-test", OUT_C]]})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    build_lines()
    build_bands()
    build_channels()


if __name__ == "__main__":
    main()
