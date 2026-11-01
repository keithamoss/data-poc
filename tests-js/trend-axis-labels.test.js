// REQ-DASH-359 criterion 18 (plans/post-build-review.md #289 D8d): a trend's
// dated x-axis labels never overprint one another. Both labelled trends - a
// check's own (its panel, on the dataset page and from the column grid) and
// the unit trend (the dataset page's columns and a column's checks) - draw
// in a viewBox, so a phone and a desktop see the same layout in the chart's
// units, and a label's extent there is its length at 0.6em a character in
// the monospaced axis font.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => (dashboard = loadDashboard()).window;

// Each drawn x label's [left, right] in the chart's units.
function extents(svg) {
  return [...svg.matchAll(/<text x="([\d.]+)"[^>]*font-size="([\d.]+)" text-anchor="(\w+)"[^>]*data-x-label>([^<]+)</g)]
    .map(([, x, size, anchor, label]) => {
      const w = label.length * 0.6 * Number(size), at = Number(x);
      return anchor === "start" ? [at, at + w] : anchor === "end" ? [at - w, at] : [at - w / 2, at + w / 2];
    });
}
function overprint(list) {
  for (let i = 0; i < list.length; i++)
    for (let j = i + 1; j < list.length; j++)
      if (list[i][0] < list[j][1] && list[j][0] < list[i][1]) return [list[i], list[j]];
  return null;
}

const day = (i) => new Date(Date.UTC(2026, 8, 30 + i * 3));

describe("a trend's dated x-axis labels", () => {
  it("never overprint on a check's own trend, at any number of runs", () => {
    const w = load();
    for (let n = 1; n <= 12; n++) {
      const history = Array.from({ length: n }, (_, i) => ({ run_id: `r${i}`, run_date: day(i).toISOString().slice(0, 10),
        date: day(i), value: i, status: "green", not_evaluated: null }));
      const svg = w.trendChart({ history, warn: 5, fail: 10, unit: "count", changelog: [] }, null, null, null);
      const got = extents(svg);
      expect(got.length, `n=${n}`).toBeGreaterThan(0);
      expect(overprint(got), `n=${n}`).toBeNull();
    }
  });

  it("never overprint on a unit trend, at any number of runs", () => {
    const w = load();
    for (let n = 1; n <= 12; n++) {
      const series = Array.from({ length: n }, (_, i) => ({ runId: `r${i}`, date: day(i), counted: 3, red: 1, amber: 0, sectionNames: [] }));
      const html = w.unitTrendBlock(series, { kind: "dataset", title: "t", yTitle: "% of columns", unitWord: "Columns", noun: "column" });
      const got = extents(html);
      expect(got.length, `n=${n}`).toBeGreaterThan(0);
      expect(overprint(got), `n=${n}`).toBeNull();
    }
  });

  it("always show the last date", () => {
    const w = load();
    const history = [0, 1].map((i) => ({ run_id: `r${i}`, run_date: day(i).toISOString().slice(0, 10), date: day(i),
      value: i, status: "green", not_evaluated: null }));
    const svg = w.trendChart({ history, warn: 5, fail: 10, unit: "count", changelog: [] }, null, null, null);
    expect(svg).toContain(`>${w.shortDay(day(1))}</text>`);
  });
});
