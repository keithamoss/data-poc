// REQ-DASH-299, the post-build critic's findings (plans/post-build-review.md):
// the tiles stay on a blocked page (criterion 10, "WHILE shown"); every
// left-out reason's 'Not checked' comes through statusWords; the agency
// panel names a tool by its display name, never its raw key.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const HIERARCHY = { agencies: [
  { id: "ag-one", name: "Agency One", collections: [
    { id: "registers", name: "Registers", datasets: [{ id: "people", name: "People Register" }] }] },
  { id: "ag-two", name: "Agency Two", collections: [
    { id: "places", name: "Places", datasets: [{ id: "people-places", name: "People Places" }] }] }] };
const RUN = { run_id: "pp__1", supply_id: "pp@1", run_date: "2026-05-02", rank: 1 };
const raw = (id, name, extra = {}) => ({ id, name, provider: "P", deliveryFormat: "CSV",
  sla: { cadence: { kind: "quarterly" }, timeline: [] }, runs: [], columns: [], closedSlots: [], runStates: {},
  promotionTimeline: { points: [], standing: [] }, arrivalHistory: [], ...extra });
const CENSUS = { setting: "census_years", label: "Census years", version: "2022-08-01", members: [2011, 2016, 2021], added: [2021] };
const GEO = raw("people-places", "People Places", {
  runs: [RUN], linkedSource: { datasetId: "people", relation: "Geocodes" }, rowCount: 10, prevRowCount: 10,
  lastArrival: { run_id: "pp__1", run_date: "2026-05-02", arrivedAt: "2026-05-02T02:00:00+00:00", arrivalStatus: "on_time" },
  arrivalHistory: [{ run_date: "2026-05-02", arrivalStatus: "on_time" }],
  columns: [{ name: "census_year", stats: { current: { total: 10, invalid: 0 }, previous: { total: 10, invalid: 0 }, history: [] },
    checks: [{ check_id: "a.b.c.people-places.census_year.missing_set_members_dbt", key: "m", name: "m",
      tool_ref: "dbt:missing_set_members", current: 0, warn: null, fail: 0, current_status: "green", unit: "count", changelog: [],
      history: [{ run_id: "pp__1", rank: 1, run_date: "2026-05-02", value: 0, status: "green", member_set: CENSUS }] }] }] });

function page() {
  const data = { registers: { datasets: [raw("people", "People Register")] }, places: { datasets: [GEO] } };
  const html = readFileSync(TEMPLATE_PATH, "utf-8").replace("const COLLECTION_DATA = null;",
    `const COLLECTION_DATA = ${JSON.stringify(data)};`);
  dashboard = loadDashboard({ html, hierarchy: HIERARCHY,
    url: "http://localhost/?in-place-on=2026-05-10#/agency/ag-two/collection/places/dataset/people-places" });
  return dashboard.window;
}
const HELD = { kind: "held", datasetId: "people-places", supply: "pp@2", openedAt: "2026-05-08T02:00:00+00:00",
  resolvedAt: null, reason: "held", files: [], loadFailures: [] };

describe("the tiles on a blocked page (criterion 10)", () => {
  it("keeps the Geocodes and Census years tiles while its supply waits for a person", () => {
    const w = page();
    w.blockerOpenInPlaceOn = (id) => (id === "people-places" ? { ...HELD, count: 1, newestAt: HELD.openedAt } : null);
    w.blockerWithoutARunOfItsOwn = () => ({ ...HELD, count: 1 });
    w.setInPlaceOnQuietly("2026-05-11");
    w.render();
    const strip = w.document.querySelector(".sla-strip");
    expect(strip.textContent).toContain("Waiting since");
    expect(strip.querySelector('[data-linked-source="people"] .k').textContent).toBe("Geocodes");
    expect(strip.querySelector('[data-list-setting="census_years"] [data-list-setting-members]').textContent)
      .toBe("2011, 2016, 2021");
  });
});

describe("a left-out reason's words (critic item 3)", () => {
  it("takes 'Not checked' from statusWords, for every code", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const real = w.statusWords;
    w.statusWords = (v, f) => (v === "notchecked" ? "LEFT OUT" : real(v, f));
    for (const code of ["not_in_agreement", "not_supplied_by_decision", "calendar_differs"]) {
      expect(w.notInAgreementReason({ code, period: "2026-Q2", dataset: "x", calendar: "monthly" }))
        .toMatch(/^LEFT OUT: /);
    }
  });
});

describe("the agency panel's tool (critic item 7)", () => {
  it("names the tool by its display name", () => {
    dashboard = loadDashboard({ hierarchy: HIERARCHY });
    const w = dashboard.window;
    const ck = { check_id: "a.ag-two.places.people-places.x.y_datacontract", key: "x", name: "Theirs",
      tool_ref: "datacontract:coverage", current_status: "green", history: [],
      between: { declared_on: "people-places", reads: ["people"] } };
    const host = w.document.createElement("div");
    host.innerHTML = w.collectionCrossTableSection({ id: "ag-two" },
      { id: "places", datasets: [{ id: "people-places", name: "People Places", columns: [{ scope: "cross-table", checks: [ck] }] }] });
    const ds = host.querySelector("[data-across-collections] .ds").textContent;
    expect(ds).toContain("· datacontract-cli");
    expect(ds).not.toMatch(/· datacontract$/);
  });
});
