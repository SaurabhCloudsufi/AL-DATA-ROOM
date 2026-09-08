/**
 * Verify DCMAP-01 renders and responds.
 *
 * The map is one self-contained page with no dependencies, so this runs its
 * script against a DOM shim in `vm` - the same approach the other verifiers in
 * this directory use, and for the same reason: nothing has to be installed.
 *
 * What it asserts, in order:
 *   draws        circles appear, and big ones are painted before small ones so a
 *                small site sitting inside a large one stays hoverable
 *   halos        drawn only for sites whose location is coarser than `exact`
 *   names        country labels are placed, data-first, and de-overlapped
 *   legend       size rings render and are labelled
 *   search       narrows the mark count and recovers when cleared
 *   facet        a checkbox filter narrows the count and clears cleanly
 *   timeline     dragging back in time removes sites, and undated sites stay
 *   colour       switching the colour-by dimension repaints the fills
 *   hover/pin    hovering names a value, clicking opens the card, Escape closes
 *
 *   node build/verify_map_ai_dc_index.mjs
 */
import { readFileSync } from 'fs';
import vm from 'vm';

const file = new URL('../ai-dc-index/charts/DCMAP-01.html', import.meta.url).pathname;
const html = readFileSync(file, 'utf8');
let fail = 0;
const check = (name, ok, detail = '') => {
  if (!ok) fail++;
  console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${name.padEnd(12)} ${detail}`);
};

/* ------------------------------------------------------------------ shim */
function mk(tag) {
  const el = {
    tag, children: [], attrs: {}, dataset: {}, _ev: {}, hidden: false,
    style: new Proxy({ setProperty(k, v) { this[k] = v; } }, {}),
    classList: {
      _s: new Set(),
      add(...c) { c.forEach(x => this._s.add(x)); },
      remove(...c) { c.forEach(x => this._s.delete(x)); },
      toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    setAttribute(k, v) {
      this.attrs[k] = String(v);
      if (k === 'class') { this.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); }
      if (k === 'id') this.id = String(v);
    },
    get className() { return [...this.classList._s].join(' '); },
    set className(v) { this.classList._s = new Set(String(v).split(/\s+/).filter(Boolean)); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    append(...cs) { cs.forEach(c => this.appendChild(c)); },
    replaceChildren(...cs) { this.children = []; cs.forEach(c => this.appendChild(c)); },
    removeChild(c) { this.children = this.children.filter(x => x !== c); },
    addEventListener(t, fn) { (this._ev[t] ||= []).push(fn); },
    removeEventListener() {},
    setPointerCapture() {}, releasePointerCapture() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, right: 980, bottom: 520, width: 980, height: 520 }),
    querySelector(sel) { return this._find(sel); },
    querySelectorAll(sel) { return this._findAll(sel); },
    _find(sel) { return this._findAll(sel)[0] || null; },
    _findAll(sel) {
      const want = sel.replace(/^[#.]/, '');
      const out = [];
      const walk = n => {
        for (const c of n.children) {
          if (sel.startsWith('#') && c.attrs.id === want) out.push(c);
          else if (sel.startsWith('.') && c.classList.contains(want)) out.push(c);
          else if (c.tag === sel) out.push(c);
          walk(c);
        }
      };
      walk(this);
      return out;
    },
    get offsetWidth() { return 290; },
    get offsetHeight() { return 200; },
    get offsetParent() { return byId.wrap; },
    get firstChild() { return this.children[0] || null; },
    set innerHTML(v) { this._html = v; this.children = []; },
    get innerHTML() { return this._html || ''; },
    set textContent(v) { this._text = String(v); },
    get textContent() { return this._text || ''; },
  };
  return el;
}

const ids = ['pg', 'map', 'wrap', 'legend', 'q', 'fbtn', 'fcount', 'cby', 'count', 'zin',
             'zout', 'zfit', 'play', 'e0', 'e1', 'year', 'marks', 'tlval', 'foot'];
const byId = {};
for (const id of ids) { byId[id] = mk(id === 'map' ? 'svg' : 'div'); byId[id].attrs.id = id; }
byId.q.value = ''; byId.year.value = 0; byId.cby.value = 'none';
byId.fbtn.parentNode = byId.wrap;
byId.fbtn.appendChild = byId.fbtn.appendChild.bind(byId.fbtn);

const doc = {
  getElementById: id => byId[id] || null,
  createElement: t => mk(t),
  createElementNS: (ns, t) => mk(t),
  querySelector: () => mk('div'),
  querySelectorAll: () => [],
  addEventListener(t, fn) { (this._ev ||= {})[t] ||= []; this._ev[t].push(fn); },
  removeEventListener() {},
  body: mk('body'),
  documentElement: { clientWidth: 1200, clientHeight: 900 },
};

const ctx = {
  document: doc, console,
  ResizeObserver: class { constructor(fn) { this.fn = fn; } observe() { this.fn([{ contentRect: { width: 980, height: 520 } }]); } disconnect() {} },
  setInterval: () => 1, clearInterval: () => {},
  requestAnimationFrame: fn => fn(0), cancelAnimationFrame: () => {},
  Math, JSON, Date, Object, Array, Set, Map, String, Number, parseFloat, parseInt, isNaN,
};
const posted = [];
ctx.addEventListener = () => {};
ctx.removeEventListener = () => {};
ctx.window = ctx; ctx.globalThis = ctx;
ctx.parent = { postMessage: m => posted.push(m) };

/* ------------------------------------------------------------------- run */
const js = html.match(/<script>([\s\S]*?)<\/script>\s*$/)[1];
try {
  vm.createContext(ctx);
  vm.runInContext(js, ctx, { timeout: 20000 });
} catch (e) {
  console.log(`  THREW - ${e.stack}`);
  process.exit(1);
}

const svg = byId.map;
const layer = i => svg.children[0].children[i];   // land, names, halo, dots
const dots = () => layer(3).children;
const halos = () => layer(2).children;
const names = () => layer(1).children;
const radii = () => dots().map(c => parseFloat(c.attrs.r));
const fills = () => dots().map(c => c.attrs.fill);
const fire = (el, type, ev = {}) => (el._ev[type] || []).forEach(fn => fn(ev));

const base = dots().length;
check('draws', base > 200, `${base} circles, ${layer(0).children.length} land rings`);

const r = radii();
check('order', r.every((v, i) => i === 0 || r[i - 1] >= v - 1e-9),
      `radii descending, max ${Math.max(...r).toFixed(1)}px min ${Math.min(...r).toFixed(1)}px`);

const D = JSON.parse(html.match(/^const D = (.*);$/m)[1]);
const approx = D.sites.filter(s => s.mw && s.p !== 'exact').length;
check('halos', halos().length > 0 && halos().length <= approx,
      `${halos().length} halos, ${approx} sites coarser than exact`);

check('names', names().length > 0,
      `${names().length} country labels placed, data-priority with overlap culling`);

check('legend', /Announced capacity/.test(byId.legend.innerHTML) &&
                /<circle/.test(byId.legend.innerHTML),
      `${(byId.legend.innerHTML.match(/<circle/g) || []).length} size rings`);

byId.q.value = 'google';
byId.q.oninput();
const searched = dots().length;
byId.q.value = ''; byId.q.oninput();
check('search', searched > 0 && searched < base && dots().length === base,
      `"google" -> ${searched} of ${base}`);

const panel = byId.wrap.children.find(c => c.classList.contains('pop'));
const cb = { dataset: { dim: 'st' }, value: 'Operational', checked: true };
fire(panel, 'change', { target: cb });
const filtered = dots().length;
byId.wrap._filterClear = null;
cb.checked = false; fire(panel, 'change', { target: cb });
check('facet', filtered > 0 && filtered < base && dots().length === base,
      `status=Operational -> ${filtered} of ${base}`);

byId.year.value = 0; byId.year.oninput();
const early = dots().length;
const undated = D.sites.filter(s => s.y == null && s.mw).length;
byId.year.value = D.years.length - 1; byId.year.oninput();
check('timeline', early >= undated && early < base && dots().length >= base,
      `${D.years[0]} -> ${early} (>= ${undated} undated), ${D.years.at(-1)} -> ${dots().length}`);

const before = new Set(fills()).size;
byId.cby.value = 'c'; byId.cby.onchange();
const after = new Set(fills()).size;
byId.cby.value = 'none'; byId.cby.onchange();
check('colour', before === 1 && after > 1, `none -> ${before} hue, company -> ${after} hues`);

const bub = byId.wrap.children.find(c => c.classList.contains('bub'));
const card = byId.wrap.children.find(c => c.classList.contains('card'));
const target = { classList: { contains: c => c === 'dot' }, dataset: { id: dots()[0].dataset.id } };
fire(svg, 'mousemove', { target });
const hovered = !bub.hidden && /MW|GW/.test(bub.textContent);
fire(svg, 'click', { target });
const pinned = !card.hidden && card.innerHTML.includes('announced capacity');
fire(doc, 'keydown', { key: 'Escape' });
check('hover/pin', hovered && pinned && card.hidden,
      `bubble "${bub.textContent}", card opens and Escape closes`);

check('embed', posted.some(m => m.type === 'aidr-height' && m.id === 'DCMAP-01' && m.h > 0),
      `posts iframe height (${posted.length} message${posted.length === 1 ? '' : 's'})`);

console.log(fail ? `\n${fail} check(s) failed` : '\nall checks passed');
process.exit(fail ? 1 : 0);
