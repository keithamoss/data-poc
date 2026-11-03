// REQ-DASH-299 criteria 9, 10, 12 and 16: the census-years tile, the
// geocodes tile and the year checks' trend breaks. Generic on purpose - the
// tile reads any recorded list-setting version, the relation tile any dataset
// linking one source with no code - and these are the branches no generated
// page reaches: the fourth version (2027-08-01) is after the history ends.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = (opts) => (dashboard = loadDashboard(opts)).window;
const host = (w, html) => { const d = w.document.createElement("div"); d.innerHTML = html; return d; };

const set = (version, members, added) => ({ setting: "census_years", label: "Census years", version, members, added });
const VERSIONS = [
  ["2013-03-01", set("2013-01-01", [2011], [])],
  ["2017-09-01", set("2017-08-01", [2011, 2016], [2016])],
  ["2022-09-01", set("2022-08-01", [2011, 2016, 2021], [2021])],
  ["2027-09-01", set("2027-08-01", [2011, 2016, 2021, 2026], [2026])],
];
const geoPage = (entries) => ({ id: "geo", columns: [{ name: "census_year", checks: [{
  check_id: "a.b.c.geo.census_year.missing_set_members_dbt",
  history: entries.map(([run_date, member_set], rank) => ({ run_date, rank, member_set })) }] }] });

describe("the census-years tile (criterion 9)", () => {
  it("names the set each recorded version held, its sub-line only where it added one", () => {
    const w = load();
    const ds = geoPage(VERSIONS);
    const at = (date) => host(w, w.listSettingTilesHtml(ds, date));
    const first = at("2015-06-30");
    expect(first.querySelector(".k").textContent).toBe("Census years");
    expect(first.querySelector("[data-list-setting-members]").textContent).toBe("2011");
    expect(first.querySelector("[data-list-setting-added]")).toBeNull();
    expect(at("2020-01-01").querySelector("[data-list-setting-members]").textContent).toBe("2011, 2016");
    expect(at("2020-01-01").querySelector("[data-list-setting-added]").textContent).toBe("2016 added on 1 Aug 2017");
    expect(at("2024-01-01").querySelector("[data-list-setting-members]").textContent).toBe("2011, 2016, 2021");
  });

  it("reads a recorded fourth version '2026 added on 1 Aug 2027'", () => {
    const w = load();
    const tile = host(w, w.listSettingTilesHtml(geoPage(VERSIONS), "2028-01-01"));
    expect(tile.querySelector("[data-list-setting-members]").textContent).toBe("2011, 2016, 2021, 2026");
    expect(tile.querySelector("[data-list-setting-added]").textContent).toBe("2026 added on 1 Aug 2027");
  });

  it("shows no tile on a date before the dataset's first recorded result", () => {
    const w = load();
    expect(w.listSettingTilesHtml(geoPage(VERSIONS), "2012-12-31")).toBe("");
    expect(w.listSettingTilesHtml({ id: "x", columns: [{ checks: [{ history: [{ run_date: "2020-01-01" }] }] }] }, "2021-01-01")).toBe("");
  });
});

describe("the geocodes tile (criterion 10)", () => {
  const HIERARCHY = { agencies: [
    { id: "ag-one", name: "Agency One", collections: [
      { id: "registers", name: "Registers", datasets: [{ id: "people", name: "People Register" }] }] },
    { id: "ag-two", name: "Agency Two", collections: [
      { id: "places", name: "Places", datasets: [{ id: "people-places", name: "People Places" }] }] }] };
  const raw = (id, name, extra = {}) => ({ id, name, provider: "P", deliveryFormat: "CSV", sla: null,
    runs: [], columns: [], closedSlots: [], runStates: {}, promotionTimeline: { points: [], standing: [] }, ...extra });
  const page = (linked) => {
    const data = { registers: { datasets: [raw("people", "People Register")] },
                   places: { datasets: [raw("people-places", "People Places", linked ? { linkedSource: linked } : {})] } };
    const html = readFileSync(TEMPLATE_PATH, "utf-8").replace("const COLLECTION_DATA = null;",
      `const COLLECTION_DATA = ${JSON.stringify(data)};`);
    return load({ html, hierarchy: HIERARCHY });
  };

  it("names the source in the long form, keyed by the dataset's word, as a real link", () => {
    const w = page({ datasetId: "people", relation: "Geocodes" });
    const tile = host(w, w.linkedSourceTileHtml({ id: "people-places" }));
    expect(tile.querySelector(".k").textContent).toBe("Geocodes");
    expect(tile.querySelector("[data-linked-source-name]").textContent).toBe("Registers' People Register");
    const link = tile.querySelector("a.dataset-link");
    expect(link).not.toBeNull();
    expect(JSON.parse(link.dataset.nav)).toMatchObject({ tier: "dataset", datasetId: "people", collectionId: "registers" });
  });

  it("is absent for a dataset that links no single source with no code", () => {
    const w = page(null);
    expect(w.linkedSourceTileHtml({ id: "people-places" })).toBe("");
  });
});

describe("the year checks' trend breaks (criterion 12)", () => {
  it("draws a breaking marker between the points either side of each widening", () => {
    const w = load();
    const dates = ["2016-05-01", "2017-05-01", "2017-11-01", "2021-05-01", "2022-11-01", "2027-05-01", "2027-11-01"];
    const history = dates.map((d, i) => ({ run_id: `r${i}`, run_date: d, date: new Date(`${d}T00:00:00Z`), value: 0, status: "green" }));
    const changelog = ["2017-08-01", "2022-08-01", "2027-08-01"].map((d) => ({
      date: new Date(`${d}T00:00:00Z`), description: "The set widens.", author: "K", breaking: true }));
    const svg = w.trendChart({ history, warn: null, fail: 0, unit: "count", changelog }, null, null, null);
    expect((svg.match(/class="break-glyph"/g) || []).length).toBe(3);
  });
});
