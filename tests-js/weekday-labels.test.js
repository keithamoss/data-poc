// REQ-DASH-347: a dataset that participates by weekday on a daily asset is
// worded in its baseline's own terms - its cycle on the SLA tile, and each day
// it owes nothing in.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
function load() { dashboard = loadDashboard(); return dashboard.window; }

const DAILY = { type: "daily", expected_time: "10:00", latency_minutes: 120 };

describe("the SLA tile's cycle for a weekday subset (criterion 1)", () => {
  it.each([
    [[0], "Weekly (Monday), by 10:00"],
    [[0, 1, 2, 3, 4], "Weekdays, by 10:00"],
    [[4, 0, 2, 1, 3], "Weekdays, by 10:00"],
    [[0, 3], "2 days a week (Monday, Thursday), by 10:00"],
    [[0, 1, 2, 3, 4, 5], "6 days a week (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday), by 10:00"],
    [[1, 2, 3, 4, 5], "5 days a week (Tuesday, Wednesday, Thursday, Friday, Saturday), by 10:00"],
  ])("weekdays %j read %s", (days, expected) => {
    const w = load();
    expect(w.cadenceLabel({ ...DAILY, weekdays: days })).toBe(expected);
  });

  it("all seven read Daily, as a daily dataset with no subset does", () => {
    const w = load();
    expect(w.cadenceLabel({ ...DAILY, weekdays: [0, 1, 2, 3, 4, 5, 6] })).toBe("Daily, by 10:00");
    expect(w.cadenceLabel(DAILY)).toBe("Daily, by 10:00");
  });

  it("keeps the evening-before wording", () => {
    const w = load();
    expect(w.cadenceLabel({ ...DAILY, weekdays: [0], days_before: 1 }))
      .toBe("Weekly (Monday), by 10:00 the day before");
  });
});

describe("a day owed nothing by weekday (criterion 2)", () => {
  it("reads 'Not owed - it supplies only on Mondays'", () => {
    const w = load();
    const got = w.owedNothingLabel({ period: "2026-09-15", date: "2026-09-15",
                                     kind: "participation", reason: "weekly", weekdays: [0] });
    expect(got.word).toBe("Not owed");
    expect(got.label).toBe("Not owed — it supplies only on Mondays");
    expect(got.reason).toBe("weekly");
  });

  it("names several weekdays in week order", () => {
    const w = load();
    expect(w.owedNothingLabel({ kind: "participation", weekdays: [3, 0] }).label)
      .toBe("Not owed — it supplies only on Mondays and Thursdays");
  });

  it("leaves the month wording alone", () => {
    const w = load();
    expect(w.owedNothingLabel({ kind: "participation", months: [2, 8] }).label)
      .toBe("Not owed — it supplies only in the February and August rounds");
  });
});
