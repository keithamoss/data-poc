// computeChangeMarkers: where a check's changelog entries break its trend.
// A FUTURE-DATED ENTRY DRAWS NOTHING (post-build-review #305): REQ-QAC-300's
// census-year widenings declare their changes ahead of time (2027-08-01 for
// the 2026 census), and the "entry postdates the last known run" fallback put
// one on the newest point, drawing a third break between two runs on the
// same definition. An entry after the date on show has not happened yet.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

const day = (s) => new Date(`${s}T00:00:00Z`);
const history = ["2022-05-01", "2022-08-01", "2026-05-01", "2026-08-01"].map((d) => ({ date: day(d) }));
const entry = (d) => ({ date: day(d), description: "widened", author: "x", breaking: true });

describe("computeChangeMarkers", () => {
  it("marks the first run on or after a past entry", () => {
    dashboard = loadDashboard();
    const m = dashboard.window.computeChangeMarkers(history, [entry("2022-08-01")], "2026-11-02");
    expect(Object.keys(m)).toEqual(["1"]);
  });

  it("draws nothing for an entry dated after the date on show", () => {
    dashboard = loadDashboard();
    const m = dashboard.window.computeChangeMarkers(history, [entry("2027-08-01")], "2026-11-02");
    expect(Object.keys(m)).toEqual([]);
  });

  it("still marks the newest run for an entry after it but on or before the date on show", () => {
    dashboard = loadDashboard();
    const m = dashboard.window.computeChangeMarkers(history, [entry("2026-09-01")], "2026-11-02");
    expect(Object.keys(m)).toEqual(["3"]);
  });
});
