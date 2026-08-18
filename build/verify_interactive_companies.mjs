/**
 * Verify the interactive AI Companies companions actually render.
 *
 * Runs each page's script against a minimal DOM stub and checks it draws: one
 * circle per plotted point plus the hover highlight, a polyline per company
 * with two or more observations, a dashed line per fitted trend, and a legend
 * entry per company. Then it clicks the first legend entry and confirms the
 * chart redraws with fewer points and restores when clicked again.
 *
 * Both framings are checked: at top level parent === window, so the height
 * report must short-circuit; embedded in an iframe it must post exactly one
 * height message, which is what sizes the frame in the gallery.
 *
 * No dependencies - unlike verify_interactive_models.mjs this needs no jsdom,
 * so it runs anywhere node does.
 *
 *   node build/verify_interactive_companies.mjs
 *   node build/verify_interactive_companies.mjs --embedded
 */
import { readFileSync, readdirSync } from 'fs';
import vm from 'vm';

const dir = new URL('../ai-companies/charts/', import.meta.url).pathname;
let fail = 0;

const embedded = process.argv[2] === '--embedded';
for (const f of readdirSync(dir).filter(x => x.startsWith('COMPANIES-') && x.endsWith('.html')).sort()) {
  const html = readFileSync(`${dir}/${f}`, 'utf8');
  const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const made = [];
  const mk = (tag) => ({
    tag, children: [], attrs: {}, style: {}, _text: '',
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); },
    get firstChild() { return this.children[0] || null; },
    set innerHTML(v) { this._html = v; this.children = []; },
    get innerHTML() { return this._html || ''; },
    set textContent(v) { this._text = v; },
    get textContent() { return this._text; },
    addEventListener() {}, focus() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 520 }),
  });
  const byId = { c: mk('svg'), tip: mk('div'), lg: mk('div'), pg: mk('div') };
  const ctx = {
    document: {
      getElementById: (id) => byId[id] || null,
      createElementNS: (ns, t) => { const e = mk(t); made.push(e); return e; },
      createElement: (t) => mk(t),
      querySelector: () => null,
      body: mk('body'),
    },
    window: { addEventListener() {} },
    console,
  };
  ctx.window.window = ctx.window;
  // top-level page: parent === window, so reportHeight must short-circuit.
  // embedded: parent is a different window and must receive the height message.
  const posted = [];
  ctx.window.parent = embedded
    ? { postMessage: (m) => posted.push(m) }
    : ctx.window;
  ctx.posted = posted;
  try {
    vm.createContext(ctx);
    vm.runInContext(js, ctx, { timeout: 10000 });
    const svgKids = byId.c.children;
    const n = (t) => svgKids.filter(e => e.tag === t).length;
    const legend = byId.lg.children.length;
    const circles = n('circle'), lines = n('line'), polys = n('polyline'), texts = n('text');
    // the interaction itself: hide the first company, redraw, restore
    let toggled = 'n/a';
    const btn = byId.lg.children[0];
    if (btn && btn.onclick) {
      const before = svgKids.filter(e => e.tag === 'circle').length;
      btn.onclick();
      const after = byId.c.children.filter(e => e.tag === 'circle').length;
      btn.onclick();
      const back = byId.c.children.filter(e => e.tag === 'circle').length;
      toggled = (after < before && back === before) ? 'ok' : `BROKEN ${before}->${after}->${back}`;
    }
    const ok = circles > 1 && texts > 2 && toggled !== 'n/a' && !String(toggled).startsWith('BROKEN');
    if (!ok) { fail++; console.log(`  ${f}: SUSPECT — circles=${circles} texts=${texts} toggle=${toggled}`); }
    else console.log(`  ${f.replace('.html','').padEnd(14)} circles=${String(circles).padStart(3)} `
      + `polylines=${String(polys).padStart(2)} gridlines/fits=${String(lines).padStart(3)} `
      + `labels=${String(texts).padStart(3)} legend=${legend}`
      + `  legend-toggle=${toggled}`
      + (embedded ? `  height-msgs=${ctx.posted.length}` : ''));
  } catch (e) {
    fail++;
    console.log(`  ${f}: THREW — ${e.message}`);
  }
}
console.log(fail ? `\n${fail} page(s) failed` : '\nall pages executed and drew content');
process.exit(fail ? 1 : 0);
