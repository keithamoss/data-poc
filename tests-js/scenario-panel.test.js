// The scenario map in the dashboard (REQ-DASH-046).
//
// The point of the panel: the dashboard deliberately carries NO label
// on the injected runs - "this is still just a proof of concept", and
// the red IS the point - so this is the one place that says which red
// was on purpose and takes you to it.
//
// THE LINK IS CONSTRUCTED HERE, FROM COORDINATES. The map carries a
// dataset, a period and an as-of date and never a URL, because the
// generator that wrote it does not know this page's routing scheme.
// Every assertion below is about that construction.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

const HIERARCHY = {
  agencies: [{
    id: "child-protection-family-support",
    name: "Department for Child Protection",
    collections: [{
      id: "child-protection",
      name: "Casework Management System",
      datasets: [
        { id: "cp-clients", name: "Client Register" },
        { id: "cp-carers", name: "Carer Register" },
      ],
    }],
  }],
};

function load() {
  dashboard = loadDashboard({ hierarchy: HIERARCHY });
  return dashboard.window;
}

function entry(overrides = {}) {
  return {
    id: "TS-1", mode: "INJECT", title: "Forward cascade",
    section: "Slot assignment",
    demonstrates: "The 20:00 arrival files as a **resupply of Monday**.",
    breaksAs: null, config: "Config: daily, due 12:00.",
    coordinates: null,
    ...overrides,
  };
}

const PLACED = entry({
  coordinates: {
    dataset: "cp-clients", supplies: ["cp_run_007"],
    period: "2026-Q3", asOf: "2026-08-15",
  },
});

describe("turning coordinates into a target", () => {
  it("resolves a dataset id to its own page, with the as-of date the entry names", () => {
    const w = load();
    const target = w.scenarioTarget(PLACED);
    expect(target.asOf).toBe("2026-08-15");
    expect(target.nav).toEqual({
      tier: "dataset",
      agencyId: "child-protection-family-support",
      collectionId: "child-protection",
      datasetId: "cp-clients",
    });
  });

  it("resolves a dataset by its display name too, since the map is written for people", () => {
    const w = load();
    const target = w.scenarioTarget(entry({
      coordinates: { dataset: "Carer Register", period: "2026-Q3", asOf: "2026-08-15" },
    }));
    expect(target.nav.datasetId).toBe("cp-carers");
  });

  it("resolves a collection to its agency page", () => {
    const w = load();
    const target = w.scenarioTarget(entry({
      coordinates: { dataset: "child-protection", period: "2026-Q3", asOf: "2026-08-15" },
    }));
    expect(target.nav).toEqual({ tier: "agency", agencyId: "child-protection-family-support" });
  });

  it("an entry with NO coordinates has no target", () => {
    const w = load();
    expect(w.scenarioTarget(entry())).toBeNull();
  });

  it("a coordinate naming something this page cannot place has no target", () => {
    // A dataset since renamed or retired still has a map entry.
    // Sending a reader to a page that does not exist is worse than
    // telling them it has gone.
    const w = load();
    expect(w.scenarioTarget(entry({
      coordinates: { dataset: "a-dataset-that-never-existed", period: "p", asOf: "2026-01-01" },
    }))).toBeNull();
  });
});

describe("the panel", () => {
  it("says nothing is embedded rather than rendering an empty panel", () => {
    const w = load();
    w.renderScenariosPanel();
    const body = w.document.getElementById("scenarios-panel-body").innerHTML;
    expect(body).toContain("No scenario map embedded");
  });

  it("is registered as one of the page's side panels", () => {
    const w = load();
    // Asserted through the page's own mechanism rather than against a
    // list written here: a panel the page does not know about cannot
    // be opened, closed or deep-linked.
    expect(w.document.getElementById("scenarios-panel")).not.toBeNull();
    expect(w.document.getElementById("scenarios-btn")).not.toBeNull();
    expect(w.document.getElementById("scenarios-backdrop")).not.toBeNull();
  });
});

describe("what the map may not contain", () => {
  it("the target carries a STATE, never a href the map authored", () => {
    // Criterion 3: the page constructs the link. If a map entry could
    // supply one, a route change would break it silently.
    const w = load();
    const target = w.scenarioTarget(PLACED);
    expect(Object.keys(target).sort()).toEqual(["asOf", "nav"]);
    expect(JSON.stringify(target)).not.toContain("http");
    expect(JSON.stringify(target)).not.toContain("#/");
  });

  it("a coordinate that already looks like a URL is still not followed", () => {
    const w = load();
    expect(w.scenarioTarget(entry({
      coordinates: { dataset: "https://example.test/evil", period: "p", asOf: "2026-01-01" },
    }))).toBeNull();
  });
});
