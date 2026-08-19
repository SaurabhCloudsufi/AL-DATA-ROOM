#!/usr/bin/env python3
"""Emit self-contained interactive companions for the AI Chip Owners charts.

The domain is sixteen quarters deep and ten owners wide, which a stacked area
can show and cannot label. These pages let a reader hover a quarter and read
every series in it, and switch the stack between owner and chip type without
leaving the page.

Four pages:

    OWNERS-01   installed base by owner, with a chip-type view on the same axes
    OWNERS-D01  the concentration ranking, with the running total on hover
    OWNERS-D02  the published 5th-95th interval, which is the thing hovering
                exists to read
    OWNERS-D04  what was added each quarter against the running total

No external scripts, fonts or styles. Runs offline and inside an iframe.

Usage:
    python build/generate_interactive_chip_owners.py
"""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "ai-chip-owners" / "data"
OUT = REPO / "ai-chip-owners" / "charts"

OWNER_COLOUR = {
    "Google": "#1f3864", "Microsoft": "#4a6fa5", "Amazon": "#6b8f71",
    "Meta": "#b4763a", "Oracle": "#7d5a7d", "CoreWeave": "#4e8a8b",
    "xAI": "#a46b6b", "China": "#8a8f5c", "China (smuggled)": "#c08a5a",
    "Other": "#c3c8d1",
}
PALETTE = ["#1f3864", "#b4763a", "#6b8f71", "#7d5a7d", "#4e8a8b",
           "#a46b6b", "#4a6fa5", "#8a8f5c", "#9aa9c4", "#5f7a99"]
RESIDUAL = "#c9ced8"
SRC1 = "cumulative_by_designer.csv"
SRC2 = "cumulative_by_chip_type.csv"
SRC3 = "quarters_by_chip_type.csv"

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
<div class="foot">__HINT__ Source: Epoch AI, AI Chip Owners (CC-BY) — __FILE__ —
epoch.ai/data/ai-chip-owners. H100e is a normalising unit, so a TPU and a Blackwell can
be added — it measures compute, not chips. Almost none of this is disclosed by the owners;
Epoch publishes a 5th–95th percentile beside every median. The final quarter of the
download is flagged incomplete at source and is excluded.</div>
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



