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
