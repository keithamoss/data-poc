// REQ-DASH-337: a check that reads another collection is grouped by that
// collection, names and links the dataset it is about, and shows on that
// dataset's page with its effect, its percentage and its cause - all
// generically. Every name here is INVENTED on purpose (Keith, 2026-10-28:
// "nothing special-cased"): the page learns collections, datasets and their
// order from the hierarchy and the embedded data, so made-up ones must work
// exactly as real ones do. The real-browser half is tests/test_dashboard_e2e.py.
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

// Two agencies; the second holds two collections, so a check declared in
// "Matches" reads a dataset of "Registers" - another agency's collection.
const HIERARCHY = { agencies: [
  { id: "ag-one", name: "Agency One", collections: [
    { id: "registers", name: "Registers", datasets: [
      { id: "people", name: "People Register" }, { id: "events", name: "Events" }] }] },
  { id: "ag-two", name: "Agency Two", collections: [
    { id: "visits", name: "Visits", datasets: [{ id: "visit-log", name: "Visit Log" }] },
    { id: "matches", name: "Matches", datasets: [{ id: "match-keys", name: "Match Keys" }] }] },
] };

const PERIOD = "2026-Q2";
const SUPPLY = "people@1";
const RUN = { run_id: "people__1", supply_id: SUPPLY, run_date: "2026-05-02" };
const DUE = "2026-06-30T08:00:00+00:00";

const raw = (id, name, extra = {}) => ({ id, name, provider: "P", deliveryFormat: "CSV", sla: null,
  runs: [], columns: [], closedSlots: [], runStates: {}, promotionTimeline: { points: [], standing: [] },
  ...extra });

function data(extra = {}) {
  return {
    registers: { datasets: [
      raw("people", "People Register", { runs: [RUN], arrivalByRun: { [RUN.run_id]: { slot: PERIOD } },
                                         ...(extra.people || {}) }),
      raw("events", "Events")] },
    visits: { datasets: [raw("visit-log", "Visit Log")] },
    matches: { datasets: [raw("match-keys", "Match Keys", {
      periodSlots: { slots: [{ period: PERIOD, opens: "2026-05-01T00:00:00+00:00", due: DUE }] },
      ...(extra.matchKeys || {}) })] },
  };
}

function load(extra) {
  const html = readFileSync(TEMPLATE_PATH, "utf-8").replace("const COLLECTION_DATA = null;",
    `const COLLECTION_DATA = ${JSON.stringify(data(extra))};`);
  dashboard = loadDashboard({ html, hierarchy: HIERARCHY });
  return dashboard.window;
}

const COL = { id: "registers", datasets: [{ id: "people", name: "People Register" },
                                          { id: "events", name: "Events" }] };

// One tool's card of a cross-table check. `result` gives it a result about
// the supply on show, in the warehouse cell.
function card(name, between, { tool = "soda", status = "green", value = 0, unit = "count", result = true } = {}) {
  return {
    key: `${name}_${tool}`, name, tool_ref: `${tool}:${name}`, current_status: status, unit, between,
    history: result ? [{ run_id: "m__1", rank: 4, supply_id: SUPPLY, status, value }] : [],
    placed: result ? { 4: [{ on: "2026-05-02", bucket: "warehouse", note: [], sentence: [] }] } : {},
  };
}
const FROM_MATCHES = { declared_on: "match-keys", reads: ["people"] };
const FROM_VISITS = { declared_on: "visit-log", reads: ["people"] };
const OWN = { declared_on: "events", reads: ["people"] };

function grid(w, cards) {
  const c = { name: "Cross-table checks", key: "cross-table", scope: "cross-table" };
  const ds = { id: "people", runs: [RUN] };
  const rows = w.crossTableGridRows(COL, ds, cards.map((ck) => ({ c, ck })), "2026-05-02");
  const out = w.crossTableGridHtml(rows);
  const host = w.document.createElement("div");
  host.innerHTML = out.html;
  w.document.body.appendChild(host);
  return { rows, host };
}

