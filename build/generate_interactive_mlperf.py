#!/usr/bin/env python3
"""Emit self-contained interactive companions for the MLPerf Inference charts.

The static charts have to pick one cell out of the results table: MLPERF-01
shows one workload in one scenario, when the release carries 7 workloads across
3 scenarios. That is 21 rankings, of which a printed figure can show one. These
pages carry the controls instead.

Three pages:

    MLPERF-01   the ranking, with a workload and a scenario selector, and every
                submitted chip on hover
    MLPERF-02   the three scenarios side by side, with a workload selector
    MLPERF-D01  the generation succession, with a workload selector

No external scripts, fonts or styles. Runs offline and inside an iframe.

Usage:
    python build/generate_interactive_mlperf.py
"""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "mlperf-inference" / "data"
OUT = REPO / "mlperf-inference" / "charts"
SRC = "MLPerf_Inference_Hardware_Performance_Benchmarks.csv"

VENDOR_COLOUR = {"NVIDIA": "#1f3864", "AMD": "#b4763a", "": "#6b8f71"}
SCENARIO_COLOUR = {"Offline": "#1f3864", "Server": "#4e8a8b", "Interactive": "#b4763a"}
SCENARIOS = ["Offline", "Server", "Interactive"]

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
  .axis { fill:#6b7280; font-size:11px; }
  .axlab { fill:#1a1a1a; font-size:11.5px; }
  .rowlab { fill:#1a1a1a; font-size:11px; }
  .tip { position:absolute; pointer-events:none; background:#fff; border:1px solid #d7dbe2;
          border-radius:6px; padding:8px 10px; font-size:12px;
          box-shadow:0 4px 14px rgba(0,0,0,.10); opacity:0; transition:opacity .08s;
          max-width:300px; z-index:5; }
  .tip b { display:block; margin-bottom:3px; font-size:12.5px; }
  .tip .m { color:#6b7280; }
  .tip .row { display:flex; gap:8px; }
  .tip .row i { font-style:normal; margin-left:auto; font-variant-numeric:tabular-nums; }
  .foot { color:#6b7280; font-size:11px; margin-top:6px; }
  .empty { fill:#6b7280; font-size:12px; }
</style>
<div id="pg">
<div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
<div class="sub">__SUB__ <span class="badge">BENCHMARK CONDITIONS</span></div>
<div class="ctl" id="ctl"></div>
<div class="legend" id="lg"></div>
<div style="position:relative">
  <svg id="c" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">__HINT__ Source: MLCommons, MLPerf Inference v6.0 closed division —
__FILE__ — mlcommons.org/benchmarks/inference-datacenter. Throughput is per accelerator:
the published result is the whole system, and systems here run from 1 accelerator to 288.
Every figure is a vendor-tuned submission, so these are ceilings rather than expected
production throughput.</div>
</div>
<script>
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip');
const ctl=document.getElementById('ctl'), lgw=document.getElementById('lg');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000;
let WI=0, SI=0;
const wk=()=>D.workloads[WI], sc=()=>D.scenarios[SI];
function cell(w,s){ return (D.data[w]||{})[s]||[]; }
function rows(){ return D.mode==='rank' ? cell(wk(),sc()) : cell(wk(),'__all__'); }
function tok(v){ return v>=1000 ? (v/1000).toFixed(1)+'k' : v.toFixed(0); }

function buildCtl(){
  ctl.innerHTML='';
  const add=(cap,opts,cur,pick,enabled)=>{
    const g=document.createElement('div'); g.className='grp';
    const c=document.createElement('span'); c.className='cap'; c.textContent=cap;
    g.appendChild(c);
    opts.forEach((o,i)=>{
      const b=document.createElement('button'); b.className='btn'; b.type='button';
      b.textContent=o; b.setAttribute('aria-pressed', i===cur?'true':'false');
      if(enabled && !enabled(i)) b.disabled=true;
      b.onclick=()=>{ if(b.disabled) return; pick(i); buildCtl(); draw(); reportHeight(); };
      g.appendChild(b);
    });
    ctl.appendChild(g);
  };
  // a workload with no submission in the chosen scenario is disabled rather than
  // silently drawn empty
  add('Workload', D.workloads, WI, i=>{WI=i;},
      i=>D.mode!=='rank' ? (cell(D.workloads[i],'__all__').length>0)
                         : (cell(D.workloads[i],sc()).length>0));
  if(D.mode==='rank') add('Scenario', D.scenarios, SI, i=>{SI=i;},
      i=>cell(wk(),D.scenarios[i]).length>0);
  const s=document.createElement('span'); s.className='cap';
  s.textContent=rows().length+' chips submitted';
  ctl.appendChild(s);
}

function drawEmpty(msg){
  svg.setAttribute('viewBox','0 0 1000 140');
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const t=el('text',{x:500,y:70,class:'empty','text-anchor':'middle'});
  t.textContent=msg; svg.appendChild(t); lgw.innerHTML='';
}

let RR=[], MM, SXX, RH;
function draw(){
  const R=rows();
  if(!R.length){ drawEmpty('No submissions for this combination.'); return; }
  RR=R;
  if(D.mode==='rank') drawRank(R); else drawScenarios(R);
}

function drawRank(R){
  RH=26; MM={l:D.labelW,r:96,t:14,b:46};
  const H=MM.t+MM.b+R.length*RH;
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const hi=Math.max.apply(null,R.map(r=>r[1]))*1.04;
  SXX=v=>MM.l+v/hi*(W-MM.l-MM.r);
  const step=hi/5, mag=Math.pow(10,Math.floor(Math.log10(step)));
  const st=[1,2,2.5,5,10].map(m=>m*mag).find(x=>x>=step)||10*mag;
  for(let v=0;v<=hi*1.0001;v+=st){
    const x=SXX(v);
    svg.appendChild(el('line',{x1:x,x2:x,y1:MM.t,y2:H-MM.b,class:'grid'}));
    const t=el('text',{x:x,y:H-MM.b+17,class:'axis','text-anchor':'middle'});
    t.textContent=tok(v); svg.appendChild(t);
  }
  R.forEach((r,i)=>{
    const y=MM.t+i*RH, bh=RH-9;
    svg.appendChild(el('rect',{x:MM.l,y:y+(RH-bh)/2,width:Math.max(1,SXX(r[1])-MM.l),
      height:bh,fill:D.vendorColour[r[3]]||D.vendorColour[''],rx:1.5}));
    const lab=el('text',{x:MM.l-7,y:y+RH/2+3.6,class:'rowlab','text-anchor':'end'});
    lab.textContent=r[0]; svg.appendChild(lab);
    const val=el('text',{x:SXX(r[1])+6,y:y+RH/2+3.6,class:'axis','text-anchor':'start'});
    val.textContent=tok(r[1]); svg.appendChild(val);
  });
  const xl=el('text',{x:(MM.l+W-MM.r)/2,y:H-MM.b+38,class:'axlab','text-anchor':'middle'});
  xl.textContent='Tokens per second, per accelerator'; svg.appendChild(xl);
  lgw.innerHTML='';
  ['NVIDIA','AMD',''].forEach(v=>{
    const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:'+D.vendorColour[v]+'"></span>'
      +(v||'Other vendor'); lgw.appendChild(d);
  });
}

function drawScenarios(R){
  RH=54; MM={l:D.labelW,r:92,t:14,b:46};
  const H=MM.t+MM.b+R.length*RH;
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const hi=Math.max.apply(null,R.map(r=>Math.max.apply(null,r[1])))*1.04;
  SXX=v=>MM.l+v/hi*(W-MM.l-MM.r);
  const step=hi/5, mag=Math.pow(10,Math.floor(Math.log10(step)));
  const st=[1,2,2.5,5,10].map(m=>m*mag).find(x=>x>=step)||10*mag;
  for(let v=0;v<=hi*1.0001;v+=st){
    const x=SXX(v);
    svg.appendChild(el('line',{x1:x,x2:x,y1:MM.t,y2:H-MM.b,class:'grid'}));
    const t=el('text',{x:x,y:H-MM.b+17,class:'axis','text-anchor':'middle'});
    t.textContent=tok(v); svg.appendChild(t);
  }
  R.forEach((r,i)=>{
    const y0=MM.t+i*RH, bh=13;
    r[1].forEach((v,k)=>{
      if(v===null) return;
      const y=y0+6+k*(bh+2);
      svg.appendChild(el('rect',{x:MM.l,y:y,width:Math.max(1,SXX(v)-MM.l),height:bh,
        fill:D.scenarioColour[D.scenarios[k]],rx:1.5}));
      const t=el('text',{x:SXX(v)+5,y:y+bh-2.5,class:'axis','text-anchor':'start'});
      t.textContent=tok(v); svg.appendChild(t);
    });
    const lab=el('text',{x:MM.l-7,y:y0+RH/2+3.6,class:'rowlab','text-anchor':'end'});
    lab.textContent=r[0]; svg.appendChild(lab);
    if(r[1][0]!==null && r[1][2]!==null){
      const pen=(1-r[1][2]/r[1][0])*100;
      const t=el('text',{x:W-MM.r+34,y:y0+RH/2+4,class:'axis','text-anchor':'middle',
                         style:'font-weight:700;fill:#b4763a'});
      t.textContent='\\u2212'+pen.toFixed(0)+'%'; svg.appendChild(t);
    }
  });
  const xl=el('text',{x:(MM.l+W-MM.r)/2,y:H-MM.b+38,class:'axlab','text-anchor':'middle'});
  xl.textContent='Tokens per second, per accelerator'; svg.appendChild(xl);
  lgw.innerHTML='';
  D.scenarios.forEach(s=>{
    const d=document.createElement('span'); d.className='lg';
    d.innerHTML='<span class="sw" style="background:'+D.scenarioColour[s]+'"></span>'+s;
    lgw.appendChild(d);
  });
  const d=document.createElement('span'); d.className='lg';
  d.innerHTML='<span style="color:#b4763a;font-weight:700">\\u2212n%</span>&nbsp;interactive vs offline';
  lgw.appendChild(d);
}

svg.addEventListener('pointermove',ev=>{
  if(!RR.length){ tip.style.opacity=0; return; }
  const r=svg.getBoundingClientRect();
  const py=(ev.clientY-r.top)/r.width*W;
  const i=Math.floor((py-MM.t)/RH);
  if(i<0||i>=RR.length){ tip.style.opacity=0; return; }
  const x=RR[i];
  let h='<b>'+x[0]+'</b>';
  if(D.mode==='rank'){
    h+='<div class="row">Per accelerator<i>'+tok(x[1])+' tok/s</i></div>';
    h+='<div class="row m">Best system<i>'+tok(x[4])+' tok/s</i></div>';
    h+='<div class="row m">Accelerators in it<i>'+x[5]+'</i></div>';
    h+='<div class="row m">Submissions<i>'+x[2]+'</i></div>';
    h+='<div class="m">rank '+(i+1)+' of '+RR.length+' &middot; '+wk()+' &middot; '+sc()+'</div>';
  } else {
    D.scenarios.forEach((s,k)=>{
      if(x[1][k]===null) return;
      h+='<div class="row"><span class="sw" style="display:inline-block;width:9px;height:9px;'
        +'border-radius:2px;background:'+D.scenarioColour[s]+'"></span>'+s
        +'<i>'+tok(x[1][k])+' tok/s</i></div>';
    });
    if(x[1][0]!==null && x[1][2]!==null)
      h+='<div class="m">interactive costs '+((1-x[1][2]/x[1][0])*100).toFixed(0)+'% of offline</div>';
  }
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
</script>
"""


def read(name):
    with (DATA / name).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    best = read("mlperf_by_chip.csv")
    meta = read("mlperf_summary.csv")[0]

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    workloads = sorted({r["workload"] for r in best})
    # llama2-70b-99 carries the most submissions, so it opens
    workloads.sort(key=lambda w: -sum(1 for r in best if r["workload"] == w))

    # ---- MLPERF-01: the ranking, workload x scenario --------------------
    rank = {}
    for w in workloads:
        rank[w] = {}
        for s in SCENARIOS:
            rows = [r for r in best if r["workload"] == w and r["scenario"] == s]
            rows.sort(key=lambda r: -num(r["per_accelerator"]))
            rank[w][s] = [[r["chip"], round(num(r["per_accelerator"]), 1),
                           int(r["submissions"]), r["vendor"] or "",
                           round(num(r["best_system_result"]), 1),
                           int(float(r["max_accelerators"]))] for r in rows]
    widest = max((len(c[0]) for w in rank for s in rank[w] for c in rank[w][s]),
                 default=30)
    emit("MLPERF-01", "Throughput per accelerator, by chip",
         f"All {len(workloads)} workloads across {len(SCENARIOS)} scenarios — "
         f"{sum(1 for w in rank for s in rank[w] if rank[w][s])} rankings, of which the "
         f"static chart can show one.",
         "Pick a workload and a scenario; hover a bar for the system behind it.",
         {"mode": "rank", "workloads": workloads, "scenarios": SCENARIOS,
          "data": rank, "vendorColour": VENDOR_COLOUR,
          "scenarioColour": SCENARIO_COLOUR,
          "labelW": min(330, max(150, int(widest * 6.3) + 16))})

    # ---- MLPERF-02: the three scenarios together, per workload ----------
    scen = {}
    for w in workloads:
        rows = {}
        for r in best:
            if r["workload"] != w:
                continue
            rows.setdefault(r["chip"], [None, None, None])
            if r["scenario"] in SCENARIOS:
                rows[r["chip"]][SCENARIOS.index(r["scenario"])] = \
                    round(num(r["per_accelerator"]), 1)
        # a chip needs offline and interactive for the penalty to mean anything
        keep = [[c, v] for c, v in rows.items() if v[0] is not None]
        keep.sort(key=lambda x: -x[1][0])
        scen[w] = {"__all__": keep}
    emit("MLPERF-02", "Throughput across the three serving scenarios",
         "The same chips in offline, server and interactive serving, for any workload "
         "in the release. The interactive penalty is stated per chip.",
         "Pick a workload; hover a row for all three scenarios and the penalty.",
         {"mode": "scenarios", "workloads": workloads, "scenarios": SCENARIOS,
          "data": scen, "vendorColour": VENDOR_COLOUR,
          "scenarioColour": SCENARIO_COLOUR,
          "labelW": min(330, max(150, int(widest * 6.3) + 16))})
    print(f"  {int(meta['token_results_used'])} of {int(meta['submitted_results'])} "
          f"submitted results carried into the interactive pages")


def emit(pid, title, sub, hint, payload):
    html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                .replace("__TITLE__", title).replace("__PID__", pid)
                .replace("__SUB__", sub).replace("__HINT__", hint)
                .replace("__FILE__", SRC))
    (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
    n = sum(len(v) for w in payload["data"] for v in payload["data"][w].values())
    print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
          f"({len(payload['workloads'])} workloads, {n} rows)")


if __name__ == "__main__":
    main()
