// REQ-PIPE-279 criteria 10 to 15 on the page: a result is placed on ONE POINT,
// (the supply it is about, the cause of its run), each point counted once and
// ordered by the build's emitted rank - never by a day or a recording time.
// Written first, against the template as it stood after REQ-DASH-264.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
const load = () => (dashboard = loadDashboard()).window;

// One history entry as the build emits it (REQ-PIPE-279 criterion 16).
const entry = ({ run, rank, supply, cause, at, status = "green", by = null, inn = null, ...extra }) => ({
  run_id: run, rank, supply_id: supply, cause, status, value: status === "red" ? 3 : 0,
  run_date: at.slice(0, 10), date: new Date(`${at.slice(0, 10)}T00:00:00Z`),
  recorded_at: at, recorded_by: by, recorded_in: by ? (inn || "arrival") : null, ...extra,
});
const column = (name, ...histories) => ({ name, checks: histories.map((history) => ({ history })) });
const cross = (...histories) => ({ name: "Cross-table", scope: "cross-table",
                                   checks: histories.map((history) => ({ history })) });

describe("a result is placed on the supply it read (test 1)", () => {
  it("two Clients supplies in a day: a Notifications run reading the 15:00 one is on the 15:00 supply", () => {
    const w = load();
    const nine = entry({ run: "c09", rank: 1, supply: "cp-clients@09", cause: "arrival:d@09",
                         at: "2026-03-02T09:00:00+08:00", status: "red" });
    const three = entry({ run: "c15", rank: 2, supply: "cp-clients@15", cause: "arrival:d2@15",
                          at: "2026-03-02T15:00:00+08:00" });
    const read15 = entry({ run: "n16", rank: 3, supply: "cp-clients@15", cause: "arrival:d3@16",
                           at: "2026-03-02T16:00:00+08:00", status: "amber", by: "cp-notifications" });
    const counts = w.unitCounts([
      column("a", [nine, three]),
      // The cross-table check has no result of its own under the 15:00 run.
      cross([{ ...nine }, read15]),
    ]);
    expect(counts.map((p) => p.rank)).toEqual([1, 2, 3]);
    // The Notifications point carries column a from the 15:00 supply (green),
    // never from the 09:00 one (red).
    expect(counts[2]).toMatchObject({ counted: 2, red: 0, amber: 1 });
  });
});

describe("one delivery, two receipt instants, is two points (tests 2 and 3)", () => {
  const own = entry({ run: "n_mon", rank: 1, supply: "cp-notifications@mon", cause: "arrival:zip@23:50",
                      at: "2026-03-02T23:50:00+08:00", status: "red" });

  it("across midnight: the own Monday point unchanged, Clients' Tuesday result a second, newer point", () => {
    const w = load();
    const tue = entry({ run: "c_tue", rank: 2, supply: "cp-notifications@mon", cause: "arrival:zip@00:10",
                        at: "2026-03-03T00:10:00+08:00", by: "cp-clients" });
    const counts = w.unitCounts([cross([own, tue])]);
    expect(counts).toHaveLength(2);
    expect(counts[0]).toMatchObject({ runId: "n_mon", red: 1 });
    expect(counts[1]).toMatchObject({ rank: 2, red: 0 });
    const col = { datasets: [{ id: "cp-clients", name: "Client Register" }] };
    expect(w.historySource(col, tue)).toBe("from the Client Register's run, 12:10am Tuesday, 3 March 2026");
  });

  it("within one day: Notifications 09:00 and Clients 11:50 are two points, not one", () => {
    const w = load();
    const nine = entry({ run: "n09", rank: 1, supply: "cp-notifications@09", cause: "arrival:zip@09",
                         at: "2026-03-02T09:00:00+08:00", status: "red" });
    const later = entry({ run: "c1150", rank: 2, supply: "cp-notifications@09", cause: "arrival:zip@11:50",
                          at: "2026-03-02T11:50:00+08:00", by: "cp-clients" });
    const counts = w.unitCounts([cross([nine, later])]);
    expect(counts).toHaveLength(2);
    expect(counts.map((p) => p.red)).toEqual([1, 0]);
    expect(w.deliveryCount([nine, later])).toBe(2);
  });
});

