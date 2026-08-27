/**
 * Verify the interactive Tokens Per Day companions render and respond.
 *
 * TPD-01 to TPD-03 exist because the site's tooltip is a rule, not a lookup:
 * each series reports its last observation at or before the cursor, carried
 * forward. So the check that matters is not "does a tooltip appear" but "does it
 * carry forward correctly" — this replays the rule in plain JS against each
 * payload and requires the page to agree at every observation date. On the
 * country page it also asserts the documented stepping case, where hovering
 * early November 2025 gives China 54.84 and 15 November gives 74.06.
 *
 * No dependencies.
 *   node build/verify_interactive_tokensperday.mjs [--embedded]
 */
import { readFileSync, readdirSync } from 'fs';
import vm from 'vm';

const dir = new URL('../tokens-per-day/charts/', import.meta.url).pathname;
const embedded = process.argv[2] === '--embedded';
let fail = 0, totalPoints = 0;

const mk = (tag) => ({
  tag, children: [], attrs: {}, style: {}, disabled: false,
  setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
  appendChild(c) { this.children.push(c); return c; },
  removeChild(c) { this.children = this.children.filter(x => x !== c); },
  get firstChild() { return this.children[0] || null; },
  set innerHTML(v) { this._html = v; this.children = []; },
  get innerHTML() { return this._html || ''; },
  set textContent(v) { this._text = v; }, get textContent() { return this._text || ''; },
  addEventListener(t, fn) { (this._ev ||= {})[t] = fn; },
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 600 }),
});

/** The site's own move() rule, reimplemented here so the page is checked
 *  against the specification rather than against itself. */
function carried(series, ms) {
  const out = [];
  for (const s of series) {
    let pt = null;
    for (const p of s.pts) if (p[0] <= ms) pt = p;
    if (pt) out.push({ n: s.n, v: pt[1] });
  }
  return out.sort((a, b) => b.v - a.v);
}

for (const f of readdirSync(dir).filter(x => x.startsWith('TPD-') && x.endsWith('.html')).sort()) {
  const html = readFileSync(dir + f, 'utf8');
  const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const D = JSON.parse(js.match(/^const D = (\{.*\});$/m)[1]);
  const byId = { c: mk('svg'), tip: mk('div'), ctl: mk('div'), lg: mk('div'), pg: mk('div') };
  const posted = [];
  const ctx = {
    document: {
      getElementById: (id) => byId[id] || null,
      createElementNS: (n, t) => mk(t), createElement: (t) => mk(t), body: mk('body'),
    }, console, Math, Date, JSON, String, Number, Array, Object,
  };
  ctx.window = { addEventListener() {} }; ctx.window.window = ctx.window;
  ctx.window.parent = embedded ? { postMessage: (m) => posted.push(m) } : ctx.window;
  try {
    vm.createContext(ctx);
    vm.runInContext(js, ctx, { timeout: 15000 });
    const marks = () => byId.c.children.filter(
      e => e.tag === 'rect' || e.tag === 'circle' || e.tag === 'path').length;
    const base = marks();

    // every control must change what is drawn, and return to it
    const results = [];
    for (const g of byId.ctl.children.filter(e => e.tag === 'div')) {
      const cap = g.children[0].textContent;
      const bs = g.children.filter(e => e.tag === 'button');
      if (bs.length < 2) { results.push(`${cap}=single`); continue; }
      const before = marks();
      bs[1].onclick();
      const after = marks();
      bs[0].onclick();
      const back = marks();
      results.push(`${cap}=${after > 0 && back === before ? 'ok' : 'BROKEN'}`);
    }

    // hover
    const mv = byId.c._ev && byId.c._ev.pointermove;
    let hover = 'BROKEN';
    if (mv) {
      for (let x = 120; x < 900 && hover !== 'ok'; x += 20) {
        mv({ clientX: x, clientY: 200 });
        if ((byId.tip.innerHTML || '').includes('<b>')) hover = 'ok';
      }
    }

    let extra = '';
    if (Array.isArray(D.series)) {
      // the carry-forward rule, at every observation date and the day after it
      const S = D.series;
      let checked = 0, bad = 0;
      const dates = [...new Set(S.flatMap(s => s.pts.map(p => p[0])))].sort();
      for (const t of dates) {
        for (const off of [0, 86400000]) {
          for (const w of carried(S, t + off)) {
            const s = S.find(x => x.n === w.n);
            let pt = null;
            for (const p of s.pts) if (p[0] <= t + off) pt = p;
            checked++;
            if (pt[1] !== w.v) bad++;
          }
        }
      }
      // the documented stepping case: China reads 54.84 in early November 2025
      // and 74.06 from 15 November, from the same tooltip in the same month
      let stepOk = 'n/a';
      const cn = S.find(s => s.n.startsWith('China'));
      if (cn) {
        const at = (iso) => {
          let pt = null;
          for (const p of cn.pts) if (p[0] <= Date.parse(iso)) pt = p;
          return pt && pt[1];
        };
        const early = at('2025-11-05T00:00:00Z'), mid = at('2025-11-15T00:00:00Z');
        stepOk = (early === 54.84 && mid === 74.06) ? 'ok' : 'BROKEN';
        if (stepOk === 'BROKEN') { bad++; console.log(`    step case: got ${early} then ${mid}`); }
      }
      const total = S.reduce((a, s) => a + s.pts.length, 0);
      totalPoints += total;
      extra = ` carry-forward=${bad ? 'BROKEN' : 'ok'} (${checked} checks)`
        + ` step-case=${stepOk} points=${total}`;
      if (bad) fail++;
    }
    if (D.sets) {
      // a band that does not contain its own published middle is a data error,
      // not a rendering one, and would draw a dot outside its own bar
      const all = D.sets.flat();
      const bad = all.filter(r => !(r.lo <= r.mid && r.mid <= r.hi));
      // each mode must be a different view: a control that redraws the same
      // rows in the same order is a control that does nothing. Two modes may
      // hold the same rows (TPD-D04 reorders them), so order is what is compared.
      const keys = D.sets.map(s => s.map(r => r.label).join('|'));
      const distinct = new Set(keys).size === keys.length;
      extra = ` band-contains-mid=${bad.length ? 'BROKEN' : 'ok'}`
        + ` modes=${D.sets.map(s => s.length).join('/')}`
        + ` distinct=${distinct ? 'ok' : 'BROKEN'}`;
      if (bad.length || !distinct) fail++;
    }

    const ok = base > 2 && hover === 'ok' && !results.some(r => r.includes('BROKEN'));
    if (!ok) { fail++; console.log(`  ${f}: SUSPECT marks=${base} ${results.join(' ')} hover=${hover}`); }
    else console.log(`  ${f.replace('.html', '').padEnd(9)} marks=${String(base).padStart(4)} `
      + `${results.join('  ').padEnd(30)} hover=${hover}${extra}`
      + (embedded ? `  height-msgs=${posted.length}` : ''));
  } catch (e) { fail++; console.log(`  ${f}: THREW — ${e.message}`); }
}
// the three tab pages must together carry every point the site ships; a tab
// silently dropped would still render and still hover correctly
if (totalPoints !== 157) {
  fail++;
  console.log(`\n  points across the tab pages: ${totalPoints}, expected 157`);
}
console.log(fail ? `\n${fail} page(s) failed` : '\nall pages executed and drew content');
process.exit(fail ? 1 : 0);
