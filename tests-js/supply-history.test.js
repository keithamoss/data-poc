// Supply-history grouping: buildSupplyHistory()/rowCountAtRun() - Phase
// 5j Stage 2's "a final view of how the refresh period went" (module
// comment) - groups a dataset's real run history by cadence cycle, newest
// cycle first, each cycle's own entries newest-attempt-first, resupply
// attempts NOT nested under their parent delivery (Keith's own confirmed
// answer, quoted in buildSupplyHistory()'s own comment).
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

function dailyDataset(runs, arrivalByRun = {}) {
  return {
    sla: { cadence: { type: "daily", expected_time: "14:00" } },
    runs,
    arrivalByRun,
    columns: [],
  };
}

describe("buildSupplyHistory", () => {
  it("groups daily runs one cycle per run, newest cycle first", () => {
    const w = load();
    const d = dailyDataset([
      { run_id: "r1", run_date: "2026-01-01" },
      { run_id: "r2", run_date: "2026-01-02" },
      { run_id: "r3", run_date: "2026-01-03" },
    ]);

    const history = w.buildSupplyHistory(d);

    expect(history.map((c) => c.cycleStart)).toEqual(["2026-01-03", "2026-01-02", "2026-01-01"]);
    expect(history.every((c) => c.entries.length === 1)).toBe(true);
  });

  it("groups multiple runs into the SAME weekly cycle, newest run first within it", () => {
    const w = load();
    const d = {
      sla: { cadence: { type: "weekly", weekday: 0, expected_time: "09:00" } },
      // 2026-03-16 is a Monday (this cadence's anchor weekday); 03-17/03-18
      // fall in the same week, all sharing cycleStart 2026-03-16
      runs: [
        { run_id: "r1", run_date: "2026-03-16" },
        { run_id: "r2", run_date: "2026-03-17" },
        { run_id: "r3", run_date: "2026-03-18" },
      ],
      arrivalByRun: {},
      columns: [],
    };

    const history = w.buildSupplyHistory(d);

    expect(history).toHaveLength(1);
    expect(history[0].cycleStart).toBe("2026-03-16");
    expect(history[0].entries.map((e) => e.run_id)).toEqual(["r3", "r2", "r1"]);
  });

  it("carries each run's own arrival status/rowCount/resupply metadata through into its entry", () => {
    const w = load();
    const d = dailyDataset(
      [{ run_id: "r1", run_date: "2026-01-01", is_resupply: true, attempt_number: 2, dirty_severity: "amber" }],
      { r1: { arrivalStatus: "late", arrivedAt: "16:30 AWST" } },
    );
    d.columns = [{ stats: { byRun: { r1: { total: 4321 } } } }];

    const [{ entries }] = w.buildSupplyHistory(d);

    expect(entries).toEqual([
      {
        run_id: "r1", run_date: "2026-01-01",
        arrivalStatus: "late", arrivedAt: "16:30 AWST",
        rowCount: 4321, isResupply: true, attemptNumber: 2, dirtySeverity: "amber",
      },
    ]);
  });

  it("a resupply attempt is its own entry in its cycle, not nested under the original delivery", () => {
    const w = load();
    const d = dailyDataset([
      { run_id: "r1", run_date: "2026-01-01", is_resupply: false, attempt_number: 1 },
      { run_id: "r1-resupply2", run_date: "2026-01-01", is_resupply: true, attempt_number: 2 },
    ]);

    const [{ entries }] = w.buildSupplyHistory(d);

    // same run_date (same cycle, daily) -> two independent, sibling
    // entries, not one entry with a nested list
    expect(entries).toHaveLength(2);
    expect(entries.map((e) => e.isResupply)).toEqual([true, false]);
  });

  it("returns [] for a dataset with no real runs", () => {
    const w = load();
    expect(w.buildSupplyHistory(dailyDataset([]))).toEqual([]);
  });
});

describe("rowCountAtRun", () => {
  it("returns the row count from the first column whose byRun covers this run", () => {
    const w = load();
    const d = { columns: [{ stats: { byRun: {} } }, { stats: { byRun: { r1: { total: 42 } } } }] };
    expect(w.rowCountAtRun(d, "r1")).toBe(42);
  });

  it("returns null when no column's byRun covers this run", () => {
    const w = load();
    const d = { columns: [{ stats: { byRun: {} } }] };
    expect(w.rowCountAtRun(d, "r1")).toBeNull();
  });
});
