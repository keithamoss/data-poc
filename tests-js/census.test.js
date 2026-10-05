// REQ-PIPE-081 criteria 14 and 15: the census as at the date on show is the
// last RECORDED census on or before it, and a disagreement is said
// prominently, naming the period and the table.
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

const ds = {
  census: [
    { takenAt: "2026-10-01T02:00:00+00:00", discrepancies: [] },
    { takenAt: "2026-10-03T02:00:00+00:00", discrepancies: [
      { kind: "missing", period: "2026-Q3", datasetId: "cp-carers", table: "cp_carers",
        supply: "cp-carers@1", detail: "the decision log says 2026-Q3 holds cp_carers" } ] },
    { takenAt: "2026-10-04T02:00:00+00:00", discrepancies: [] },
  ],
};

describe("the census as at a date", () => {
  it("reads the last census on or before the date, never a later one", () => {
    const w = load();
    expect(w.censusAsOf(ds, "2026-09-30")).toBe(null);
    expect(w.censusAsOf(ds, "2026-10-03").discrepancies).toHaveLength(1);
    expect(w.censusAsOf(ds, "2026-10-05").discrepancies).toHaveLength(0);
  });

  it("names the period and the table, and says nothing when they agree", () => {
    const w = load();
    const html = w.censusBanner(ds, "2026-10-03");
    expect(html).toContain("data-census");
    expect(html).toContain("2026-Q3");
    expect(html).toContain("cp_carers");
    expect(w.censusBanner(ds, "2026-10-04")).toBe("");
    expect(w.censusBanner({}, "2026-10-04")).toBe("");
  });
});

describe("the census date is the asset's", () => {
  it("counts a census taken at 22:00 UTC as the next Perth day (#113)", () => {
    dashboard = loadDashboard({ assetTimezone: "Australia/Perth" });
    const w = dashboard.window;
    const late = { census: [{ takenAt: "2026-10-05T22:00:00+00:00", discrepancies: [
      { kind: "stray", period: "p", datasetId: null, table: "t", supply: null, detail: "d" }] }] };
    expect(w.censusAsOf(late, "2026-10-05")).toBe(null);
    expect(w.censusAsOf(late, "2026-10-06")).not.toBe(null);
  });
});
