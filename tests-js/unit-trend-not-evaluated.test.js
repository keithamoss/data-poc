// REQ-DASH-359 criterion 19 (plans/post-build-review.md #289 D8e): a QA run
// whose point on a unit-count trend was not evaluated is left out of the
// line - as plotted() leaves a not-evaluated point out of a check's own
// trend - and never drawn as a 0% dip. Written first and seen failing: a
// not-evaluated result with no failing verdict counted as a pass, so the
// line between two failing runs fell to 0% and back.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => (dashboard = loadDashboard()).window;

const d = (iso) => new Date(iso + "T00:00:00Z");
const DATES = { r1: "2026-01-01", r2: "2026-02-01", r3: "2026-03-01", r4: "2026-04-01" };
const entry = (run_id, status, notEvaluated) => ({ run_id, date: d(DATES[run_id]), status,
  value: notEvaluated ? null : 1, not_evaluated: notEvaluated ? "the table it reads is not in place" : null });
const unit = (name, entries) => ({ name, checks: [{ history: entries }] });

// Every y the red line is drawn at, as a share 0..1, given the chart's top
// and bottom padding (the sparkline's is 2 and 2, the large trend's 8 and 22).
function redShares(svg, padT = 2, padB = 2) {
  const h = Number(svg.match(/viewBox="0 0 \d+ (\d+)"/)[1]);
  return [...svg.matchAll(/<path d="([^"]+)"[^>]*data-series="red"/g)]
    .flatMap((m) => [...m[1].matchAll(/[ML][\d.]+,([\d.]+)/g)]
      .map((p) => +((h - padB - Number(p[1])) / (h - padT - padB)).toFixed(3)));
}

describe("a not-evaluated point on a unit-count trend", () => {
  const units = [
    unit("a", [entry("r1", "red"), entry("r2", "green", true), entry("r3", "red"), entry("r4", "red")]),
    unit("b", [entry("r1", "green"), entry("r2", "green", true), entry("r3", "green"), entry("r4", "green")]),
  ];

  it("is marked not evaluated in the series, which keeps its place", () => {
    const series = load().unitCounts(units);
    expect(series.map((p) => p.runId)).toEqual(["r1", "r2", "r3", "r4"]);
    expect(series.map((p) => !!p.notEvaluated)).toEqual([false, true, false, false]);
  });

  it("is left out of the line, never drawn as a 0% dip", () => {
    const w = load();
    const svg = w.twoLineSparkline(w.unitCounts(units), { w: 120, h: 28 });
    const shares = redShares(svg);
    expect(shares.length).toBeGreaterThan(0);
    expect(shares).not.toContain(0);
  });

  it("on the dataset page's large trend too", () => {
    const w = load();
    const html = w.unitTrendBlock(w.unitCounts(units), { kind: "dataset", title: "t", yTitle: "% of columns",
      unitWord: "Columns", noun: "column" });
    const svg = html.match(/<svg[\s\S]*?<\/svg>/)[0];
    const shares = redShares(svg, 8, 22);
    expect(shares.length).toBeGreaterThan(0);
    expect(shares).not.toContain(0);
  });

  it("a point with an evaluated result as well is still drawn", () => {
    const w = load();
    const mixed = [
      unit("a", [entry("r1", "red"), entry("r2", "green"), entry("r3", "red")]),
      unit("b", [entry("r1", "green"), entry("r2", "green", true), entry("r3", "green")]),
    ];
    const series = w.unitCounts(mixed);
    expect(series.map((p) => !!p.notEvaluated)).toEqual([false, false, false]);
    expect(redShares(w.twoLineSparkline(series, { w: 120, h: 28 }))).toContain(0);
  });
});