describe("points are ordered by their emitted rank (test 11)", () => {
  it("orders two points with the same date and recording time by rank", () => {
    const w = load();
    const at = "2026-03-02T09:00:00+08:00";
    const counts = w.unitCounts([column("a",
      [entry({ run: "a", rank: 7, supply: "s@a", cause: "arrival:a", at, status: "red" }),
       entry({ run: "z", rank: 3, supply: "s@z", cause: "arrival:z", at })])]);
    // Run ids that sort the other way, so only the rank can give this order.
    expect(counts.map((p) => p.runId)).toEqual(["z", "a"]);
  });
});

describe("a re-check is a point of its own the same day (test 12)", () => {
  it("a 15:00 Clients re-check after a 09:00 zip is its own point", () => {
    const w = load();
    const zip = { supply: "cp-notifications@09", cause: "arrival:zip@09", at: "2026-03-02T09:00:00+08:00" };
    const own = entry({ run: "n09", rank: 1, ...zip, status: "red" });
    const carried = entry({ run: "c09", rank: 2, ...zip, status: "red", by: "cp-clients" });
    const recheck = entry({ run: "c09__r1", rank: 3, supply: "cp-notifications@09", cause: "decision:41",
                            at: "2026-03-02T15:00:00+08:00", by: "cp-clients", inn: "re-check" });
    const counts = w.unitCounts([column("a", [own]), cross([carried, recheck])]);
    expect(counts).toHaveLength(2);
    // The zip's two runs are ONE point, the supply's own; the re-check another.
    expect(counts[0]).toMatchObject({ runId: "n09", red: 2, counted: 2 });
    // Column a's red carried into the re-check point; the re-checked one green.
    expect(counts[1]).toMatchObject({ rank: 3, red: 1, counted: 2 });
    const col = { datasets: [{ id: "cp-clients", name: "Client Register" }] };
    expect(w.historySource(col, recheck)).toBe("from the Client Register's re-check, 3:00pm Monday, 2 March 2026");
  });
});

describe("a result read by another arrival is on the supply it read (test 13)", () => {
  it("Investigations reading the 1 February Case Workers supply is a point of that supply", () => {
    const w = load();
    const feb = entry({ run: "w_feb", rank: 1, supply: "cp-case-workers@feb", cause: "arrival:feb",
                        at: "2025-02-01T09:00:00+08:00" });
    const mayHeld = entry({ run: "w_may", rank: 2, supply: "cp-case-workers@may", cause: "arrival:may",
                           at: "2025-05-01T09:00:00+08:00" });
    const inv = entry({ run: "i_may", rank: 3, supply: "cp-case-workers@feb", cause: "arrival:inv-may",
                        at: "2025-05-01T09:00:05+08:00", by: "cp-investigations", status: "red" });
    const counts = w.unitCounts([
      column("a", [feb]), { name: "Table-level checks", scope: "table", checks: [{ history: [feb, mayHeld] }] },
      cross([inv]),
    ]);
    const newest = counts[counts.length - 1];
    expect(newest.rank).toBe(3);
    // Carrying the February supply's other checks, not the held May one's.
    expect(newest).toMatchObject({ counted: 3, red: 1 });
  });
});

