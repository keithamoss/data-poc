// Drill-down navigation: stateToHash/hashToState (the hash-based STATE
// persistence "Thread C - as of is a global filter... deliberately
// separate from" - navigate()'s own neighbouring comment) plus a real
// end-to-end navigate() call through jsdom, driving the actual DOM the
// same way a click on an agency card does.
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

describe("stateToHash / hashToState round-trip", () => {
  it("round-trips a real drill-down state through the URL hash", () => {
    const w = load();
    const state = { tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations" };
    w.location.hash = w.stateToHash(state);
    expect(w.hashToState()).toEqual(state);
  });

  // 2026-09-18 (running-thoughts.md #9): the hash used to be opaque
  // encodeURIComponent(JSON.stringify(state)) - unreadable, but any JS
  // object round-tripped through it losslessly. Now a real, readable
  // path (#/agency/<id>/collection/<id>/dataset/<id>/column/<name>/
  // check/<key>) - this asserts that BOTH the readable shape and the
  // deepest drill-down (column + check together, arbitrary names with
  // spaces/slashes) still round-trip correctly through per-segment
  // encodeURIComponent/decodeURIComponent.
  it("produces a real, readable path for a dataset state", () => {
    const w = load();
    const state = { tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations" };
    expect(w.stateToHash(state)).toBe("#/agency/registry-services/collection/civil-registration/dataset/birth-registrations");
  });

  it("keys a check URL on its stable key, never on its display heading", () => {
    // plans/running-thoughts.md #19. The URL used to carry the check's
    // DISPLAY name, which is why headings read "Invalid values -
    // dbt:accepted_values (dbt-core)": the heading had to stay unique
    // within a column, because it WAS the identity.
    //
    // It is now the check_id's final segment, which REQ-QAC-023's
    // validate_tail_uniqueness() already guarantees unique per column -
    // a gate written for exactly this and left unwired until now. The
    // point of the test is that rewording a heading must not move a URL.
    const w = load();
    const state = {
      tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration",
      datasetId: "birth-registrations", columnName: "sex",
      checkKey: "invalid_percent_soda",
    };
    const hash = w.stateToHash(state);
    expect(hash).toContain("/check/invalid_percent_soda");
    // and nothing tool-shaped leaks into it
    expect(hash).not.toMatch(/dbt|soda-core|datacontract-cli/i);
    w.location.hash = hash;
    expect(w.hashToState().checkKey).toBe("invalid_percent_soda");
  });

  it("round-trips a column+check drill-down, including names with spaces and slashes", () => {
    const w = load();
    const state = {
      tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations",
      columnName: "child_date_of_birth", checkKey: "not null / accepted range",
    };
    w.location.hash = w.stateToHash(state);
    expect(w.hashToState()).toEqual(state);
  });

  it("hashToState returns null for no hash at all", () => {
    const w = load();
    w.location.hash = "";
    expect(w.hashToState()).toBeNull();
  });

  it("hashToState returns null for a malformed hash rather than throwing", () => {
    const w = load();
    w.location.hash = "#not-real-json";
    expect(w.hashToState()).toBeNull();
  });

  it("falls back to the agency tier for a path that starts right but doesn't complete a dataset", () => {
    const w = load();
    w.location.hash = "#/agency/registry-services/collection/civil-registration";
    expect(w.hashToState()).toEqual({ tier: "agency", agencyId: "registry-services" });
  });
});

describe("side panels - openPanel()/closePanel() real history integration", () => {
  // 2026-09-18 (running-thoughts.md #9): the 4 header side panels
  // (activity/changelog/requirements/snapshots) used to be independent
  // DOM-only open()/close() pairs, entirely outside STATE/URL. Now
  // unified under openPanel()/closePanel() - opening one is a real
  // history.pushState (synchronous, safe to assert directly), closing
  // goes through history.back() (async in a real browser/jsdom - the
  // real back-button behaviour itself is covered by the Playwright e2e
  // suite, tests/test_dashboard_e2e.py, not duplicated here).
  it("opening a panel shows its DOM, sets ?panel= in the URL, and pushes a real history entry", () => {
    const w = load();
    const before = w.history.length;
    w.openPanel("activity");
    expect(w.document.getElementById("activity-panel").classList.contains("open")).toBe(true);
    expect(new w.URLSearchParams(w.location.search).get("panel")).toBe("activity");
    expect(w.history.length).toBe(before + 1);
  });

  it("opening a second panel closes the first rather than stacking both open", () => {
    const w = load();
    w.openPanel("activity");
    w.openPanel("requirements");
    expect(w.document.getElementById("activity-panel").classList.contains("open")).toBe(false);
    expect(w.document.getElementById("requirements-panel").classList.contains("open")).toBe(true);
    expect(new w.URLSearchParams(w.location.search).get("panel")).toBe("requirements");
  });

  it("a plain navigate() call closes any open panel", () => {
    const w = load();
    w.openPanel("snapshots");
    w.navigate({ tier: "agency", agencyId: "registry-services" });
    expect(w.document.getElementById("snapshots-panel").classList.contains("open")).toBe(false);
  });
});

describe("navigate() - real drill-down through the DOM", () => {
  it("starts on the executive tier with every real agency card rendered", () => {
    const w = load();
    const cards = dashboard.document.querySelectorAll("#agency-grid .card");
    expect(cards.length).toBeGreaterThan(0);
    // the real registry-services agency (birth registrations' own agency,
    // stable across the illustrative mock dataset - buildData()'s own
    // hardcoded id) is one of them
    const navs = [...cards].map((c) => JSON.parse(c.dataset.nav));
    expect(navs.some((n) => n.agencyId === "registry-services")).toBe(true);
  });

  it("drilling into an agency updates the hash, the rail, and removes the exec grid", () => {
    const w = load();
    w.navigate({ tier: "agency", agencyId: "registry-services" });

    expect(w.hashToState()).toEqual({ tier: "agency", agencyId: "registry-services" });
    expect(dashboard.document.getElementById("agency-grid")).toBeNull();
    expect(dashboard.document.getElementById("rail").textContent).toContain("Registry Services");
  });

  it("drilling all the way to a real dataset resolves the exact same dataset via resolveContext", () => {
    const w = load();
    const state = { tier: "dataset", agencyId: "registry-services", collectionId: "civil-registration", datasetId: "birth-registrations" };
    w.navigate(state);

    const ctx = w.resolveContext(state);
    expect(ctx).not.toBeNull();
    expect(ctx.ds.id).toBe("birth-registrations");
    expect(ctx.ag.id).toBe("registry-services");
    expect(ctx.col.id).toBe("civil-registration");
  });

  it("resolveContext returns null for a state that doesn't resolve to a real agency/collection/dataset", () => {
    const w = load();
    expect(w.resolveContext({ agencyId: "does-not-exist" })).toBeNull();
    expect(w.resolveContext(null)).toBeNull();
  });
});
