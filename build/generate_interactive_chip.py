#!/usr/bin/env python3
"""Emit self-contained interactive companions for the AI Chip Components charts.

Epoch publishes one configurable figure with four tabs, a colour-by control and
an absolute/share switch. The static gallery carries the settings that matter as
two-panel figures; this page carries the whole control surface, which is what the
source actually is.

Three pages:

    CHIP-01   the explorer: tab x colour-by x absolute/share, over the eight
              complete quarters, with the world-supply denominator drawn on the
              absolute views
    CHIP-D03  chip-level concentration - 17 chip types, too many to label
    CHIP-D04  the published uncertainty, where hovering is the only way to read
              a 5th-95th percentile range off a point

No external scripts, fonts or styles. Runs offline and inside an iframe.

Usage:
    python build/generate_interactive_chip.py
"""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "ai-chip-components" / "data"
OUT = REPO / "ai-chip-components" / "charts"
SRC = "quarterly_by_designer.csv"

DESIGNERS = [("NVIDIA", "#1f3864"), ("Google", "#4a6fa5"),
             ("Amazon", "#6b8f71"), ("AMD", "#b4763a")]
COMPONENTS = [("logic_cost_usd", "Logic wafers", "#1f3864"),
              ("cowos_cost_usd", "CoWoS packaging", "#4e8a8b"),
              ("hbm_cost_usd", "HBM memory", "#b4763a"),
              ("aux_cost_usd", "Auxiliary", "#9aa9c4")]
OTHER = ("Other", "#c3c8d1")