describe("the panel's default comparison is the newest earlier evaluated point (N1 = B, test 26)", () => {
  const h = (run, rank, supply, cause, extra = {}) =>
    entry({ run, rank, supply, cause, at: `2026-0${rank}-01T09:00:00+08:00`, ...extra });
  // Point B's newest result could not be evaluated, so the default skips the
  // whole of point B, not just that entry.
  const history = [
    h("a", 1, "s@1", "arrival:1"),
    h("b1", 2, "s@2", "arrival:2"),
    h("b2", 3, "s@2", "arrival:2", { by: "cp-clients", not_evaluated: "not yet supplied" }),
    h("c", 4, "s@3", "arrival:3"),
  ];

  it("skips an earlier point whose result was not evaluated", () => {
    const w = load();
    expect(w.defaultCompareIndex(history)).toBe(0);
  });

  it("writes no ?cmp= for the default and one for any other choice, from one function", () => {
    const w = load();
    w.openCheckPanel = () => {};
    const check = { history };
    w.setCompareIdx({}, {}, {}, {}, check, w.defaultCompareIndex(history));
    expect(new URL(w.location.href).searchParams.get("cmp")).toBe(null);
    w.setCompareIdx({}, {}, {}, {}, check, 1);
    expect(new URL(w.location.href).searchParams.get("cmp")).toBe("1");
  });

  // The copied link, opened again: the URL read back through cmpFromUrl
  // into STATE, and the real panel rendered from it, shows the comparison
  // that was on screen when it was copied.
  const panelCheck = () => ({
    key: "k", name: "A check", dimension: "validity", unit: "count", warn: null, fail: null,
    current: 0, current_status: "green", previous: 0, changelog: [], history,
  });
  const open = (w, check) => {
    const column = { name: "c", checks: [check], stats: {} };
    const ds = { name: "D", runs: [], columns: [column] };
    w.openCheckPanel({ name: "A" }, { name: "C" }, ds, column, check, { pushHistory: false });
    return w.document.querySelector("#check-panel-body select option[selected]");
  };
  const reopenAt = (w, href) => {
    w.history.replaceState(null, "", href);
    w.eval("STATE = stateFromLocation()");
  };

  it("opens a copied link at the comparison it was copied from", () => {
    const w = load();
    const check = panelCheck();
    open(w, check);
    w.setCompareIdx({ name: "A" }, { name: "C" }, { name: "D", runs: [], columns: [] },
                    { name: "c", checks: [check], stats: {} }, check, 1);
    const copied = w.location.href;
    expect(new URL(copied).searchParams.get("cmp")).toBe("1");
    reopenAt(w, copied);
    expect(w.cmpFromUrl()).toBe(1);
    expect(open(w, panelCheck()).value).toBe("1");
  });

  it("opens a link with no ?cmp= at the default comparison", () => {
    const w = load();
    const check = panelCheck();
    open(w, check);
    w.setCompareIdx({ name: "A" }, { name: "C" }, { name: "D", runs: [], columns: [] },
                    { name: "c", checks: [check], stats: {} }, check, w.defaultCompareIndex(history));
    const copied = w.location.href;
    expect(new URL(copied).searchParams.get("cmp")).toBe(null);
    reopenAt(w, copied);
    expect(open(w, panelCheck()).value).toBe(String(w.defaultCompareIndex(history)));
  });
});

describe("a held table's cross-table row reads the held supply (criterion 15)", () => {
  const held = (...history) => ({ columns: [{ name: "Cross-table", scope: "cross-table",
                                              checks: [{ key: "ref", history, current_status: "red" }] }] });

  it("shows a result whose read of this table is HELD with the held supply, whenever it was recorded", () => {
    const w = load();
    const ds = held(entry({ run: "n", rank: 4, supply: "cp-clients@held", cause: "arrival:n",
                            at: "2020-10-01T09:00:00+08:00", status: "red", by: "cp-notifications",
                            read_state: "HELD" }));
    expect(w.blockChecksWhileHeld(ds, { supply: "cp-clients@held", openedAt: "2020-11-01T08:20:00+08:00" }))
      .toBe(1);
    expect(w.checkStatus(ds.columns[0].checks[0])).toBe("red");
  });

  it("does not show one recorded after the receipt that read another supply", () => {
    const w = load();
    const ds = held(entry({ run: "n", rank: 4, supply: "cp-clients@other", cause: "arrival:n",
                            at: "2020-12-01T09:00:00+08:00", status: "red", by: "cp-notifications" }));
    expect(w.blockChecksWhileHeld(ds, { supply: "cp-clients@held", openedAt: "2020-11-01T08:20:00+08:00" }))
      .toBe(0);
    expect(w.checkStatus(ds.columns[0].checks[0])).toBe("nodata");
  });
});

