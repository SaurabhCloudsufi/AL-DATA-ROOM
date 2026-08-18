// Render each interactive AI Models chart in a simulated DOM and assert it drew.
//
// A scatter whose maths is right can still ship blank if the markup or the
// wiring is broken, so this runs the published HTML end to end: draw, legend
// toggle, hover readout, height report.
//
// Needs jsdom, a dev-time dependency only, not vendored into the site. Skips
// with a clear message if it is not installed.
// Run: node build/verify_interactive_models.mjs [path-to-node_modules]
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";

const CHARTS = ["MODELS-01", "MODELS-02", "MODELS-03", "MODELS-04",
                "MODELS-05", "MODELS-13"];
const DIR = new URL("../ai-models/charts/", import.meta.url);

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

  // the payload is the contract: every point in it must reach the page
  const data = JSON.parse(readFileSync(file, "utf8")
    .match(/const D = (\{.*?\});\n/s)[1]);
  const circles = svg.querySelectorAll("circle");
  // one marker per point, plus the hover highlight ring
  check(`${id} drew one marker per recorded model`,
        circles.length === data.pts.length + 1,
        `got ${circles.length} for ${data.pts.length} points`);
  check(`${id} no NaN in any marker`,
        ![...circles].some(c => ["cx", "cy"].some(a => Number.isNaN(parseFloat(c.getAttribute(a))))));
  check(`${id} every marker sits inside the plot area`,
        [...circles].slice(0, -1).every(c => {
          const x = parseFloat(c.getAttribute("cx")), y = parseFloat(c.getAttribute("cy"));
          return x >= 0 && x <= 1000 && y >= 0 && y <= 520;
        }));
  check(`${id} gridlines and axis labels drawn`,
        svg.querySelectorAll("line.grid").length >= 4 &&
        svg.querySelectorAll("text.axis").length >= 5);
  check(`${id} both axes are labelled`,
        svg.querySelectorAll("text.axlab").length === 2);

  const legend = doc.querySelectorAll("#lg button.lg");
  check(`${id} legend has an entry per group`,
        legend.length === (data.groups.length > 1 ? data.groups.length : 0),
        `got ${legend.length} for ${data.groups.length} groups`);

  if (legend.length) {
    // clicking a legend entry must remove exactly that group's points
    const before = svg.querySelectorAll("circle").length;
    legend[0].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    const after = svg.querySelectorAll("circle").length;
    check(`${id} legend toggle removes exactly that group`,
          before - after === data.groups[0].n, `${before} -> ${after}`);
    check(`${id} toggle marks the entry pressed`,
          legend[0].getAttribute("aria-pressed") === "true");
    legend[0].dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    check(`${id} legend toggle restores the group`,
          svg.querySelectorAll("circle").length === before);
  }

  // hover must name the model under the pointer. jsdom has no PointerEvent, but
  // a MouseEvent carries the clientX/clientY the handler actually reads.
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 520 });
  const point = (type, x, y) => svg.dispatchEvent(
    new window.MouseEvent(type, { bubbles: true, clientX: x, clientY: y }));

  // aim at a marker that is actually on the page rather than a guessed pixel
  const target = [...svg.querySelectorAll("circle")].find(c => c.getAttribute("id") !== "hl");
  point("pointermove", parseFloat(target.getAttribute("cx")),
        parseFloat(target.getAttribute("cy")));
  const tip = doc.getElementById("tip");
  check(`${id} hover names a model`, tip.style.opacity === "1" && /<b>.+<\/b>/.test(tip.innerHTML),
        tip.innerHTML.slice(0, 60));
  check(`${id} hover rings the point`,
        parseFloat(doc.getElementById("hl").getAttribute("cx")) > 0);

  point("pointermove", 5, 5);
  check(`${id} pointer away from any model retracts the readout`,
        tip.style.opacity === "0");

  point("pointerleave", 500, 260);
  check(`${id} leaving hides the readout and the ring`,
        tip.style.opacity === "0" &&
        parseFloat(doc.getElementById("hl").getAttribute("cx")) < 0);

  // jsdom has no layout engine, so a real measurement is always 0 here. Stub the
  // wrapper's box and fire a resize: that tests the wiring, which is the part
  // that can actually break.
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