describe("names resolved across the asset (criterion 2)", () => {
  it("names another collection's dataset with its collection", () => {
    const w = load();
    expect(w.crossTableBetween(COL, { between: FROM_MATCHES })).toBe("Match Keys (Matches) → People Register");
  });

  it("names the page's own collection's datasets as before", () => {
    const w = load();
    expect(w.crossTableBetween(COL, { between: OWN })).toBe("Events → People Register");
  });

  it("names another collection's run by its dataset's name", () => {
    const w = load();
    const note = w.recheckNote(COL, { recorded_by: "match-keys", recorded_at: "2026-05-02T01:00:00+00:00" });
    expect(note).toContain("when the Match Keys supply arrived");
  });

  it("links both tables in the check's panel, outside any button", () => {
    const w = load();
    const host = w.document.createElement("div");
    host.innerHTML = w.xtBetweenLinksHtml(COL, { between: FROM_MATCHES });
    const links = [...host.querySelectorAll("a.dataset-link")];
    expect(links.map((a) => a.textContent)).toEqual(["Match Keys", "People Register"]);
    expect(links.every((a) => a.getAttribute("href"))).toBe(true);
    expect(host.textContent).toContain("(Matches)");
    expect(host.querySelector("button a")).toBeNull();
    // And nothing extra on a check involving only the page's collection.
    expect(w.xtBetweenLinksHtml(COL, { between: OWN })).toBe("");
  });
});