// The gate's TestColumnsNotGreenMatchesTheDatasetPage on cp-notifications
// (2026-10-23): a column with no rule defined has history entries with no
// rank, and comparing ranked points with unranked ones by insertion order is
// no order at all - the sort scrambled the series, so the list's "latest"
// point was an old one and disagreed with the page.
describe("points are in rank order whatever unranked entries sit among them", () => {
  it("orders a later column's lower-ranked points before an earlier column's, across placeholders", () => {
    const w = load();
    const at = "2026-03-02T09:00:00+08:00";
    const placeholder = (run) => ({ run_id: run, run_date: "2026-03-02", value: 0, status: "inactive" });
    const own = (rank) => entry({ run: `n${rank}`, rank, supply: `s@${rank}`, cause: `arrival:${rank}`, at });
    const elsewhere = (rank) => entry({ run: `c${rank}`, rank, supply: `s@${rank}`, cause: `arrival:c${rank}`,
                                        at, by: "cp-clients", status: "red" });
    // The real page's shape: own columns first, the no-rule placeholder
    // column, then the cross-table section's results from other tables'
    // runs - seen last, though most rank earlier.
    const counts = w.unitCounts([
      column("a", [own(10), own(20), own(30)]),
      { name: "no_rule", checks: [{ history: [placeholder("p1"), placeholder("p2"), placeholder("p3")] }] },
      cross([elsewhere(5), elsewhere(15), elsewhere(25)]),
    ]);
    expect(counts.map((p) => p.rank)).toEqual([5, 10, 15, 20, 25, 30]);
  });
});

// REQ-DASH-264 criterion 3's "held or contested", kept where REQ-PIPE-279
// criteria 14 and 15 left a gap (PROVISIONAL, 2026-10-23, for Keith): TS-80's
// Client Register was a contested pair, and its readers recorded it ABSENT,
// contested, naming both files. Keyed on the pair, never on a time.
describe("a contested table's cross-table row reads the pair", () => {
  const pair = ["cp_clients__k__1", "cp_clients__k__2"];
  const blocker = { kind: "contested", supply: "cp-clients@k#1", tables: pair };
  const page = (files) => ({ columns: [{ name: "Cross-table", scope: "cross-table", checks: [{
    key: "ref", history: [entry({ run: "old", rank: 1, supply: "cp-clients@q3", cause: "arrival:q3",
                                   at: "2020-08-01T09:00:00+08:00", by: "cp-notifications" })],
    current_status: "green",
    contested_reads: [entry({ run: "n", rank: 5, supply: null, cause: "arrival:n", status: "red",
                              at: "2020-11-01T08:20:00+08:00", by: "cp-notifications",
                              read_state: "ABSENT", contested_files: files })] }] }] });

  it("shows a reader's result that found the blocking pair's own files", () => {
    const w = load();
    const ds = page([...pair].reverse());
    expect(w.blockChecksWhileHeld(ds, blocker)).toBe(1);
    expect(w.checkStatus(ds.columns[0].checks[0])).toBe("red");
  });

  // Keith, 2026-10-24, reversing provisional #22: a check whose only result
  // on the pair's page is a contested read still has a card there, kept out of
  // every count and history until the pair blocks the page.
  const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1,
                      expected_time: "09:00" };
  const onlyContested = (files) => {
    const own = { run_id: "cp_clients__202008010900000800", run_date: "2020-08-01" };
    return {
      id: "cp-clients", name: "Client Register", sla: { cadence: QUARTERLY },
      runs: [own], rowCount: 10, prevRowCount: 10,
      arrivalHistory: [{ run_id: own.run_id, run_date: own.run_date, arrivalStatus: "onTime" }],
      arrivalByRun: { [own.run_id]: { arrivedAt: "2020-08-01T09:00:00+08:00", arrivalStatus: "onTime" } },
      lastArrival: { run_date: own.run_date, arrivedAt: "2020-08-01T09:00:00+08:00", arrivalStatus: "onTime" },
      columns: [{ name: "Cross-table", scope: "cross-table", stats: { current: {}, previous: {}, byRun: {} },
        checks: [],
        // The build puts such a card BESIDE the column's checks (criterion 14).
        contested_only: [{ key: "ref", name: "Client reference", history: [], warn: 0, fail: 0,
          contested_reads: [entry({ run: "n", rank: 5, supply: null, cause: "arrival:n", status: "red",
                                    at: "2020-11-01T08:20:00+08:00", by: "cp-notifications",
                                    read_state: "ABSENT", contested_files: files })] }] }] };
  };
  const coll = { datasets: [{ id: "cp-notifications", name: "Notifications" }] };

  it("gives a check whose only result is a contested read a red row while the pair blocks", () => {
    const w = load();
    const ds = w.clipDatasetToInPlaceOn(onlyContested([...pair]), "2020-11-02");
    // Out of every count until the pair blocks the page (criterion 14).
    expect(ds.columns[0].checks).toHaveLength(0);
    expect(w.blockChecksWhileHeld(ds, blocker)).toBe(1);
    const [ck] = ds.columns[0].checks;
    expect(w.checkStatus(ck)).toBe("red");
    expect(w.rowRecheckNote(coll, ck)).toMatch(/Notifications/);
  });

  it("keeps it off the page before it was recorded, by the as-of clip", () => {
    const w = load();
    const ds = w.clipDatasetToInPlaceOn(onlyContested([...pair]), "2020-10-31");
    expect(w.blockChecksWhileHeld(ds, blocker)).toBe(0);
    expect(ds.columns[0].checks).toHaveLength(0);
  });

  it("does not show one that found another pair", () => {
    const w = load();
    const ds = page(["cp_clients__other__1", "cp_clients__other__2"]);
    expect(w.blockChecksWhileHeld(ds, blocker)).toBe(0);
    expect(w.checkStatus(ds.columns[0].checks[0])).toBe("nodata");
  });
});

