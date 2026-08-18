#!/usr/bin/env python3
"""Emit self-contained interactive companions for the AI Usage charts.

The static charts have to truncate: 20 countries of 121, 15 activities of 35.
That is the right call for a printed figure and the wrong one for a reader
looking for their own country. These pages carry the whole list - hover a bar
for the exact value and its rank, and switch between the leading entries and
every one of them.

Two shapes:

    bar      the ranked views, with a Top-N / All toggle where the full list is
             too long to read at once
    scatter  AEI-D05, where the point of the chart is identifying which country
             is which, and the static version can only label twelve

No external scripts, fonts or styles: the page works offline and inside an
iframe on GitHub Pages.

Usage:
    python build/generate_interactive_aei.py
"""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "ai-usage" / "data"
OUT = REPO / "ai-usage" / "charts"
AEI_FILE = "aei_claude_ai_2026-06-26.csv"

NAVY = "#1f3864"
ORANGE = "#b4763a"

# pid -> how to build it. "extra" fields are quoted in the tooltip, giving the
# interactive version the cross-reference the static bars have no room for.
CHARTS = {
    "AEI-01": dict(kind="bar", table="aei_countries.csv", label="country",
                   col="usage_per_capita_index", dp=2, unit="",
                   default_top=25, rule=1.0,
                   title="Anthropic AI Usage Index, by country",
                   xlabel="Usage share divided by working-age population share",
                   extra=[("usage_pct", "Share of global conversations", 2, "%")]),
    "AEI-02": dict(kind="bar", table="aei_countries.csv", label="country",
                   col="usage_pct", dp=2, unit="%", default_top=25, rule=None,
                   title="Share of Claude usage, by country",
                   xlabel="Share of global Claude conversations",
                   extra=[("usage_per_capita_index", "Usage per working-age person", 2, "")]),
    "AEI-03": dict(kind="bar", table="aei_us_states.csv", label="geo_id",
                   col="usage_per_capita_index", dp=2, unit="",
                   default_top=25, rule=1.0,
                   title="Anthropic AI Usage Index, by US state",
                   xlabel="Usage share divided by working-age population share",
                   extra=[]),
    "AEI-07": dict(kind="bar", table="aei_request_major.csv", label="node_name",
                   col="pct", dp=1, unit="%", default_top=0, rule=None,
                   title="What people ask Claude for, by topic",
                   xlabel="Share of Claude conversations",
                   extra=[("collaboration_bucket_automation_pct", "Automation share", 1, "%")]),
    "AEI-08": dict(kind="bar", table="aei_soc_major.csv", label="node_name",
                   col="pct", dp=1, unit="%", default_top=0, rule=None,
                   title="Claude usage mapped to occupation groups",
                   xlabel="Share of Claude conversations",
                   extra=[("collaboration_bucket_automation_pct", "Automation share", 1, "%"),
                          ("time_ratio", "Estimated time saved", 1, "x")]),
    "AEI-09": dict(kind="bar", table="aei_onet_gwa.csv", label="node_name",
                   col="pct", dp=1, unit="%", default_top=20, rule=None,
                   title="Claude usage mapped to work activities",
                   xlabel="Share of Claude conversations",
                   extra=[("collaboration_bucket_automation_pct", "Automation share", 1, "%")]),
    "AEI-10": dict(kind="bar", table="aei_artifacts.csv", label="artifact",
                   col="value", dp=2, unit="%", default_top=20, rule=None,
                   title="What Claude actually produced",
                   xlabel="Share of Claude conversations", extra=[]),
    "AEI-D05": dict(kind="scatter", table="aei_countries.csv", label="country",
                    x="usage_pct", y="usage_per_capita_index",
                    title="Usage volume against usage intensity",
                    xlabel="Share of global Claude conversations",
                    ylabel="Usage per working-age person (1.0 = proportional)"),
}

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
  .ctl { display:flex; gap:8px; margin:8px 0 4px; align-items:center; flex-wrap:wrap; }
  .btn { font-size:12px; border:1px solid #d7dbe2; background:#fff; color:#1a1a1a;
          padding:3px 11px; border-radius:999px; cursor:pointer; }
  .btn[aria-pressed="true"] { background:#1f3864; color:#fff; border-color:#1f3864; }
  .btn:focus-visible { outline:2px solid #1f3864; outline-offset:2px; }
  .cnt { color:#6b7280; font-size:11.5px; }
  svg { width:100%; height:auto; display:block; touch-action:none; }
  .grid { stroke:#d7dbe2; stroke-width:1; }
  .axis { fill:#6b7280; font-size:11px; }
  .axlab { fill:#1a1a1a; font-size:11.5px; }
  .rowlab { fill:#1a1a1a; font-size:11px; }
  .tip { position:absolute; pointer-events:none; background:#fff; border:1px solid #d7dbe2;
          border-radius:6px; padding:8px 10px; font-size:12px; box-shadow:0 4px 14px rgba(0,0,0,.10);
          opacity:0; transition:opacity .08s; max-width:300px; z-index:5; }
  .tip b { display:block; margin-bottom:3px; font-size:12.5px; }
  .tip .m { color:#6b7280; }
  .foot { color:#6b7280; font-size:11px; margin-top:6px; }
</style>
<div id="pg">
<div class="hd"><span class="pid">__PID__</span><h1>__TITLE__</h1></div>
<div class="sub">__SUB__ <span class="badge">ONE PROVIDER'S OWN TRAFFIC</span></div>
<div class="ctl" id="ctl"></div>
<div style="position:relative">
  <svg id="c" role="img" aria-label="__TITLE__"></svg>
  <div class="tip" id="tip"></div>
</div>
<div class="foot">__HINT__ Source: Anthropic Economic Index (CC-BY) — __FILE__ —
huggingface.co/datasets/Anthropic/EconomicIndex. Claude.ai consumer traffic only, so every
share is a share of Claude conversations and not of AI use at large. A cell Anthropic did
not publish is absent, not zero.</div>
</div>
<script>
const D = __DATA__;
const svg=document.getElementById('c'), tip=document.getElementById('tip'), ctl=document.getElementById('ctl');
const NS='http://www.w3.org/2000/svg';
const el=(n,a)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const W=1000;
let showAll = !D.defaultTop;

function fmt(v,dp,unit){ return v.toLocaleString('en-US',{minimumFractionDigits:dp,maximumFractionDigits:dp})+unit; }
function niceTicks(hi,n){
  const raw=hi/n, mag=Math.pow(10,Math.floor(Math.log10(raw)));
  const step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=raw)||10*mag;
  const out=[]; for(let v=0; v<=hi*1.0001; v+=step) out.push(+v.toFixed(6));
  return out;
}

function rows(){ return showAll ? D.rows : D.rows.slice(0, D.defaultTop); }

function drawBar(){
  const R=rows(), n=R.length;
  const rowH = n>60 ? 15 : n>34 ? 19 : 24;
  const M={l:D.labelW,r:64,t:14,b:46};
  const H=M.t+M.b+n*rowH;
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const hi=Math.max.apply(null,R.map(r=>r[1]))*1.04;
  const sx=v=>M.l+v/hi*(W-M.l-M.r);

  niceTicks(hi,6).forEach(v=>{
    const x=sx(v);
    svg.appendChild(el('line',{x1:x,x2:x,y1:M.t,y2:H-M.b,class:'grid'}));
    const t=el('text',{x:x,y:H-M.b+17,class:'axis','text-anchor':'middle'});
    t.textContent=fmt(v,v<10?(D.dp>1?1:0):0,D.unit); svg.appendChild(t);
  });
  R.forEach((r,i)=>{
    const y=M.t+i*rowH, bh=Math.max(7,rowH-7);
    svg.appendChild(el('rect',{x:M.l,y:y+(rowH-bh)/2,width:Math.max(1,sx(r[1])-M.l),
      height:bh,fill:D.color,rx:1.5,'data-i':i}));
    const lab=el('text',{x:M.l-7,y:y+rowH/2+3.6,class:'rowlab','text-anchor':'end'});
    lab.textContent=r[0]; svg.appendChild(lab);
    const val=el('text',{x:sx(r[1])+6,y:y+rowH/2+3.6,class:'axis','text-anchor':'start'});
    val.textContent=fmt(r[1],D.dp,D.unit); svg.appendChild(val);
  });
  if(D.rule!==null && D.rule<=hi){
    const x=sx(D.rule);
    svg.appendChild(el('line',{x1:x,x2:x,y1:M.t,y2:H-M.b,stroke:'#b4763a',
      'stroke-width':1.5,'stroke-dasharray':'5 3'}));
  }
  const xl=el('text',{x:(M.l+W-M.r)/2,y:H-M.b+38,class:'axlab','text-anchor':'middle'});
  xl.textContent=D.xLabel; svg.appendChild(xl);
  svg.appendChild(el('rect',{id:'hl',x:-99,y:-99,width:0,height:0,fill:'none',
    stroke:'#1a1a1a','stroke-width':1.4}));
  svg._rowH=rowH; svg._M=M; svg._H=H; svg._sx=sx; svg._R=R;
}

function drawScatter(){
  const H=560, M={l:78,r:22,t:16,b:52};
  svg.setAttribute('viewBox','0 0 '+W+' '+H);
  while(svg.firstChild) svg.removeChild(svg.firstChild);
  const xs=D.rows.map(r=>r[1]), ys=D.rows.map(r=>r[2]);
  const lx=v=>Math.log10(v);
  const xLo=lx(Math.min.apply(null,xs))-0.08, xHi=lx(Math.max.apply(null,xs))+0.08;
  const yLo=lx(Math.min.apply(null,ys))-0.08, yHi=lx(Math.max.apply(null,ys))+0.08;
  const sx=v=>M.l+(lx(v)-xLo)/(xHi-xLo)*(W-M.l-M.r);
  const sy=v=>H-M.b-(lx(v)-yLo)/(yHi-yLo)*(H-M.t-M.b);
  const decades=(lo,hi)=>{const o=[];for(let e=Math.floor(lo);e<=Math.ceil(hi);e++)
    for(const m of [1,2,5]){const v=m*Math.pow(10,e); if(lx(v)>=lo&&lx(v)<=hi) o.push(v);} return o;};
  decades(yLo,yHi).forEach(v=>{const y=sy(v);
    svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:y,y2:y,class:'grid'}));
    const t=el('text',{x:M.l-8,y:y+4,class:'axis','text-anchor':'end'});
    t.textContent=(+v.toPrecision(2)); svg.appendChild(t);});
  decades(xLo,xHi).forEach(v=>{const x=sx(v);
    svg.appendChild(el('line',{x1:x,x2:x,y1:M.t,y2:H-M.b,class:'grid'}));
    const t=el('text',{x:x,y:H-M.b+18,class:'axis','text-anchor':'middle'});
    t.textContent=(+v.toPrecision(2))+'%'; svg.appendChild(t);});
  const y1=sy(1.0);
  svg.appendChild(el('line',{x1:M.l,x2:W-M.r,y1:y1,y2:y1,stroke:'#b4763a',
    'stroke-width':1.5,'stroke-dasharray':'5 3'}));
  const pl=el('text',{x:M.l+6,y:y1-6,class:'axis',fill:'#b4763a'});
  pl.textContent='proportional to population'; svg.appendChild(pl);
  D.rows.forEach(r=>{
    svg.appendChild(el('circle',{cx:sx(r[1]).toFixed(2),cy:sy(r[2]).toFixed(2),r:4.2,
      fill:D.color,'fill-opacity':.62,stroke:'#fff','stroke-width':.7}));
  });
  const xl=el('text',{x:(M.l+W-M.r)/2,y:H-M.b+40,class:'axlab','text-anchor':'middle'});
  xl.textContent=D.xLabel; svg.appendChild(xl);
  const yl=el('text',{x:0,y:0,class:'axlab','text-anchor':'middle',
    transform:'translate(15,'+((M.t+H-M.b)/2)+') rotate(-90)'});
  yl.textContent=D.yLabel; svg.appendChild(yl);
  svg.appendChild(el('circle',{id:'hl',r:7.5,fill:'none',stroke:'#1a1a1a','stroke-width':1.6,cx:-99,cy:-99}));
  svg._sx=sx; svg._sy=sy; svg._H=H;
}

const draw = D.kind==='bar' ? drawBar : drawScatter;

function buildCtl(){
  ctl.innerHTML='';
  if(D.kind==='bar' && D.defaultTop && D.rows.length>D.defaultTop){
    [[false,'Top '+D.defaultTop],[true,'All '+D.rows.length]].forEach(([val,txt])=>{
      const b=document.createElement('button');
      b.className='btn'; b.type='button'; b.textContent=txt;
      b.setAttribute('aria-pressed', showAll===val ? 'true':'false');
      b.onclick=()=>{ showAll=val; buildCtl(); draw(); reportHeight(); };
      ctl.appendChild(b);
    });
  }
  const s=document.createElement('span');
  s.className='cnt';
  s.textContent = D.kind==='bar'
    ? rows().length+' of '+D.rows.length+' shown'
    : D.rows.length+' countries';
  ctl.appendChild(s);
}

function tipFor(r){
  let h='<b>'+r[0]+'</b>';
  if(D.kind==='bar'){
    h+='<div>'+D.valueLabel+': '+fmt(r[1],D.dp,D.unit)+'</div>';
    h+='<div class="m">rank '+(D.rows.indexOf(r)+1)+' of '+D.rows.length+'</div>';
    (D.extra||[]).forEach((e,k)=>{ const v=r[2+k];
      if(v!==null&&v!==undefined) h+='<div class="m">'+e[0]+': '+fmt(v,e[1],e[2])+'</div>'; });
  } else {
    h+='<div>'+D.xLabel+': '+fmt(r[1],2,'%')+'</div>';
    h+='<div>Usage per working-age person: '+fmt(r[2],2,'')+'</div>';
  }
  return h;
}

function place(px,py,rect){
  tip.style.left=Math.min(Math.max(8,px+14), rect.width-tip.offsetWidth-8)+'px';
  tip.style.top=Math.min(Math.max(8,py-10), rect.height-tip.offsetHeight-8)+'px';
}

svg.addEventListener('pointermove',ev=>{
  const rect=svg.getBoundingClientRect();
  const px=(ev.clientX-rect.left)/rect.width*W, py=(ev.clientY-rect.top)/rect.width*W;
  const hl=document.getElementById('hl');
  if(D.kind==='bar'){
    const {_rowH:rowH,_M:M,_R:R,_sx:sx}=svg;
    const i=Math.floor((py-M.t)/rowH);
    if(i<0||i>=R.length||px<M.l-4){ tip.style.opacity=0; hl.setAttribute('x',-99); return; }
    const r=R[i], bh=Math.max(7,rowH-7);
    hl.setAttribute('x',M.l); hl.setAttribute('y',M.t+i*rowH+(rowH-bh)/2);
    hl.setAttribute('width',Math.max(1,sx(r[1])-M.l)); hl.setAttribute('height',bh);
    tip.innerHTML=tipFor(r); tip.style.opacity=1;
    place(sx(r[1])/W*rect.width,(M.t+i*rowH+rowH/2)/W*rect.width,rect);
  } else {
    const {_sx:sx,_sy:sy}=svg; let best=null,bd=18*18;
    D.rows.forEach(r=>{const dx=sx(r[1])-px,dy=sy(r[2])-py,d=dx*dx+dy*dy;
      if(d<bd){bd=d;best=r;}});
    if(!best){ tip.style.opacity=0; hl.setAttribute('cx',-99); return; }
    hl.setAttribute('cx',sx(best[1])); hl.setAttribute('cy',sy(best[2]));
    tip.innerHTML=tipFor(best); tip.style.opacity=1;
    place(sx(best[1])/W*rect.width,sy(best[2])/W*rect.width,rect);
  }
});
svg.addEventListener('pointerleave',()=>{tip.style.opacity=0;
  const hl=document.getElementById('hl'); if(hl){hl.setAttribute('x',-99);hl.setAttribute('cx',-99);}});

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


def num(v):
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = read("aei_summary.csv")[0]
    month = meta["period_last"][:7]

    for pid, cfg in CHARTS.items():
        src = read(cfg["table"])
        if cfg["kind"] == "bar":
            rows = [r for r in src if num(r.get(cfg["col"])) is not None]
            rows.sort(key=lambda r: -num(r[cfg["col"]]))
            data = [[r[cfg["label"]], num(r[cfg["col"]])]
                    + [num(r.get(e[0])) for e in cfg["extra"]] for r in rows]
            longest = max(len(str(r[0])) for r in data)
            payload = {
                "kind": "bar", "rows": data, "dp": cfg["dp"], "unit": cfg["unit"],
                "color": NAVY, "rule": cfg["rule"], "xLabel": cfg["xlabel"],
                "valueLabel": cfg["xlabel"].split(" (")[0],
                "defaultTop": cfg["default_top"],
                "extra": [[e[1], e[2], e[3]] for e in cfg["extra"]],
                # room for the longest row label, capped so the bars keep the page
                "labelW": min(310, max(96, int(longest * 6.4) + 16)),
            }
            hint = ("Hover a bar for the exact value and its rank"
                    + (
                        f"; switch between the leading {cfg['default_top']} and all "
                        f"{len(data)}." if cfg["default_top"] and
                        len(data) > cfg["default_top"] else "."))
            # the live counter in the control bar reports what is on screen, so
            # the subtitle states what is available rather than what is shown
            sub = (f"{len(data)} in the release, {month} data. The static chart has "
                   f"room for a ranked selection; this one carries the whole list.")
        else:
            rows = [r for r in src
                    if num(r.get(cfg["x"])) and num(r.get(cfg["y"]))]
            data = [[r[cfg["label"]], num(r[cfg["x"]]), num(r[cfg["y"]])] for r in rows]
            payload = {"kind": "scatter", "rows": data, "color": NAVY,
                       "xLabel": cfg["xlabel"], "yLabel": cfg["ylabel"],
                       "dp": 2, "unit": "%", "defaultTop": 0, "extra": []}
            hint = "Hover a point to identify the country and read both measures."
            sub = (f"All {len(data)} countries, {month} data. The static chart can "
                   f"label twelve; here every point identifies itself.")

        html = (PAGE.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                    .replace("__TITLE__", cfg["title"]).replace("__PID__", pid)
                    .replace("__SUB__", sub).replace("__HINT__", hint)
                    .replace("__FILE__", AEI_FILE))
        (OUT / f"{pid}.html").write_text(html, encoding="utf-8")
        print(f"wrote {(OUT / f'{pid}.html').relative_to(REPO)} "
              f"({cfg['kind']}, {len(payload['rows'])} rows)")


if __name__ == "__main__":
    main()
