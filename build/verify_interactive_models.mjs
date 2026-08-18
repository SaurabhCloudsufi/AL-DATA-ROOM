/**
 * Verify the interactive AI Models companions render and their controls work.
 *
 * Runs each page against a minimal DOM stub. Checks it drew a circle per plotted
 * point plus the hover highlight, then exercises the two controls Epoch offers
 * and this page reproduces: switching the metric must change the plotted count,
 * and switching "colour by" must change the number of legend entries. Finally it
 * fires a hover and requires the tooltip to name a model.
 *
 * No dependencies - the previous version needed jsdom and could not run here.
 *
 *   node build/verify_interactive_models.mjs [--embedded]
 */
import { readFileSync, readdirSync } from 'fs';
import vm from 'vm';

const dir = new URL('../ai-models/charts/', import.meta.url).pathname;
const embedded = process.argv[2] === '--embedded';
let fail = 0;

for (const f of readdirSync(dir).filter(x => x.startsWith('MODELS-') && x.endsWith('.html')).sort()) {
  const html = readFileSync(dir + f, 'utf8');
  const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const D = JSON.parse(js.match(/^const D = (\{.*\});$/m)[1]);
  const mk = (tag) => ({
    tag, children: [], attrs: {}, style: {},
    setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); },
    get firstChild() { return this.children[0] || null; },
    set innerHTML(v) { this._html = v; this.children = []; },
    get innerHTML() { return this._html || ''; },
    set textContent(v) { this._text = v; }, get textContent() { return this._text || ''; },
    addEventListener(t, fn) { (this._ev ||= {})[t] = fn; },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 520 }),
  });
  const byId = { c: mk('svg'), tip: mk('div'), lg: mk('div'), ctl: mk('div'), pg: mk('div') };
  const posted = [];
  const ctx = { document: {
      getElementById: (id) => byId[id] || byId.c.children.find(e => e.attrs.id === id) || null,
      createElementNS: (n, t) => mk(t), createElement: (t) => mk(t),
      querySelector: () => null, body: mk('body') },
    console };
  ctx.window = { addEventListener() {} }; ctx.window.window = ctx.window;
  ctx.window.parent = embedded ? { postMessage: (m) => posted.push(m) } : ctx.window;
  try {
    vm.createContext(ctx);
    vm.runInContext(js, ctx, { timeout: 20000 });
    const circles = () => byId.c.children.filter(e => e.tag === 'circle').length;
    const base = circles(), texts = byId.c.children.filter(e => e.tag === 'text').length;

    const groups = byId.ctl.children.filter(e => e.tag === 'div');
    const btns = (g) => g.children.filter(e => e.tag === 'button');
    let metricTest = 'n/a', colourTest = 'n/a';
    for (const g of groups) {
      const cap = g.children[0].textContent, bs = btns(g);
      if (cap === 'Metric' && bs.length > 1) {
        bs[1].onclick(); const after = circles(); bs[0].onclick();
        metricTest = (after !== base && circles() === base) ? 'ok' : `BROKEN ${base}->${after}`;
      }
      if (cap === 'Colour by' && bs.length > 1) {
        const before = byId.lg.children.length;
        bs[1].onclick(); const after = byId.lg.children.length; bs[0].onclick();
        colourTest = (after > before) ? `ok (${before}->${after} keys)` : `BROKEN ${before}->${after}`;
      }
    }
    let hover = 'BROKEN';
    const mv = byId.c._ev && byId.c._ev.pointermove;
    if (mv) {
      // the scales live inside the page, so sweep the plot area until a point is
      // hit rather than guessing one position
      outer: for (let x = 90; x < 980; x += 12) {
        for (let y = 20; y < 470; y += 12) {
          mv({ clientX: x, clientY: y });
          if ((byId.tip.innerHTML || '').includes('<b>')) { hover = 'ok'; break outer; }
        }
      }
    }
    const ok = base > 2 && texts > 3 && hover === 'ok'
               && !String(metricTest).startsWith('BROKEN')
               && !String(colourTest).startsWith('BROKEN');
    if (!ok) { fail++; console.log(`  ${f}: SUSPECT circles=${base} texts=${texts} metric=${metricTest} colour=${colourTest} hover=${hover}`); }
    else console.log(`  ${f.replace('.html','').padEnd(11)} points=${String(base-1).padStart(4)} `
      + `metric=${String(metricTest).padEnd(6)} colour=${String(colourTest).padEnd(16)} hover=${hover}`
      + (embedded ? `  height-msgs=${posted.length}` : ''));
  } catch (e) { fail++; console.log(`  ${f}: THREW — ${e.message}`); }
}
console.log(fail ? `\n${fail} page(s) failed` : '\nall pages executed and drew content');
process.exit(fail ? 1 : 0);
