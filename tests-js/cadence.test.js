// Cadence math: cadenceLabel/cycleStartDate/cycleLabel/addDaysToDateStr -
// the dashboard's own JS-side mirror of pipeline/cadence.py's cycle_start()
// (see cycleStartDate()'s own comment on why that pairing exists: the
// server-side Python only ever needs to know a run's OWN cycle, the
// client-side JS also needs "what cycle does an arbitrary as-of date fall
// in", so both exist and must agree).
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

describe("cadenceLabel", () => {
  it("labels a daily cadence", () => {
    const w = load();
    expect(w.cadenceLabel({ type: "daily", expected_time: "14:00" })).toBe("Daily, by 14:00 AWST");
  });

  it("labels a weekly cadence with the real weekday name", () => {
    const w = load();
    expect(w.cadenceLabel({ type: "weekly", weekday: 2, expected_time: "09:00" })).toBe("Weekly (Wed), by 09:00 AWST");
  });

  it("labels a quarterly cadence with real month names and day", () => {
    const w = load();
    const label = w.cadenceLabel({ type: "quarterly", anchor_months: [1, 4, 7, 10], day_of_month: 15, expected_time: "17:00" });
    expect(label).toBe("Quarterly (Jan/Apr/Jul/Oct, day 15), by 17:00 AWST");
  });
});

describe("cycleStartDate", () => {
  it("a daily cadence's own cycle start is the run date itself", () => {
    const w = load();
    expect(w.cycleStartDate({ type: "daily" }, "2026-03-15")).toBe("2026-03-15");
  });

  it("a weekly cadence's cycle start is the most recent occurrence of its weekday, at or before the date", () => {
    const w = load();
    // weekday 0 = Monday (Python date.weekday() convention, per the
    // function's own comment) - 2026-03-18 is a Wednesday, so the most
    // recent Monday on/before it is 2026-03-16.
    expect(w.cycleStartDate({ type: "weekly", weekday: 0 }, "2026-03-18")).toBe("2026-03-16");
  });

  it("a weekly cadence's cycle start is the date itself when the date IS the anchor weekday", () => {
    const w = load();
    expect(w.cycleStartDate({ type: "weekly", weekday: 0 }, "2026-03-16")).toBe("2026-03-16");
  });

  it("a quarterly cadence's cycle start is the latest anchor on/before the date", () => {
    const w = load();
    const cadence = { type: "quarterly", anchor_months: [1, 4, 7, 10], day_of_month: 15 };
    expect(w.cycleStartDate(cadence, "2026-05-01")).toBe("2026-04-15");
  });

  it("a quarterly cadence rolls back into the PREVIOUS year when the date is before this year's first anchor", () => {
    const w = load();
    const cadence = { type: "quarterly", anchor_months: [1, 4, 7, 10], day_of_month: 15 };
    expect(w.cycleStartDate(cadence, "2026-01-10")).toBe("2025-10-15");
  });

  it("throws on an unknown cadence type rather than silently misclassifying a real run", () => {
    const w = load();
    expect(() => w.cycleStartDate({ type: "fortnightly" }, "2026-01-01")).toThrow(/unknown cadence type/);
  });
});

describe("cycleLabel", () => {
  it("a daily cycle's label is just the date", () => {
    const w = load();
    expect(w.cycleLabel({ type: "daily" }, "2026-03-15")).toBe(w.fmtDate(new Date("2026-03-15T00:00:00Z")));
  });

  it("a weekly cycle's label is prefixed 'Week of'", () => {
    const w = load();
    expect(w.cycleLabel({ type: "weekly" }, "2026-03-16")).toBe(`Week of ${w.fmtDate(new Date("2026-03-16T00:00:00Z"))}`);
  });

  it("a quarterly cycle's label is prefixed 'Cycle starting'", () => {
    const w = load();
    expect(w.cycleLabel({ type: "quarterly" }, "2026-04-15")).toBe(`Cycle starting ${w.fmtDate(new Date("2026-04-15T00:00:00Z"))}`);
  });
});

describe("addDaysToDateStr", () => {
  it("adds real calendar days, crossing a month boundary", () => {
    const w = load();
    expect(w.addDaysToDateStr("2026-01-30", 3)).toBe("2026-02-02");
  });

  it("subtracts real calendar days, crossing a year boundary", () => {
    const w = load();
    expect(w.addDaysToDateStr("2026-01-02", -5)).toBe("2025-12-28");
  });
});
