// The browser half of the shared display-time table (REQ-DASH-071).
//
// Every case comes from display-time-cases.json at the repo root, which
// neither this suite nor tests/test_display_time.py owns. That is the
// point: a table either side could edit is a table either side can
// quietly bend to whatever it already does.
//
// Same shape as status-cases.json and for the same reason - two
// implementations of one rule drifted once already
// (plans/qa-pipeline.md item 74) and the drift rendered a check with 14
// real violations GREEN.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CASES = JSON.parse(
  readFileSync(path.join(__dirname, "..", "display-time-cases.json"), "utf8"),
);

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

// The asset timezone is an embedded const, so it is passed in the same
// way the real build passes it rather than assigned onto the window -
// a top-level `const` in a classic script is not reachable from
// outside it, so assigning would create a NEW global the page never
// reads (the trap schedule-runway.test.js documents).
function load() {
  dashboard = loadDashboard({ assetTimezone: CASES.asset_timezone });
  return dashboard.window;
}

describe("every day case", () => {
  for (const c of CASES.day_cases) {
    it(`${c.id} reads the way the table says`, () => {
      expect(load().fmtDay(c.at), c.why).toBe(c.expect);
    });
  }
});

describe("every instant case", () => {
  for (const c of CASES.instant_cases) {
    it(`${c.id} reads the way the table says`, () => {
      expect(load().fmtInstant(c.at), c.why).toBe(c.expect);
    });
  }
});

describe("every relative case", () => {
  for (const c of CASES.relative_cases.filter((x) => x.id)) {
    it(`${c.id} reads the way the table says`, () => {
      expect(load().fmtRelative(c.from, c.at)).toBe(c.expect);
    });
  }
});

describe("it never emits something unreadable", () => {
  // Matched as a PATTERN rather than by banning characters - the Python
  // twin's first draft asserted "T" was absent and failed on Tuesday.
  const ISO = /\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}|[+-]\d{2}:\d{2}/;

  it("no day or instant output looks like an ISO timestamp", () => {
    const w = load();
    for (const c of CASES.day_cases) expect(w.fmtDay(c.at)).not.toMatch(ISO);
    for (const c of CASES.instant_cases) expect(w.fmtInstant(c.at)).not.toMatch(ISO);
  });

  it("refuses a naive instant rather than guessing its zone", () => {
    // An instant with no offset could be anything, and guessing is how
    // a date lands on the wrong day - the bug this standard ends.
    expect(() => load().fmtInstant("2026-09-29T14:15:00")).toThrow();
  });
});

// CRITERION 14. The residue of post-build-review #35: assetTodayDateStr()
// used to catch an unknown zone and quietly carry on with the VIEWER's,
// which is the original bug wearing a try/catch. For eight hours of
// every Perth day the two clocks are on different calendar dates, so a
// silent fallback does not degrade the answer - it changes it, and says
// nothing.
describe("with no asset clock it refuses to draw an instant at all", () => {
  const INSTANT = "2026-09-29T14:15:00+08:00";

  it("throws rather than falling back to the reader's own clock", () => {
    const w = loadDashboard({ assetTimezone: null }).window;
    dashboard = { close: () => w.close() };
    expect(() => w.fmtInstant(INSTANT)).toThrow(/no asset timezone is embedded/);
  });

  it("throws rather than falling back to UTC", () => {
    const w = loadDashboard({ assetTimezone: null }).window;
    dashboard = { close: () => w.close() };
    // Both halves, because a date is the half that was actually wrong
    // on the live site - the arrival column showed the day before.
    expect(() => w.assetTodayDateStr()).toThrow(/no asset timezone is embedded/);
  });

  it("says which zone it could not resolve, rather than just failing", () => {
    const w = loadDashboard({ assetTimezone: "Australia/Nowhere" }).window;
    dashboard = { close: () => w.close() };
    expect(() => w.fmtInstant(INSTANT)).toThrow(/Australia\/Nowhere/);
  });
});
