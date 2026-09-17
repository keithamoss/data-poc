// Confirms the jsdom-loading harness itself works against the real
// committed template - the raw-template-with-illustrative-mock-data
// scenario CLAUDE.md/plans/publishing-and-history.md call out as needing
// its own explicit coverage (a suite built only against the real BUILT
// dashboard, step 6, wouldn't otherwise exercise this path at all).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

describe("loading the raw template with no real data embedded", () => {
  it("runs both inline scripts with zero console errors", () => {
    dashboard = loadDashboard();
    expect(dashboard.errors).toEqual([]);
  });

  it("exposes the dashboard's own top-level functions on window", () => {
    dashboard = loadDashboard();
    expect(typeof dashboard.window.cadenceLabel).toBe("function");
    expect(typeof dashboard.window.fmtDate).toBe("function");
    expect(typeof dashboard.window.hashSeed).toBe("function");
    expect(typeof dashboard.window.mulberry32).toBe("function");
  });

  it("falls back to rendering the illustrative mock dataset (the template's own REAL_BIRTH_REG_DATA const is null)", () => {
    // REAL_BIRTH_REG_DATA is declared `const`, so - correctly, matching
    // real non-module browser script scoping - it's never a `window`
    // property to read back directly; the real, end-to-end proof the
    // main script ran (not just parsed without throwing) is the DOM it
    // actually rendered from the mock-data fallback.
    dashboard = loadDashboard();
    const themeBtn = dashboard.document.getElementById("theme-btn");
    expect(themeBtn.textContent).toMatch(/light mode|dark mode/i);
    expect(dashboard.document.querySelectorAll("#agency-grid .card").length).toBeGreaterThan(0);
  });
});
