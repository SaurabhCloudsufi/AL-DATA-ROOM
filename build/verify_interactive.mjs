// Verify the interactive charts' geometry maths before it ships.
//
// The browser code cannot be exercised here, but its pure functions can: this
// runs the exact same geometry() / nearestIndex() / niceTicks() emitted into the
// HTML against the real observed data and asserts the output is well formed.
// Run: node build/verify_interactive.mjs
import { geometry, nearestIndex, niceTicks, SAMPLE } from "./_interactive_geometry.mjs";

const W = 1000, H = 470, M = { l: 74, r: 16, t: 14, b: 34 };
let failures = 0;
const check = (name, ok, detail = "") => {
  if (!ok) { failures++; console.error(`  FAIL  ${name} ${detail}`); }
  else console.log(`  ok    ${name}`);
};

const D = SAMPLE;
check("data present", D.dates.length > 0 && D.series.length > 0,
      `dates=${D.dates.length} series=${D.series.length}`);
check("dates strictly increasing",
      D.dates.every((t, i) => i === 0 || t > D.dates[i - 1]));

for (const hidden of [new Set(), new Set([D.series[0].name]),
                      new Set(D.series.slice(0, 3).map(s => s.name))]) {
  const tag = hidden.size ? `(${hidden.size} hidden)` : "(all visible)";
  const G = geometry(D, hidden, W, H, M);

  check(`bands match visible series ${tag}`,
        G.bands.length === D.series.length - hidden.size);

  // stacking must never invert: every band's upper edge >= its lower edge
  let stackOk = true, finite = true, inBox = true;
  for (const b of G.bands) {
    for (let i = 0; i < D.dates.length; i++) {
      if (b.upper[i] < b.lower[i] - 1e-9) stackOk = false;
      if (!Number.isFinite(b.lower[i]) || !Number.isFinite(b.upper[i])) finite = false;
    }
    for (const n of b.path.match(/-?\d+\.\d+/g) || []) {
      const v = parseFloat(n);
      if (!Number.isFinite(v) || v < -1 || v > Math.max(W, H) + 1) inBox = false;
    }
  }
  check(`stacking never inverts ${tag}`, stackOk);
  check(`all band values finite ${tag}`, finite);
  check(`all path coords inside the viewBox ${tag}`, inBox);

  // the visible stack top must equal the sum of visible series at every point
  let sumOk = true;
  for (let i = 0; i < D.dates.length; i++) {
    const want = D.series.filter(s => !hidden.has(s.name))
                         .reduce((a, s) => a + s.values[i], 0);
    if (Math.abs(G.tops[i] - want) > 1e-6 * Math.max(1, want)) sumOk = false;
  }
  check(`stack top equals sum of visible series ${tag}`, sumOk);

  // y scale: 0 at the baseline, larger values higher up the page
  check(`y scale orientation ${tag}`, G.sy(0) > G.sy(G.yMax));
  check(`y ticks ascend from zero ${tag}`,
        G.yTicks[0] === 0 && G.yTicks.every((v, i) => i === 0 || v > G.yTicks[i - 1]));
  check(`x scale spans the plot area ${tag}`,
        Math.abs(G.sx(D.dates[0]) - M.l) < 1e-6 &&
        Math.abs(G.sx(D.dates[D.dates.length - 1]) - (W - M.r)) < 1e-6);
}

// hover lookup must land on the nearest point, including at both ends
check("nearestIndex at first point", nearestIndex(D, D.dates[0]) === 0);
check("nearestIndex at last point",
      nearestIndex(D, D.dates[D.dates.length - 1]) === D.dates.length - 1);
check("nearestIndex before range clamps to 0", nearestIndex(D, D.dates[0] - 1e9) === 0);
check("nearestIndex after range clamps to last",
      nearestIndex(D, D.dates[D.dates.length - 1] + 1e9) === D.dates.length - 1);
let nearOk = true;
for (let i = 0; i < D.dates.length; i++) {
  if (nearestIndex(D, D.dates[i]) !== i) nearOk = false;
}
check("nearestIndex exact on every point", nearOk);

check("niceTicks handles a zero maximum", niceTicks(0, 5).length >= 1);

const total = D.series.reduce((a, s) => a + s.values[s.values.length - 1], 0);
console.log(`\n  final stacked total: ${total.toLocaleString("en-US")}`);
console.log(failures ? `\n${failures} check(s) FAILED` : "\nall checks passed");
process.exit(failures ? 1 : 0);
