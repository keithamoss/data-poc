// REQ-DASH-356 and REQ-DASH-367 on the page's own functions: under a chosen
// period a dataset is the supply that period holds, the dataset page says so,
// and the agencies list and agency page split into source supplies and derived
// releases, each rolled up on its own.
import { afterEach, describe, expect, it } from "vitest";
import { MINIMAL_HIERARCHY, loadDashboard } from "./support/loadDashboard.js";

let page;
afterEach(() => page && page.close());

const RUNS = [
  { run_id: "r1", run_date: "2025-11-01", received_at: "2025-11-01T01:00:00+00:00" },
  { run_id: "r2", run_date: "2026-02-01", received_at: "2026-02-01T01:00:00+00:00" },
];
const slot = (o) => ({ action: "promote", actor: "promotion rule", actor_kind: "rule",
                       reason: "passed", decision_id: 1, ...o });
const RAW = {
  id: "ds", runs: RUNS, columns: [],
  runStates: { r1: [{ at: "2025-11-02T01:00:00+00:00", state: "promoted" }],
               r2: [{ at: "2026-02-02T01:00:00+00:00", state: "promoted" }] },
  slotTimeline: [
    slot({ at: "2025-11-02T01:00:00+00:00", on: "2025-11-02", slot: "2025-Q4", held_as: "promoted",
           holder: "ds@1", holder_run_id: "r1" }),
    slot({ at: "2026-02-02T01:00:00+00:00", on: "2026-02-02", slot: "2026-Q1", held_as: "promoted",
           holder: "ds@2", holder_run_id: "r2" }),
  ],
};

describe("a dataset under a chosen period (REQ-DASH-356 criteria 1 to 3)", () => {
  it("is the supply the period holds, never the newest", () => {
    page = loadDashboard();
    const { row, clipped } = page.window.clipDatasetToPeriod(RAW, "2025-Q4", "2026-03-01");
    expect(row.kind).toBe("promoted");
    expect(clipped.onShowRun.run_id).toBe("r1");
    expect(clipped.runs.map((r) => r.run_id)).toEqual(["r1"]);
    expect(clipped.staleInPlaceOn).toBe(false);
  });

  it("is the period's own supply in the period it fills", () => {
    page = loadDashboard();
    const { clipped } = page.window.clipDatasetToPeriod(RAW, "2026-Q1", "2026-03-01");
    expect(clipped.onShowRun.run_id).toBe("r2");
  });

  it("holds nothing in a period with nothing in it, and says why", () => {
    page = loadDashboard();
    const { row, clipped } = page.window.clipDatasetToPeriod(RAW, "2026-Q2", "2026-06-01");
    expect(clipped).toBeNull();
    expect(row.kind).toBe("notsupplied");
  });

  it("is said on its page: 'For <P> · results recorded by <date>' and what it holds", () => {
    page = loadDashboard();
    const w = page.window;
    expect(w.periodHoldsWords({ kind: "promoted" })).toBe("Promoted");
    expect(w.periodHoldsWords({ kind: "inherited", from: "2025-Q4" })).toBe("Inherited from 2025-Q4");
    expect(w.periodHoldsWords({ kind: "substituted", from: "2025-Q4" })).toBe("Substituted from 2025-Q4");
    expect(w.periodHoldsWords({ kind: "notsupplied", word: "No supply" })).toBe("Not supplied"); // criterion 1's word (group D review F6)
    expect(w.periodHoldsWords({ kind: "notowed", label: "Not owed — it supplies only on Mondays" }))
      .toBe("Not owed — it supplies only on Mondays");
  });
});

describe("the two sections (REQ-DASH-356 criteria 4 and 5)", () => {
  const HIERARCHY = { agencies: [
    { id: "doh", name: "Health", collections: [
      { id: "ed", name: "Emergency Department", datasets: [{ id: "a", name: "A" }] },
      { id: "lp", name: "Linkage Products", derived: true, datasets: [{ id: "b", name: "B" }] } ] },
    { id: "cpfs", name: "Child Protection", collections: [
      { id: "cp", name: "Child Protection", datasets: [{ id: "c", name: "C" }] } ] } ] };
  const agencies = [
    { id: "doh", name: "Health", collections: [{ id: "ed", name: "Emergency Department", status: "green" },
                                               { id: "lp", name: "Linkage Products", status: "red" }] },
    { id: "cpfs", name: "Child Protection", collections: [{ id: "cp", name: "Child Protection", status: "amber" }] },
  ];

  it("puts source supplies first and the derived releases under their own names", () => {
    page = loadDashboard({ hierarchy: HIERARCHY });
    const w = page.window;
    w.eval('CURRENT_PERIOD = "2026-Q1"');
    const sections = w.periodSectionsOf(agencies);
    expect(sections.map((s) => s.heading)).toEqual(["Source supplies for 2026-Q1",
                                                    "Linkage Products for 2026-Q1"]);
    expect(sections[0].agencies.map((a) => a.id)).toEqual(["doh", "cpfs"]);
    expect(sections[1].agencies.map((a) => a.id)).toEqual(["doh"]);
  });

  it("rolls each agency card up from its section's collections alone", () => {
    page = loadDashboard({ hierarchy: HIERARCHY });
    const w = page.window;
    w.eval('CURRENT_PERIOD = "2026-Q1"');
    const [source, derived] = w.periodSectionsOf(agencies);
    expect(source.agencies[0].status).toBe("green");
    expect(derived.agencies[0].status).toBe("red");
  });

  it("shows no section, and no heading, that would hold nothing", () => {
    page = loadDashboard({ hierarchy: MINIMAL_HIERARCHY });
    const w = page.window;
    w.eval('CURRENT_PERIOD = "2026-Q1"');
    const sections = w.periodSectionsOf([{ id: "x", name: "X", collections: [{ id: "y", name: "Y", status: "green" }] }]);
    expect(sections.map((s) => s.key)).toEqual(["source"]);
  });
});


describe("the verdict line under a period (group D review, UX #4)", () => {
  const ds = { verdictOf: { state: "promoted" }, lastArrival: { arrivedAt: "2025-08-01T00:00:00+00:00" },
               blocked: null, noDataInPlaceOn: false, packageGatingOn: null };
  it("names the supply the period holds while a period is chosen", () => {
    page = loadDashboard();
    page.window.eval('CURRENT_PERIOD = "2026-Q2"');
    const text = page.window.verdictLine(ds);
    expect(text).toContain("The results below are the supply 2026-Q2 holds, received");
    expect(text).not.toContain("in place in the warehouse");
  });
  it("names the warehouse's supply with none chosen", () => {
    page = loadDashboard();
    page.window.eval("CURRENT_PERIOD = null");
    expect(page.window.verdictLine(ds)).toContain("the supply in place in the warehouse, received");
  });
});
