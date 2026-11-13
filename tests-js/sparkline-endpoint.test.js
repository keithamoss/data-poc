// post-build-review #57's last open item, signed off 2026-09-25
// ("yep, fix it"). REWRITTEN for REQ-DASH-225 criteria 13 and 14: the
// endpoint dot is gone - the count beside the lines states where a dataset
// stands - so its assertions went with it. What still guards live code is
// kept: statusColorVar() never defaults to green, and a quiet state draws
// its history without colour.
//
// THE ONLY RED PIXEL IN THE VIEWPORT SAT UNDER A PILL SAYING THERE IS
// NO DATA. Where history exists but none of it is current, the card
// still painted the full sparkline ending in a red endpoint dot - 130px
// under a "No data" pill. The line itself is right and Keith has said
// so before ("no red amber and greens... but I should still be able to
// see the historical graphs"); it is the ENDPOINT that asserts "and
// this is where it stands now", which is the one thing a quiet state
// means nobody can say.
//
// A SECOND BUG IN THE SAME FUNCTION, found writing these:
// statusColorVar() is a two-branch ternary falling through to
// var(--good), so EVERY status it does not recognise - nodata,
// exhausted, inactive, and anything added later - paints green. A
// colour function whose default is "healthy" is the same false-green
// shape this project keeps finding.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}

const d = (iso) => new Date(iso + "T00:00:00Z");
const h = (run_id, date, status) => ({ run_id, date: d(date), status });
const COLS = [
  { name: "a", checks: [{ history: [
      h("r1", "2026-01-01", "green"), h("r2", "2026-01-02", "amber"), h("r3", "2026-01-03", "red")] }] },
  { name: "b", checks: [{ history: [
      h("r1", "2026-01-01", "green"), h("r2", "2026-01-02", "red"), h("r3", "2026-01-03", "red")] }] },
];
const GREEN = [
  { name: "a", checks: [{ history: [h("r1", "2026-01-01", "green"), h("r2", "2026-01-02", "green")] }] },
];

describe("statusColorVar", () => {
  it("does not paint an unrecognised status green", () => {
    const w = load();
    const good = w.statusColorVar("green");
    for (const quiet of ["nodata", "exhausted", "inactive"]) {
      expect(w.statusColorVar(quiet), `${quiet} paints as healthy`).not.toBe(good);
    }
  });

  it("still paints the three verdicts as it always did", () => {
    const w = load();
    expect(w.statusColorVar("red")).toBe("var(--bad)");
    expect(w.statusColorVar("amber")).toBe("var(--warn-fill)");
    expect(w.statusColorVar("green")).toBe("var(--good)");
  });
});

describe("the two trend lines", () => {
  it("draw red solid and amber dotted, with no endpoint dot", () => {
    const w = load();
    const svg = w.aggregateSparkline(COLS);
    expect(svg).toContain('stroke="var(--bad)"');
    expect(svg).toMatch(/stroke="var\(--warn\)"[^>]*stroke-dasharray="1.5,2.5"/);
    expect(svg).not.toContain("<circle");
  });

  it("draw no red or amber pixel for a history green on every run", () => {
    const w = load();
    const svg = w.aggregateSparkline(GREEN);
    expect(svg).toContain("<line"); // the neutral baseline
    expect(svg).not.toContain("var(--bad)");
    expect(svg).not.toContain("var(--warn)");
    expect(svg).not.toContain("var(--warn-fill)");
  });

  it("keep every stroke the same width however the box stretches", () => {
    const w = load();
    const svg = w.aggregateSparkline(COLS);
    const strokes = [...svg.matchAll(/<(path|line)\b[^>]*>/g)].map((m) => m[0]);
    expect(strokes.length).toBeGreaterThan(2);
    for (const s of strokes) expect(s).toContain('vector-effect="non-scaling-stroke"');
  });
});

// post-build-review #184 (delivery-critic on REQ-DASH-225): the amber line
// is --warn, as the signed CONTRAST NFR says (--warn-fill is 2.7:1 on white),
// and where the two lines coincide red is drawn on top (LEGIBILITY NFR).
describe("the lines' colour and stacking", () => {
  it("draws amber in --warn, never --warn-fill", () => {
    const w = load();
    const svg = w.aggregateSparkline(COLS);
    expect(svg).toMatch(/stroke="var\(--warn\)"[^>]*stroke-dasharray="1.5,2.5"/);
    expect(svg).not.toContain("var(--warn-fill)");
    expect(w.columnsNotGreenKey()).toContain('stroke="var(--warn)"');
    expect(w.columnsNotGreenKey()).not.toContain("var(--warn-fill)");
  });

  it("draws red after amber, so red is on top where they coincide", () => {
    const w = load();
    const svg = w.aggregateSparkline(COLS);
    expect(svg.lastIndexOf('data-series="red"')).toBeGreaterThan(svg.lastIndexOf('data-series="amber"'));
  });
});

describe("the lines under a quiet state", () => {
  it("still draw the history, in neutral ink, told apart by style alone", () => {
    // Keith, on the quiet states generally: "no red amber and greens...
    // but I should still be able to see the historical graphs and
    // comparison stuff."
    const w = load();
    for (const quiet of ["nodata", "exhausted", "inactive"]) {
      const svg = w.aggregateSparkline(COLS, quiet);
      expect(svg, quiet).not.toContain("var(--bad)");
      expect(svg, quiet).not.toContain("var(--warn)");
      expect(svg, quiet).not.toContain("var(--warn-fill)");
      expect(svg, quiet).not.toContain("var(--good)");
      expect(svg, quiet).toContain('data-series="red"');
      expect(svg, quiet).toMatch(/data-series="amber"/);
      expect(svg, quiet).toContain('stroke-dasharray="1.5,2.5"');
    }
  });
});
