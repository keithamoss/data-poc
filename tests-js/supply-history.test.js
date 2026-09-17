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

  it("carries a non-resupply run's own arrival status/rowCount metadata through into its entry", () => {
    const w = load();
    const d = dailyDataset(
      [{ run_id: "r1", run_date: "2026-01-01", is_resupply: false, attempt_number: 1, dirty_severity: "amber" }],
      { r1: { arrivalStatus: "late", arrivedAt: "16:30 AWST" } },
    );
    d.columns = [{ stats: { byRun: { r1: { total: 4321 } } } }];

    const [{ entries }] = w.buildSupplyHistory(d);

    expect(entries).toEqual([
      {
        run_id: "r1", run_date: "2026-01-01",
        arrivalStatus: "late", arrivedAt: "16:30 AWST", daysSincePrevious: null,
        rowCount: 4321, isResupply: false, attemptNumber: 1, dirtySeverity: "amber",
      },
    ]);
  });

  it("a resupply carries NO arrivalStatus (item 69 - a resupply reuses its original extract_timestamp, so early/late against its own arrival cycle is a category error, not a real fact) but DOES carry rowCount/dirtySeverity", () => {
    const w = load();
    const d = dailyDataset(
      [{ run_id: "r1", run_date: "2026-01-01", is_resupply: true, attempt_number: 2, dirty_severity: "amber" }],
      { r1: { arrivalStatus: "early", arrivedAt: "16:30 AWST" } },
    );
    d.columns = [{ stats: { byRun: { r1: { total: 4321 } } } }];

    const [{ entries }] = w.buildSupplyHistory(d);

    expect(entries[0].arrivalStatus).toBeUndefined();
    expect(entries[0].arrivedAt).toBeUndefined();
    expect(entries[0].rowCount).toBe(4321);
    expect(entries[0].dirtySeverity).toBe("amber");
  });

  it("a resupply's daysSincePrevious is measured against the run it supersedes, via supersedes_run_id", () => {
    const w = load();
    // delivery_date pinned to the same cycle for all three (a resupply's
    // own delivery_date always matches its original delivery - only
    // run_date/arrived_date differ), so this test exercises daysSince
    // Previous in isolation from the delivery_date-grouping behaviour
    // the regression test below covers separately.
    const d = dailyDataset([
      { run_id: "original", run_date: "2026-01-01", delivery_date: "2026-01-01", is_resupply: false, attempt_number: 1 },
      { run_id: "resupply1", run_date: "2026-01-01", delivery_date: "2026-01-01", is_resupply: true, attempt_number: 2, supersedes_run_id: "original" },
      { run_id: "resupply2", run_date: "2026-01-05", delivery_date: "2026-01-01", is_resupply: true, attempt_number: 3, supersedes_run_id: "resupply1" },
    ]);

    const [{ entries }] = w.buildSupplyHistory(d);
    const byId = Object.fromEntries(entries.map((e) => [e.run_id, e]));

    expect(byId.original.daysSincePrevious).toBeNull();
    expect(byId.resupply1.daysSincePrevious).toBe(0); // same run_date as the original it supersedes
    expect(byId.resupply2.daysSincePrevious).toBe(4); // 2026-01-05 minus 2026-01-01
  });

  it("REGRESSION (Keith's own real bug report, 2026-09-17): a resupply that lands weeks late on some OTHER cycle's own delivery day groups under its OWN delivery's cycle, not the arrival day's cycle - a resupply landing on the same calendar day as a completely unrelated delivery must never be lumped into that delivery's own group", () => {
    const w = load();
    const d = dailyDataset([
      // the real, unrelated delivery that's actually scheduled for this day
      { run_id: "todays_delivery", run_date: "2026-01-20", delivery_date: "2026-01-20", is_resupply: false, attempt_number: 1 },
      // a resupply for a delivery originally due three weeks earlier, whose
      // real arrival happens to land on the exact same calendar day
      { run_id: "late_resupply", run_date: "2026-01-20", delivery_date: "2026-01-01", is_resupply: true, attempt_number: 2 },
    ]);

    const history = w.buildSupplyHistory(d);

    const jan20 = history.find((c) => c.cycleStart === "2026-01-20");
    const jan1 = history.find((c) => c.cycleStart === "2026-01-01");
    expect(jan20.entries.map((e) => e.run_id)).toEqual(["todays_delivery"]);
    expect(jan1.entries.map((e) => e.run_id)).toEqual(["late_resupply"]);
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
