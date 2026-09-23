// Supply-history chain derivation: buildSupplyHistory()/datasetStatusByRun()/
// rowCountAtRun() - Phase 5j Stage 2's "a final view of how the refresh
// period went" (module comment), REDESIGNED Phase 7 (2026-09-17,
// plans/conceptual-design.md Thread A): chain membership is derived purely
// from cadence (cycleStartDate, only to anchor where a NEW chain starts)
// and each arrival's own real aggregate red/amber/green status (the worst
// status among every check's own history[] value vs its warn/fail
// thresholds) - never from the generator's synthetic is_resupply/
// supersedes_run_id/attempt_number bookkeeping, which REQ-GEN-042 has
// since retired from the generator outright, and which a real
// production dashboard would never have. A RED arrival starts/continues a
// chain; the chain closes on the first AMBER or GREEN after a RED (Keith's
// own "keep it simple" rule).
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

// Builds a dataset with exactly one check, whose history gives it the
// requested status (green/amber/red) on each run in `statuses` (an
// ordered [run_id, run_date, status] list). warn=1, fail=2, values chosen
// so 0 -> green, 1.5 -> amber, 3 -> red.
const VALUE_FOR_STATUS = { green: 0, amber: 1.5, red: 3 };
function datasetWithStatuses(entries, cadence = { type: "daily", expected_time: "14:00" }, arrivalByRun = {}) {
  const history = entries.map(([run_id, run_date, status]) => ({
    run_id, run_date, value: VALUE_FOR_STATUS[status],
  }));
  return {
    sla: { cadence },
    runs: entries.map(([run_id, run_date]) => ({ run_id, run_date })),
    arrivalByRun,
    columns: [{ checks: [{ warn: 1, fail: 2, history }] }],
  };
}

describe("datasetStatusByRun", () => {
  it("returns the worst status among every check that has a result for that run", () => {
    const w = load();
    const d = {
      columns: [
        { checks: [{ warn: 1, fail: 2, history: [{ run_id: "r1", value: 0 }] }] },
        { checks: [{ warn: 1, fail: 2, history: [{ run_id: "r1", value: 3 }] }] },
      ],
    };
    const byRun = w.datasetStatusByRun(d);
    expect(byRun.get("r1")).toBe("red");
  });

  it("a run with no check history at all is absent from the map", () => {
    const w = load();
    const d = { columns: [{ checks: [{ warn: 1, fail: 2, history: [] }] }] };
    expect(w.datasetStatusByRun(d).has("r1")).toBe(false);
  });
});

