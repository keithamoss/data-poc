// REQ-DASH-209 - a period's composition: one row per dataset of a collection,
// what each held in that period at the end of the date on show, looked up
// from the timelines the build embeds and never worked out again.
import { afterEach, describe, expect, it } from "vitest";
import { MINIMAL_HIERARCHY, loadDashboard } from "./support/loadDashboard.js";

let page;
afterEach(()=> page && page.close());

const Q = [{period: "2025-Q4", date: "2025-11-01"}, {period: "2026-Q1", date: "2026-02-01"},
           {period: "2026-Q2", date: "2026-05-01"}];
const slot = (o)=> ({action: "promote", actor: "promotion rule", actor_kind: "rule",
                     reason: "passed", decision_id: 1, supply: null, run_id: null, ...o});

// Five datasets, one of each kind in 2026-Q1.
const RAW = {
  promoted: {id: "promoted", runs: [{run_id: "r-p", received_at: "2026-02-01T01:00:00+00:00"}],
    slotTimeline: [slot({at: "2026-02-03T01:00:00+00:00", on: "2026-02-03", slot: "2026-Q1",
                         held_as: "promoted", holder: "p@1", holder_run_id: "r-p"})],
    promotedHealth: {"r-p": {promotedOn: "green"}}},
  substituted: {id: "substituted", runs: [{run_id: "r-s", received_at: "2025-11-01T01:00:00+00:00"}],
    slotTimeline: [
      slot({at: "2025-11-03T01:00:00+00:00", on: "2025-11-03", slot: "2025-Q4",
            held_as: "promoted", holder: "s@1", holder_run_id: "r-s"}),
      slot({at: "2026-02-20T01:00:00+00:00", on: "2026-02-20", slot: "2026-Q1", action: "substitute",
            actor: "Robin Hale", actor_kind: "person", reason: "<b>no file</b> this quarter",
            held_as: "substituted", holder: "s@1", holder_run_id: "r-s", stands_on: "2025-Q4"})],
    promotedHealth: {"r-s": {promotedOn: "amber"}},
    acknowledgements: {"r-s": {promotedAt: "2025-11-03T01:00:00+00:00",
      acks: [{actor: "Robin Hale", reason: "fine", at: "2025-11-04T01:00:00+00:00", withdrawn: null}]}}},
  inherited: {id: "inherited", runs: [], slotTimeline: [
      slot({at: "2026-02-01T01:00:00+00:00", on: "2026-02-01", slot: "2026-Q1", action: "inherit",
            held_as: "inherited", holder: "i@1", holder_run_id: null, stands_on: "2025-Q4"})],
    owedNothing: [{period: "2026-Q1", date: "2026-02-01", kind: "participation", months: [11]}]},
  nothing: {id: "nothing", runs: [], slotTimeline: [],
    closedSlots: [{period: "2026-Q1", closesAt: "2026-02-15T09:00:00+08:00", changes: [], marks: []}]},
  off: {id: "off", runs: [], slotTimeline: [],
    owedNothing: [{period: "2026-Q1", date: "2026-02-01", kind: "turned_off", reason: "retired"}]},
};
const COL = {id: "c", name: "Child Protection", datasets: [
  {id: "promoted", name: "Promoted One"}, {id: "substituted", name: "Substituted One"},
  {id: "inherited", name: "Inherited One"}, {id: "nothing", name: "Nothing One"},
  {id: "off", name: "Off One"}]};

function load(){
  page = loadDashboard({hierarchy: MINIMAL_HIERARCHY});
  const w = page.window;
  w.rawRealDatasetById = id => RAW[id] || null;
  w.periodsFor = () => Q;
  w.eval(`DATA = {agencies: [{id: "a", name: "Agency", collections: [${JSON.stringify(COL)}]}]}`);
  return w;
}

