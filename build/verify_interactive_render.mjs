// Render each interactive chart in a simulated DOM and assert it drew.
//
// verify_interactive.mjs checks the geometry maths in isolation. This runs the
// published HTML end to end - script, legend, hover - because a page whose maths
// is correct can still ship a blank chart if the markup or wiring is broken.
//
// Needs jsdom, which is a dev-time dependency only and is not vendored into the
// site. Skips with a clear message if it is not installed.
// Run: node build/verify_interactive_render.mjs [path-to-node_modules]
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";

const CHARTS = ["EPOCH-03", "EPOCH-04", "EPOCH-05"];
const DIR = new URL("../ai-infrastructure/charts/", import.meta.url);

let JSDOM;
try {
  const req = createRequire(process.argv[2] ? process.argv[2] + "/" : import.meta.url);
  ({ JSDOM } = req("jsdom"));
} catch {
  console.log("jsdom not installed - skipping render verification");
  process.exit(0);
}

let failures = 0;
const check = (name, ok, detail = "") => {
  if (!ok) { failures++; console.error(`  FAIL  ${name} ${detail}`); }
  else console.log(`  ok    ${name}`);
};

for (const id of CHARTS) {
  const file = new URL(id + ".html", DIR);
  if (!existsSync(file)) { check(`${id} exists`, false); continue; }
  console.log(`\n${id}`);

  const posted = [];
  const dom = new JSDOM(readFileSync(file, "utf8"), {
    runScripts: "dangerously", pretendToBeVisual: true, url: "https://example.test/",
  });
  const { window } = dom;
  window.parent = { postMessage: (m) => posted.push(m) };
  await new Promise(r => setTimeout(r, 60));
  const doc = window.document;

  const svg = doc.getElementById("c");
  check(`${id} svg present`, !!svg);
  const paths = svg.querySelectorAll("path");
  check(`${id} drew one band per series`, paths.length === 10,
        `got ${paths.length}`);
  check(`${id} every band has a non-empty path`,
        [...paths].every(p => (p.getAttribute("d") || "").length > 50));
  check(`${id} no NaN in any path`,
        ![...paths].some(p => (p.getAttribute("d") || "").includes("NaN")));
  check(`${id} gridlines and axis labels drawn`,
        svg.querySelectorAll("line.grid").length >= 3 &&
        svg.querySelectorAll("text.axis").length >= 5);

  const legend = doc.querySelectorAll("#lg button.lg");
  check(`${id} legend has an entry per series`, legend.length === 10,
        `got ${legend.length}`);

  // clicking a legend entry must remove exactly that band and redraw
  const before = svg.querySelectorAll("path").length;
  legend[0].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const after = svg.querySelectorAll("path").length;
  check(`${id} legend toggle removes a band`, after === before - 1,
        `${before} -> ${after}`);
  check(`${id} toggle marks the entry pressed`,
        legend[0].getAttribute("aria-pressed") === "true");
  legend[0].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check(`${id} legend toggle restores the band`,
        svg.querySelectorAll("path").length === before);

  // hover must fill the tooltip and move the guide line. The chart listens for
  // pointer events so touch works too; jsdom has no PointerEvent, but a
  // MouseEvent carries the clientX/clientY the handler actually reads.
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 470 });
  const point = (type, x, y) => svg.dispatchEvent(
    new window.MouseEvent(type, { bubbles: true, clientX: x, clientY: y }));
  point("pointermove", 700, 200);
  const tip = doc.getElementById("tip");
  check(`${id} hover fills the tooltip`, /Total/.test(tip.innerHTML));
  check(`${id} tooltip is visible`, tip.style.opacity === "1");
  const guide = doc.getElementById("gd");
  check(`${id} hover moves the guide line`,
        guide && parseFloat(guide.getAttribute("x1")) > 0);

  point("pointerleave", 700, 200);
  check(`${id} leaving hides the tooltip and the guide`,
        tip.style.opacity === "0" && parseFloat(guide.getAttribute("x1")) < 0);

  // outside the plot area the readout must retract, not stick to the last point
  point("pointermove", 20, 200);
  check(`${id} pointer left of the plot area retracts the readout`,
        tip.style.opacity === "0");

  // jsdom has no layout engine, so a real measurement is always 0 here. Stub the
  // wrapper's box and fire a resize: that tests the wiring, which is the part
  // that can actually break. True pixel heights are a browser-only concern.
  const pg = doc.getElementById("pg");
  check(`${id} wraps its content in #pg`, !!pg);
  if (pg) {
    pg.getBoundingClientRect = () => ({ height: 613 });
    posted.length = 0;
    window.dispatchEvent(new window.Event("resize"));
    check(`${id} reports its measured height to the parent`,
          posted.some(m => m && m.type === "aidr-height" && m.id === id && m.h === 615),
          JSON.stringify(posted.slice(-1)));
  }

  window.close();
}

console.log(failures ? `\n${failures} check(s) FAILED` : "\nall render checks passed");
process.exit(failures ? 1 : 0);