// post-build-review #262 F5 and criterion 13 (Keith, 2026-10-24: fix now).
describe("the column drawer's run dots are the page's points", () => {
  it("counts two causes on one day as two points, in rank order", () => {
    const w = load();
    const ck = { warn: 1, fail: 2, history: [
      entry({ run: "a", rank: 2, supply: "s@1", cause: "arrival:1", at: "2026-03-01T09:00:00+08:00" }),
      entry({ run: "b", rank: 3, supply: "s@1", cause: "decision:7", at: "2026-03-01T15:00:00+08:00",
              status: "red" }),
      entry({ run: "z", rank: 1, supply: "s@0", cause: "arrival:0", at: "2026-02-01T09:00:00+08:00" }),
    ] };
    const dots = w.statusHistoryForColumn({ name: "c", checks: [ck] });
    expect(dots.map((d) => d.worst)).toEqual(["green", "green", "red"]);
  });
});

describe("a supply's history is in the order its runs were opened", () => {
  it("orders one day's runs by rank, never by run id", () => {
    const w = load();
    // __r10 sorts before __r9 as text; the build's rank says r9 came first.
    const runs = [
      { run_id: "t__X__r10", run_date: "2026-01-01", rank: 2 },
      { run_id: "t__X__r9", run_date: "2026-01-01", rank: 1 },
    ];
    const d = {
      id: "birth-registrations", sla: { cadence: { type: "daily", expected_time: "14:00" } },
      runs, arrivalByRun: { "t__X__r10": { slot: "2026-01-01" }, "t__X__r9": { slot: "2026-01-01" } },
      columns: [{ checks: [{ warn: 1, fail: 2, history: [
        { run_id: "t__X__r9", run_date: "2026-01-01", value: 3 },
        { run_id: "t__X__r10", run_date: "2026-01-01", value: 0 },
      ] }] }],
    };
    const [chain] = w.buildSupplyHistory(d);
    // Newest first: r10 resupplies r9's red, so it is attempt 2.
    expect(chain.entries.map((e) => [e.run_id, e.attemptNumber])).toEqual(
      [["t__X__r10", 2], ["t__X__r9", 1]]);
  });
});

