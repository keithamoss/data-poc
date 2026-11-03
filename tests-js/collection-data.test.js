// REQ-DASH-244 criteria 4, 5, 6 and 17: every real collection's datasets come
// from one COLLECTION_DATA const and are built by one function, through one
// dataset-id index - so a THIRD collection, present only in the embedded data
// and the hierarchy, gets its tiles with no page code of its own.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";

const raw = (id, name, provider) => ({
  id, name, provider, deliveryFormat: "CSV", sla: null, runs: [], columns: [],
  closedSlots: [], runStates: {}, promotionTimeline: {points: [], standing: []},
});

const DATA = {
  "civil-registration": {datasets: [raw("birth-registrations", "Birth Registrations", "BDM")]},
  "child-protection": {datasets: [raw("cp-clients", "Clients", "DCPFS"), raw("cp-carers", "Carers", "DCPFS")]},
  "fake-collection": {datasets: [raw("fake-things", "Fake Things", "The Fake Agency")]},
};

const HIERARCHY = {agencies: [
  {id: "registry-services", name: "Registry Services", collections: [
    {id: "civil-registration", name: "Civil Registration",
     datasets: [{id: "birth-registrations", name: "Birth Registrations"}]}]},
  {id: "child-protection-family-support", name: "Child Protection and Family Support", collections: [
    {id: "child-protection", name: "Child Protection",
     datasets: [{id: "cp-clients", name: "Clients"}, {id: "cp-carers", name: "Carers"}]}]},
  {id: "fake-agency", name: "Fake Agency", collections: [
    {id: "fake-collection", name: "Fake Collection",
     datasets: [{id: "fake-things", name: "Fake Things"}]}]},
]};

let dashboard;
afterEach(() => dashboard && dashboard.close());

const load = (data) => {
  const html = readFileSync(TEMPLATE_PATH, "utf-8").replace("const COLLECTION_DATA = null;",
    `const COLLECTION_DATA = ${JSON.stringify(data)};`);
  dashboard = loadDashboard({html, hierarchy: HIERARCHY});
  return dashboard.window;
};

describe("REQ-DASH-244: one COLLECTION_DATA const, one build function", () => {
  it("lists every collection's raw datasets in the order they are embedded", () => {
    const w = load(DATA);
    expect(w.rawRealDatasets().map(d => d.id))
      .toEqual(["birth-registrations", "cp-clients", "cp-carers", "fake-things"]);
  });

  it("finds a third collection's dataset by its id alone", () => {
    const w = load(DATA);
    expect(w.rawRealDatasetById("fake-things").provider).toBe("The Fake Agency");
    expect(w.rawRealDatasetById("no-such-dataset")).toBeNull();
  });

  it("gives a third collection with no recorded runs a no-data tile from its own data", () => {
    const w = load(DATA);
    const built = w.buildDatasetsOn("2026-10-01");
    const fake = built.agencies.find(a => a.id === "fake-agency").collections[0].datasets[0];
    expect(fake.id).toBe("fake-things");
    expect(fake.noDataInPlaceOn).toBe(true);
    // From the embedded data, not the hierarchy's fallback: the fallback has
    // no provider at all.
    expect(fake.provider).toBe("The Fake Agency");
  });

  it("builds a collection's datasets once per date, whichever dataset asks first", () => {
    const w = load(DATA);
    const cache = {};
    const carers = w.datasetTile("cp-carers", "2026-10-01", cache);
    const clients = w.datasetTile("cp-clients", "2026-10-01", cache);
    expect([carers.id, clients.id]).toEqual(["cp-carers", "cp-clients"]);
    expect(Object.keys(cache)).toEqual(["collection:child-protection"]);
  });

  it("renders the raw template, with nothing embedded, as before", () => {
    const w = load(null);
    expect(w.rawRealDatasets()).toEqual([]);
    expect(w.buildCollectionDatasets("child-protection", "2026-10-01")).toEqual([]);
  });
});
