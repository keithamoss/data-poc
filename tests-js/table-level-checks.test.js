// plans/running-thoughts.md #20 - table-level checks, and the stale
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
