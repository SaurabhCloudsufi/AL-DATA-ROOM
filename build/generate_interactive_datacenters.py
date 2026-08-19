#!/usr/bin/env python3
"""Emit the interactive companion for DERIVED-05, the cooling equipment catalogue.

DERIVED-05 is the measurement backbone of the AI Data Centers domain: it is the
relationship that turns a rooftop counted in satellite imagery into a power
figure, and from there into a compute estimate. The static chart can show the
670 catalogue units and their three equipment classes, but not which company
made any given unit — 31 manufacturers is far past what a scatter can label.

This page adds that: hover a point for the manufacturer, the model's rated
capacity and footprint and the intensity that follows from them, or colour the
whole catalogue by manufacturer instead of by equipment class.

It also draws the median intensity per class rather than one line across all
three, because the classes differ roughly four-fold and the single-ratio version
is where most of the uncertainty in the published IT power figures comes from.

Usage:
    python build/generate_interactive_datacenters.py
"""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "ai-infrastructure" / "data"
OUT = REPO / "ai-infrastructure" / "charts"
SRC = "data_center_cooling_towers.csv + data_center_chillers.csv"

CLASS_COLOUR = {"Cooling tower (wet)": "#1f3864",
                "Chiller (air-cooled)": "#b4763a",
                "Chiller (water-cooled)": "#6b8f71"}
PALETTE = ["#1f3864", "#b4763a", "#6b8f71", "#7d5a7d", "#4e8a8b",
           "#a46b6b", "#4a6fa5", "#8a8f5c"]
RESIDUAL = "#c9ced8"

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
<div class="sub">__SUB__ <span class="badge">CATALOGUE SPECIFICATIONS</span></div>
<div class="ctl" id="ctl"></div>
<div class="legend" id="lg"></div>
<div style="position:relative">
  <svg id="c" viewBox="0 0 1000 470" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">__HINT__ Source: Epoch AI, AI Data Centers (CC-BY) — __FILE__ —
epoch.ai/data/ai-data-centers. These are manufacturer catalogue specifications, not
measurements of installed units: rated capacity is an upper bound that real duty rarely
reaches. This relationship is what converts a rooftop counted in imagery into a power
figure, so it is where most of the uncertainty in the published IT power estimates begins.</div>
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



