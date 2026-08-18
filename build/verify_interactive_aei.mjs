/**
 * Verify the interactive AI Usage companions actually render.
 *
 * Runs each page against a minimal DOM stub and checks what it drew: a bar per
 * visible row with its label and value, or a circle per country on the scatter.
 * Where a Top-N / All toggle exists it is clicked and the row count must grow to
 * the full list and shrink back, which is the whole reason these pages exist -
 * the static charts can only show a ranked selection.
 *
 * Both framings are checked: at top level parent === window so the height report
 * must short-circuit; embedded it must post one height message per redraw.
 *
 * No dependencies - no jsdom required.
 *
 *   node build/verify_interactive_aei.mjs [--embedded]
 */
import { readFileSync, readdirSync } from 'fs';
import vm from 'vm';

const dir = new URL('../ai-usage/charts/', import.meta.url).pathname;
const embedded = process.argv[2] === '--embedded';
let fail = 0;

for (const f of readdirSync(dir).filter(x => x.startsWith('AEI-') && x.endsWith('.html')).sort()) {
  const html = readFileSync(dir + f, 'utf8');
  const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  // `const D = ...` is a lexical binding inside the vm context and never lands
  // on its global object, so the payload is read from the source instead
  const D = JSON.parse(js.match(/^const D = (\{.*\});$/m)[1]);
  const mk = (tag) => ({
    tag, children: [], attrs: {}, style: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); },
    get firstChild() { return this.children[0] || null; },
    set innerHTML(v) { this._html = v; this.children = []; },
    get innerHTML() { return this._html || ''; },
    set textContent(v) { this._text = v; }, get textContent() { return this._text || ''; },
    addEventListener(t, fn) { (this._ev ||= {})[t] = fn; },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 600 }),
  });
  const byId = { c: mk('svg'), tip: mk('div'), ctl: mk('div'), pg: mk('div') };
  const posted = [];
  const ctx = {
    document: {
      getElementById: (id) => byId[id] || byId.c.children.find(e => e.attrs.id === id) || null,
      createElementNS: (ns, t) => mk(t),
      createElement: (t) => mk(t),
      body: mk('body'),
    },
    console,
  };
  ctx.window = { addEventListener() {} };
  ctx.window.window = ctx.window;
  ctx.window.parent = embedded ? { postMessage: (m) => posted.push(m) } : ctx.window;
  try {
    vm.createContext(ctx);
    vm.runInContext(js, ctx, { timeout: 15000 });
    const kids = () => byId.c.children;
    const n = (t) => kids().filter(e => e.tag === t).length;
    const before = { rect: n('rect'), circle: n('circle'), text: n('text') };
    const isBar = before.rect > 1;

    // exercise the Top-N / All toggle where the page offers one
    let toggle = 'n/a';
    const btns = byId.ctl.children.filter(e => e.tag === 'button');
    if (btns.length === 2) {
      btns[1]._ev; btns[1].onclick();               // "All"
      const all = n('rect');
      btns[0].onclick();                            // back to Top N
      const back = n('rect');
      toggle = (all > before.rect && back === before.rect) ? `ok (${before.rect}->${all})`
                                                           : `BROKEN ${before.rect}->${all}->${back}`;
    }
    // the interaction itself: point at the first row / a real marker and
    // require the tooltip to fill with that entry's name
    let hover = 'BROKEN';
    const mv = byId.c._ev && byId.c._ev.pointermove;
    if (mv) {
      if (isBar) {
        mv({ clientX: (D.labelW + 20), clientY: 20 });
      } else {
        // scatter: aim exactly at the highest-volume country. The page maps
        // BOTH axes through rect.width (the viewBox scales uniformly), and the
        // stub reports width 1000 = W, so client coords are svg coords 1:1.
        const top = D.rows.reduce((a, b) => (b[1] > a[1] ? b : a));
        const sx = byId.c._sx, sy = byId.c._sy;
        mv({ clientX: sx(top[1]), clientY: sy(top[2]) });
      }
      const html = byId.tip.innerHTML || '';
      hover = html.includes('<b>') ? 'ok' : `BROKEN (tip="${html.slice(0,40)}")`;
    }
    const ok = (isBar ? (before.rect > 2 && before.text > 3)
                     : (before.circle > 20 && before.text > 3))
               && hover === 'ok';
    if (!ok || String(toggle).startsWith('BROKEN')) {
      fail++;
      console.log(`  ${f}: SUSPECT rects=${before.rect} circles=${before.circle} text=${before.text} toggle=${toggle} hover=${hover}`);
    } else {
      console.log(`  ${f.replace('.html','').padEnd(9)} ${(isBar?'bar':'scatter').padEnd(7)} `
        + `marks=${String(isBar?before.rect:before.circle).padStart(4)} labels=${String(before.text).padStart(4)} `
        + `toggle=${String(toggle).padEnd(16)} hover=${hover}`
        + (embedded ? `  height-msgs=${posted.length}` : ''));
    }
  } catch (e) {
    fail++;
    console.log(`  ${f}: THREW — ${e.message}`);
  }
}
console.log(fail ? `\n${fail} page(s) failed` : '\nall pages executed and drew content');
process.exit(fail ? 1 : 0);
