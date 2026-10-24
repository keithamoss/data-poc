// A run whose check COULD NOT BE EVALUATED (plans/post-build-review.md
// #77, gap 1). The table it reads was missing, held or contested, so
// there is no value - and the trend chart used to draw it as ZERO, the
// "nothing wrong" end of the axis. It must read as a gap, marked red and
// labelled, never as a value.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

function check(lastNotEvaluated) {
  const day = (d) => ({ run_date: `2026-0${d}-01`, date: new Date(`2026-0${d}-01`) });
  const history = [
    { ...day(1), run_id: "r1", value: 3, status: "green", not_evaluated: null },
    { ...day(2), run_id: "r2", value: 4, status: "green", not_evaluated: null },
    { ...day(3), run_id: "r3", value: lastNotEvaluated ? null : 5, status: lastNotEvaluated ? "red" : "green",
      not_evaluated: lastNotEvaluated ? "cp_clients has no filled slot in this period" : null },
  ];
  return { history, warn: 5, fail: 10, unit: "count", changelog: [] };
}

describe("a run that could not be evaluated", () => {
  it("is recognised only by its recorded reason", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    expect(w.notEvaluated({ not_evaluated: "held" })).toBe(true);
    expect(w.notEvaluated({ not_evaluated: null, value: 0 })).toBe(false);
    expect(w.notEvaluated(undefined)).toBe(false);
  });

  it("is labelled on the chart and never plotted as a value", () => {
    dashboard = loadDashboard();
    const svg = dashboard.window.trendChart(check(true), 1, null, null);
    expect(svg).toContain("Not evaluated");
    expect(svg).toContain("not-evaluated-mark");
    // The line reaches only the two evaluated runs: one segment, two points.
    const d = svg.match(/<path d="([^"]*)"/)[1].trim();
    expect(d.split(/(?=[ML])/).filter(Boolean)).toHaveLength(2);
  });

  it("leaves an evaluated latest run drawn exactly as before", () => {
    dashboard = loadDashboard();
    const svg = dashboard.window.trendChart(check(false), 1, null, null);
    expect(svg).not.toContain("Not evaluated");
    const d = svg.match(/<path d="([^"]*)"/)[1].trim();
    expect(d.split(/(?=[ML])/).filter(Boolean)).toHaveLength(3);
  });
});
