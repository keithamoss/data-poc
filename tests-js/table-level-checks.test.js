// REQ-DASH-032 - table-level checks, and the stale
// workaround that hid them.
//
// Row-count checks were skipped by both dashboard builders for a reason
// that was real when written: a row-count check's severity is "warning",
// so its fail_threshold is None, checks_out defaulted a missing one to
// 0, and checkStatus() (current > fail) read any healthy positive row
// count as RED. Item 74 fixed that at the source - checkStatus() now
// returns the tool's own verdict first - but the workaround outlived the
// bug by long enough to hide 12 real checks.
//
// This is the render-layer assertion that keeps it fixed. It is
// deliberately at this layer rather than the data layer: CLAUDE.md's own
// item-74 write-up is about a green data layer saying nothing about a
// render layer that has its own transform.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

describe("a check whose thresholds cannot be applied", () => {
  it("renders the tool's own verdict, not threshold maths", () => {
    dashboard = loadDashboard();
    const { checkStatus } = dashboard.window;

    // Real shape from the built data: a row-count check whose warn sits
    // ABOVE its fail, because the two are the ends of a band rather than
    // a rising scale. Threshold maths on this is meaningless.
    expect(checkStatus({ current_status: "green", current: 3000, warn: 500, fail: 100 }))
      .toBe("green");

    // And the other real shape - no thresholds at all.
    expect(checkStatus({ current_status: "green", current: 3000, warn: null, fail: null }))
      .toBe("green");
  });

  it("still falls back to thresholds when no verdict was recorded", () => {
    // The fallback is not dead code - it covers the synthesized
    // "No automated quality rule defined" placeholder and any older
    // committed result predating current_status.
    dashboard = loadDashboard();
    const { checkStatus } = dashboard.window;
    expect(checkStatus({ current: 9, warn: 0, fail: 5 })).toBe("red");
    expect(checkStatus({ current: 0, warn: 0, fail: 5 })).toBe("green");
  });
});

// REQ-DASH-033 - those two pseudo-columns became real sections of the
// dataset page. These cover the split itself and the URL key; the
// rendering, the omit-when-empty case and the click-through are in
// tests/test_dashboard_e2e.py, because a section's position relative to
// the grid and its rollup pill are things only a real layout has.
describe("REQ-DASH-033 - column scopes", () => {
  it("keys a column URL on its key, not its display name", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    expect(w.columnKey({ name: "Supply-level checks", key: "supply" })).toBe("supply");
    expect(w.columnKey({ name: "sex", key: "sex" })).toBe("sex");
  });

  it("falls back to the name for a dataset built before key existed", () => {
    // What a committed snapshot from last week is. It must still
    // resolve rather than producing an empty URL segment.
    dashboard = loadDashboard();
    const w = dashboard.window;
    expect(w.columnKey({ name: "sex" })).toBe("sex");
    expect(w.columnKey(null)).toBe("");
  });

  it("splits scoped columns out of the real ones by scope, never by name", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const ds = { columns: [
      { name: "sex", key: "sex" },
      { name: "Supply-level checks", key: "supply", scope: "supply" },
      { name: "Table-level checks", key: "table", scope: "table" },
    ] };
    expect(w.realColumns(ds).map(c => c.name)).toEqual(["sex"]);
    expect(w.scopedColumns(ds, "supply").map(c => c.key)).toEqual(["supply"]);
    expect(w.scopedColumns(ds, "table").map(c => c.key)).toEqual(["table"]);
  });

  it("a column whose NAME looks scoped but carries no scope stays a real column", () => {
    // The point of keying on `scope` rather than matching a display
    // name: the name is prose now and prose gets reworded.
    dashboard = loadDashboard();
    const w = dashboard.window;
    const ds = { columns: [{ name: "Supply-level checks", key: "x" }] };
    expect(w.realColumns(ds)).toHaveLength(1);
    expect(w.scopedColumns(ds, "supply")).toHaveLength(0);
  });

  // The order the two sections render in is asserted in the e2e suite
  // instead. COLUMN_SCOPES is a top-level `const`, and a `const` in a
  // classic script never becomes a window property the way a function
  // declaration does - the same jsdom limitation tests-js/
  // requirements.test.js documents for REQUIREMENTS.
});