describe("each dataset's row, looked up as at the date on show (criteria 1 and 2)", () => {
  it("names each kind, and the period a stand-in stands on", () => {
    const w = load();
    const kind = id => w.compositionRow(RAW[id], "2026-Q1", "2026-03-01");
    expect(kind("promoted").kind).toBe("promoted");
    expect(kind("substituted")).toMatchObject({kind: "substituted", from: "2025-Q4"});
    expect(kind("inherited")).toMatchObject({kind: "inherited", from: "2025-Q4"});
    expect(kind("nothing")).toMatchObject({kind: "notsupplied", word: "No supply"});
    expect(kind("off")).toMatchObject({kind: "notowed", word: "Turned off"});
  });

  it("answers an earlier date as it stood then", () => {
    const w = load();
    // Before the substitution took effect the period held nothing.
    expect(w.compositionRow(RAW.substituted, "2026-Q1", "2026-02-10").kind).toBe("notsupplied");
  });
});

describe("the view (criteria 3, 4, 8, 12 and 14)", () => {
  const view = (w, date = "2026-03-01", period = "2026-Q1")=>{
    const div = w.document.createElement("div");
    div.innerHTML = w.compositionHtml(w.eval("DATA.agencies[0]"), COL, period, date);
    return div;
  };

  it("opens with one counting line, then the groups in their order", () => {
    const w = load();
    const div = view(w);
    expect(div.querySelector("[data-composition-count]").textContent)
      .toBe("5 datasets: 1 not supplied, 1 substituted, 1 inherited, 1 promoted, 1 not owed");
    const kinds = [...div.querySelectorAll("tbody tr")].map(tr => tr.dataset.kind);
    expect(kinds).toEqual(["notsupplied", "substituted", "inherited", "promoted", "notowed"]);
  });

  it("says who decided by name or the schedule, the status when promoted, and the acknowledgement", () => {
    const w = load();
    const div = view(w);
    const heads = [...div.querySelectorAll("thead th")].map(th => th.textContent.trim());
    expect(heads).toContain("Status when promoted");
    const row = div.querySelector('tr[data-kind="substituted"]');
    expect(row.textContent).toContain("Decided by Robin Hale");
    expect(row.textContent).toContain("Amber");
    expect(row.textContent).toContain("Acknowledged");
    expect(div.querySelector('tr[data-kind="promoted"]').textContent)
      .toContain("Applied automatically by the schedule");
  });

  it("renders a reason as text, never as markup (criterion 9)", () => {
    const w = load();
    const row = view(w).querySelector('tr[data-kind="substituted"]');
    expect([...row.querySelectorAll("b")].some(b => b.textContent === "no file")).toBe(false);
    expect(row.textContent).toContain("<b>no file</b>");
  });

  it("links each dataset's name and each 'from' period", () => {
    const w = load();
    const row = view(w).querySelector('tr[data-kind="substituted"]');
    const hrefs = [...row.querySelectorAll("a[href]")].map(a => a.getAttribute("href"));
    expect(hrefs.some(h => h.includes("/dataset/substituted"))).toBe(true);
    expect(hrefs.some(h => h.includes("/period/2025-Q4"))).toBe(true);
  });

  it("heads the view and captions the table", () => {
    const w = load();
    const div = view(w);
    expect(div.querySelector("h2").textContent).toBe("Child Protection · 2026-Q1");
    expect(div.querySelector(".view-sub").textContent).toContain("What each dataset held at the end of");
    expect(div.querySelector("caption")).not.toBeNull();
  });

  it("links the previous period, and the next only once it had opened", () => {
    const w = load();
    let div = view(w);
    expect(div.querySelector("[data-period-prev]").textContent).toContain("Previous period: 2025-Q4");
    expect(div.querySelector("[data-period-next]")).toBeNull();
    div = view(w, "2026-06-01");
    expect(div.querySelector("[data-period-next]").textContent).toContain("Next period: 2026-Q2");
    div = view(w, "2026-03-01", "2025-Q4");
    expect(div.querySelector("[data-period-prev]")).toBeNull();
  });

  it("says a period had not opened by the date, in place of the rows", () => {
    const w = load();
    const div = view(w, "2026-03-01", "2026-Q2");
    expect(div.querySelector("[data-not-opened]").textContent).toContain("had not opened by");
    expect(div.querySelector("tbody")).toBeNull();
  });

  it("says so in one line where nothing is held", () => {
    const w = load();
    w.rawRealDatasetById = id => ({id, slotTimeline: []});
    const div = view(w);
    expect(div.querySelector("[data-nothing-held]")).not.toBeNull();
    // Only where nothing is held: the ordinary view has no such line.
    expect(view(load()).querySelector("[data-nothing-held]")).toBeNull();
  });
});

