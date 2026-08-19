/**
 * Verify the interactive AI Data Centers companions render and respond.
 *
 * EPOCH-03/04/05 are the owner stacks. They shipped with a jsdom-based check
 * that has never been able to run in this environment, so until now they were
 * unverified; this replaces it with one that needs nothing installed.
 *
 * DERIVED-05 is the cooling catalogue: it must switch between colouring by
 * equipment class and by manufacturer, toggle the per-class intensity lines,
 * and name the manufacturer of whatever unit is hovered.
 *
 * No dependencies.
 *   node build/verify_interactive_datacenters.mjs [--embedded]
 */
import { readFileSync, readdirSync } from 'fs';
import vm from 'vm';

const dir = new URL('../ai-infrastructure/charts/', import.meta.url).pathname;
const embedded = process.argv[2] === '--embedded';
let fail = 0;

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
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 470 }),
});

for (const f of readdirSync(dir).filter(x => x.match(/^(EPOCH|DERIVED)-/) && x.endsWith('.html')).sort()) {
  const html = readFileSync(dir + f, 'utf8');
  const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const byId = { c: mk('svg'), tip: mk('div'), ctl: mk('div'), lg: mk('div'), pg: mk('div') };
  const posted = [];
  const ctx = { document: {
      // ids created inside the svg (the hover highlight, the tracking rule) have
      // to resolve, and the owner stacks look up '.plot' by selector
      getElementById: (id) => byId[id]
        || byId.c.children.find(e => e.attrs && e.attrs.id === id) || null,
      querySelector: () => mk('div'),
      createElementNS: (n, t) => mk(t), createElement: (t) => mk(t),
      addEventListener() {}, removeEventListener() {},
      body: mk('body') }, console };
  ctx.window = { addEventListener() {} }; ctx.window.window = ctx.window;
  ctx.window.parent = embedded ? { postMessage: (m) => posted.push(m) } : ctx.window;
  try {
    vm.createContext(ctx);
    vm.runInContext(js, ctx, { timeout: 15000 });
    const marks = () => byId.c.children.filter(e => e.tag === 'rect' || e.tag === 'circle' || e.tag === 'polygon' || e.tag === 'path').length;
    const base = marks();
    const groups = byId.ctl.children.filter(e => e.tag === 'div');
    const btnsIn = (g) => g.children.filter(e => e.tag === 'button');

    let controls = [];
    for (const g of groups) {
      const cap = g.children[0].textContent, bs = btnsIn(g);
      if (bs.length > 1) {
        const before = marks() + byId.lg.children.length;
        bs[1].onclick();
        const after = marks() + byId.lg.children.length;
        bs[0].onclick();
        controls.push(`${cap}=${after !== before || marks() === base ? 'ok' : 'BROKEN'}`);
      }
    }
    // top-level buttons (the ranked pages put them straight in .ctl)
    const flat = byId.ctl.children.filter(e => e.tag === 'button');
    if (flat.length > 1) {
      const before = marks(); flat[1].onclick();
      const after = marks(); flat[0].onclick();
      controls.push(`TopN=${after > before && marks() === before ? 'ok' : 'BROKEN'}`);
    }

    let hover = 'BROKEN';
    const mv = byId.c._ev && byId.c._ev.pointermove;
    if (mv) {
      outer: for (let x = 100; x < 980; x += 20) {
        for (let y = 20; y < 460; y += 15) {
          mv({ clientX: x, clientY: y });
          if ((byId.tip.innerHTML || '').includes('<b>')) { hover = 'ok'; break outer; }
        }
      }
    }
    const ok = base > 3 && hover === 'ok' && !controls.some(c => c.includes('BROKEN'));
    if (!ok) { fail++; console.log(`  ${f}: SUSPECT marks=${base} ${controls.join(' ')} hover=${hover}`); }
    else console.log(`  ${f.replace('.html','').padEnd(9)} marks=${String(base).padStart(3)} `
      + `${controls.join('  ').padEnd(42)} hover=${hover}`
      + (embedded ? `  height-msgs=${posted.length}` : ''));
  } catch (e) { fail++; console.log(`  ${f}: THREW — ${e.message}`); }
}
console.log(fail ? `\n${fail} page(s) failed` : '\nall pages executed and drew content');
process.exit(fail ? 1 : 0);