describe("a dataset's own re-check names its cause (criterion 13)", () => {
  it("says it came from the dataset's own re-check, as another table's does", () => {
    const w = load();
    const own = entry({ run: "r", rank: 4, supply: "s@1", cause: "decision:7",
                        at: "2026-03-01T15:00:00+08:00" });
    const said = w.historySource({ datasets: [] }, own, { name: "Client Register" });
    expect(said).toMatch(/^from the Client Register's re-check, /);
    const arrival = entry({ run: "a", rank: 3, supply: "s@1", cause: "arrival:1",
                            at: "2026-03-01T09:00:00+08:00" });
    expect(w.historySource({ datasets: [] }, arrival, { name: "Client Register" })).toBe("");
  });
});

// Keith, 2026-10-24, reversing provisional #18: the dataset list's small
// sparkline names each point's cause in a per-point tooltip (criterion 13).
describe("the dataset list's sparkline names each point's cause", () => {
  it("gives every point a tooltip saying when it was and what caused it", () => {
    const w = load();
    const col = { datasets: [{ id: "cp-notifications", name: "Notifications" }] };
    const ds = { id: "cp-clients", name: "Client Register" };
    const units = [column("c", [
      entry({ run: "a", rank: 1, supply: "s@1", cause: "arrival:1", at: "2026-03-01T09:00:00+08:00" }),
      entry({ run: "b", rank: 2, supply: "s@1", cause: "decision:7", at: "2026-03-02T15:00:00+08:00",
              status: "red" }),
      entry({ run: "n", rank: 3, supply: "s@1", cause: "arrival:9", at: "2026-03-03T10:00:00+08:00",
              by: "cp-notifications" }),
    ])];
    const html = w.columnsNotGreenCell(units, false, false, { col, ds });
    const doc = new w.DOMParser().parseFromString(html, "text/html");
    const titles = [...doc.querySelectorAll("svg title")].map((t) => t.textContent);
    expect(titles).toHaveLength(3);
    expect(titles[0]).toMatch(/Client Register's run/);
    expect(titles[1]).toMatch(/Client Register's re-check/);
    expect(titles[2]).toMatch(/Notifications's run/);
    // One accessible name for the whole sparkline, as before.
    expect(doc.querySelectorAll("svg[aria-label]")).toHaveLength(1);
  });
});

// Keith, 2026-10-24: a row matched to the blocker - rule #21's contested pair
// or the held rule - that could not be checked says WHY, in the same sentence
// the banner alone used to explain.
describe("a blocked table's could-not-be-checked row says why", () => {
  const coll = { datasets: [{ id: "cp-notifications", name: "Notifications" }] };
  const tried = (extra) => entry({ run: "n", rank: 5, supply: null, cause: "arrival:n", status: "red",
                                   at: "2020-11-01T08:20:00+08:00", by: "cp-notifications",
                                   not_evaluated: "missing_table", ...extra });
  const page = (ck) => ({ id: "cp-clients", name: "Client Register",
                          columns: [{ name: "Cross-table", scope: "cross-table", checks: [ck] }] });
  const START = "Could not be checked 8:20am Sunday, 1 November 2020, when the Notifications supply arrived";

  it("names the contested pair's files", () => {
    const w = load();
    const pair = ["cp_clients__k__1", "cp_clients__k__2"];
    const ds = page({ key: "ref", history: [], contested_reads: [
      tried({ read_state: "ABSENT", contested_files: pair })] });
    w.blockChecksWhileHeld(ds, { kind: "contested", supply: "cp-clients@k#1", tables: pair,
                                 files: ["cp_clients.csv", "cp_clients_part2.csv"] });
    expect(w.rowRecheckNote(coll, ds.columns[0].checks[0])).toBe(
      `${START}: two Client Register files (cp_clients.csv, cp_clients_part2.csv) are waiting to be settled.`);
  });

  it("says the held supply is held", () => {
    const w = load();
    const ds = page({ key: "ref", history: [tried({ supply: "cp-clients@held", read_state: "HELD" })] });
    w.blockChecksWhileHeld(ds, { kind: "held", supply: "cp-clients@held" });
    expect(w.rowRecheckNote(coll, ds.columns[0].checks[0])).toBe(
      `${START}: the Client Register supply is held.`);
  });

  it("leaves a row the blocker did not match as it was", () => {
    const w = load();
    const ck = { key: "ref", history: [tried({})] };
    expect(w.rowRecheckNote(coll, ck)).toBe(`${START}.`);
  });
});
