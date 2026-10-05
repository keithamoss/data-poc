// REQ-PIPE-081 criteria 1, 2 and 8 as amended 2026-10-05 (Keith): the
// dataset's verdict is the newest supply PROMOTED or AWAITING A DECISION
// on the date on show - a withdrawn one leaves the view - labelled which.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const RUNS = [{run_id: "r1", run_date: "2026-01-10"}, {run_id: "r2", run_date: "2026-02-10"}];
const dataset = runStates => ({id: "cp-carers", runs: RUNS, columns: [], runStates});

describe("a run's supply on the date on show", () => {
  it("is awaiting before any decision, then whatever the last decision said", () => {
    const w = loadDashboard().window;
    const d = dataset({r1: [{at: "2026-01-20T01:00:00+00:00", state: "promoted"}]});
    expect(w.runStateAsOf(d, "r1", "2026-01-15")).toBe("awaiting");
    expect(w.runStateAsOf(d, "r1", "2026-01-20")).toBe("promoted");
  });
});

describe("the verdict's supply", () => {
  it("skips a newer supply withdrawn by the date on show", () => {
    const w = loadDashboard().window;
    const d = dataset({r1: [{at: "2026-01-20T01:00:00+00:00", state: "promoted"}],
                       r2: [{at: "2026-02-12T01:00:00+00:00", state: "withdrawn"}]});
    const clipped = w.clipDatasetToAsOf(d, "2026-02-20");
    expect(clipped.runs.map(r=>r.run_id)).toEqual(["r1"]);
    expect(clipped.verdictOf.state).toBe("promoted");
  });

  it("shows a newer supply still awaiting, naming the one in place", () => {
    const w = loadDashboard().window;
    const d = dataset({r1: [{at: "2026-01-20T01:00:00+00:00", state: "promoted"}]});
    const clipped = w.clipDatasetToAsOf(d, "2026-02-20");
    expect(clipped.runs.map(r=>r.run_id)).toEqual(["r1", "r2"]);
    expect(clipped.verdictOf).toEqual({state: "awaiting", inPlaceRunDate: "2026-01-10"});
  });

  it("before the withdrawal the newer supply was the verdict", () => {
    const w = loadDashboard().window;
    const d = dataset({r2: [{at: "2026-02-12T01:00:00+00:00", state: "withdrawn"}]});
    expect(w.clipDatasetToAsOf(d, "2026-02-11").runs.map(r=>r.run_id)).toEqual(["r1", "r2"]);
  });
});
