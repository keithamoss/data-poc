// A count the build recorded no number for renders as a dash, never a crash
// (found building REQ-DASH-204, 2026-10-25): a held Case Workers whose only
// run measured nothing has `rowCount: null`, and fmtInt(null) threw inside
// renderAgency - the whole collection page failed to draw.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

describe("fmtInt", () => {
  it("formats a number", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.fmtInt(12345)).toBe("12,345");
  });

  it("renders no number as a dash", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.fmtInt(null)).toBe("—");
    expect(dashboard.window.fmtInt(undefined)).toBe("—");
  });
});
