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

// The template with a scenario map embedded, as a build of a synthetic asset
// has (an empty map has no scenarios page at all, REQ-PIPE-385).
function withMap(entries) {
  return require("node:fs").readFileSync(
    require("node:path").join(__dirname, "..", "dashboard", "qa-reporting-dashboard.template.html"),
    "utf-8").replace("const SCENARIO_MAP = [];", `const SCENARIO_MAP = ${JSON.stringify(entries)};`);
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
    period: "2026-Q3", inPlaceOn: "2026-08-15",
  },
});

describe("turning coordinates into a target", () => {
  it("resolves a dataset id to its own page, with the as-of date the entry names", () => {
    const w = load();
    const target = w.scenarioTarget(PLACED);
    expect(target.inPlaceOn).toBe("2026-08-15");
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
      coordinates: { dataset: "Carer Register", period: "2026-Q3", inPlaceOn: "2026-08-15" },
    }));
    expect(target.nav.datasetId).toBe("cp-carers");
  });

  it("resolves a collection to its agency page", () => {
    const w = load();
    const target = w.scenarioTarget(entry({
      coordinates: { dataset: "child-protection", period: "2026-Q3", inPlaceOn: "2026-08-15" },
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
      coordinates: { dataset: "a-dataset-that-never-existed", period: "p", inPlaceOn: "2026-01-01" },
    }))).toBeNull();
  });
});

describe("the panel", () => {
  // REQ-DASH-139 criterion 1: a top-level tab with a URL of its own, beside
  // Plans and Demo, in place of REQ-DASH-046's drawer.
  it("is a top-level tab with a route of its own, not a drawer", () => {
    const w = load();
    expect(w.stateToPath({tier: "scenarios"})).toBe("/scenarios");
    expect(w.pathToState("/scenarios")).toEqual({tier: "scenarios"});
    expect(w.document.getElementById("scenarios-btn")).not.toBeNull();
    expect(w.document.getElementById("scenarios-panel")).toBeNull();
  });

  it("opens from a saved ?panel=scenarios link", () => {
    const w = loadDashboard({html: withMap([PLACED]), url: "http://localhost/?panel=scenarios"}).window;
    expect(w.stateFromLocation()).toEqual({tier: "scenarios"});
  });

  it("drops the old parameter once it has opened the tab", () => {
    // Sprint 11 critic, defect 2: left in the address bar it took over
    // every later reload and every copied link - click Plans, reload, and
    // the page showed Scenarios.
    const w = loadDashboard({html: withMap([PLACED]),
                             url: "http://localhost/?panel=scenarios&theme=dark"}).window;
    expect(new URLSearchParams(w.location.search).get("panel")).toBeNull();
    expect(new URLSearchParams(w.location.search).get("theme")).toBe("dark");
    expect(w.location.hash).toBe("#/scenarios");
  });
});

describe("what the map may not contain", () => {
  it("the target carries a STATE, never a href the map authored", () => {
    // Criterion 3: the page constructs the link. If a map entry could
    // supply one, a route change would break it silently.
    const w = load();
    const target = w.scenarioTarget(PLACED);
    expect(Object.keys(target).sort()).toEqual(["inPlaceOn", "nav"]);
    expect(JSON.stringify(target)).not.toContain("http");
    expect(JSON.stringify(target)).not.toContain("#/");
  });

  it("a coordinate that already looks like a URL is still not followed", () => {
    const w = load();
    expect(w.scenarioTarget(entry({
      coordinates: { dataset: "https://example.test/evil", period: "p", inPlaceOn: "2026-01-01" },
    }))).toBeNull();
  });
});

// REQ-DASH-139 criterion 3: each scenario shows the requirements it
// demonstrates and whether it has data behind it yet.
describe("what each entry says", () => {
  it("names the requirements it demonstrates, and says when nothing is behind it", () => {
    const w = load();
    const html = w.scenarioEntryHtml(entry({requirements: ["REQ-PIPE-118"]}), 0);
    const view = w.document.createElement("div");
    view.innerHTML = html;
    expect(view.querySelector("[data-demonstrates]").textContent).toContain("REQ-PIPE-118");
    expect(view.textContent).toContain("no data behind it yet");
  });
});

describe("the mode pill says what is true (#121 D9)", () => {
  it("an injected scenario nothing has placed is planned, not in the data", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const html = w.scenarioModePill({ mode: "INJECT" }, null);
    expect(html).toContain("Planned for the data");
    expect(html).not.toContain("nodata");
    expect(w.scenarioModePill({ mode: "INJECT" }, { nav: {} })).toContain("In the data");
  });
});

// REQ-PIPE-385 criteria 11 and 13: a page built with no scenario map - an
// asset with no synthetic history - has no scenario button, and every old
// scenario address lands on the plain not-found page.
describe("a page with no scenario map", () => {
  function open(url) {
    dashboard = loadDashboard({ hierarchy: HIERARCHY, url });
    return dashboard.window;
  }
  const notFound = (w) => w.document.querySelector("#view h2")?.textContent;

  it("shows no Scenarios button", () => {
    const w = open("http://localhost/");
    expect(w.document.getElementById("scenarios-btn").hidden).toBe(true);
  });

  it("shows the button once a map is embedded", () => {
    dashboard = loadDashboard({ html: withMap([PLACED]), hierarchy: HIERARCHY });
    expect(dashboard.window.document.getElementById("scenarios-btn").hidden).toBe(false);
  });

  it("answers /scenarios with the not-found page, naming the word back", () => {
    const w = open("http://localhost/#/scenarios");
    expect(notFound(w)).toBe("Page not found");
    expect(w.document.querySelector("#view code").textContent).toBe("scenarios");
    expect(w.document.title).toMatch(/^Page not found/);
    expect(w.document.getElementById("route-announcer").textContent).toBe("Page not found");
  });

  it.each([
    ["?panel=scenarios", "panel"],
    ["?scenario=ts-12", "scenario"],
  ])("lands %s on the not-found page and drops the parameter", (query, param) => {
    const w = open(`http://localhost/${query}&theme=dark`);
    expect(notFound(w)).toBe("Page not found");
    expect(w.document.title).toMatch(/^Page not found/);
    const search = new URLSearchParams(w.location.search);
    expect(search.get(param)).toBeNull();
    expect(search.get("theme")).toBe("dark");
    // A reload then opens the rest of the address, not the not-found page.
    expect(w.stateFromLocation().tier).not.toBe("scenarios");
  });
});
