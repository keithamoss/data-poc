// Cadence math: cadenceLabel/cycleLabel/addDaysToDateStr, plus the period
// LOOKUPS that replaced this page's own JS port of pipeline/cadence.py's
// cycle_start() (REQ-DASH-054).
//
// WHY THERE USED TO BE A PORT AT ALL: the server-side Python only ever
// needs a run's OWN cycle, while the page also needs "what period does an
// arbitrary as-of date fall in" - so both existed and had to agree. The
// port could compute a cadence RULE and could never compute an AUTHORED
// date list, which is what the quarterly calendar is, so the agreement was
// never achievable for one of the two real calendars. Shipping the
// sequences removes the second implementation rather than fixing it.
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

// NO ZONE LABEL since REQ-DASH-071 criterion 6: everything a reader
// sees is on the asset's clock, so naming one implies a second to
// distinguish it from. The TIME keeps its written "14:00" form, which
// is criterion 8 - it is a deadline echoed out of contract/*.yaml, not
// an instant, and a reader checking the tile against the contract is
// comparing those two strings.
describe("cadenceLabel", () => {
  it("labels a daily cadence", () => {
    const w = load();
    expect(w.cadenceLabel({ type: "daily", expected_time: "14:00" })).toBe("Daily, by 14:00");
  });

  it("labels a weekly cadence with the real weekday name", () => {
    const w = load();
    expect(w.cadenceLabel({ type: "weekly", weekday: 2, expected_time: "09:00" })).toBe("Weekly (Wed), by 09:00");
  });

  it("labels a quarterly cadence with real month names and day", () => {
    const w = load();
    const label = w.cadenceLabel({ type: "quarterly", anchor_months: [1, 4, 7, 10], day_of_month: 15, expected_time: "17:00" });
    expect(label).toBe("Quarterly (Jan/Apr/Jul/Oct, day 15), by 17:00");
  });

  // delivery-critic on REQ-PIPE-167, finding 2 (post-build-review #142).
  it("says a following-period dataset is due days before each date", () => {
    const w = load();
    const label = w.cadenceLabel({ type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1,
                                   expected_time: "09:00", days_before: 60 });
    expect(label).toBe("Quarterly (Feb/May/Aug/Nov, day 1), due 60 days before each date, by 09:00");
  });
});

describe("periodStartDate", () => {
  // IT REPLACED cycleStartDate(cadence, dateStr), a JS port of Python's
  // cycle_start(). The port is gone rather than kept alongside, so these
  // are the same QUESTIONS asked of the new mechanism: which period does
  // this date fall in, and what happens at the edges.
  //
  // The cases it could never answer are here too, and they are the reason
  // for the change: an AUTHORED calendar is not a rule, so a Feb/May/Aug/
  // Nov quarterly sequence had no computable answer at all.

  it("a daily calendar's period start is the date itself", () => {
    const w = load();
    expect(w.periodStartDate("birth-registrations", "2026-03-15")).toBe("2026-03-15");
  });

  it("an AUTHORED calendar's period start is the latest authored date at or before it", () => {
    const w = load();
    // The default fixture's quarterly calendar is 2025-08-01, 2025-11-01,
    // 2026-02-01, 2026-05-01 - the real asset's own shape, which is NOT
    // calendar quarters. A rule could not have produced this answer.
    expect(w.periodStartDate("child-protection", "2026-03-20")).toBe("2026-02-01");
  });

  it("a date that IS a period's own start returns that date", () => {
    const w = load();
    expect(w.periodStartDate("child-protection", "2026-02-01")).toBe("2026-02-01");
  });

  it("a date before every period in the sequence has no period", () => {
    const w = load();
    // Not an exception and not the first period - there is genuinely no
    // period a 2019 date falls in, and saying so is the honest answer.
    expect(w.periodStartDate("child-protection", "2019-01-01")).toBeNull();
  });

  it("a dataset with no calendar has no period arithmetic rather than an error", () => {
    const w = load();
    // REQ-PIPE-106's subject: a dataset can exist before any supply is
    // agreed. The picker simply has nothing to compute for it.
    expect(w.periodStartDate("not-a-dataset", "2026-03-15")).toBeNull();
  });

  it("the unbuilt template answers nothing rather than guessing", () => {
    dashboard = loadDashboard({ periodSequences: null });
    expect(dashboard.window.periodStartDate("birth-registrations", "2026-03-15")).toBeNull();
  });
});

describe("periodNameFor", () => {
  it("names the period rather than returning its date", () => {
    const w = load();
    // The NAME is what a reader recognises - "2026-Q1", not "2026-02-01" -
    // and it exists only in the authored list. This is the half of
    // REQ-DASH-054 criterion 6 that the port could not have served at all.
    expect(w.periodNameFor("child-protection", "2026-03-20")).toBe("2026-Q1");
  });

  it("a daily calendar's period name is its date, which is the honest answer", () => {
    const w = load();
    expect(w.periodNameFor("birth-registrations", "2026-03-15")).toBe("2026-03-15");
  });
});

describe("coveredDateRange", () => {
  it("spans the earliest period start to the latest across every calendar", () => {
    const w = load();
    const range = w.coveredDateRange();
    expect(range.first).toBe("2025-01-01");   // the daily fixture's first day
    expect(range.last).toBe("2027-03-11");    // its 800th
  });

  it("is null on the unbuilt template, which covers nothing", () => {
    dashboard = loadDashboard({ periodSequences: null });
    expect(dashboard.window.coveredDateRange()).toBeNull();
  });
});

describe("no schedule derivation in the browser (criterion 5)", () => {
  it("the JS port of cycle_start() is gone rather than kept as a fallback", () => {
    const w = load();
    // Kept alongside the lookup it would be two implementations wearing
    // one name, and the one taken would depend on which calendar a
    // dataset happened to be on - which is how a page ends up right for
    // one asset and confidently wrong for the next.
    expect(w.cycleStartDate).toBeUndefined();
  });

  it("with nothing embedded the page computes nothing rather than falling back", () => {
    // The honest failure. A page that derived a schedule when the embed
    // was missing would answer every question plausibly and some of them
    // wrongly, and nothing on screen would say which.
    dashboard = loadDashboard({ periodSequences: null });
    const w = dashboard.window;
    expect(w.periodStartDate("child-protection", "2026-03-20")).toBeNull();
    expect(w.periodNameFor("child-protection", "2026-03-20")).toBeNull();
    expect(w.coveredDateRange()).toBeNull();
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
