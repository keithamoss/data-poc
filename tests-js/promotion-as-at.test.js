// The promotion panel and the standing-in qualifier as at the date on show
// (REQ-DASH-197, REQ-DASH-198). The build embeds change points; the page
// only looks one up and words it - it never works an answer out.
import { afterEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadDashboard, MINIMAL_HIERARCHY } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const BUILT = "2026-09-20T02:00:00+08:00";
const SENTENCES = {
  "awaiting-decision": {present: "this supply is staged and nobody has decided about it yet",
                        past: "this supply was staged and nobody had decided about it yet"},
  "two-files-for-one-table": {present: "two files arrived", past: "two files had arrived"},
  "promoted-into-its-own-period": {present: "a supply promoted later into {period} is what downstream reads most recently",
                                   past: "a supply promoted later into {period} was what downstream read most recently"},
};

// The template as the build leaves it: BUILT_AT and the reason sentences
// embedded, everything else as authored.
function builtTemplate() {
  const file = fileURLToPath(new URL("../dashboard/qa-reporting-dashboard.template.html", import.meta.url));
  return readFileSync(file, "utf-8")
    .replace("const BUILT_AT = null;", `const BUILT_AT = ${JSON.stringify(BUILT)};`)
    .replace("const WHY_NOT_SENTENCES = {};", `const WHY_NOT_SENTENCES = ${JSON.stringify(SENTENCES)};`);
}
function loadBuilt() {
  dashboard = loadDashboard({ hierarchy: MINIMAL_HIERARCHY, html: builtTemplate() });
  return dashboard.window;
}

const POINTS = [
  {on: "2026-05-02", promoted: {supply: "s1", period: "2026-Q2", runId: "r1"},
   arrived: {supply: "s1", period: "2026-Q2", files: []}, differs: false, whyNot: null, decisions: []},
  {on: "2026-08-03", promoted: {supply: "s1", period: "2026-Q2", runId: "r1"},
   arrived: {supply: "s2", period: "2026-Q3", files: []}, differs: true,
   whyNot: "awaiting-decision", decisions: []},
];
const raw = (extra = {}) => ({id: "cp-carers", promotionTimeline: {points: POINTS, standing: []}, ...extra});

describe("the panel's answer is the newest change point on or before the date", () => {
  it("names nothing filed after the date (criterion 2)", () => {
    const w = loadBuilt();
    expect(w.promotionStateOn(raw(), "2026-06-01").differs).toBe(false);
    expect(w.promotionStateOn(raw(), "2026-08-04").arrived.supply).toBe("s2");
  });

  it("renders no panel at all where the build embedded no change points (criterion 15)", () => {
    const w = loadBuilt();
    const st = w.promotionStateOn({id: "cp-carers"}, "2026-08-04");
    expect(w.promotionSplit({promotionState: st})).toBe("");
  });
});

describe("the panel's wording", () => {
  it("on a past date, names the date and reads in the past tense (criteria 8 and 20)", () => {
    const w = loadBuilt();
    const html = w.promotionSplit({promotionState: w.promotionStateOn(raw(), "2026-08-10")});
    expect(html).toContain("the warehouse did not hold the latest file");
    expect(html).toContain(w.fmtDay("2026-08-10"));
    expect(html).toContain("Promoted — what everyone downstream was reading");
    expect(html).toContain(`Latest arrival by ${w.fmtDay("2026-08-10")} — not promoted`);
    expect(html).toContain("nobody had decided");
  });

  it("on the build's own date reads exactly as it always has (criterion 14)", () => {
    const w = loadBuilt();
    const html = w.promotionSplit({promotionState: w.promotionStateOn(raw(), "2026-09-20")});
    expect(html).toContain("What is in the warehouse is not the latest file");
    expect(html).toContain("Promoted — what everyone downstream reads");
    expect(html).toContain("Latest arrival — not promoted");
    expect(html).toContain("nobody has decided");
  });

  it("names both files of an open contest, not the #1 id (criterion 4)", () => {
    const w = loadBuilt();
    const points = [{...POINTS[1], arrived: {supply: "s2#1", period: "2026-Q3",
      files: ["carers_a.csv", "carers_b.csv"]}, whyNot: "two-files-for-one-table"}];
    const html = w.promotionSplit({promotionState: w.promotionStateOn(
      {id: "cp-carers", promotionTimeline: {points, standing: []}}, "2026-09-20")});
    expect(html).toContain("carers_a.csv");
    expect(html).toContain("carers_b.csv");
    expect(html).not.toContain("s2#1");
  });

  it("says a latest arrival promoted into its own period WAS promoted (criterion 6)", () => {
    const w = loadBuilt();
    const points = [{on: "2026-08-03", promoted: {supply: "s1", period: "2026-Q2", runId: "r1"},
      arrived: {supply: "s2", period: "2026-Q3", files: []}, differs: true,
      whyNot: "promoted-into-its-own-period", decisions: []}];
    const html = w.promotionSplit({promotionState: w.promotionStateOn(
      {id: "cp-carers", promotionTimeline: {points, standing: []}}, "2026-09-20")});
    expect(html).toContain("Latest arrival — promoted into 2026-Q3");
    expect(html).toContain("a supply promoted later into 2026-Q2 is what downstream reads most recently");
    expect(html).not.toContain("not promoted");
  });
});