SCATTER_JS = """
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip');
const ctl=document.getElementById('ctl'), lgw=document.getElementById('lg');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000,H=520,M={l:86,r:24,t:16,b:54};
let GI=0, LINES=true;
const hidden=new Set();
const dim=()=>D.dims[GI];
const grp=p=>p[2+GI];
const lg10=Math.log10;
function fmt(v){ return v>=1000?(v/1000).toFixed(1)+'k':v>=10?v.toFixed(0):v.toFixed(1); }

function buildCtl(){
  ctl.innerHTML='';
  const add=(cap,opts,cur,pick)=>{
    const g=document.createElement('div'); g.className='grp';
    const c=document.createElement('span'); c.className='cap'; c.textContent=cap; g.appendChild(c);
    opts.forEach((o,i)=>{
      const b=document.createElement('button'); b.className='btn'; b.type='button';
      b.textContent=o; b.setAttribute('aria-pressed', i===cur?'true':'false');
      b.onclick=()=>{ pick(i); hidden.clear(); buildCtl(); drawLegend(); draw(); reportHeight(); };
      g.appendChild(b);
    });
    ctl.appendChild(g);
  };
  add('Colour by', D.dims.map(d=>d.label), GI, i=>{GI=i;});
  add('Median intensity', ['Hide','Show'], LINES?1:0, i=>{LINES=i===1;});
  const s=document.createElement('span'); s.className='cap';
  s.textContent=D.pts.filter(p=>!hidden.has(grp(p))).length+' of '+D.pts.length+' units';
  ctl.appendChild(s);
}

function drawLegend(){
  lgw.innerHTML='';
  dim().groups.forEach((g,i)=>{
    const b=document.createElement('button');
    b.className='lg'; b.type='button';
    b.setAttribute('aria-pressed', hidden.has(i)?'true':'false');
    b.innerHTML='<span class="sw" style="background:'+g.color+'"></span>'+g.name+' ('+g.n+')';
    b.onclick=()=>{
      if(hidden.has(i)) hidden.delete(i);
      else if(hidden.size < dim().groups.length-1) hidden.add(i);
      else return;
      b.setAttribute('aria-pressed', hidden.has(i)?'true':'false');
      buildCtl(); draw();
    };
    lgw.appendChild(b);
  });
}

let SX,SY,SHOWN=[];
function draw(){
  SHOWN=D.pts.map((p,i)=>i).filter(i=>!hidden.has(grp(D.pts[i])));
  if(!SHOWN.length) return;
  const xs=SHOWN.map(i=>D.pts[i][0]), ys=SHOWN.map(i=>D.pts[i][1]);
  const xLo=lg10(Math.min.apply(null,xs))-0.08, xHi=lg10(Math.max.apply(null,xs))+0.08;
  const yLo=lg10(Math.min.apply(null,ys))-0.08, yHi=lg10(Math.max.apply(null,ys))+0.08;
  SX=v=>M.l+(lg10(v)-xLo)/(xHi-xLo)*(W-M.l-M.r);
  SY=v=>H-M.b-(lg10(v)-yLo)/(yHi-yLo)*(H-M.t-M.b);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  const dec=(lo,hi)=>{const o=[];for(let e=Math.floor(lo);e<=Math.ceil(hi);e++)
    for(const m of [1,2,5]){const v=m*Math.pow(10,e); if(lg10(v)>=lo&&lg10(v)<=hi) o.push(v);} return o;};
  dec(yLo,yHi).forEach(v=>{const y=SY(v);
    svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:y,y2:y,class:'grid'}));
    const t=el('text',{x:M.l-8,y:y+4,class:'axis','text-anchor':'end'});
    t.textContent=fmt(v); svg.appendChild(t);});
  dec(xLo,xHi).forEach(v=>{const x=SX(v);
    svg.appendChild(el('line',{x1:x,x2:x,y1:M.t,y2:H-M.b,class:'grid'}));
    const t=el('text',{x:x,y:H-M.b+18,class:'axis','text-anchor':'middle'});
    t.textContent=fmt(v); svg.appendChild(t);});
  // one median-intensity line per equipment class: the classes differ about
  // four-fold, and a single ratio across all of them is the main error source
  if(LINES){
    D.intensity.forEach(k=>{
      const x0=Math.pow(10,xLo), x1=Math.pow(10,xHi);
      svg.appendChild(el('line',{x1:SX(x0),y1:SY(x0*k.kwm2),x2:SX(x1),y2:SY(x1*k.kwm2),
        stroke:k.color,'stroke-width':1.6,'stroke-dasharray':'6 3','stroke-opacity':.9}));
      const t=el('text',{x:W-M.r-4,y:SY(Math.pow(10,xHi)*k.kwm2)-5,class:'axis',
                         'text-anchor':'end',style:'fill:'+k.color});
      t.textContent=k.name+'  '+k.kwm2.toFixed(0)+' kW/m\\u00B2'; svg.appendChild(t);
    });
  }
  SHOWN.forEach(i=>{
    const p=D.pts[i];
    svg.appendChild(el('circle',{cx:SX(p[0]).toFixed(2),cy:SY(p[1]).toFixed(2),r:3.8,
      fill:dim().groups[grp(p)].color,'fill-opacity':.72,stroke:'#fff','stroke-width':.6}));
  });
  const xl=el('text',{x:(M.l+W-M.r)/2,y:H-M.b+42,class:'axlab','text-anchor':'middle'});
  xl.textContent='Footprint of the unit (m\\u00B2, log scale)'; svg.appendChild(xl);
  const yl=el('text',{x:0,y:0,class:'axlab','text-anchor':'middle',
    transform:'translate(15,'+((M.t+H-M.b)/2)+') rotate(-90)'});
  yl.textContent='Rated cooling capacity (kW, log scale)'; svg.appendChild(yl);
  svg.appendChild(el('circle',{id:'hl',r:7,fill:'none',stroke:'#1a1a1a','stroke-width':1.6,cx:-99,cy:-99}));
}

svg.addEventListener('pointermove',ev=>{
  if(!SX) return;
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W, py=(ev.clientY-r.top)/r.width*W;
  let best=-1,bd=15*15;
  SHOWN.forEach(i=>{const p=D.pts[i];
    const dx=SX(p[0])-px, dy=SY(p[1])-py, d=dx*dx+dy*dy; if(d<bd){bd=d;best=i;}});
  const hl=document.getElementById('hl');
  if(best<0){ tip.style.opacity=0; if(hl) hl.setAttribute('cx',-99); return; }
  const p=D.pts[best];
  hl.setAttribute('cx',SX(p[0])); hl.setAttribute('cy',SY(p[1]));
  tip.innerHTML='<b>'+p[4]+'</b><div class="m">'+p[5]+'</div>'
    +'<div class="row">Rated capacity<i>'+fmt(p[1])+' kW</i></div>'
    +'<div class="row">Footprint<i>'+fmt(p[0])+' m\\u00B2</i></div>'
    +'<div class="row">Intensity<i>'+(p[1]/p[0]).toFixed(0)+' kW/m\\u00B2</i></div>';
  tip.style.opacity=1;
  tip.style.left=Math.min(Math.max(8,SX(p[0])/W*r.width+14), r.width-tip.offsetWidth-8)+'px';
  tip.style.top=Math.min(Math.max(8,SY(p[1])/W*r.width-10), r.height-tip.offsetHeight-8)+'px';
});
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
"""

