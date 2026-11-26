// REQ-DASH-224: one function decides how a column - or a check section
// counted as one - stands on each QA run, and every count and trend line
// of columns or checks is drawn from it. Written first, against the page
// as it stood after post-build-review #181.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});
const load = () => (dashboard = loadDashboard()).window;

const d = (iso) => new Date(iso + "T00:00:00Z");
// One check, one recorded verdict per run: {run_id: status}.
const check = (byRun, extra = {}) => ({
  history: Object.entries(byRun).map(([run_id, status]) => ({
    run_id, date: d(RUN_DATES[run_id]), status,
  })),
  ...extra,
});
const RUN_DATES = { r1: "2026-01-01", r2: "2026-02-01", r2b: "2026-02-01" };
const column = (name, ...checks) => ({ name, checks });

describe("unitCounts", () => {
  it("counts a column with one amber and one red check as one red column", () => {
    const w = load();
    const [run] = w.unitCounts([column("a", check({ r1: "amber" }), check({ r1: "red" }))]);
    expect([run.counted, run.red, run.amber]).toEqual([1, 1, 0]);
  });

  it("leaves out a column whose only check is inactive, and a run with nothing counted", () => {
    // Also post-build-review #181's rule, carried over when its function
    // went: a check not judged that run - inactive or nodata - is in
    // neither the count nor the total.
    const w = load();
    const series = w.unitCounts([
      column("a", check({ r1: "inactive", r2: "green" })),
      column("b", check({ r1: "nodata", r2: "inactive" })),
    ]);
    expect(series.map((p) => p.runId)).toEqual(["r2"]);
    expect(series[0].counted).toBe(1);
  });

  it("counts a supply-level section as one red unit, by its section heading", () => {
    const w = load();
    const [run] = w.unitCounts([
      { name: "Supply-level checks", scope: "supply", checks: [check({ r1: "red" }), check({ r1: "green" })] },
      column("a", check({ r1: "green" })),
    ]);
    expect([run.counted, run.red, run.amber]).toEqual([2, 1, 0]);
    expect(run.sectionNames).toEqual(["Supply-level checks"]);
  });

  it("returns counted, red and amber for a run with one of each", () => {
    const w = load();
    const [run] = w.unitCounts([
      column("a", check({ r1: "red" })),
      column("b", check({ r1: "amber" })),
      column("c", check({ r1: "green" })),
    ]);
    expect([run.counted, run.red, run.amber]).toEqual([3, 1, 1]);
  });

  it("keys points by run, so two runs on one day stay two points", () => {
    const w = load();
    const series = w.unitCounts([column("a", check({ r2: "red", r2b: "green" }))]);
    expect(series.map((p) => p.runId)).toEqual(["r2", "r2b"]);
  });

  it("leaves retired checks out of every point", () => {
    const w = load();
    const [run] = w.unitCounts([column("a", check({ r1: "red" }, { retired: true }), check({ r1: "green" }))]);
    expect(run.red).toBe(0);
  });

  it("refuses a status it does not recognise rather than counting it", () => {
    const w = load();
    expect(() => w.unitCounts([column("a", check({ r1: "purple" }))])).toThrow(/unrecognised status/);
  });
});

// Criterion 10's behavioural case, through the row's own drawing entry
// point rather than the new function by name.
describe("the dataset list row's trend", () => {
  const share = (svg, colour) => {
    // Every coordinate pair of the paths stroked in `colour`, as a share
    // of the plot height: 0 at the baseline, 1 at the top.
    const box = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
    const h = Number(box[2]);
    const pad = 2;
    const paths = [...svg.matchAll(/<path d="([^"]+)"[^>]*stroke="([^"]+)"/g)]
      .filter((m) => m[2] === colour);
    return paths.flatMap((m) => [...m[1].matchAll(/[ML]([\d.]+),([\d.]+)/g)]
      .map((p) => +((h - pad - Number(p[2])) / (h - 2 * pad)).toFixed(3)));
  };

  it("draws red at 50% and no amber for one red column beside one green", () => {
    const w = load();
    const cols = [
      column("a", check({ r1: "amber", r2: "amber" }), check({ r1: "red", r2: "red" })),
      column("b", check({ r1: "green", r2: "green" })),
    ];
    const svg = w.aggregateSparkline(cols);
    const red = share(svg, "var(--bad)");
    expect(red.length).toBeGreaterThan(0);
    expect(red.every((v) => v === 0.5)).toBe(true);
    expect(share(svg, "var(--warn-fill)")).toEqual([]);
  });
});
