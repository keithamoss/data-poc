// REQ-DASH-355: the period control - its words, its choices, the period=
// parameter, the statement while one is chosen, the title and the
// announcement, and a period the baseline does not hold.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const QUARTERLY = {
  calendars: { quarterly: [
    { period: "2025-Q3", date: "2025-08-01" }, { period: "2025-Q4", date: "2025-11-01" },
    { period: "2026-Q1", date: "2026-02-01" }, { period: "2026-Q2", date: "2026-05-01" },
    { period: "2026-Q3", date: "2026-08-01" } ] },
  datasetCalendar: {}, today: "2026-09-25",
};
const DAILY = {
  calendars: { daily: Array.from({ length: 30 }, (_, i) => {
    const day = new Date(Date.UTC(2026, 8, 1 + i)).toISOString().slice(0, 10);
    return { period: day, date: day };
  }) },
  datasetCalendar: {}, today: "2026-09-25",
};
function load(periodSequences, url) {
  dashboard = loadDashboard({ periodSequences, url });
  return dashboard.window;
}
const label = (w) => w.document.getElementById("period-btn-label").textContent;
const search = (w) => new URLSearchParams(w.location.search);

describe("the control's words (criterion 1)", () => {
  it("reads 'Period: all current' with none chosen, and 'For period: <P>' with one", () => {
    const w = load(QUARTERLY);
    expect(label(w)).toBe("Period: all current");
    w.applyPeriod("2026-Q2");
    expect(label(w)).toBe("For period: 2026-Q2");
  });

  it("reads 'Day: latest' and 'For day: <date>' on a daily baseline", () => {
    const w = load(DAILY);
    expect(label(w)).toBe("Day: latest");
    w.applyPeriod("2026-09-14");
    expect(label(w)).toBe(`For day: ${w.fmtPeriodName("2026-09-14")}`);
  });
});

describe("the choices (criterion 2)", () => {
  it("lists the baseline's periods newest first under year headings", () => {
    const w = load(QUARTERLY);
    w.openPeriodPanel();
    const body = w.document.getElementById("period-panel-body");
    const years = [...body.querySelectorAll("[role=group] .legend-key")].map((e) => e.textContent);
    expect(years).toEqual(["2026", "2025"]);
    const periods = [...body.querySelectorAll("[data-period]")].map((b) => b.dataset.period);
    expect(periods).toEqual(["2026-Q3", "2026-Q2", "2026-Q1", "2025-Q4", "2025-Q3"]);
  });

  it("offers a date input bounded to the days the page has, on a daily baseline", () => {
    const w = load(DAILY);
    w.openPeriodPanel();
    const input = w.document.getElementById("period-day-input");
    expect(input.type).toBe("date");
    expect(input.min).toBe("2026-09-01");
    expect(input.max).toBe("2026-09-25");
  });
});

describe("the parameter (criteria 3 to 5)", () => {
  it("is set and cleared in period=, replacing the history entry", () => {
    const w = load(QUARTERLY);
    const before = w.history.length;
    w.applyPeriod("2026-Q1");
    expect(search(w).get("period")).toBe("2026-Q1");
    w.applyPeriod(null);
    expect(search(w).has("period")).toBe(false);
    expect(w.history.length).toBe(before);
  });

  it("is read from the address on load", () => {
    const w = load(QUARTERLY, "http://localhost/?period=2025-Q4");
    expect(label(w)).toBe("For period: 2025-Q4");
  });

  it("keeps the date on show when the period changes", () => {
    const w = load(QUARTERLY, "http://localhost/?in-place-on=2026-03-01");
    w.applyPeriod("2025-Q4");
    expect(search(w).get("in-place-on")).toBe("2026-03-01");
    expect(w.eval("CURRENT_IN_PLACE_ON")).toBe("2026-03-01");
  });
});

describe("while a period is chosen (criteria 6 and 7)", () => {
  it("states it in place of the past-date notice, with a button that clears it", () => {
    const w = load(QUARTERLY, "http://localhost/?in-place-on=2026-03-01");
    w.applyPeriod("2025-Q4");
    const notice = w.document.getElementById("in-place-on-past-notice");
    expect(notice.hidden).toBe(false);
    expect(notice.textContent.replace(/\s+/g, " ")).toContain(
      `Showing 2025-Q4 — results recorded by the end of ${w.fmtDay("2026-03-01")} · Clear period`);
    notice.querySelector("#period-clear-inline").click();
    expect(search(w).has("period")).toBe(false);
  });

  it("labels the date control 'Results recorded by'", () => {
    const w = load(QUARTERLY);
    w.applyPeriod("2025-Q4");
    expect(w.document.getElementById("in-place-on-btn-word").textContent).toBe("Results recorded by");
    w.applyPeriod(null);
    expect(w.document.getElementById("in-place-on-btn-word").textContent).toBe("In the warehouse on");
  });

  it("adds ' · <P>' to the title and announces the choice and the clearing", () => {
    const w = load(QUARTERLY);
    w.applyPeriod("2025-Q4");
    expect(w.document.title.endsWith(" · 2025-Q4")).toBe(true);
    expect(w.document.getElementById("route-announcer").textContent).toBe("Showing 2025-Q4");
    w.applyPeriod(null);
    expect(w.document.title.includes("2025-Q4")).toBe(false);
    expect(w.document.getElementById("route-announcer").textContent).toBe("Showing all current");
  });

  it("announces 'Showing latest' when a day is cleared on a daily baseline", () => {
    const w = load(DAILY);
    w.applyPeriod("2026-09-14");
    w.applyPeriod(null);
    expect(w.document.getElementById("route-announcer").textContent).toBe("Showing latest");
  });
});

describe("a period the baseline does not hold (criterion 8)", () => {
  it("is named in a notice, removed from the address, and none is chosen", () => {
    const w = load(QUARTERLY, "http://localhost/?period=2031-Q9&in-place-on=2026-03-01");
    const notice = w.document.getElementById("period-param-notice");
    expect(notice.hidden).toBe(false);
    expect(notice.textContent).toContain("2031-Q9");
    expect(search(w).has("period")).toBe(false);
    expect(search(w).get("in-place-on")).toBe("2026-03-01");
    expect(label(w)).toBe("Period: all current");
  });
});
