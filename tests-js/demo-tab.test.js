// The "Demo" tab (plans/tooling.md #1 Phase 6) - a genuinely new
// top-level tier (STATE.tier==="demo"), same pattern as the "Plans" tab.
// jsdom's default JSDOM config (no `resources: "usable"`, matching
// loadDashboard.js's own real config) never fetches/executes an external
// <script src=...> - so the real vendored dashboard/vendor/
// asciinema-player.min.js this tab's own <script src="vendor/...">
// references never actually loads here, and `AsciinemaPlayer` stays
// undefined in the jsdom window. That's exactly the real "not built /
// player unavailable" case renderDemo()'s own guard exists for - these
// tests cover the tab's routing/rendering logic and that graceful-
// degradation path, not real player playback (a real Playwright check
// against the real, built dashboard covers that - see
// tests/test_dashboard_e2e.py).
//
// STATE itself is a `let` at the template's own top level, so - same as
// every other test file here (navigation.test.js's own real back/forward
// coverage is deferred to Playwright for the identical reason) - these
// assert on the real, OBSERVABLE DOM/URL a user/browser would actually
// see, never on `window.STATE` directly (it isn't exposed on `window` -
// only top-level `function` declarations are, per loadDashboard.js's own
// comment).
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

describe("Demo tab routing", () => {
  it("stateToHash produces a real, readable /demo path", () => {
    const w = load();
    expect(w.stateToHash({ tier: "demo" })).toBe("#/demo");
  });

  it("hashToState round-trips #/demo back to {tier: demo}", () => {
    const w = load();
    w.location.hash = "#/demo";
    expect(w.hashToState()).toEqual({ tier: "demo" });
  });

  it("clicking the Demo header button navigates to the demo tier", () => {
    const w = load();
    w.document.getElementById("demo-btn").click();
    expect(w.location.hash).toBe("#/demo");
    expect(w.document.getElementById("view").querySelector("h2").textContent).toBe("Demo");
  });
});

describe("Demo tab rendering", () => {
  it("shows the real header/description text", () => {
    const w = load();
    w.navigate({ tier: "demo" });
    const view = w.document.getElementById("view");
    expect(view.querySelector("h2").textContent).toBe("Demo");
    expect(view.textContent).toContain("mothman CLI/TUI");
  });

  it("with no player library loaded (the raw template's own real scenario here), shows the 'not built yet' fallback rather than throwing", () => {
    const w = load();
    expect(w.AsciinemaPlayer).toBeUndefined(); // never fetched under jsdom - see file header
    expect(() => w.navigate({ tier: "demo" })).not.toThrow();
    const view = w.document.getElementById("view");
    expect(view.textContent).toContain("No demo recording embedded yet");
  });

  it("re-renders cleanly on repeated navigation (no leftover DOM/state)", () => {
    const w = load();
    w.navigate({ tier: "demo" });
    w.navigate({ tier: "exec" });
    w.navigate({ tier: "demo" });
    expect(w.document.getElementById("view").querySelector("h2").textContent).toBe("Demo");
  });

  it("a plain navigate() to Demo closes any open panel, same as every other tier", () => {
    const w = load();
    w.openPanel("snapshots");
    w.navigate({ tier: "demo" });
    expect(w.document.getElementById("snapshots-panel").classList.contains("open")).toBe(false);
  });
});
