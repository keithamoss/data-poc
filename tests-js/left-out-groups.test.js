// REQ-DASH-299 criteria 14, 16 and 18 - amendments A1 and A5 to REQ-DASH-337:
// a cross-table check left out for the period sits in its collection's group,
// a quiet 'Not checked' row; the group's pill is the worst of its EVALUATED
// checks, its count ends '<n> not checked', and a group whose every row is
// left out reads 'Not checked' - never Pass, never 'No data', never a
// collection group's 'Not counted'. Invented names (REQ-DASH-337 c15).
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const HIERARCHY = { agencies: [
  { id: "ag-one", name: "Agency One", collections: [
    { id: "registers", name: "Registers", datasets: [{ id: "people", name: "People Register" }] }] },
  { id: "ag-two", name: "Agency Two", collections: [
    { id: "matches", name: "Matches", datasets: [{ id: "match-keys", name: "Match Keys" }] }] },
] };
const RUN = { run_id: "m__1", supply_id: "match-keys@1", run_date: "2026-05-02" };
const raw = (id, name, extra = {}) => ({ id, name, provider: "P", deliveryFormat: "CSV", sla: null,
  runs: [], columns: [], closedSlots: [], runStates: {}, promotionTimeline: { points: [], standing: [] }, ...extra });

function load() {
  // The embedded data as tests-js/cross-collection.test.js gives it: each
  // dataset with the fields the page's start-up reads.
  const data = {
    registers: { datasets: [raw("people", "People Register")] },
    matches: { datasets: [raw("match-keys", "Match Keys", { runs: [RUN], arrivalByRun: { [RUN.run_id]: { slot: "2026-Q2" } },
      periodSlots: { slots: [{ period: "2026-Q2", opens: "2026-05-01T00:00:00+00:00", due: "2026-06-30T08:00:00+00:00" }] } })] },
  };
  const html = readFileSync(TEMPLATE_PATH, "utf-8").replace("const COLLECTION_DATA = null;",
    `const COLLECTION_DATA = ${JSON.stringify(data)};`);
  dashboard = loadDashboard({ html, hierarchy: HIERARCHY });
  return dashboard.window;
}
const COL = { id: "matches", datasets: [{ id: "match-keys", name: "Match Keys" }] };
const BETWEEN = { declared_on: "match-keys", reads: ["people"] };
function card(name, status) {
  return { key: `${name}_soda`, check_id: `a.ag-two.matches.match-keys.${name}.x_soda`, name,
    tool_ref: `soda:${name}`, current_status: status, unit: "count", between: BETWEEN,
    history: [{ run_id: "m__1", rank: 4, supply_id: RUN.supply_id, status, value: 0 }],
    placed: { 4: [{ on: "2026-05-02", bucket: "warehouse", note: [], sentence: [] }] } };
}
function leftOut(name) {
  return { entry: { runId: "m__1", checkId: `a.ag-two.matches.match-keys.${name}.y_soda`, code: "not_supplied_by_decision",
    period: "2026-Q2", dataset: "people", between: BETWEEN },
    ck: { check_id: `a.ag-two.matches.match-keys.${name}.y_soda`, key: name, name, tool_ref: `soda:${name}` } };
}
function grid(w, cards, outs) {
  const c = { name: "Cross-table checks", key: "cross-table", scope: "cross-table" };
  const rows = w.crossTableGridRows(COL, { id: "match-keys", runs: [RUN] }, cards.map((ck) => ({ c, ck })), "2026-05-02");
  const host = w.document.createElement("div");
  host.innerHTML = w.crossTableGridHtml(rows, w.leftOutRowModels(COL, outs)).html;
  w.wireNotInAgreement(host, COL, outs);
  return host;
}

