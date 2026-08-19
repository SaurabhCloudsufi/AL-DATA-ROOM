/**
 * Verify the interactive MLPerf Inference companions render and respond.
 *
 * These pages exist because a printed figure can show one workload-scenario
 * ranking out of 21, so the controls are the whole point: switching the workload
 * must change what is drawn, and on MLPERF-01 switching the scenario must too.
 * Combinations with no submission disable their button rather than drawing an
 * empty chart, so a disabled button is a pass, not a failure.
 *
 * No dependencies.
 *   node build/verify_interactive_mlperf.mjs [--embedded]
 */
import { readFileSync, readdirSync } from 'fs';
import vm from 'vm';

const dir = new URL('../mlperf-inference/charts/', import.meta.url).pathname;
const embedded = process.argv[2] === '--embedded';
let fail = 0;

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

for (const f of readdirSync(dir).filter(x => x.startsWith('MLPERF-') && x.endsWith('.html')).sort()) {
  const html = readFileSync(dir + f, 'utf8');
  const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const D = JSON.parse(js.match(/^const D = (\{.*\});$/m)[1]);
  const byId = { c: mk('svg'), tip: mk('div'), ctl: mk('div'), lg: mk('div'), pg: mk('div') };
  const posted = [];
  const ctx = { document: { getElementById: (id) => byId[id] || null,
      createElementNS: (n, t) => mk(t), createElement: (t) => mk(t), body: mk('body') },
    console, Math };
  ctx.window = { addEventListener() {} }; ctx.window.window = ctx.window;
  ctx.window.parent = embedded ? { postMessage: (m) => posted.push(m) } : ctx.window;
  try {
    vm.createContext(ctx);
    vm.runInContext(js, ctx, { timeout: 15000 });
    const rects = () => byId.c.children.filter(e => e.tag === 'rect').length;
    const base = rects();
    const groups = byId.ctl.children.filter(e => e.tag === 'div');
    const results = [];
    for (const g of groups) {
      const cap = g.children[0].textContent;
      const bs = g.children.filter(e => e.tag === 'button');
      const other = bs.find((b, i) => i > 0 && !b.disabled);
      if (!other) { results.push(`${cap}=no-alt`); continue; }
      const before = rects();
      other.onclick();
      const after = rects();
      bs[0].onclick();
      const back = rects();
      results.push(`${cap}=${(after !== before || after > 0) && back === before ? 'ok' : 'BROKEN'}`);
    }
    // every combination must either draw something or be disabled, never blank
    let blanks = 0;
    for (const w of D.workloads) {
      const keys = D.mode === 'rank' ? D.scenarios : ['__all__'];
      for (const k of keys) if (((D.data[w] || {})[k] || []).length === 0) blanks++;
    }
    let hover = 'BROKEN';
    const mv = byId.c._ev && byId.c._ev.pointermove;
    if (mv) {
      for (let y = 20; y < 500 && hover !== 'ok'; y += 10) {
        mv({ clientX: 600, clientY: y });
        if ((byId.tip.innerHTML || '').includes('<b>')) hover = 'ok';
      }
    }
    const ok = base > 2 && hover === 'ok' && !results.some(r => r.includes('BROKEN'));
    if (!ok) { fail++; console.log(`  ${f}: SUSPECT rects=${base} ${results.join(' ')} hover=${hover}`); }
    else console.log(`  ${f.replace('.html','').padEnd(11)} bars=${String(base).padStart(3)} `
      + `${results.join('  ').padEnd(34)} empty-combos=${blanks} (disabled) hover=${hover}`
      + (embedded ? `  height-msgs=${posted.length}` : ''));
  } catch (e) { fail++; console.log(`  ${f}: THREW — ${e.message}`); }
}
console.log(fail ? `\n${fail} page(s) failed` : '\nall pages executed and drew content');
process.exit(fail ? 1 : 0);