TABS = [
    dict(key="cost", label="Total cost", col="total_cost_usd", scale=1e9,
         unit="$", suffix="bn", dp=1, supply=None,
         ylabel="Component cost (US$ billions)"),
    dict(key="logic", label="Logic", col="logic_wafers", scale=1e3,
         unit="", suffix="k", dp=1, supply="logic_supply_wafers",
         ylabel="Logic wafers consumed (thousands)"),
    dict(key="cowos", label="Packaging", col="cowos_wafers", scale=1e3,
         unit="", suffix="k", dp=1, supply="cowos_supply_wafers",
         ylabel="CoWoS wafers consumed (thousands)"),
    dict(key="hbm", label="Memory", col="hbm_cost_usd", scale=1e9,
         unit="$", suffix="bn", dp=1, supply="hbm_supply_usd",
         ylabel="HBM consumed (US$ billions)"),
]

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
  .badge { display:inline-block; background:#1f3864; color:#fff; font-weight:700;
            font-size:10.5px; padding:3px 9px; border-radius:999px; }
  .ctl { display:flex; flex-wrap:wrap; gap:14px; margin:8px 0 2px; align-items:center; }
  .grp { display:flex; gap:6px; align-items:center; }
  .cap { color:#6b7280; font-size:11.5px; }
  .btn { font-size:12px; border:1px solid #d7dbe2; background:#fff; color:#1a1a1a;
          padding:3px 10px; border-radius:999px; cursor:pointer; }
  .btn[aria-pressed="true"] { background:#1f3864; color:#fff; border-color:#1f3864; }
  .btn:focus-visible { outline:2px solid #1f3864; outline-offset:2px; }
  .legend { display:flex; flex-wrap:wrap; gap:5px 12px; margin:8px 0 4px; }
  .lg { display:inline-flex; align-items:center; gap:6px; font-size:12px; color:#1a1a1a; }
  .lg .sw { width:11px; height:11px; border-radius:2px; flex:none; }
  svg { width:100%; height:auto; display:block; touch-action:none; }
  .grid { stroke:#d7dbe2; stroke-width:1; }
  .axis { fill:#6b7280; font-size:11px; }
  .axlab { fill:#1a1a1a; font-size:11.5px; }
  .tip { position:absolute; pointer-events:none; background:#fff; border:1px solid #d7dbe2;
          border-radius:6px; padding:8px 10px; font-size:12px;
          box-shadow:0 4px 14px rgba(0,0,0,.10); opacity:0; transition:opacity .08s;
          max-width:290px; z-index:5; }
  .tip b { display:block; margin-bottom:3px; font-size:12.5px; }
  .tip .m { color:#6b7280; }
  .tip .row { display:flex; gap:8px; align-items:center; }
  .tip .row i { font-style:normal; margin-left:auto; font-variant-numeric:tabular-nums; }
  .foot { color:#6b7280; font-size:11px; margin-top:6px; }
</style>
<div id="pg">
<div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
<div class="sub">__SUB__ <span class="badge">COMPLETE QUARTERS ONLY</span></div>
<div class="ctl" id="ctl"></div>
<div class="legend" id="lg"></div>
<div style="position:relative">
  <svg id="c" viewBox="0 0 1000 470" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">__HINT__ Source: Epoch AI, AI Chip Components (CC-BY) — __FILE__ —
epoch.ai/data/ai-chip-components. Every value is a Monte Carlo median over 10,000 draws;
medians do not add, because Epoch simulates each aggregation separately. Q1 2026 is
incomplete at source and excluded.</div>
</div>
<script>
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip');
const ctl=document.getElementById('ctl'), lgw=document.getElementById('lg');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000,H=470,M={l:86,r:20,t:16,b:56};
let TI=0, GI=0, SI=0;               // tab, colour-by, absolute/share

function tab(){ return D.tabs[TI]; }
function byDesigner(){ return GI===1; }
function shareMode(){ return SI===1; }

function fmt(v,dp,unit,suffix){
  return (unit||'')+v.toLocaleString('en-US',{minimumFractionDigits:dp,maximumFractionDigits:dp})+(suffix||'');
}
function series(){
  const t=tab();
  // the cost tab is the only one Epoch colours by component
  const useComp = (t.key==='cost') && !byDesigner();
  const out=[];
  if(useComp){
    for(const c of D.components) out.push({name:c[1], color:c[2], vals:D.comp[t.key][c[0]]});
  } else {
    for(const d of D.designers) out.push({name:d[0], color:d[1], vals:D.des[t.key][d[0]]});
    if(shareMode() && t.supply) out.push({name:D.other[0], color:D.other[1], vals:D.residual[t.key]});
  }
  return out;
}
function totals(s){
  return D.quarters.map((_,i)=>s.reduce((a,x)=>a+(x.vals[i]||0),0));
}

function buildCtl(){
  ctl.innerHTML='';
  const add=(cap,opts,cur,pick)=>{
    if(opts.length<2) return;
    const g=document.createElement('div'); g.className='grp';
    const c=document.createElement('span'); c.className='cap'; c.textContent=cap; g.appendChild(c);
    opts.forEach((o,i)=>{
      const b=document.createElement('button'); b.className='btn'; b.type='button';
      b.textContent=o; b.setAttribute('aria-pressed', i===cur?'true':'false');
      b.onclick=()=>{ pick(i); buildCtl(); draw(); reportHeight(); };
      g.appendChild(b);
    });
    ctl.appendChild(g);
  };
  add('Tab', D.tabs.map(t=>t.label), TI, i=>{TI=i; if(!D.tabs[i].supply && SI===1) SI=1;});
  if(tab().key==='cost') add('Colour by', ['Component','Designer'], GI, i=>{GI=i;});
  add('Show as', [tab().supply?'Amount':'Amount', tab().supply?'Share of supply':'Share of cost'],
      SI, i=>{SI=i;});
}

let S=[], TOT=[], SX=null, SY=null;
function draw(){
  const t=tab(); S=series();
  const pct=shareMode();
  let vals;
  if(pct){
    const raw=totals(S);
    vals=S.map(s=>s.vals.map((v,i)=>raw[i]?v/raw[i]*100:0));
  } else {
    vals=S.map(s=>s.vals.slice());
  }
  TOT=D.quarters.map((_,i)=>vals.reduce((a,v)=>a+(v[i]||0),0));
  let hi = pct?100:Math.max.apply(null,TOT);
  const supply = (!pct && t.supply) ? D.supply[t.key] : null;
  if(supply) hi=Math.max(hi, Math.max.apply(null,supply));
  hi*= pct?1.02:1.16;

  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const n=D.quarters.length, bw=(W-M.l-M.r)/n*0.62;
  SX=i=>M.l+(W-M.l-M.r)*(i+0.5)/n;
  SY=v=>H-M.b-(v/hi)*(H-M.t-M.b);

  const ticks=pct?[0,20,40,60,80,100]:niceTicks(hi,5);
  ticks.forEach(v=>{
    const y=SY(v);
    svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:y,y2:y,class:'grid'}));
    const tx=el('text',{x:M.l-8,y:y+4,class:'axis','text-anchor':'end'});
    tx.textContent=pct?v+'%':fmt(v,v<10?t.dp:0,t.unit,t.suffix); svg.appendChild(tx);
  });
  D.quarters.forEach((q,i)=>{
    let acc=0;
    vals.forEach((vv,k)=>{
      const v=vv[i]||0; if(v<=0) return;
      svg.appendChild(el('rect',{x:SX(i)-bw/2,y:SY(acc+v),width:bw,
        height:Math.max(0,SY(acc)-SY(acc+v)),fill:S[k].color,stroke:'#fff','stroke-width':.8}));
      acc+=v;
    });
    const lab=el('text',{x:SX(i),y:H-M.b+18,class:'axis','text-anchor':'middle'});
    lab.textContent=q.split(' ')[0]; svg.appendChild(lab);
    const yr=el('text',{x:SX(i),y:H-M.b+31,class:'axis','text-anchor':'middle'});
    yr.textContent=q.split(' ')[1]; svg.appendChild(yr);
    if(!pct){
      const tt=el('text',{x:SX(i),y:SY(TOT[i])-6,class:'axis','text-anchor':'middle',
                          style:'font-weight:700;fill:#1a1a1a'});
      tt.textContent=fmt(TOT[i],t.dp,t.unit,t.suffix); svg.appendChild(tt);
    }
  });
  if(supply){
    const pts=supply.map((v,i)=>SX(i)+','+SY(v)).join(' ');
    svg.appendChild(el('polyline',{points:pts,fill:'none',stroke:'#6b7280',
      'stroke-width':1.6,'stroke-dasharray':'6 3'}));
  }
  const xl=el('text',{x:(M.l+W-M.r)/2,y:H-M.b+50,class:'axlab','text-anchor':'middle'});
  xl.textContent='Quarter'; svg.appendChild(xl);
  const yl=el('text',{x:0,y:0,class:'axlab','text-anchor':'middle',
    transform:'translate(15,'+((M.t+H-M.b)/2)+') rotate(-90)'});
  yl.textContent=pct?(t.supply?'Share of world supply (%)':'Share of cost (%)'):t.ylabel;
  svg.appendChild(yl);

  lgw.innerHTML='';
  S.forEach(s=>{
    const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:'+s.color+'"></span>'+s.name;
    lgw.appendChild(d);
  });
  if(supply){
    const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:#6b7280"></span>World supply (all users)';
    lgw.appendChild(d);
  }
  window._vals=vals; window._pct=pct;
}
function niceTicks(hi,n){
  const raw=hi/n, mag=Math.pow(10,Math.floor(Math.log10(raw)));
  const step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=raw)||10*mag;
  const out=[]; for(let v=0;v<=hi*1.0001;v+=step) out.push(+v.toFixed(6));
  return out;
}

svg.addEventListener('pointermove',ev=>{
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W;
  const n=D.quarters.length;
  const i=Math.round((px-M.l)/((W-M.l-M.r)/n)-0.5);
  if(i<0||i>=n){ tip.style.opacity=0; return; }
  const t=tab(), pct=window._pct, vals=window._vals;
  let h='<b>'+D.quarters[i]+'</b>';
  S.forEach((s,k)=>{
    const v=vals[k][i]||0;
    h+='<div class="row"><span class="sw" style="display:inline-block;width:9px;height:9px;'
      +'border-radius:2px;background:'+s.color+'"></span>'+s.name
      +'<i>'+(pct?v.toFixed(1)+'%':fmt(v,t.dp,t.unit,t.suffix))+'</i></div>';
  });
  if(!pct) h+='<div class="row" style="border-top:1px solid #d7dbe2;margin-top:4px;'
             +'padding-top:4px;font-weight:700">Total<i>'+fmt(TOT[i],t.dp,t.unit,t.suffix)+'</i></div>';
  tip.innerHTML=h; tip.style.opacity=1;
  const left=SX(i)/W*r.width;
  tip.style.left=Math.min(Math.max(8,left+14), r.width-tip.offsetWidth-8)+'px';
  tip.style.top='12px';
});
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;});

buildCtl(); draw();
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


def qkey(q):
    a, b = q.split()
    return (int(b), int(a[1]))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = read("chip_quarterly_by_designer.csv")
    sup = {r["quarter"]: r for r in read("chip_supply.csv")}
    quarters = sorted({r["quarter"] for r in rows}, key=qkey)

    def val(r, col):
        v = r.get(col + "_p50")
        return float(v) if v not in (None, "") else 0.0

    des, comp, supply, residual = {}, {}, {}, {}
    for t in TABS:
        k = t["key"]
        des[k] = {}
        for name, _ in DESIGNERS:
            des[k][name] = [
                round(sum(val(r, t["col"]) for r in rows
                          if r["quarter"] == q and r["designer"] == name) / t["scale"], 4)
                for q in quarters]
        if k == "cost":
            comp[k] = {c: [round(sum(val(r, c) for r in rows if r["quarter"] == q)
                                / t["scale"], 4) for q in quarters]
                       for c, _, _ in COMPONENTS}
        if t["supply"]:
            supply[k] = [round(float(sup[q][t["supply"] + "_p50"]) / t["scale"], 4)
                         for q in quarters]
            # Epoch's residual: the denominator less the four tracked designers
            residual[k] = [round(max(0.0, supply[k][i]
                                     - sum(des[k][n][i] for n, _ in DESIGNERS)), 4)
                           for i in range(len(quarters))]

    payload = {
        "quarters": quarters,
        "tabs": [{kk: t[kk] for kk in ("key", "label", "scale", "unit", "suffix",
                                       "dp", "supply", "ylabel")} for t in TABS],
        "designers": DESIGNERS,
        "components": [[c, lab, col] for c, lab, col in COMPONENTS],
        "other": list(OTHER),
        "des": des, "comp": comp, "supply": supply, "residual": residual,
    }
    sub = (f"All four tabs of Epoch's figure over {len(quarters)} complete quarters, "
           f"{quarters[0]} to {quarters[-1]}. The static chart carries two settings "
           f"side by side; this one carries the whole control surface.")
    hint = ("Switch tab, colouring and absolute/share above; hover a quarter to read "
            "every series in it.")
    html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                .replace("__TITLE__", "AI chip components — Epoch's figure, all settings")
                .replace("__PID__", "CHIP-01").replace("__SUB__", sub)
                .replace("__HINT__", hint).replace("__FILE__", SRC))
    (OUT / "CHIP-01.html").write_text(html, encoding="utf-8")
    print(f"wrote {(OUT / 'CHIP-01.html').relative_to(REPO)} "
          f"({len(TABS)} tabs x {len(quarters)} quarters)")


# --------------------------------------------------------- ranked / interval pages
RANK_JS = """
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip');
const ctl=document.getElementById('ctl'), lgw=document.getElementById('lg');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000;
let showAll=false;
function rows(){ return showAll?D.rows:D.rows.slice(0,D.top); }
function fmt(v){ return (D.unit||'')+v.toLocaleString('en-US',{minimumFractionDigits:D.dp,maximumFractionDigits:D.dp})+(D.suffix||''); }
function buildCtl(){
  ctl.innerHTML='';
  if(D.rows.length>D.top){
    [[false,'Top '+D.top],[true,'All '+D.rows.length]].forEach(([v,t])=>{
      const b=document.createElement('button'); b.className='btn'; b.type='button';
      b.textContent=t; b.setAttribute('aria-pressed',showAll===v?'true':'false');
      b.onclick=()=>{showAll=v;buildCtl();draw();reportHeight();}; ctl.appendChild(b);
    });
  }
  const s=document.createElement('span'); s.className='cap';
  s.textContent=rows().length+' of '+D.rows.length+' shown'; ctl.appendChild(s);
}
let RH,MM,SXX,RR;
function draw(){
  const R=rows(), n=R.length;
  RH=n>20?20:26; MM={l:D.labelW,r:D.interval?150:70,t:14,b:44};
  const H=MM.t+MM.b+n*RH; svg.setAttribute('viewBox','0 0 '+W+' '+H);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const hi=Math.max.apply(null,R.map(r=>D.interval?r[3]:r[1]))*1.04;
  SXX=v=>MM.l+v/hi*(W-MM.l-MM.r); RR=R;
  const step=hi/5, mag=Math.pow(10,Math.floor(Math.log10(step)));
  const st=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=step)||10*mag;
  for(let v=0;v<=hi*1.0001;v+=st){
    const x=SXX(v);
    svg.appendChild(el('line',{x1:x,x2:x,y1:MM.t,y2:H-MM.b,class:'grid'}));
    const t=el('text',{x:x,y:H-MM.b+17,class:'axis','text-anchor':'middle'});
    t.textContent=fmt(v); svg.appendChild(t);
  }
  R.forEach((r,i)=>{
    const y=MM.t+i*RH, bh=Math.max(8,RH-9);
    if(D.interval){
      svg.appendChild(el('line',{x1:SXX(r[2]),x2:SXX(r[3]),y1:y+RH/2,y2:y+RH/2,
        stroke:'#9aa9c4','stroke-width':3.4,'stroke-linecap':'round'}));
      svg.appendChild(el('circle',{cx:SXX(r[1]),cy:y+RH/2,r:4.4,fill:'#1f3864',
        stroke:'#fff','stroke-width':.8}));
      const t=el('text',{x:SXX(r[3])+8,y:y+RH/2+3.6,class:'axis','text-anchor':'start'});
      t.textContent=fmt(r[1])+'  ('+fmt(r[2])+'–'+fmt(r[3])+')'; svg.appendChild(t);
    } else {
      svg.appendChild(el('rect',{x:MM.l,y:y+(RH-bh)/2,width:Math.max(1,SXX(r[1])-MM.l),
        height:bh,fill:D.color,rx:1.5}));
      const t=el('text',{x:SXX(r[1])+6,y:y+RH/2+3.6,class:'axis','text-anchor':'start'});
      t.textContent=fmt(r[1]); svg.appendChild(t);
    }
    const lab=el('text',{x:MM.l-7,y:y+RH/2+3.6,class:'axis','text-anchor':'end',
                         style:'fill:#1a1a1a'});
    lab.textContent=r[0]; svg.appendChild(lab);
  });
  const xl=el('text',{x:(MM.l+W-MM.r)/2,y:H-MM.b+36,class:'axlab','text-anchor':'middle'});
  xl.textContent=D.xLabel; svg.appendChild(xl);
}
svg.addEventListener('pointermove',ev=>{
  const r=svg.getBoundingClientRect();
  const py=(ev.clientY-r.top)/r.width*W;
  const i=Math.floor((py-MM.t)/RH);
  if(i<0||i>=RR.length){ tip.style.opacity=0; return; }
  const x=RR[i];
  let h='<b>'+x[0]+'</b><div>'+D.valueLabel+': '+fmt(x[1])+'</div>';
  if(D.interval) h+='<div class="m">5th–95th percentile: '+fmt(x[2])+' – '+fmt(x[3])+'</div>'
                   +'<div class="m">interval is '+((x[3]-x[2])/x[1]).toFixed(1)+'x the median</div>';
  h+='<div class="m">rank '+(D.rows.indexOf(x)+1)+' of '+D.rows.length+'</div>';
  tip.innerHTML=h; tip.style.opacity=1;
  tip.style.left=Math.min(Math.max(8,(MM.l/W*r.width)+20), r.width-tip.offsetWidth-8)+'px';
  tip.style.top=Math.min(Math.max(8,(MM.t+i*RH)/W*r.width), r.height-tip.offsetHeight-8)+'px';
});
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;});
buildCtl(); draw();
function reportHeight(){
  const h=Math.ceil(document.getElementById('pg').getBoundingClientRect().height)+2;
  if(window.parent!==window) window.parent.postMessage({type:'aidr-height',id:'__PID__',h:h},'*');
}
window.addEventListener('load',reportHeight);
window.addEventListener('resize',reportHeight);
if(window.ResizeObserver) new ResizeObserver(reportHeight).observe(document.body);
reportHeight();
"""

RANK_PAGE = PAGE[:PAGE.index("<script>") + len("<script>")] + RANK_JS + "\n</script>\n"


def emit_rank(pid, title, sub, hint, payload, src):
    html = (RANK_PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                     .replace("__TITLE__", title).replace("__PID__", pid)
                     .replace("__SUB__", sub).replace("__HINT__", hint)
                     .replace("__FILE__", src))
    (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
    print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} ({len(payload['rows'])} rows)")


def extras():
    # ---- CHIP-D03: chip-level concentration, 17 types is too many to label ----
    cc = read("chip_cumulative_by_chip.csv")
    last = sorted({r["quarter"] for r in cc}, key=qkey)[-1]
    tot = {}
    for r in cc:
        if r["quarter"] != last:
            continue
        v = r.get("total_cost_usd_p50")
        if v:
            tot[r["chip_type"]] = tot.get(r["chip_type"], 0.0) + float(v) / 1e9
    rows = sorted(([k, round(v, 3)] for k, v in tot.items()), key=lambda x: -x[1])
    emit_rank("CHIP-D03", "Cumulative component cost, by chip type",
              f"All {len(rows)} chip types Epoch tracks, cumulative to {last}. The static "
              f"chart has room for the leaders; this one carries every type.",
              "Hover a bar for the exact figure and its rank.",
              {"rows": rows, "top": 10, "unit": "$", "suffix": "bn", "dp": 2,
               "color": "#1f3864", "interval": False,
               "xLabel": "Cumulative component cost (US$ billions)",
               "valueLabel": "Cumulative cost",
               "labelW": min(300, max(120, max(len(r[0]) for r in rows) * 7 + 16))},
              "cumulative_by_chip.csv")

    # ---- CHIP-D04: the published uncertainty, unreadable without hover ----
    q = read("chip_quarterly_by_designer.csv")
    lastq = sorted({r["quarter"] for r in q}, key=qkey)[-1]
    iv = []
    for r in q:
        if r["quarter"] != lastq:
            continue
        m = r.get("total_cost_usd_p50")
        if not m:
            continue
        iv.append([r["designer"],
                   round(float(m) / 1e9, 3),
                   round(float(r["total_cost_usd_p5"]) / 1e9, 3),
                   round(float(r["total_cost_usd_p95"]) / 1e9, 3)])
    iv.sort(key=lambda x: -x[1])
    emit_rank("CHIP-D04", "The interval behind every published median",
              f"Component cost in {lastq} with Epoch's published 5th-95th percentile "
              f"range. Every figure elsewhere in this domain is the dot; this is the bar "
              f"it sits on.",
              "Hover for the interval and how wide it is relative to the median.",
              {"rows": iv, "top": 10, "unit": "$", "suffix": "bn", "dp": 2,
               "color": "#1f3864", "interval": True,
               "xLabel": "Component cost (US$ billions), 5th-95th percentile",
               "valueLabel": "Median",
               "labelW": 150},
              SRC)




def more():
    """CHIP-D07 and CHIP-D01, the two derived views hover actually helps.

    D07 carries 16 chip types across four designers, which no static legend can
    label without crowding. D01 is three lines over eight quarters where the
    question is always "what was the share in that quarter", and reading it off
    a gridline is exactly what a tooltip removes.
    """
    # ---- D07: generation handover, one series per chip, grouped by designer ----
    rows = read("chip_quarterly_by_chip.csv")
    quarters = sorted({r["quarter"] for r in rows}, key=qkey)
    qi = {q: i for i, q in enumerate(quarters)}
    tracked = [d for d, _ in DESIGNERS]
    RAMPS = {"NVIDIA": ["#c3cddf", "#8fa3c4", "#4a6fa5", "#1f3864"],
             "Google": ["#cfd9e8", "#93a9cd", "#4a6fa5", "#22406f"],
             "Amazon": ["#c8dbcb", "#94b79a", "#6b8f71", "#3f6247"],
             "AMD": ["#e8d3bd", "#d6b083", "#b4763a", "#7d4f22"]}
    panels = []
    for d in tracked:
        chips = {}
        for r in rows:
            if r["designer"] != d:
                continue
            v = r.get("total_cost_usd_p50")
            if not v:
                continue
            chips.setdefault(r["chip_type"], [0.0] * len(quarters))[qi[r["quarter"]]] \
                += float(v) / 1e9
        ordered = sorted(chips.items(),
                         key=lambda kv: next((i for i, x in enumerate(kv[1]) if x > 0), 99))
        ramp = RAMPS[d]
        panels.append({"name": d, "series": [
            {"name": c, "vals": [round(x, 4) for x in vals],
             "color": ramp[min(int(j * len(ramp) / max(1, len(ordered))), len(ramp) - 1)]}
            for j, (c, vals) in enumerate(ordered)]})
    emit_panels("CHIP-D07", "Chip generations handing over, by designer",
                f"All 16 tracked chip types across {len(quarters)} quarters. Pick a "
                f"designer; hover a quarter to read every generation in it.",
                "Epoch's \"Other\" residual is excluded: it is untracked supply, not a "
                "chip generation.",
                {"quarters": quarters, "panels": panels, "unit": "$", "suffix": "bn",
                 "dp": 2, "ylabel": "Component cost (US$ bn)"},
                "quarterly_by_chip.csv")

    # ---- D01: the three components' share of world supply, quarter by quarter ----
    q = read("chip_quarterly_by_designer.csv")
    sup = {r["quarter"]: r for r in read("chip_supply.csv")}
    lines = [("Logic wafers", "logic_wafers_p50", "logic_supply_wafers_p50", "#1f3864"),
             ("CoWoS packaging", "cowos_wafers_p50", "cowos_supply_wafers_p50", "#4e8a8b"),
             ("HBM memory", "hbm_cost_usd_p50", "hbm_supply_usd_p50", "#b4763a")]
    series = []
    for lab, ai, sc, col in lines:
        vals = []
        for qq in quarters:
            num = sum(float(r[ai] or 0) for r in q
                      if r["quarter"] == qq and r["designer"] in tracked)
            vals.append(round(num / float(sup[qq][sc]) * 100, 2))
        series.append({"name": lab, "vals": vals, "color": col})
    emit_panels("CHIP-D01", "Share of world supply taken by AI, by component",
                "The three components on one axis, quarter by quarter. Hover to read "
                "all three at once.",
                "Share is of total world supply of the component, not of AI demand. "
                "Epoch's \"Other\" row is the residual of that denominator and is "
                "excluded from the numerator.",
                {"quarters": quarters, "panels": [{"name": "All components",
                                                   "series": series}],
                 "unit": "", "suffix": "%", "dp": 1, "lines": True,
                 "ylabel": "Share of world supply (%)"},
                "quarterly_by_designer.csv + supply_denominators.csv")


PANEL_JS = """
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip');
const ctl=document.getElementById('ctl'), lgw=document.getElementById('lg');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000,H=440,M={l:92,r:24,t:18,b:56};
let PI=0;
const panel=()=>D.panels[PI];
function fmt(v){ return (D.unit||'')+v.toLocaleString('en-US',{minimumFractionDigits:D.dp,maximumFractionDigits:D.dp})+(D.suffix||''); }
function buildCtl(){
  ctl.innerHTML='';
  if(D.panels.length<2) return;
  const g=document.createElement('div'); g.className='grp';
  const c=document.createElement('span'); c.className='cap'; c.textContent='Designer'; g.appendChild(c);
  D.panels.forEach((p,i)=>{
    const b=document.createElement('button'); b.className='btn'; b.type='button';
    b.textContent=p.name; b.setAttribute('aria-pressed', i===PI?'true':'false');
    b.onclick=()=>{PI=i; buildCtl(); draw(); reportHeight();}; g.appendChild(b);
  });
  ctl.appendChild(g);
}
let SX,SY,TOT;
function draw(){
  const S=panel().series, n=D.quarters.length;
  TOT=D.quarters.map((_,i)=>D.lines?0:S.reduce((a,s)=>a+(s.vals[i]||0),0));
  const hi=Math.max.apply(null, D.lines
    ? S.flatMap(s=>s.vals) : TOT)*1.20;
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  SX=i=>M.l+(W-M.l-M.r)*(i+0.5)/n;
  SY=v=>H-M.b-(v/hi)*(H-M.t-M.b);
  const step=hi/5, mag=Math.pow(10,Math.floor(Math.log10(step)));
  const st=[1,2,2.5,5,10].map(m=>m*mag).find(x=>x>=step)||10*mag;
  for(let v=0;v<=hi*1.0001;v+=st){
    const y=SY(v);
    svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:y,y2:y,class:'grid'}));
    const t=el('text',{x:M.l-8,y:y+4,class:'axis','text-anchor':'end'});
    t.textContent=fmt(v); svg.appendChild(t);
  }
  if(D.lines){
    S.forEach(s=>{
      svg.appendChild(el('polyline',{points:s.vals.map((v,i)=>SX(i)+','+SY(v)).join(' '),
        fill:'none',stroke:s.color,'stroke-width':2.4}));
      s.vals.forEach((v,i)=>svg.appendChild(el('circle',{cx:SX(i),cy:SY(v),r:3.6,
        fill:s.color,stroke:'#fff','stroke-width':.8})));
    });
  } else {
    const bw=(W-M.l-M.r)/n*0.62;
    D.quarters.forEach((_,i)=>{
      let acc=0;
      S.forEach(s=>{
        const v=s.vals[i]||0; if(v<=0) return;
        svg.appendChild(el('rect',{x:SX(i)-bw/2,y:SY(acc+v),width:bw,
          height:Math.max(0,SY(acc)-SY(acc+v)),fill:s.color,stroke:'#fff','stroke-width':.8}));
        acc+=v;
      });
      const t=el('text',{x:SX(i),y:SY(acc)-6,class:'axis','text-anchor':'middle',
                         style:'font-weight:700;fill:#1a1a1a'});
      t.textContent=fmt(acc); svg.appendChild(t);
    });
  }
  D.quarters.forEach((q,i)=>{
    const a=el('text',{x:SX(i),y:H-M.b+18,class:'axis','text-anchor':'middle'});
    a.textContent=q.split(' ')[0]; svg.appendChild(a);
    const b=el('text',{x:SX(i),y:H-M.b+31,class:'axis','text-anchor':'middle'});
    b.textContent=q.split(' ')[1]; svg.appendChild(b);
  });
  const xl=el('text',{x:(M.l+W-M.r)/2,y:H-M.b+50,class:'axlab','text-anchor':'middle'});
  xl.textContent='Quarter'; svg.appendChild(xl);
  const yl=el('text',{x:0,y:0,class:'axlab','text-anchor':'middle',
    transform:'translate(15,'+((M.t+H-M.b)/2)+') rotate(-90)'});
  yl.textContent=D.ylabel; svg.appendChild(yl);
  lgw.innerHTML='';
  S.forEach(s=>{ const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:'+s.color+'"></span>'+s.name;
    lgw.appendChild(d); });
}
svg.addEventListener('pointermove',ev=>{
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W, n=D.quarters.length;
  const i=Math.round((px-M.l)/((W-M.l-M.r)/n)-0.5);
  if(i<0||i>=n){ tip.style.opacity=0; return; }
  let h='<b>'+D.quarters[i]+'</b>';
  panel().series.forEach(s=>{
    const v=s.vals[i]||0; if(v<=0 && !D.lines) return;
    h+='<div class="row"><span class="sw" style="display:inline-block;width:9px;height:9px;'
      +'border-radius:2px;background:'+s.color+'"></span>'+s.name+'<i>'+fmt(v)+'</i></div>';
  });
  if(!D.lines) h+='<div class="row" style="border-top:1px solid #d7dbe2;margin-top:4px;'
                 +'padding-top:4px;font-weight:700">Total<i>'+fmt(TOT[i])+'</i></div>';
  tip.innerHTML=h; tip.style.opacity=1;
  tip.style.left=Math.min(Math.max(8,SX(i)/W*r.width+14), r.width-tip.offsetWidth-8)+'px';
  tip.style.top='12px';
});
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;});
buildCtl(); draw();
function reportHeight(){
  const h=Math.ceil(document.getElementById('pg').getBoundingClientRect().height)+2;
  if(window.parent!==window) window.parent.postMessage({type:'aidr-height',id:'__PID__',h:h},'*');
}
window.addEventListener('load',reportHeight);
window.addEventListener('resize',reportHeight);
if(window.ResizeObserver) new ResizeObserver(reportHeight).observe(document.body);
reportHeight();
"""

PANEL_PAGE = PAGE[:PAGE.index("<script>") + len("<script>")] + PANEL_JS + "\n</script>\n"


def emit_panels(pid, title, sub, hint, payload, src):
    html = (PANEL_PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                      .replace("__TITLE__", title).replace("__PID__", pid)
                      .replace("__SUB__", sub).replace("__HINT__", hint)
                      .replace("__FILE__", src))
    (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
    print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
          f"({len(payload['panels'])} panel(s))")


if __name__ == "__main__":
    main()
    extras()
    more()
