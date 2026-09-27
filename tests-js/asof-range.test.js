// The as-of picker's bounds, its per-calendar period statement, and what
// it says about a date it has no periods for (REQ-DASH-054 criteria 6-10).
//
// WHY THESE ARE HERE RATHER THAN IN THE PYTHON E2E SUITE: the real built
// dashboard's covered range ends at the build date, so an assertion about
// a date outside it either hard-codes a date that goes stale or computes
// one from the clock - and the page computes its own on the asset's clock,
// which is the shape that has already gone red overnight twice in this
// project. Here the sequences are a fixture, so "outside the range" is a
// fact about the fixture rather than about the day the test ran.
//
// The render layer is still asserted in a real browser - see
// tests/test_dashboard_e2e.py's own as-of coverage - because a correct
// lookup says nothing about a template with its own transform.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load(opts) {
  dashboard = loadDashboard(opts);
  return dashboard.window;
}

// A top-level `const` in a classic script is NOT a window property, so
// CURRENT_AS_OF and DEFAULT_AS_OF cannot be read off `window` - and
// reading them there returns undefined rather than throwing, which makes
// `expect(w.CURRENT_AS_OF).toBe(w.DEFAULT_AS_OF)` pass by comparing
// undefined against undefined. Asked through the page's own scope
// instead, where they exist.
function asOf(w, name) {
  return w.eval(name);
}

// The default fixture: a daily calendar over 2025-01-01..2027-03-11, and a
// Feb/May/Aug/Nov quarterly one over 2025-08-01..2026-08-01.
const COVERED_FIRST = "2025-01-01";
const COVERED_LAST = "2027-03-11";

describe("the period a date falls in, per named calendar (criterion 6)", () => {
  it("names one period per calendar, not one per dataset", () => {
    const w = load();
    w.openAsOfPanel();
    const text = w.document.getElementById("asof-periods").textContent;
    // Two calendars, two lines - never the nine datasets mapped to them.
    expect(text).toContain("daily calendar");
    expect(text).toContain("quarterly calendar");
    expect(text).not.toContain("cp-clients");
  });

  it("names the period the chosen date is in, on each calendar", () => {
    const w = load();
    w.renderAsOfPeriods("2026-03-20");
    const text = w.document.getElementById("asof-periods").textContent;
    // The same date is a whole quarter's worth of different answers: its
    // own day on the daily calendar, and a quarter that began seven weeks
    // earlier on the quarterly one. That gap is the point of criterion 6.
    expect(text).toContain("2026-Q1");
    expect(text).toContain("2026-03-20");
  });

  it("says a calendar does not go back that far rather than going quiet", () => {
    const w = load();
    // 2025-03-01 is inside the daily sequence and before the quarterly
    // one's first authored date. Omitting the quarterly line would read as
    // "no opinion"; the real answer is that its records start later.
    w.renderAsOfPeriods("2025-03-01");
    const text = w.document.getElementById("asof-periods").textContent;
    expect(text).toContain("no period");
    expect(text).toContain("does not go back that far");
  });

  it("says nothing at all on a template with no embedded sequences", () => {
    const w = load({ periodSequences: null });
    w.renderAsOfPeriods("2026-03-20");
    expect(w.document.getElementById("asof-periods").textContent).toBe("");
  });
});

describe("the as-of input is bounded to the covered range (criterion 8)", () => {
  it("bounds the input when the panel opens", () => {
    const w = load();
    w.openAsOfPanel();
    const input = w.document.getElementById("asof-input");
    expect(input.getAttribute("min")).toBe(COVERED_FIRST);
    expect(input.getAttribute("max")).toBe(COVERED_LAST);
  });

  it("bounds the MAXIMUM at what is embedded, not at today", () => {
    // Criterion 3 is that nothing which has not begun is embedded, so the
    // newest pickable date is the newest period - which on a daily
    // calendar is the date of the last build. Bounding at `today` instead
    // would offer dates the page has no period for, which is the state
    // criterion 9 then has to apologise for.
    const w = load();
    w.openAsOfPanel();
    expect(w.document.getElementById("asof-input").max).toBe(w.coveredDateRange().last);
  });

  it("leaves the input unbounded when there are no sequences to bound it to", () => {
    const w = load({ periodSequences: null });
    w.openAsOfPanel();
    const input = w.document.getElementById("asof-input");
    expect(input.hasAttribute("min")).toBe(false);
    expect(input.hasAttribute("max")).toBe(false);
  });
});

