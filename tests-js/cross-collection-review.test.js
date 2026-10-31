// REQ-DASH-337's post-build UX review (2026-10-30): defects a critic found on
// the built page, each pinned here before its fix. Every name is invented
// (criterion 15: nothing special-cased) - the page learns which supply is on
// show, which way a band points and what a cause was from the data alone.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

function win() {
  dashboard = loadDashboard();
  return dashboard.window;
}

// D1. A RE-RUN OF AN OLD SUPPLY IS NOT THE SUPPLY ON SHOW. The build lists a
// supply by its current run, in evaluation order (rank), so a correction that
// re-files and re-checks a supply received years ago puts that supply's run
// LAST - and it was taken as the newest supply on every date after the old
// receipt, before the re-run even existed. A cross-table card then looked up
// what counts toward that old supply: nothing ('No data') on every date until
// the re-run, and the old supply's green after it, while the dataset's own
// newest supply carried an amber.
const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1, expected_time: "09:00" };
const OLD = "visits@2013", NEW = "visits@2026", MID = "visits@2019";
function visits() {
  const runs = [
    { run_id: "visits__2019", run_date: "2019-05-01", received_at: "2019-05-01T10:00:00+08:00", supply_id: MID, rank: 3 },
    { run_id: "visits__2026", run_date: "2026-08-01", received_at: "2026-08-01T10:00:00+08:00", supply_id: NEW, rank: 5 },
    // Re-filed and re-checked on 2026-09-25: received 2013, run last.
    { run_id: "visits__2013__r1", run_date: "2013-10-10", received_at: "2013-10-10T10:00:00+08:00", supply_id: OLD, rank: 6 },
  ];
  const reader = (run_id, rank, supply_id, at, status, value) => ({
    run_id, run_date: at.slice(0, 10), rank, supply_id, read_state: "READ", value, status,
    recorded_at: at, recorded_by: "keys", recorded_in: "arrival", cause: `c:${run_id}` });
  return {
    id: "visits", name: "Visits", sla: { cadence: QUARTERLY }, runs, rowCount: 10, prevRowCount: 10,
    arrivalHistory: [], arrivalByRun: {},
    columns: [{ name: "Cross-table", scope: "cross-table", stats: { current: {}, previous: {}, byRun: {} }, checks: [{
      key: "coverage", name: "Coverage", unit: "%", warn: 90, fail: 85,
      history: [
        reader("keys__2013", 1, OLD, "2013-10-20T17:00:00+08:00", "green", 93),
        reader("keys__2019", 2, MID, "2019-05-01T17:00:00+08:00", "red", 79.9),
        reader("keys__2026", 4, NEW, "2026-08-01T17:00:00+08:00", "amber", 85.6),
        reader("keys__2013__r1", 7, OLD, "2026-09-25T14:00:00+08:00", "green", 92.1),
      ],
      counted: {
        [OLD]: [{ on: "2013-10-20", rank: 1, reason: null }, { on: "2026-09-25", rank: 7, reason: null }],
        [MID]: [{ on: "2019-05-01", rank: 2, reason: null }],
        [NEW]: [{ on: "2026-08-01", rank: 4, reason: null }],
      },
    }] }],
  };
}

describe("D1: the supply on show is the newest received, not the newest re-run", () => {
  it("shows the newest supply's result after an old supply is re-run", () => {
    const ck = win().clipDatasetToInPlaceOn(visits(), "2026-10-30").columns[0].checks[0];
    expect(ck.current_status).toBe("amber");
    expect(ck.current).toBe(85.6);
  });

  it("the page's built dataset keeps that supply, which its rows' cells read (#289 D1 residual)", () => {
    // clipDatasetToInPlaceOn picked visits__2026, but buildRealDataset - which
    // builds what the page renders - dropped onShowRun, so supplyOnShow fell
    // back to the run listed last: the 2013 supply's re-run.
    const w = win();
    const raw = { ...visits(), lastArrival: { run_id: "visits__2026", run_date: "2026-08-01" } };
    const built = w.buildRealDataset(w.clipDatasetToInPlaceOn(raw, "2026-10-30"));
    const onShow = w.supplyOnShow(built);
    expect(onShow && onShow.run_id).toBe("visits__2026");
  });

  it("shows the supply of the day on a date before the re-run existed", () => {
    const ck = win().clipDatasetToInPlaceOn(visits(), "2019-06-15").columns[0].checks[0];
    expect(ck.current_status).toBe("red");
    expect(ck.current).toBe(79.9);
  });
});