describe("grouped by the other collection (criteria 6 and 7)", () => {
  const cards = () => [
    card("from_matches", FROM_MATCHES, { status: "red" }),
    card("own", OWN, { status: "green" }),
    card("from_visits", FROM_VISITS, { status: "amber" }),
    card("from_matches_2", FROM_MATCHES, { status: "green" }),
  ];

  it("shows the page's own checks first, ungrouped, then a group per collection in hierarchy order", () => {
    const w = load();
    const { rows, host } = grid(w, cards());
    expect(rows.map((r) => r.group)).toEqual([null, "visits", "matches", "matches"]);
    const groups = [...host.querySelectorAll(".xt-group")].map((g) => g.dataset.xtGroup);
    expect(groups).toEqual(["visits", "matches"]);
    const firstGrid = host.querySelector(".xt-grid");
    expect(firstGrid.classList.contains("xt-group-body")).toBe(false);
    expect(firstGrid.querySelectorAll(".xt-row").length).toBe(1);
  });

  it("collapses every group on load, a failing one too, under a summary heading", () => {
    const w = load();
    const { host } = grid(w, cards());
    const matches = host.querySelector('[data-xt-group="matches"]');
    const toggle = matches.querySelector(".xt-group-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(matches.querySelector(".xt-group-body").hidden).toBe(true);
    expect(matches.dataset.xtGroupStatus).toBe("red");
    expect(toggle.textContent).toContain("Matches");
    expect(toggle.querySelector(".pill.red")).not.toBeNull();
    expect(toggle.textContent).toContain("2 checks: 1 red, 1 green");
  });

  it("opens on click and keeps nothing in the URL", () => {
    const w = load();
    const { host } = grid(w, cards());
    w.wireXtGroups(host);
    const before = w.location.href;
    const toggle = host.querySelector('[data-xt-group="matches"] .xt-group-toggle');
    toggle.click();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(host.querySelector('[data-xt-group="matches"] .xt-group-body').hidden).toBe(false);
    expect(w.location.href).toBe(before);
  });

  it("links the group's datasets beside the toggle, never inside it", () => {
    const w = load();
    const { host } = grid(w, cards());
    const head = host.querySelector('[data-xt-group="matches"] .xt-group-head');
    expect([...head.querySelectorAll("a.dataset-link")].map((a) => a.textContent)).toEqual(["Match Keys"]);
    expect(head.querySelector("button a")).toBeNull();
  });

  it("renders a page with no check involving another collection as before", () => {
    const w = load();
    const { host } = grid(w, [card("own", OWN)]);
    expect(host.querySelector(".xt-group")).toBeNull();
    expect(host.children.length).toBe(1);
    expect(host.firstElementChild.classList.contains("xt-grid")).toBe(true);
  });
});

describe("a percentage in the grid cell (criterion 10)", () => {
  it("shows the recorded percentage beside the word, for any percentage result", () => {
    const w = load();
    const { rows } = grid(w, [card("share", FROM_MATCHES, { status: "amber", value: 87.34, unit: "%" })]);
    expect(w.xtCellText(rows[0], "warehouse").word).toBe("Warn 87.3%");
  });

  it("shows no number for a result that is not a percentage", () => {
    const w = load();
    const { rows } = grid(w, [card("count", FROM_MATCHES, { status: "red", value: 4 })]);
    expect(w.xtCellText(rows[0], "warehouse").word).toBe("Fail");
  });
});

describe("not yet checked, with its due date (criterion 8)", () => {
  it("says which dataset it waits on and when that is due", () => {
    const w = load();
    const { rows, host } = grid(w, [card("ref", FROM_MATCHES, { result: false })]);
    expect(rows[0].waiting).toMatchObject({ datasetId: "match-keys", period: PERIOD, due: DUE });
    const cell = host.querySelector("[data-not-yet-checked]");
    expect(cell.textContent).toContain(`Not yet checked by Match Keys - due ${w.fmtInstant(DUE)}`);
  });

  it("says nothing once that dataset has arrived for the period", () => {
    const w = load({ matchKeys: { runs: [{ run_id: "m__1", run_date: "2026-05-01" }],
                                  arrivalByRun: { m__1: { slot: PERIOD } } } });
    const { rows } = grid(w, [card("ref", FROM_MATCHES, { result: false })]);
    expect(rows[0].waiting).toBeNull();
  });
});

describe("the cause named in full where it is another collection's (criterion 11)", () => {
  it("names another collection's cause '<collection>' <period> <dataset>'", () => {
    const w = load();
    expect(w.causeName("people", "match-keys", PERIOD, false))
      .toBe(`Matches' ${w.fmtPeriodOrDay(PERIOD)} Match Keys`);
  });

  it("keeps the short form plus the period within the collection", () => {
    const w = load();
    expect(w.causeName("people", "events", PERIOD, false)).toBe(`${w.fmtPeriodOrDay(PERIOD)} Events`);
  });

  it("names it so in the no-promoted notice, and the same-collection notice as before", () => {
    const w = load();
    const host = w.document.createElement("div");
    host.innerHTML = w.noPromotedLineHtml({ datasetId: "match-keys", period: PERIOD, n: 2 }, false, false, "people");
    expect(host.textContent).toContain(`No promoted Matches' ${w.fmtPeriodOrDay(PERIOD)} Match Keys.`);
    host.innerHTML = w.noPromotedLineHtml({ datasetId: "events", period: PERIOD, n: 2 }, false, false, "people");
    expect(host.textContent).toContain(`No promoted Events for ${w.fmtPeriodOrDay(PERIOD)}.`);
  });
});

// A promoted supply that went in green and that another collection's result
// later turned amber, then red.
const PROMOTED = { [RUN.run_id]: [{ at: "2026-05-03T01:00:00+00:00", state: "promoted", action: "promote" }] };
const step = (at, status) => ({ at, status, cause: "the arrival of Match Keys",
  causeAction: "arrival", causeDataset: "match-keys", causePeriod: PERIOD });
function health(...timeline) {
  return { [RUN.run_id]: { promotedOn: "green", promotedAt: "2026-05-03T01:00:00+00:00", timeline } };
}

describe("the amber tag (criterion 9) and the red-promoted badge (criteria 4 and 11)", () => {
  const amber = () => load({ people: { runStates: PROMOTED, promotedHealth: health(
    step("2026-05-02T01:00:00+00:00", "green"), step("2026-05-10T01:00:00+00:00", "amber")) } });

  it("tags a supply a cross-table result turned amber, naming the cause in full", () => {
    const w = amber();
    const host = w.document.createElement("div");
    host.innerHTML = w.amberPromotedTag("people", RUN.run_id, "2026-05-11");
    expect(host.querySelector(".pill.amber").textContent.trim()).toBe("Amber promoted");
    expect(host.querySelector("[data-amber-promoted-why]").textContent).toBe(
      `Went in green. Amber since the arrival of Matches' ${w.fmtPeriodOrDay(PERIOD)} Match Keys, `
      + `${w.fmtInstant("2026-05-10T01:00:00+00:00")}.`);
  });

  it("shows the supply as it was before the amber began to count", () => {
    const w = amber();
    expect(w.amberPromotedTag("people", RUN.run_id, "2026-05-05")).toBe("");
  });

  it("gives a sibling's amber the same tag, in the short form", () => {
    const w = load({ people: { runStates: PROMOTED, promotedHealth: health(
      step("2026-05-02T01:00:00+00:00", "green"),
      { ...step("2026-05-10T01:00:00+00:00", "amber"), causeDataset: "events" }) } });
    const host = w.document.createElement("div");
    host.innerHTML = w.amberPromotedTag("people", RUN.run_id, "2026-05-11");
    expect(host.textContent).toContain(`Amber since the arrival of ${w.fmtPeriodOrDay(PERIOD)} Events`);
    // The dataset a real link (REQ-DASH-272 criterion 15).
    expect(host.querySelector("[data-amber-promoted-why] a.dataset-link").textContent).toBe("Events");
  });

  it("is not shown for a supply that went in amber", () => {
    const w = load({ people: { runStates: PROMOTED, promotedHealth: { [RUN.run_id]: {
      ...health(step("2026-05-10T01:00:00+00:00", "amber"))[RUN.run_id], promotedOn: "amber" } } } });
    expect(w.amberPromotedTag("people", RUN.run_id, "2026-05-11")).toBe("");
  });

  it("names another collection's cause in full on the red-promoted badge", () => {
    const w = load({ people: { runStates: PROMOTED, promotedHealth: health(
      step("2026-05-02T01:00:00+00:00", "green"), step("2026-05-10T01:00:00+00:00", "red")) } });
    const html = w.redPromotedBadge("people", RUN.run_id, "2026-05-11");
    expect(html).toContain("data-red-promoted");
    expect(html).toContain(`after the arrival of Matches' ${w.fmtPeriodOrDay(PERIOD)}`);
    expect(w.redPromotedBadge("people", RUN.run_id, "2026-05-05")).toContain("data-turns-red-later");
  });
});

describe("a band in the direction its result records (criterion 13)", () => {
  it("words a below-band as below, in the recorded unit", () => {
    const w = load();
    expect(w.bandParts({ unit: "%", band: { warn: { op: "<", value: 90 }, fail: { op: "<", value: 85 } } }))
      .toEqual(["amber below 90%", "red below 85%"]);
  });

  it("words an above-band as above", () => {
    const w = load();
    expect(w.bandParts({ unit: "count", band: { fail: { op: ">", value: 0 } } })).toEqual(["red above 0"]);
  });
});

describe("a recorded distribution as a histogram (criterion 14)", () => {
  const DIST = { bins: [{ from: 51, to: 101, count: 6 }, { from: 101, to: 151, count: 2 },
                        { from: 151, to: null, count: 1 }], count: 9, population: 400 };

  it("draws one bar per recorded bin, each with its count as text", () => {
    const w = load();
    const host = w.document.createElement("div");
    host.innerHTML = w.distributionBlock({ history: [{ distribution: DIST }] }, null);
    const bins = [...host.querySelectorAll("[data-dist-bin]")];
    expect(bins.map((b) => b.querySelector(".dist-label").textContent)).toEqual(
      ["51 to 100", "101 to 150", "151 or more"]);
    expect(bins.map((b) => b.querySelector(".dist-count").textContent)).toEqual(["6", "2", "1"]);
    expect(host.textContent).toContain("9 counted of 400");
  });

  it("shows the point on show's own distribution", () => {
    const w = load();
    const older = { distribution: { bins: [{ from: 1, to: null, count: 3 }] } };
    const point = { distribution: DIST };
    const host = w.document.createElement("div");
    host.innerHTML = w.distributionBlock({ history: [older, point] }, point);
    expect(host.querySelectorAll("[data-dist-bin]").length).toBe(3);
  });

  it("shows nothing for a check that records none", () => {
    const w = load();
    expect(w.distributionBlock({ history: [{ value: 1 }] }, null)).toBe("");
  });
});

describe("one more collection is one more collection (criteria 1 and 5)", () => {
  it("shows every collection the hierarchy gives an agency, however many", () => {
    const w = load();
    const ag = HIERARCHY.agencies[1];
    const page = w.buildData("2026-05-11").agencies.find((a) => a.id === ag.id);
    expect(page.collections.map((c) => c.id)).toEqual(ag.collections.map((c) => c.id));
  });
});

// AN ARCHITECTURE RULE WITH NO BEHAVIOUR TO OBSERVE, so this one reads source
// (CLAUDE.md's test rule 1): the same no-name rule as REQ-PIPE-336 criterion 2.
describe("nothing coded for any one collection (criterion 15)", () => {
  const FORBIDDEN = [/linkage/i, /DOC_CLIENTS/, /EDDC_PRESENTATION/];
  const files = ["dashboard/qa-reporting-dashboard.template.html", "pipeline/build_dashboard_data.py",
                 "dashboard/embed_dashboard_data.py"];

  for (const file of files) {
    it(`${file} names no collection, dataset or supplier code of its own`, () => {
      const text = readFileSync(path.join(ROOT, file), "utf-8");
      expect(text.length).toBeGreaterThan(1000);
      for (const word of FORBIDDEN) expect(text).not.toMatch(word);
    });
  }
});