describe("a date outside the covered range, arriving by URL (criteria 9 and 10)", () => {
  it("says so plainly and states the covered range", () => {
    const w = load({ url: "http://localhost/?asof=2019-06-01" });
    const notice = w.document.getElementById("asof-range-notice");
    expect(notice.hidden).toBe(false);
    expect(notice.textContent).toContain("outside the dates");
    expect(notice.textContent).toContain("1 January 2025");
    expect(notice.textContent).toContain("11 March 2027");
  });

  it("offers a one-click reset to the default", () => {
    const w = load({ url: "http://localhost/?asof=2019-06-01" });
    const reset = w.document.getElementById("asof-range-reset");
    expect(reset).not.toBeNull();
    reset.click();
    // Back to the default, the notice gone, and the page still rendered.
    expect(w.document.getElementById("asof-range-notice").hidden).toBe(true);
    expect(asOf(w, "CURRENT_AS_OF")).toBe(asOf(w, "DEFAULT_AS_OF"));
  });

  it("does not replace the page - the rest of it is still a real answer", () => {
    // Every dataset resolves to its own newest run at or before the date,
    // or to No data. Those are correct answers; hiding them to make a
    // point about the date would be the empty view criterion 10 forbids.
    const w = load({ url: "http://localhost/?asof=2019-06-01" });
    expect(w.document.getElementById("view").innerHTML.trim()).not.toBe("");
  });

  it("stays quiet for a date inside the range", () => {
    const w = load({ url: "http://localhost/?asof=2026-03-20" });
    const notice = w.document.getElementById("asof-range-notice");
    expect(notice.hidden).toBe(true);
    expect(notice.textContent).toBe("");
  });

  it("stays quiet on a template with no sequences, having nothing to compare against", () => {
    const w = load({ url: "http://localhost/?asof=2019-06-01", periodSequences: null });
    expect(w.document.getElementById("asof-range-notice").hidden).toBe(true);
  });
});

describe("the query parameter stays a calendar date (criterion 7)", () => {
  it("carries the date, never the period name", () => {
    const w = load();
    w.applyAsOf("2026-03-20");
    const params = new URLSearchParams(w.location.search);
    expect(params.get("asof")).toBe("2026-03-20");
    // 2026-Q1 is what the panel SAYS about that date; a URL carrying it
    // instead would be lossy - a period is a range, and re-reading one
    // would silently move the date to its start.
    expect(w.location.search).not.toContain("2026-Q1");
  });

  it("drops the parameter entirely for the default date", () => {
    const w = load({ url: "http://localhost/?asof=2026-03-20" });
    w.applyAsOf(asOf(w, "DEFAULT_AS_OF"));
    expect(new URLSearchParams(w.location.search).get("asof")).toBeNull();
  });
});

describe("no console errors, on any of these paths (criterion 11)", () => {
  it("an out-of-range date by URL renders cleanly", () => {
    dashboard = loadDashboard({ url: "http://localhost/?asof=2019-06-01" });
    dashboard.window.openAsOfPanel();
    expect(dashboard.errors).toEqual([]);
  });

  it("a template with no sequences at all renders cleanly", () => {
    dashboard = loadDashboard({ periodSequences: null });
    dashboard.window.openAsOfPanel();
    dashboard.window.applyAsOf("2026-03-20");
    expect(dashboard.errors).toEqual([]);
  });
});
