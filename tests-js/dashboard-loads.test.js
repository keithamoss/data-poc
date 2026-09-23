// Confirms the jsdom-loading harness itself works against the real
// committed template - the raw, unembedded scenario a suite built only
// against the real BUILT dashboard would never exercise.
//
// WHAT THAT SCENARIO NOW MEANS (REQ-DASH-055, 2026-09-23): the template
// carries no tree of its own at all. It used to fall back to an
// illustrative mock generator so this page had something to draw; that
// generator is gone, so an unembedded template correctly renders its
// "no data embedded" state instead. The test below asserts that
// directly, which is a stronger claim than the old one - it proves the
// script RAN and reached the right branch, rather than proving only
// that something got painted.
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

  it("says plainly that nothing is embedded, rather than looking like an empty asset", () => {
    // The consts are declared `const`, so - correctly, matching real
    // non-module browser script scoping - they are never `window`
    // properties to read back directly; the real, end-to-end proof the
    // main script ran (not just parsed without throwing) is the DOM it
    // actually rendered.
    dashboard = loadDashboard();
    const themeBtn = dashboard.document.getElementById("theme-btn");
    expect(themeBtn.textContent).toMatch(/light mode|dark mode/i);

    const view = dashboard.document.getElementById("view").textContent;
    expect(view).toMatch(/no data embedded/i);
    expect(view).toMatch(/mothman/i);
    // "0 agencies" would be the WRONG thing to show here: an asset with
    // no agencies is a finding, a template nobody has built is not.
    expect(view).not.toMatch(/0 agencies/);
  });

  it("renders no agency tiles, because the tree comes from embedded config alone", () => {
    dashboard = loadDashboard();
    expect(dashboard.document.querySelectorAll("#agency-grid .card").length).toBe(0);
    expect(dashboard.window.buildData(dashboard.window.CURRENT_AS_OF).agencies).toEqual([]);
  });
});