describe("a group mixing evaluated and left-out checks (A5)", () => {
  it("takes its pill from the evaluated checks and counts the rest 'not checked' after them", () => {
    const w = load();
    const host = grid(w, [card("first", "green")], [leftOut("second"), leftOut("third")]);
    const group = host.querySelector('[data-xt-group="registers"]');
    expect(group).not.toBeNull();
    expect(group.dataset.xtGroupStatus).toBe("green");
    expect(group.querySelector(".xt-group-head .pill").textContent).toBe("Pass");
    expect(group.querySelector(".xt-group-counts").textContent).toBe("3 checks: 1 passing, 2 not checked");
    expect(group.querySelectorAll(".xt-left-out")).toHaveLength(2);
    expect(group.querySelectorAll("[data-not-checked-note]")).toHaveLength(1);
  });

  it("lets a left-out row lose to a failing one, never hide it", () => {
    const w = load();
    const group = grid(w, [card("first", "red")], [leftOut("second")]).querySelector(".xt-group");
    expect(group.dataset.xtGroupStatus).toBe("red");
    expect(group.querySelector(".xt-group-counts").textContent).toBe("2 checks: 1 failing, 1 not checked");
  });

  it("words the reason with the dataset's short name (A2)", () => {
    const w = load();
    const host = grid(w, [], [leftOut("second")]);
    expect(host.querySelector(".xt-left-out .why").textContent)
      .toBe("Not checked: People Register not supplied for 2026-Q2, by decision.");
  });
});

describe("'Not checked' and 'Not counted' stay apart (criterion 18)", () => {
  it("a cross-collection group whose every row is left out reads Not checked, never Not counted", () => {
    const w = load();
    const group = grid(w, [], [leftOut("second"), leftOut("third")]).querySelector(".xt-group");
    expect(group.dataset.xtGroupStatus).toBe("notchecked");
    const pill = group.querySelector(".xt-group-head .pill").textContent;
    expect(pill).toBe("Not checked");
    expect(pill).not.toMatch(/Not counted|Pass|No data/);
    expect(group.querySelector(".xt-group-counts").textContent).toBe("2 checks: 2 not checked");
  });

  it("a collection group every dataset of which is out of its rollup still reads Not counted", () => {
    const w = load();
    const out = { id: "d", noRollup: true, columns: [] };
    w.inNoRollup = (d) => !!d.noRollup;
    expect(w.rollup([out, { ...out, id: "e" }])).toBe("notcounted");
    expect(w.statusWords(w.rollup([out]), "label")).toBe("Not counted");
  });
});

// A3: REQ-DASH-337 criterion 17 - the agency page's collection panel.
describe("the agency page's collection panel (A3)", () => {
  const xt = (checks) => ({ name: "Cross-table checks", scope: "cross-table", checks });
  const ck = (name, between) => ({ check_id: `a.ag-two.matches.match-keys.${name}.x_soda`, key: name, name,
    tool_ref: "soda:x", current_status: "green", between, history: [] });

  it("lists a check reading another collection's dataset under 'Across collections', in the long form", () => {
    const w = load();
    const col = { id: "matches", datasets: [{ id: "match-keys", name: "Match Keys", columns: [xt([
      ck("own", null), ck("theirs", BETWEEN)])] }] };
    const host = w.document.createElement("div");
    host.innerHTML = w.collectionCrossTableSection({ id: "ag-two" }, col);
    const across = host.querySelector("[data-across-collections]");
    expect(across).not.toBeNull();
    expect(across.querySelector("h4").textContent).toBe("Across collections");
    expect(across.textContent).toContain("Registers' People Register");
    expect(across.textContent).not.toMatch(/between two tables in this collection/);
    expect(across.querySelectorAll(".scope-check")).toHaveLength(1);
    // The collection's own check comes first, under the old blurb.
    const buttons = [...host.querySelectorAll(".scope-check")];
    expect(buttons[0].textContent).toContain("own");
  });

  it("renders as before where no check reads another collection", () => {
    const w = load();
    const col = { id: "matches", datasets: [{ id: "match-keys", name: "Match Keys", columns: [xt([ck("own", null)])] }] };
    const host = w.document.createElement("div");
    host.innerHTML = w.collectionCrossTableSection({ id: "ag-two" }, col);
    expect(host.querySelector("[data-across-collections]")).toBeNull();
    expect(host.textContent).toMatch(/between two tables in this collection/);
  });
});
