// REQ-DASH-225 criterion 17: the dataset list's 'Columns not green' cell -
// the count, its red/amber line and the two trend lines. Written first.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});
const load = () => (dashboard = loadDashboard()).window;

const d = (iso) => new Date(iso + "T00:00:00Z");
const DATES = { r1: "2026-01-01", r2: "2026-02-01" };
const unit = (name, byRun, scope) => ({
  name, scope,
  checks: [{ history: Object.entries(byRun).map(([run_id, status]) => ({ run_id, date: d(DATES[run_id]), status })) }],
});
const text = (w, html) => {
  const el = w.document.createElement("div");
  el.innerHTML = html;
  return el.textContent.replace(/\s+/g, " ").trim();
};

describe("the Columns not green cell", () => {
  it("names a red supply-level section as one red column", () => {
    const w = load();
    const units = [
      unit("Supply-level checks", { r1: "green", r2: "red" }, "supply"),
      unit("a", { r1: "green", r2: "green" }),
      unit("b", { r1: "green", r2: "green" }),
    ];
    const t = text(w, w.columnsNotGreenCell(units));
    expect(t).toContain("1 of 3");
    expect(t).toContain("1 red, 0 amber · incl. Supply-level checks");
  });

  it("reads 'All M green' rather than a bare 0", () => {
    const w = load();
    const t = text(w, w.columnsNotGreenCell([unit("a", { r1: "green", r2: "green" }), unit("b", { r2: "green" })]));
    expect(t).toContain("All 2 green");
    expect(t).not.toMatch(/\b0 of\b/);
  });

  it("draws the two lines at the shares the counter returns, on a fixed 0-100% scale", () => {
    const w = load();
    const units = [
      unit("a", { r1: "red", r2: "amber" }),
      unit("b", { r1: "green", r2: "amber" }),
      unit("c", { r1: "green", r2: "green" }),
      unit("e", { r1: "green", r2: "green" }),
    ];
    const html = w.columnsNotGreenCell(units);
    const svg = html.match(/<svg[\s\S]*<\/svg>/)[0];
    const h = Number(svg.match(/viewBox="0 0 \d+ (\d+)"/)[1]);
    const ys = (series) => [...svg.matchAll(new RegExp(`<path d="([^"]+)"[^>]*data-series="${series}"`, "g"))]
      .flatMap((m) => [...m[1].matchAll(/[ML][\d.]+,([\d.]+)/g)].map((p) => +((h - 2 - Number(p[1])) / (h - 4)).toFixed(3)));
    expect(ys("red")).toEqual([0.25, 0]);   // 1 of 4 red, then none
    expect(ys("amber")).toEqual([0, 0.5]);  // none, then 2 of 4 amber
  });

  it("draws no red or amber stroke for a history green on every run", () => {
    const w = load();
    const html = w.columnsNotGreenCell([unit("a", { r1: "green", r2: "green" })]);
    expect(html).not.toContain("var(--bad)");
    expect(html).not.toContain("var(--warn-fill)");
  });

  it("on a date with nothing in the current period, says so and draws the history neutral", () => {
    const w = load();
    const html = w.columnsNotGreenCell([unit("a", { r1: "red", r2: "amber" })], undefined, true);
    expect(text(w, html)).toBe("No column has a verdict on this date");
    expect(html).toContain('data-series="red"');
    expect(html).not.toContain("var(--bad)");
    expect(html).not.toContain("var(--warn-fill)");
  });

  it("says when no column has a verdict, and when there is one run so far", () => {
    const w = load();
    expect(text(w, w.columnsNotGreenCell([unit("a", { r1: "inactive" })])))
      .toBe("No column has a verdict on this date");
    expect(text(w, w.columnsNotGreenCell([unit("a", { r2: "green" })]))).toContain("One QA run so far");
  });
});