describe("buildSupplyHistory", () => {
  it("groups daily runs one cycle per run when every arrival is green, newest cycle first", () => {
    const w = load();
    const d = datasetWithStatuses([
      ["r1", "2026-01-01", "green"],
      ["r2", "2026-01-02", "green"],
      ["r3", "2026-01-03", "green"],
    ]);

    const history = w.buildSupplyHistory(d);

    expect(history.map((c) => c.cycleStart)).toEqual(["2026-01-03", "2026-01-02", "2026-01-01"]);
    expect(history.every((c) => c.entries.length === 1)).toBe(true);
    expect(history.every((c) => c.entries[0].isResupply === false)).toBe(true);
  });

  it("a RED arrival starts an open chain that a later AMBER closes - both land in the SAME group, anchored at the red arrival's own cycle", () => {
    const w = load();
    const d = datasetWithStatuses([
      ["r1", "2026-01-01", "red"],
      ["r2", "2026-01-02", "amber"],
    ]);

    const history = w.buildSupplyHistory(d);

    expect(history).toHaveLength(1);
    expect(history[0].cycleStart).toBe("2026-01-01");
    expect(history[0].entries.map((e) => e.run_id)).toEqual(["r2", "r1"]); // newest first
    expect(history[0].entries.map((e) => e.isResupply)).toEqual([true, false]);
  });

  it("a RED arrival stays open through further REDs and closes on the first GREEN", () => {
    const w = load();
    const d = datasetWithStatuses([
      ["r1", "2026-01-01", "red"],
      ["r2", "2026-01-03", "red"],
      ["r3", "2026-01-09", "red"],
      ["r4", "2026-01-10", "green"],
    ]);

    const history = w.buildSupplyHistory(d);

    expect(history).toHaveLength(1);
    expect(history[0].entries.map((e) => e.run_id)).toEqual(["r4", "r3", "r2", "r1"]);
    expect(history[0].entries.map((e) => e.attemptNumber)).toEqual([4, 3, 2, 1]);
  });

  it("keep it simple (Keith's own rule): AMBER closes a chain exactly like GREEN does - a run right after does NOT join it", () => {
    const w = load();
    const d = datasetWithStatuses([
      ["r1", "2026-01-01", "red"],
      ["r2", "2026-01-02", "amber"], // closes the chain
      ["r3", "2026-01-03", "green"], // a fresh, unrelated arrival
    ]);

    const history = w.buildSupplyHistory(d);

    expect(history).toHaveLength(2);
    const jan1 = history.find((c) => c.cycleStart === "2026-01-01");
    const jan3 = history.find((c) => c.cycleStart === "2026-01-03");
    expect(jan1.entries.map((e) => e.run_id)).toEqual(["r2", "r1"]);
    expect(jan3.entries.map((e) => e.run_id)).toEqual(["r3"]);
  });

  it("a RED arrival right after a closed chain starts a genuinely NEW chain, not a continuation", () => {
    const w = load();
    const d = datasetWithStatuses([
      ["r1", "2026-01-01", "red"],
      ["r2", "2026-01-02", "green"], // closes chain 1
      ["r3", "2026-01-05", "red"], // starts chain 2
      ["r4", "2026-01-06", "green"], // closes chain 2
    ]);

    const history = w.buildSupplyHistory(d);

    expect(history).toHaveLength(2);
    expect(history.map((c) => c.cycleStart)).toEqual(["2026-01-05", "2026-01-01"]);
    expect(history.find((c) => c.cycleStart === "2026-01-01").entries.map((e) => e.run_id)).toEqual(["r2", "r1"]);
    expect(history.find((c) => c.cycleStart === "2026-01-05").entries.map((e) => e.run_id)).toEqual(["r4", "r3"]);
  });

  it("carries the run's own real aggregate status onto its entry", () => {
    const w = load();
    const d = datasetWithStatuses([["r1", "2026-01-01", "amber"]]);
    const [{ entries }] = w.buildSupplyHistory(d);
    expect(entries[0].status).toBe("amber");
  });

  it("carries a non-resupply (chain-first) run's own arrival status/rowCount metadata through into its entry", () => {
    const w = load();
    const d = datasetWithStatuses(
      [["r1", "2026-01-01", "green"]],
      undefined,
      { r1: { arrivalStatus: "late", arrivedAt: "16:30 AWST" } },
    );
    d.columns[0].stats = { byRun: { r1: { total: 4321 } } };

    const [{ entries }] = w.buildSupplyHistory(d);

    expect(entries).toEqual([
      {
        run_id: "r1", run_date: "2026-01-01", status: "green",
        arrivalStatus: "late", arrivedAt: "16:30 AWST", daysSincePrevious: null,
        rowCount: 4321, isResupply: false, attemptNumber: 1,
      },
    ]);
  });

  it("a resupply (any entry after the first in its chain) carries NO real arrivalStatus (item 69's reasoning, now keyed off real chain position instead of a synthetic flag) but DOES carry rowCount", () => {
    const w = load();
    const d = datasetWithStatuses(
      [
        ["r1", "2026-01-01", "red"],
        ["r2", "2026-01-02", "green"],
      ],
      undefined,
      { r1: { arrivalStatus: "onTime", arrivedAt: "10:00 AWST" }, r2: { arrivalStatus: "early", arrivedAt: "16:30 AWST" } },
    );
    d.columns[0].stats = { byRun: { r2: { total: 4321 } } };

    const [{ entries }] = w.buildSupplyHistory(d);
    const byId = Object.fromEntries(entries.map((e) => [e.run_id, e]));

    expect(byId.r1.arrivalStatus).toBe("onTime"); // chain-first entry keeps its real arrival status
    expect(byId.r2.arrivalStatus).toBeUndefined(); // resupply - category error, dropped
    expect(byId.r2.arrivedAt).toBeUndefined();
    expect(byId.r2.rowCount).toBe(4321);
  });

  it("a resupply's daysSincePrevious is measured against the previous entry in its OWN chain, walked chronologically", () => {
    const w = load();
    const d = datasetWithStatuses([
      ["original", "2026-01-01", "red"],
      ["resupply1", "2026-01-01", "red"],
      ["resupply2", "2026-01-05", "green"],
    ]);

    const [{ entries }] = w.buildSupplyHistory(d);
    const byId = Object.fromEntries(entries.map((e) => [e.run_id, e]));

    expect(byId.original.daysSincePrevious).toBeNull();
    expect(byId.resupply1.daysSincePrevious).toBe(0); // same run_date as the original
    expect(byId.resupply2.daysSincePrevious).toBe(4); // 2026-01-05 minus 2026-01-01
  });

  it("REGRESSION (Keith's own real bug report, 2026-09-17, re-expressed under the new model): an unrelated on-time GREEN delivery and a RED delivery's own resupply chain must never be lumped together just because they land on the same calendar day", () => {
    const w = load();
    const d = datasetWithStatuses([
      // an open chain from three weeks earlier, still unresolved
      ["late_chain_start", "2026-01-01", "red"],
      // the real, unrelated delivery actually scheduled for this later day
      ["todays_delivery", "2026-01-20", "green"],
    ]);
    // todays_delivery arrives AFTER the still-open chain chronologically,
    // so under the "continue while open" rule it would join that chain -
    // this is the real, correct behaviour now (a still-failing chain
    // absorbs whatever arrives next, whatever day it lands on), distinct
    // from the OLD bug (grouping purely by coincidental calendar date
    // regardless of real chain state). Assert that explicitly, and that
    // it closes the chain as its resolving arrival.
    const history = w.buildSupplyHistory(d);

    expect(history).toHaveLength(1);
    expect(history[0].cycleStart).toBe("2026-01-01");
    expect(history[0].entries.map((e) => e.run_id)).toEqual(["todays_delivery", "late_chain_start"]);
    expect(history[0].entries.map((e) => e.isResupply)).toEqual([true, false]);
  });

  it("a resupply attempt is its own entry in its chain, not nested under the original delivery", () => {
    const w = load();
    const d = datasetWithStatuses([
      ["r1", "2026-01-01", "red"],
      ["r1-resupply2", "2026-01-01", "green"],
    ]);

    const [{ entries }] = w.buildSupplyHistory(d);

    expect(entries).toHaveLength(2);
    expect(entries.map((e) => e.isResupply)).toEqual([true, false]);
  });

  it("returns [] for a dataset with no real runs", () => {
    const w = load();
    expect(w.buildSupplyHistory(datasetWithStatuses([]))).toEqual([]);
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