// D2. THE RUN COMPARISON READS THE RECORDED DIRECTION. A coverage drop from
// 93.74% to 85.58% read "↓ 8.16pt — Better than the previous run": the
// panel took "up" as worse for every check, which holds only for a band
// recorded "above".
describe("D2: better or worse follows the band the result records", () => {
  const below = { unit: "%", band: { warn: { op: "<", value: 90 }, fail: { op: "<", value: 85 } } };
  const above = { unit: "count", band: { warn: { op: ">", value: 0 }, fail: { op: ">", value: 5 } } };
  const legacy = { unit: "count", warn: 0, fail: 5 };

  it("a drop in a 'below' check is worse, a rise better", () => {
    const w = win();
    expect(w.deltaVerdict(below, 85.58 - 93.74)).toMatchObject({ arrow: "↓", tone: "worse" });
    expect(w.deltaVerdict(below, 5)).toMatchObject({ arrow: "↑", tone: "better" });
  });

  it("a rise in an 'above' check is worse, as before", () => {
    const w = win();
    expect(w.deltaVerdict(above, 3)).toMatchObject({ arrow: "↑", tone: "worse" });
    expect(w.deltaVerdict(above, -3)).toMatchObject({ arrow: "↓", tone: "better" });
    expect(w.deltaVerdict(legacy, 3)).toMatchObject({ tone: "worse" });
  });

  it("a change inside the flat band is no change", () => {
    expect(win().deltaVerdict(below, 0.01)).toMatchObject({ arrow: "–", tone: "flat" });
  });
});

// D4. THE CROSS-TABLE SECTION'S PILL ROLLS UP ITS ROWS AND GROUPS. On a date
// the dataset's own tiles go quiet (post-build-review #183) the section's
// pill read 'No data' while its own rows read green and a group's heading
// amber - and the dataset's own pill 'Amber promoted', from those very rows.
describe("D4: the cross-table section's pill follows its rows", () => {
  it("rolls up the rows' statuses on a quiet date", () => {
    const w = win();
    expect(w.crossTableSectionStatus(true, "nodata", [{ status: "green" }, { status: "amber" }])).toBe("amber");
  });
  it("reads No data only when no row has a verdict", () => {
    const w = win();
    expect(w.crossTableSectionStatus(true, "nodata", [{ status: "nodata" }])).toBe("nodata");
  });
  it("on an ordinary date takes the worst of the checks and the rows, as before", () => {
    const w = win();
    expect(w.crossTableSectionStatus(false, "red", [{ status: "green" }])).toBe("red");
  });
});

// D5 and D6 name causes across collections, so they need a hierarchy.
const HIERARCHY = { agencies: [
  { id: "ag-one", name: "Agency One", collections: [
    { id: "registers", name: "Registers", datasets: [
      { id: "people", name: "People Register" }, { id: "events", name: "Events" }] }] },
  { id: "ag-two", name: "Agency Two", collections: [
    { id: "matches", name: "Matches", datasets: [{ id: "match-keys", name: "Match Keys" }] }] },
] };
const PERIOD = "2026-Q2";
function withTree() {
  const raw = (id, name) => ({ id, name, provider: "P", deliveryFormat: "CSV", sla: null, runs: [],
    columns: [], closedSlots: [], runStates: {}, promotionTimeline: { points: [], standing: [] } });
  const data = { registers: { datasets: [raw("people", "People Register"), raw("events", "Events")] },
                 matches: { datasets: [raw("match-keys", "Match Keys")] } };
  const html = readFileSync(TEMPLATE_PATH, "utf-8").replace("const COLLECTION_DATA = null;",
    `const COLLECTION_DATA = ${JSON.stringify(data)};`);
  dashboard = loadDashboard({ html, hierarchy: HIERARCHY });
  return dashboard.window;
}
const textOf = (w, html) => { const d = w.document.createElement("div"); d.innerHTML = html; return d.textContent; };