describe("the qualifier is about the period on show (REQ-DASH-198)", () => {
  const STAND = {kind: "inherited", level: "information", period: "2026-Q2", standsOn: "2026-Q1",
    supply: "s0", decidedBy: null, reason: "not due", byAPerson: false};
  const tl = {points: [], standing: [
    {on: "2026-05-07", period: "2026-Q2", standingIn: STAND, decisions: [], earnedOn: "2026-02-07",
     since: {how: "replaced", on: "2026-06-01"}},
    {on: "2026-06-01", period: "2026-Q2", standingIn: null, decisions: []}]};

  it("shows on a date in the standing period, not on a date in another (criteria 1 and 6)", () => {
    const w = loadBuilt();
    expect(w.promotionStateOn({id: "cp-carers", promotionTimeline: tl}, "2026-05-20").standingIn).toBeTruthy();
    expect(w.promotionStateOn({id: "cp-carers", promotionTimeline: tl}, "2026-08-10").standingIn).toBe(null);
  });

  it("on a past date opens the tooltip and the heading on that date (criterion 9)", () => {
    const w = loadBuilt();
    const ds = {id: "cp-carers", promotionState: w.promotionStateOn({id: "cp-carers", promotionTimeline: tl}, "2026-05-20")};
    expect(w.standingInMarker(ds)).toContain(`On ${w.fmtDay("2026-05-20")} this period's data came from 2026-Q1.`);
    expect(w.standingInDetail(ds)).toContain(`On ${w.fmtDay("2026-05-20")} this period held an earlier period's data - nothing was owed for it`);
  });

  it("says when it later ended (criterion 3)", () => {
    const w = loadBuilt();
    const ds = {id: "cp-carers", promotionState: w.promotionStateOn({id: "cp-carers", promotionTimeline: tl}, "2026-05-20")};
    expect(w.standingInDetail(ds)).toContain(`Since replaced, as from ${w.fmtDay("2026-06-01")}`);
  });
});

describe("the past-date notice names only decisions behind what is on show (post-build-review #165)", () => {
  it("does not name a decision about another supply, nor a raw action code", () => {
    const w = loadBuilt();
    const late = {id: 91, action: "promotion-refused", supply: "s9",
                  at: "2026-08-03T02:00:00+00:00", recordedAt: "2026-09-01T02:00:00+00:00"};
    const behind = {id: 92, action: "promote", supply: "s1",
                    at: "2026-05-02T02:00:00+00:00", recordedAt: "2026-09-01T02:00:00+00:00"};
    const points = [
      {...POINTS[0], decisions: [behind]},
      {...POINTS[1], decisions: [late]}];
    const raw = {id: "cp-carers", name: "Carer Register", runs: [], runStates: {},
                 promotionTimeline: {points, standing: []}};
    dashboard.close();
    dashboard = loadDashboard({ hierarchy: MINIMAL_HIERARCHY, html: builtTemplate()
      .replace("const REAL_CP_DATA = null;", `const REAL_CP_DATA = ${JSON.stringify({datasets: [raw]})};`) });
    const found = dashboard.window.decisionsChangingDate("2026-08-10", null);
    const actions = found.map(d => d.action);
    // The promotion of s1 - the supply the panel names - recorded after the
    // date, on an EARLIER change point, is named; the refusal about s9 is not.
    expect(actions).toEqual(["promote"]);
  });
});

describe("Keith's answers on the critics' findings, 2026-10-13", () => {
  const own = [{on: "2026-08-03", promoted: {supply: "s1", period: "2026-Q2", runId: "r1"},
    arrived: {supply: "s2", period: "2026-Q3", files: []}, differs: true,
    whyNot: "promoted-into-its-own-period", decisions: []}];

  it("gives the promoted-into-its-own-period case its own heading, past and present", () => {
    const w = loadBuilt();
    const raw = {id: "cp-carers", promotionTimeline: {points: own, standing: []}};
    const past = w.promotionSplit({promotionState: w.promotionStateOn(raw, "2026-08-10")});
    expect(past).toContain(`On ${w.fmtDay("2026-08-10")} the newest file was not the newest promotion`);
    expect(past).not.toContain("did not hold the latest file");
    const now = w.promotionSplit({promotionState: w.promotionStateOn(raw, "2026-09-20")});
    expect(now).toContain("The newest file is not the newest promotion");
  });

  it("the qualifier says the results are a newer supply when one is awaiting", () => {
    const w = loadBuilt();
    const st = {kind: "inherited", period: "2026-Q2", standsOn: "2026-Q1", supply: "s0",
                decidedBy: null, reason: "", byAPerson: false};
    const ds = {id: "cp-carers", verdictOf: {state: "awaiting"},
                promotionState: {standingIn: st, on: "2026-06-01", past: true}};
    const html = w.standingInDrill(ds);
    expect(html).toContain("2026-Q2 holds 2026-Q1's supply; the results below are a newer supply awaiting a decision.");
    expect(html).not.toContain("ran against 2026-Q1's supply");
  });

  it("the tooltip's second sentence starts with a capital", () => {
    const w = loadBuilt();
    const st = {kind: "inherited", period: "2026-Q2", standsOn: "2026-Q1", supply: "s0",
                decidedBy: null, reason: "", byAPerson: false};
    const html = w.standingInMarker({promotionState: {standingIn: st, on: "2026-06-01", past: true}});
    expect(html).toContain("came from 2026-Q1. Inherited automatically");
  });

  it("the picker's help says which later decisions count", () => {
    const w = loadBuilt();
    expect(w.document.body.innerHTML.replace(/\s+/g, " ")).toContain(
      "a decision written down after that date still counts if it took effect by then, and one that took effect after it does not");
  });
});