describe("its address (criteria 6 and 13)", () => {
  it("round-trips through the route", () => {
    const w = load();
    const nav = {tier: "period", agencyId: "a", collectionId: "c", period: "2026-Q1"};
    expect(w.stateToPath(nav)).toBe("/agency/a/collection/c/period/2026-Q1");
    expect(w.pathToState("/agency/a/collection/c/period/2026-Q1")).toEqual(nav);
  });
});

describe("a scenario about a whole period lands on it (criterion 7)", () => {
  it("names the view as a subject, and its chip targets the period's route", () => {
    page = loadDashboard({hierarchy: MINIMAL_HIERARCHY});
    const w = page.window;
    expect(w.eval("Object.keys(SCENARIO_SUBJECT)")).toContain("period-composition");
    const target = w.scenarioTarget({id: "TS-55", coordinates: {
      dataset: "cp-clients", period: "2026-Q1", inPlaceOn: "2026-03-01",
      subject: "period-composition"}});
    expect(target.nav).toMatchObject({tier: "period", collectionId: "child-protection",
                                      period: "2026-Q1"});
  });
});

describe("every subject the scenario map can name has a place on the page", () => {
  it("matches scenario_map.SUBJECTS", () => {
    const src = require("node:fs").readFileSync(
      require("node:path").join(__dirname, "..", "qa_tools", "common", "scenario_map.py"), "utf-8");
    const names = [...src.matchAll(/^[A-Z_]+ = "([a-z-]+)"$/gm)].map(m => m[1]);
    expect(names.length).toBeGreaterThan(4);
    page = loadDashboard({hierarchy: MINIMAL_HIERARCHY});
    const mapped = page.window.eval("Object.keys(SCENARIO_SUBJECT)");
    names.forEach(n => expect(mapped).toContain(n));
  });
});

describe("post-build-review #204 - the rows that hold nothing", () => {
  it("F1: a period with a supply received and not promoted reads Waiting, as its supply history does", () => {
    const w = load();
    const raw = {id: "x", slotTimeline: [],
                 runs: [{run_id: "r1", run_date: "2026-02-05", received_at: "2026-02-05T01:00:00+00:00"}],
                 runStates: {r1: [{at: "2026-02-05T01:00:00+00:00", state: "awaiting"}]}};
    expect(w.compositionRow(raw, "2025-Q4", "2026-03-01").word).toBe("No supply");
    expect(w.compositionRow(raw, "2026-Q1", "2026-03-01").word).toBe("Waiting");
    // Not before it arrived, and not once it was withdrawn.
    expect(w.compositionRow(raw, "2026-Q1", "2026-02-02").word).not.toBe("Waiting");
    raw.runStates.r1.push({at: "2026-02-20T01:00:00+00:00", state: "withdrawn"});
    expect(w.compositionRow(raw, "2026-Q1", "2026-03-01").word).not.toBe("Waiting");
  });

  it("F2: a period before the dataset owed anything is not owed, whatever the date on show", () => {
    const w = load();
    const raw = {id: "x", slotTimeline: [], sla: {owesFrom: "2026-02-01"}};
    expect(w.compositionRow(raw, "2025-Q4", "2026-06-01")).toMatchObject({kind: "notowed"});
    expect(w.compositionRow(raw, "2026-Q1", "2026-06-01").kind).toBe("notsupplied");
  });

  it("F3: a not-owed row says its word once", () => {
    const w = load();
    const div = w.document.createElement("div");
    div.innerHTML = w.compositionHtml(w.eval("DATA.agencies[0]"), COL, "2026-Q1", "2026-03-01");
    const inherited = {...RAW.inherited, slotTimeline: []};
    w.rawRealDatasetById = id => (id === "inherited" ? inherited : RAW[id] || null);
    div.innerHTML = w.compositionHtml(w.eval("DATA.agencies[0]"), COL, "2026-Q1", "2026-03-01");
    const text = div.querySelector('tr[data-dataset="inherited"]').textContent.replace(/\s+/g, " ");
    expect(text).toContain("Not owed");
    expect(text).not.toMatch(/Not owed\W+Not owed/);
  });
});