// D5. A PERIOD WHOSE SUPPLY WAS REJECTED IS NOT 'OVERDUE'. The build records
// each line's cause ('turned-down' where the partner's supply for the period
// was rejected, else 'overdue'); the verdict line said 'is overdue' for both,
// and the notice promised the checks 'run again by themselves' once a supply
// is promoted - which a rejected, closed period's will not be on its own.
describe("D5: the could-not-run wording follows the period's recorded state", () => {
  const line = (cause) => ({ datasetId: "people", name: "People Register", period: PERIOD, n: 2,
                             form: "general", cause, noItem: true });
  const ds = (cause) => ({ id: "match-keys", noPromotedOn: { lines: [line(cause)], ownRed: false },
                           verdictOf: { state: "awaiting" } });

  it("says a rejected period's supply was rejected, and offers no wait", () => {
    const w = withTree();
    const v = textOf(w, w.otherTablesVerdict(ds("turned-down")).sentence);
    expect(v).toContain("could not run because the supply of Registers' "
      + `${w.fmtPeriodOrDay(PERIOD)} People Register was rejected`);
    expect(v).not.toContain("overdue");
    expect(v).not.toContain("wait for");
  });

  it("keeps 'is overdue' and the wait for an overdue one", () => {
    const w = withTree();
    const v = textOf(w, w.otherTablesVerdict(ds("overdue")).sentence);
    expect(v).toContain(`because Registers' ${w.fmtPeriodOrDay(PERIOD)} People Register is overdue`);
    expect(v).toContain("or wait for that supply to be promoted");
  });

  it("does not promise a re-run for a rejected period, and names 'no promoted supply of'", () => {
    const w = withTree();
    const t = textOf(w, w.noPromotedLineHtml(line("turned-down"), false, false, "match-keys"));
    expect(t).toContain(`No promoted supply of Registers' ${w.fmtPeriodOrDay(PERIOD)} People Register.`);
    expect(t).toContain("was rejected");
    expect(t).not.toContain("by themselves");
    const o = textOf(w, w.noPromotedLineHtml(line("overdue"), false, false, "match-keys"));
    expect(o).toContain("They run again by themselves once a supply of Registers' ");
  });
});

// D6. A CAUSE'S ACTION IS A NOUN. causeWords put the recorded action verb
// straight in: "Amber since the promote of ...".
describe("D6: a recorded action reads as a noun in a cause", () => {
  const step = (causeAction) => ({ causeAction, causeDataset: "match-keys", causePeriod: PERIOD });
  it("maps the recorded verbs to nouns", () => {
    const w = withTree();
    const name = `Matches' ${w.fmtPeriodOrDay(PERIOD)} Match Keys`;
    expect(w.causeWords("people", step("promote"), false)).toBe(`the promotion of ${name}`);
    expect(w.causeWords("people", step("arrival"), false)).toBe(`the arrival of ${name}`);
    expect(w.causeWords("people", step("refile"), false)).toBe(`the re-filing of ${name}`);
    expect(w.causeWords("people", step("choose-file"), false)).toBe(`the settlement of ${name}`);
  });
  it("never shows a raw action code, an unknown one included", () => {
    const w = withTree();
    const said = w.causeWords("people", step("some-new-action"), false);
    expect(said).not.toContain("some-new-action");
    expect(said.startsWith("the some new action of ")).toBe(true);
  });
});

// D8 (polish). The marks' key names every mark a row can show, and a source
// line does not double a possessive ("Match Keys's run").
describe("D8: the marks' key and a source's possessive", () => {
  it("the key explains the amber mark '!'", () => {
    const w = win();
    const html = w.crossTableGridHtml([]).html;
    expect(textOf(w, html)).toContain("! warned");
  });
  it("a name ending in s takes an apostrophe alone", () => {
    const w = withTree();
    const said = w.historySource({ datasets: [] }, { recorded_by: "match-keys", cause: "arrival:1" }, null);
    expect(said).toBe("from the Match Keys' run");
  });
});