SCATTER_PAGE = PAGE[:PAGE.index("<script>") + len("<script>")] + SCATTER_JS + "\n</script>\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with (DATA / "dc_cooling_equipment.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)
                if r["area_m2"] and r["capacity_kw"]
                and float(r["area_m2"]) > 0 and float(r["capacity_kw"]) > 0]

    classes = sorted({r["equipment"] for r in rows})
    counts = {}
    for r in rows:
        counts[r["manufacturer"]] = counts.get(r["manufacturer"], 0) + 1
    ranked = sorted(counts, key=lambda k: -counts[k])
    top = ranked[:8]

    dims = [
        {"label": "Equipment class", "key": "equipment",
         "groups": [{"name": c, "color": CLASS_COLOUR.get(c, RESIDUAL),
                     "n": sum(1 for r in rows if r["equipment"] == c)} for c in classes],
         "index": {c: i for i, c in enumerate(classes)}},
        {"label": "Manufacturer", "key": "manufacturer",
         "groups": [{"name": m, "color": PALETTE[i % len(PALETTE)], "n": counts[m]}
                    for i, m in enumerate(top)]
                   + [{"name": f"All other ({len(ranked) - len(top)} makers)",
                       "color": RESIDUAL,
                       "n": sum(counts[m] for m in ranked[len(top):])}],
         "index": {m: i for i, m in enumerate(top)}},
    ]

    pts = []
    for r in rows:
        pts.append([round(float(r["area_m2"]), 4), round(float(r["capacity_kw"]), 3),
                    dims[0]["index"][r["equipment"]],
                    dims[1]["index"].get(r["manufacturer"], len(top)),
                    r["manufacturer"], r["equipment"]])

    def median(vs):
        vs = sorted(vs)
        n = len(vs)
        return vs[n // 2] if n % 2 else (vs[n // 2 - 1] + vs[n // 2]) / 2

    intensity = [{"name": c, "color": CLASS_COLOUR.get(c, RESIDUAL),
                  "kwm2": round(median([float(r["capacity_kw"]) / float(r["area_m2"])
                                        for r in rows if r["equipment"] == c]), 2)}
                 for c in classes]

    payload = {"pts": pts, "dims": dims, "intensity": intensity}
    lo = min(k["kwm2"] for k in intensity)
    hi = max(k["kwm2"] for k in intensity)
    sub = (f"All {len(pts)} units in Epoch's two equipment catalogues, from "
           f"{len(ranked)} manufacturers. Colour by equipment class or by maker; "
           f"hover any unit for the company that builds it. Median intensity runs "
           f"{lo:.0f} to {hi:.0f} kW/m² across the three classes — a {hi/lo:.0f}-fold "
           f"spread, which one line across all of them hides.")
    hint = ("Hover a unit for its manufacturer, rating, footprint and intensity; "
            "switch the colouring, or click a legend entry to drop a group.")
    html = (SCATTER_PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                        .replace("__TITLE__", "Cooling capacity against footprint, by maker")
                        .replace("__PID__", "DERIVED-05").replace("__SUB__", sub)
                        .replace("__HINT__", hint).replace("__FILE__", SRC))
    (OUT / "DERIVED-05.html").write_text(html, encoding="utf-8")
    print(f"wrote {(OUT / 'DERIVED-05.html').relative_to(REPO)} "
          f"({len(pts)} units, {len(ranked)} manufacturers, "
          f"intensity {lo:.0f}-{hi:.0f} kW/m2)")


if __name__ == "__main__":
    main()