AREA_JS = """
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip');
const ctl=document.getElementById('ctl'), lgw=document.getElementById('lg');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000,H=470,M={l:92,r:22,t:16,b:56};
let VI=0, PCT=false;
const view=()=>D.views[VI];
function fmt(v){ return v>=1e6?(v/1e6).toFixed(2)+'M':v>=1e3?(v/1e3).toFixed(0)+'k':v.toFixed(0); }

function buildCtl(){
  ctl.innerHTML='';
  const add=(cap,opts,cur,pick)=>{
    if(opts.length<2) return;
    const g=document.createElement('div'); g.className='grp';
    const c=document.createElement('span'); c.className='cap'; c.textContent=cap; g.appendChild(c);
    opts.forEach((o,i)=>{
      const b=document.createElement('button'); b.className='btn'; b.type='button';
      b.textContent=o; b.setAttribute('aria-pressed', i===cur?'true':'false');
      b.onclick=()=>{ pick(i); buildCtl(); draw(); reportHeight(); }; g.appendChild(b);
    });
    ctl.appendChild(g);
  };
  add('Break down by', D.views.map(v=>v.label), VI, i=>{VI=i;});
  add('Show as', ['Amount','Share'], PCT?1:0, i=>{PCT=i===1;});
}

let SER=[], TOT=[], SX, SY;
function draw(){
  const v=view(), n=D.quarters.length;
  let vals=v.series.map(s=>s.vals.slice());
  const raw=D.quarters.map((_,i)=>vals.reduce((a,x)=>a+(x[i]||0),0));
  if(PCT) vals=vals.map(s=>s.map((x,i)=>raw[i]?x/raw[i]*100:0));
  TOT=D.quarters.map((_,i)=>vals.reduce((a,x)=>a+(x[i]||0),0));
  SER=v.series; window._vals=vals;
  const hi=PCT?100:Math.max.apply(null,TOT)*1.05;
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  SX=i=>M.l+(W-M.l-M.r)*i/(n-1);
  SY=y=>H-M.b-(y/hi)*(H-M.t-M.b);
  const step=hi/5, mag=Math.pow(10,Math.floor(Math.log10(step)));
  const st=[1,2,2.5,5,10].map(m=>m*mag).find(x=>x>=step)||10*mag;
  for(let y=0;y<=hi*1.0001;y+=st){
    const py=SY(y);
    svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:py,y2:py,class:'grid'}));
    const t=el('text',{x:M.l-8,y:py+4,class:'axis','text-anchor':'end'});
    t.textContent=PCT?y.toFixed(0)+'%':fmt(y); svg.appendChild(t);
  }
  let bottom=new Array(n).fill(0);
  vals.forEach((s,k)=>{
    const top=bottom.map((b,i)=>b+(s[i]||0));
    const pts=D.quarters.map((_,i)=>SX(i)+','+SY(top[i])).concat(
      D.quarters.map((_,i)=>SX(n-1-i)+','+SY(bottom[n-1-i]))).join(' ');
    svg.appendChild(el('polygon',{points:pts,fill:SER[k].color,stroke:'#fff','stroke-width':.6}));
    bottom=top;
  });
  D.quarters.forEach((q,i)=>{
    if(i%2 && n>10) return;
    const a=el('text',{x:SX(i),y:H-M.b+18,class:'axis','text-anchor':'middle'});
    a.textContent=q.slice(0,4); svg.appendChild(a);
    const b=el('text',{x:SX(i),y:H-M.b+31,class:'axis','text-anchor':'middle'});
    b.textContent=q.slice(4); svg.appendChild(b);
  });
  const xl=el('text',{x:(M.l+W-M.r)/2,y:H-M.b+50,class:'axlab','text-anchor':'middle'});
  xl.textContent='Quarter'; svg.appendChild(xl);
  const yl=el('text',{x:0,y:0,class:'axlab','text-anchor':'middle',
    transform:'translate(15,'+((M.t+H-M.b)/2)+') rotate(-90)'});
  yl.textContent=PCT?'Share of installed compute (%)':D.ylabel; svg.appendChild(yl);
  svg.appendChild(el('line',{id:'rule',x1:-9,x2:-9,y1:M.t,y2:H-M.b,stroke:'#1a1a1a',
    'stroke-width':1,'stroke-dasharray':'3 3'}));
  lgw.innerHTML='';
  SER.forEach(s=>{ const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:'+s.color+'"></span>'+s.name;
    lgw.appendChild(d); });
}

svg.addEventListener('pointermove',ev=>{
  const r=svg.getBoundingClientRect();
  const px=(ev.clientX-r.left)/r.width*W, n=D.quarters.length;
  const i=Math.max(0,Math.min(n-1,Math.round((px-M.l)/((W-M.l-M.r)/(n-1)))));
  const rule=document.getElementById('rule');
  if(rule){ rule.setAttribute('x1',SX(i)); rule.setAttribute('x2',SX(i)); }
  const vals=window._vals;
  let h='<b>'+D.quarters[i]+'</b>';
  SER.map((s,k)=>[s,vals[k][i]||0]).filter(([,v])=>v>0)
     .sort((a,b)=>b[1]-a[1]).forEach(([s,v])=>{
    h+='<div class="row"><span class="sw" style="display:inline-block;width:9px;height:9px;'
      +'border-radius:2px;background:'+s.color+'"></span>'+s.name
      +'<i>'+(PCT?v.toFixed(1)+'%':fmt(v))+'</i></div>';
  });
  if(!PCT) h+='<div class="row" style="border-top:1px solid #d7dbe2;margin-top:4px;'
             +'padding-top:4px;font-weight:700">Total<i>'+fmt(TOT[i])+'</i></div>';
  tip.innerHTML=h; tip.style.opacity=1;
  tip.style.left=Math.min(Math.max(8,SX(i)/W*r.width+14), r.width-tip.offsetWidth-8)+'px';
  tip.style.top='12px';
});
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;
  const rule=document.getElementById('rule'); if(rule){rule.setAttribute('x1',-9);rule.setAttribute('x2',-9);}});

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

AREA_PAGE = PAGE[:PAGE.index("<script>") + len("<script>")] + AREA_JS + "\n</script>\n"


def read(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def qsort(qs):
    return sorted(qs, key=lambda s: (int(s[:4]), int(s[-1])))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    owners = read("owners_by_owner.csv")
    types = read("owners_by_chip_type.csv")
    meta = read("owners_summary.csv")[0]
    quarters = qsort({r["quarter"] for r in owners})
    last = quarters[-1]

    def stack(rows, key, colours, top_n=None):
        totals = {}
        for r in rows:
            if r["quarter"] == last:
                totals[r[key]] = totals.get(r[key], 0.0) + float(r["h100e"])
        names = sorted(totals, key=lambda k: -totals[k])
        pooled = []
        if top_n and len(names) > top_n:
            pooled, names = names[top_n:], names[:top_n]
        series = []
        for i, n in enumerate(names):
            by_q = {r["quarter"]: 0.0 for r in rows}
            for r in rows:
                if r[key] == n:
                    by_q[r["quarter"]] = by_q.get(r["quarter"], 0.0) + float(r["h100e"])
            series.append({"name": n, "color": colours(n, i),
                           "vals": [round(by_q.get(q, 0.0), 1) for q in quarters]})
        if pooled:
            by_q = {}
            for r in rows:
                if r[key] in pooled:
                    by_q[r["quarter"]] = by_q.get(r["quarter"], 0.0) + float(r["h100e"])
            series.append({"name": f"All other ({len(pooled)} types)", "color": RESIDUAL,
                           "vals": [round(by_q.get(q, 0.0), 1) for q in quarters]})
        # smallest at the bottom keeps the largest band reading against the axis
        return list(reversed(series))

    # one page per static chart, each naming only the file its chart reads: a
    # companion must never cite a source its own chart does not use
    def emit_area(pid, title, series, sub, src):
        payload = {"quarters": quarters,
                   "ylabel": "Installed compute (H100-equivalents)",
                   "views": [series]}
        html = (AREA_PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                         .replace("__TITLE__", title).replace("__PID__", pid)
                         .replace("__SUB__", sub)
                         .replace("__HINT__", "Switch between amount and share; hover "
                                              "any quarter to read every series in it.")
                         .replace("__FILE__", src))
        (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
        print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
              f"({len(series['series'])} series, {len(quarters)} quarters)")

    base = f"{len(quarters)} complete quarters, {quarters[0]} to {last}."
    emit_area("OWNERS-01", "Installed AI compute by owner",
              {"label": "Owner",
               "series": stack(owners, "owner",
                               lambda n, i: OWNER_COLOUR.get(n, RESIDUAL))},
              f"{base} Hover a quarter for every owner in it, or read the stack as a "
              f"share to see concentration change.", SRC1)
    emit_area("OWNERS-02", "Installed base by chip type",
              {"label": "Chip type",
               "series": stack(types, "chip_type",
                               lambda n, i: PALETTE[i % len(PALETTE)], top_n=9)},
              f"{base} All {len({r['chip_type'] for r in types})} chip types, the nine "
              f"largest named and the rest pooled. Hover a quarter to read the "
              f"generation mix in it.", SRC2)

    # ---- OWNERS-D04: additions per quarter, same machinery ----------------
    added = read("owners_added.csv")
    aq = qsort({r["quarter"] for r in added})
    payload2 = {
        "quarters": aq,
        "ylabel": "Added in the quarter (H100-equivalents)",
        "views": [{"label": "Owner",
                   "series": stack(added, "owner",
                                   lambda n, i: OWNER_COLOUR.get(n, RESIDUAL))}],
    }
    sub2 = (f"What was added in each of the {len(aq)} complete quarters, rather than "
            f"what stood installed. Hover a quarter to see which owners added it.")
    html2 = (AREA_PAGE.replace("__DATA__", json.dumps(payload2, separators=(",", ":")))
                      .replace("__TITLE__", "Compute added each quarter, by owner")
                      .replace("__PID__", "OWNERS-D04").replace("__SUB__", sub2)
                      .replace("__HINT__", "Switch between amount and share; hover any quarter.")
                      .replace("__FILE__", SRC3))
    (OUT / "OWNERS-D04.html").write_text(html2, encoding="utf-8")
    print(f"wrote {(OUT / 'OWNERS-D04.html').relative_to(REPO)} "
          f"({len(aq)} quarters of additions)")


if __name__ == "__main__":
    main()
