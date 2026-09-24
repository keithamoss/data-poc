// Two post-build findings Keith signed off on 2026-09-24
// (plans/post-build-review.md, the visual critic's Q2 and the
// relative-time pass):
//
//   - fmtRelativeTime() stopped at 30 days and fell back to an absolute
//     date, so the weeks / months / years half of the display standard
//     Keith set that day simply did not exist.
//   - exhaustedMarker() printed "1 schedule ended" beside a pill that
//     already said "Schedule ended" - the same fact twice, at today's
//     scale, in a marker that only earns its place once it is
//     aggregating something.
//
// Both are pure functions on the template's own inline JS, so they
// belong here rather than in the real-browser suite: no layout, no
// cascade, nothing a headless Chromium would tell us that jsdom will
// not.
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

// The marker's own template literal wraps across lines, so its text
// arrives with newlines and indentation inside it. Collapse before
// asserting - the assertion is about what a reader sees, not about how
// the source happens to be wrapped.
function text(html) {
  return html.replace(/\s+/g, " ").trim();
}

function ago(w, { minutes = 0, hours = 0, days = 0 }) {
  const ms = (minutes + hours * 60 + days * 24 * 60) * 60000;
  return w.fmtRelativeTime(new Date(Date.now() - ms).toISOString());
}

describe("fmtRelativeTime", () => {
  it("keeps the short units it already had", () => {
    const w = load();
    expect(ago(w, { minutes: 0 })).toBe("just now");
    expect(ago(w, { minutes: 5 })).toBe("5 minutes ago");
    expect(ago(w, { minutes: 1 })).toBe("1 minute ago");
    expect(ago(w, { hours: 3 })).toBe("3 hours ago");
    expect(ago(w, { days: 2 })).toBe("2 days ago");
  });

  it("hands over to weeks rather than counting to 29 days", () => {
    const w = load();
    expect(ago(w, { days: 7 })).toBe("1 week ago");
    expect(ago(w, { days: 21 })).toBe("3 weeks ago");
  });

  it("reaches months and years instead of falling back to a date", () => {
    const w = load();
    expect(ago(w, { days: 60 })).toBe("2 months ago");
    expect(ago(w, { days: 300 })).toBe("10 months ago");
    expect(ago(w, { days: 400 })).toBe("1 year ago");
    expect(ago(w, { days: 1000 })).toBe("3 years ago");
  });

  it("never says 12 months when it means a year", () => {
    const w = load();
    for (let days = 330; days <= 380; days += 5) {
      expect(ago(w, { days })).not.toMatch(/^12 months/);
    }
  });

  it("never returns an absolute date, at any distance", () => {
    const w = load();
    for (const days of [1, 10, 40, 200, 900, 4000]) {
      expect(ago(w, { days })).toMatch(/ ago$/);
    }
  });
});

describe("exhaustedMarker", () => {
  it("says nothing when the count is zero", () => {
    const w = load();
    expect(w.exhaustedMarker(0, "green")).toBe("");
  });

  it("does not repeat a count of one beside a pill already saying it", () => {
    const w = load();
    expect(w.exhaustedMarker(1, "exhausted")).toBe("");
  });

  it("STILL shows a count of one when the group's own pill says something else", () => {
    // The narrowing Keith approved must not become the absorption
    // REQ-PIPE-053 exists to prevent: one exhausted dataset inside a
    // red agency has no other signal on that card, so suppressing it
    // here would hide it completely.
    const w = load();
    for (const status of ["red", "amber", "green", "nodata"]) {
      expect(text(w.exhaustedMarker(1, status))).toContain("1 schedule ended");
    }
  });

  it("always aggregates above one, whatever the group's own status", () => {
    const w = load();
    for (const status of ["red", "exhausted", "nodata"]) {
      expect(text(w.exhaustedMarker(6, status))).toContain("6 schedules ended");
    }
  });
});
