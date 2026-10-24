// post-build-review #253, Keith's call 2026-10-19 (option a): a dataset page
// shows each check's newest result, whichever run recorded it - the promotion
// gate's reading. TS-80: the Client Register's re-check re-ran Notifications'
// "Client reference" under the Client Register's own run, and Notifications'
// page went on showing its own arrival's red until its next supply.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1, expected_time: "09:00" };

function notifications() {
  const own = { run_id: "cp_notifications__202011010820000800", run_date: "2020-11-01" };
  return {
    id: "cp-notifications", name: "Notifications", sla: { cadence: QUARTERLY },
    runs: [own], rowCount: 987, prevRowCount: 987,
    arrivalHistory: [{ run_id: own.run_id, run_date: own.run_date, arrivalStatus: "onTime" }],
    arrivalByRun: { [own.run_id]: { arrivedAt: "2020-11-01T08:20:00+08:00", arrivalStatus: "onTime" } },
    lastArrival: { run_date: own.run_date, arrivedAt: "2020-11-01T08:20:00+08:00", arrivalStatus: "onTime" },
    columns: [{
      name: "Cross-table", scope: "cross-table",
      stats: { current: {}, previous: {}, byRun: {} },
      checks: [{
        key: "client_reference", name: "Client reference", warn: 0, fail: 0,
        history: [
          { run_id: own.run_id, run_date: "2020-11-01", value: 40, status: "red",
            recorded_at: "2020-11-01T08:20:00+08:00", recorded_by: null },
          { run_id: "cp_clients__202011010830000800__1__r1", run_date: "2020-11-01", value: 0,
            status: "green", recorded_at: "2020-11-02T11:00:00+08:00", recorded_by: "cp-clients" },
        ],
      }],
    }],
  };
}

function checkOn(date) {
  dashboard = loadDashboard();
  const clipped = dashboard.window.clipDatasetToInPlaceOn(notifications(), date);
  return clipped.columns[0].checks[0];
}

describe("a result recorded under another table's run", () => {
  it("is the check's verdict from the day it was recorded", () => {
    const ck = checkOn("2020-11-03");
    expect(ck.current_status).toBe("green");
    expect(ck.history.map((h) => h.run_id)).toContain("cp_clients__202011010830000800__1__r1");
  });

  it("is not on the page before it was recorded", () => {
    const ck = checkOn("2020-11-01");
    expect(ck.current_status).toBe("red");
    expect(ck.history).toHaveLength(1);
  });
});

describe("a cross-table row names the tables it is between", () => {
  it("names the declaring dataset, then the ones it reads", () => {
    dashboard = loadDashboard();
    const col = { datasets: [{ id: "cp-notifications", name: "Notifications" },
                             { id: "cp-clients", name: "Clients" }] };
    expect(dashboard.window.crossTableBetween(col,
      { between: { declared_on: "cp-notifications", reads: ["cp-clients"] } }))
      .toBe("Notifications → Clients");
    expect(dashboard.window.crossTableBetween(col, { between: null })).toBe("");
  });
});

// REQ-DASH-264 criteria 3 and 5 (Keith 2026-10-19, option 2): while a table's
// own supply is held, its cross-table rows show what they found of the held
// supply (criterion 3 as REQ-PIPE-279 amended it); its own checks, and any
// cross-table row that met none, read not run.
describe("a held table's page", () => {
  // REQ-PIPE-279 criterion 15, amending REQ-DASH-264 criterion 3: a row shows
  // the result that met the held supply - its recorded read of this table HELD
  // with that supply's id - never one picked by being recorded after the
  // receipt, which could be about another supply.
  const HELD = "cp-notifications@held";
  function held() {
    const entry = (at, status, read_state, supply) => ({ run_id: `r_${at}`, run_date: at.slice(0, 10),
      value: status === "red" ? 40 : 0, status, recorded_at: at, recorded_by: "cp-clients",
      read_state, supply_id: supply, cause: `arrival:${at}` });
    return {
      columns: [
        { name: "cp_client_id", checks: [{ key: "not_null", history: [entry("2020-08-01T09:00:00+08:00", "green")],
                                           current_status: "green" }] },
        { name: "Cross-table", scope: "cross-table", checks: [
          { key: "client_reference", history: [entry("2020-08-01T09:00:00+08:00", "green", "READ", "cp-notifications@aug"),
                                               entry("2020-11-01T08:20:00+08:00", "red", "HELD", HELD)], current_status: "red" },
          { key: "closed_case", history: [entry("2020-12-01T09:00:00+08:00", "green", "READ", "cp-notifications@aug")],
            current_status: "green" },
        ] },
      ],
    };
  }

  it("shows a cross-table result that met the held supply, and none that did not", () => {
    dashboard = loadDashboard();
    const ds = held();
    const shown = dashboard.window.blockChecksWhileHeld(ds, { supply: HELD, openedAt: "2020-11-01T08:20:00+08:00" });
    const [own, cross] = ds.columns;
    expect(shown).toBe(1);
    expect(dashboard.window.checkStatus(own.checks[0])).toBe("nodata");
    expect(dashboard.window.checkStatus(cross.checks[0])).toBe("red");
    // Recorded after the receipt, but about another supply.
    expect(dashboard.window.checkStatus(cross.checks[1])).toBe("nodata");
    expect(own.status).toBe("nodata");
  });

  it("shows none when no result met the held supply", () => {
    dashboard = loadDashboard();
    const ds = held();
    expect(dashboard.window.blockChecksWhileHeld(ds, { supply: "cp-notifications@another" })).toBe(0);
    expect(ds.columns[1].checks.every((ck) => dashboard.window.checkStatus(ck) === "nodata")).toBe(true);
  });
});

// REQ-DASH-264 criterion 1: "recorded on or before the in-place-on date" holds
// for a dataset's OWN re-check too - its run is dated by the supply it
// re-checked, but its result exists only from when it was recorded.
describe("an own re-check recorded after the date on show", () => {
  it("is not on the page before it was recorded", () => {
    dashboard = loadDashboard();
    const ds = notifications();
    ds.runs.push({ run_id: "cp_notifications__202011010820000800__1__r1", run_date: "2020-11-01" });
    ds.columns[0].checks[0].history = [
      ds.columns[0].checks[0].history[0],
      { run_id: "cp_notifications__202011010820000800__1__r1", run_date: "2020-11-01", value: 0,
        status: "green", recorded_at: "2020-11-02T11:00:00+08:00", recorded_by: null },
    ];
    const on1 = dashboard.window.clipDatasetToInPlaceOn(ds, "2020-11-01").columns[0].checks[0];
    expect(on1.current_status).toBe("red");
    const on2 = dashboard.window.clipDatasetToInPlaceOn(ds, "2020-11-02").columns[0].checks[0];
    expect(on2.current_status).toBe("green");
  });
});

// REQ-DASH-225 criterion 18 with REQ-DASH-264: a result recorded under another
// table's run counts against the dataset's own run it follows, so the list's
// latest count and the page agree.
describe("unitCounts with a result from another table's run", () => {
  // A RE-CHECK of the supply is a point of its own (REQ-PIPE-279 criterion 10,
  // its cause a decision), carrying every other unit from that supply's point
  // before. It was a point of its own for being recorded on a later DAY (#258
  // Q4), a rule the point key retired.
  it("counts a re-check as its own point, carrying the other units forward", () => {
    dashboard = loadDashboard();
    const own = { run_id: "own_1", run_date: "2020-11-01", status: "red", recorded_at: "2020-11-01T08:20:00+08:00",
                  recorded_by: null, rank: 1, supply_id: "cp-notifications@1", cause: "arrival:d@1" };
    const later = { run_id: "other_r1", run_date: "2020-11-01", status: "green", rank: 2,
                    recorded_at: "2020-11-02T11:00:00+08:00", recorded_by: "cp-clients",
                    supply_id: "cp-notifications@1", cause: "decision:7" };
    const units = [
      { name: "a_column", checks: [{ history: [{ ...own, status: "green" }] }] },
      { name: "Cross-table", scope: "cross-table", checks: [{ history: [own, later] }] },
    ];
    const counts = dashboard.window.unitCounts(units);
    expect(counts.map((c) => c.runId)).toEqual(["own_1", "cp-notifications@1 | decision:7"]);
    expect(counts[0]).toMatchObject({ counted: 2, red: 1, amber: 0 });
    expect(counts[1]).toMatchObject({ counted: 2, red: 0, amber: 0 });
  });
});

// REQ-DASH-264 criteria 7-9 (Keith 2026-10-19, approved as worded).
describe("a result from another table's re-check says so", () => {
  const col = { datasets: [{ id: "cp-clients", name: "Client Register" }, { id: "cp-notifications", name: "Notifications" }] };

  it("names when and which table was re-checked", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.recheckNote(col, {
      recorded_by: "cp-clients", recorded_in: "re-check", recorded_at: "2020-11-02T11:00:00+08:00",
    })).toBe("Re-checked 11:00am Monday, 2 November 2020, when the Client Register was re-checked.");
  });

  it("says nothing for the dataset's own run", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.recheckNote(col, { recorded_by: null, recorded_at: "2020-11-01T08:20:00+08:00" })).toBe("");
  });

  // Keith, 2026-10-19 night: arrivals too, every time, in these words.
  it("names when and which table's supply arrived, for another table's arrival", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.recheckNote(col, {
      recorded_by: "cp-notifications", recorded_in: "arrival", recorded_at: "2020-11-01T08:20:00+08:00",
    })).toBe("Checked 8:20am Sunday, 1 November 2020, when the Notifications supply arrived.");
  });

  it("dates its point on the chart by when it was recorded", () => {
    dashboard = loadDashboard();
    const ds = notifications();
    ds.columns[0].checks[0].history[1].recorded_in = "re-check";
    const built = dashboard.window.buildRealDataset(dashboard.window.clipDatasetToInPlaceOn(ds, "2020-11-03"));
    const last = built.columns[0].checks[0].history.at(-1);
    expect(dashboard.window.assetDateStrOf(last.date.toISOString())).toBe("2020-11-02");
  });
});

// UX critic on REQ-DASH-264 (post-build-review #258, finding 1): a result that
// could not be evaluated checked nothing, so neither sentence may say it did.
describe("a result that could not be evaluated", () => {
  it("does not count toward the banner's 'did run' sentence", () => {
    dashboard = loadDashboard();
    const ds = { columns: [{ name: "Cross-table", scope: "cross-table", checks: [{ key: "ref", history: [
      { run_id: "r", run_date: "2020-11-01", status: "red", value: null, recorded_by: "cp-notifications",
        recorded_at: "2020-11-01T08:20:00+08:00", not_evaluated: "could not run",
        read_state: "HELD", supply_id: "cp-clients@held", cause: "arrival:r" }] }] }] };
    expect(dashboard.window.blockChecksWhileHeld(ds, { supply: "cp-clients@held" })).toBe(0);
    // ...but the row still shows what was recorded (criterion 3).
    expect(dashboard.window.checkStatus(ds.columns[0].checks[0])).not.toBe("nodata");
    // ...and the section's pill follows the rows it shows, not the banner's
    // count (post-build-review #258 D1): a red row under a No data head is a
    // contradiction on screen.
    expect(ds.crossTableRowsWhileHeld).toBe(1);
  });
});

// post-build-review #258, the functional critic's D2 and P1.
describe("a held table's cross-table row", () => {
  const held = (recordedAt) => ({ columns: [{ name: "Cross-table", scope: "cross-table", checks: [{ key: "ref", history: [
    { run_id: "r", run_date: "2020-11-01", status: "green", value: 0, recorded_by: "cp-notifications",
      recorded_in: "arrival", recorded_at: recordedAt }] }] }] });
  const col = { datasets: [{ id: "cp-notifications", name: "Notifications" }] };

  it("says nothing about when it was checked while it reads No data", () => {
    dashboard = loadDashboard();
    const ds = held("2020-08-01T08:20:00+08:00");
    dashboard.window.blockChecksWhileHeld(ds, "2020-11-01T08:20:00+08:00");
    const ck = ds.columns[0].checks[0];
    expect(ck.blockedThisPeriod).toBe(true);
    expect(dashboard.window.rowRecheckNote(col, ck)).toBe("");
  });

  it("is blocked when the held supply is unknown, rather than shown", () => {
    dashboard = loadDashboard();
    const ds = held("2020-08-01T08:20:00+08:00");
    expect(dashboard.window.blockChecksWhileHeld(ds, null)).toBe(0);
    expect(ds.columns[0].checks[0].blockedThisPeriod).toBe(true);
  });
});

// Keith's four answers on post-build-review #258, 2026-10-20 - (a) on each.
describe("Q1: a result that could not run, on a held table's page", () => {
  const col = { datasets: [{ id: "cp-notifications", name: "Notifications" }, { id: "cp-clients", name: "Client Register" }] };
  it("says it could not be checked, and when", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.recheckNote(col, {
      recorded_by: "cp-notifications", recorded_in: "arrival", recorded_at: "2020-11-01T08:20:00+08:00",
      status: "red", not_evaluated: "could not run - two files claim cp_clients for this period",
    })).toBe("Could not be checked 8:20am Sunday, 1 November 2020, when the Notifications supply arrived.");
    expect(dashboard.window.recheckNote(col, {
      recorded_by: "cp-clients", recorded_in: "re-check", recorded_at: "2020-11-02T11:00:00+08:00",
      status: "red", not_evaluated: "could not run",
    })).toBe("Could not be checked 11:00am Monday, 2 November 2020, when the Client Register was re-checked.");
  });

  it("gives the banner its own sentence when none of the shown checks ran", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    expect(w.heldCrossTableSentence({ crossTableRowsWhileHeld: 12, crossTableShownWhileHeld: 0 }))
      .toBe(" The cross-table checks could not run either: the tables that read this one need its supply first.");
    expect(w.heldCrossTableSentence({ crossTableRowsWhileHeld: 3, crossTableShownWhileHeld: 3 }))
      .toBe(" The cross-table checks did run, on the tables that read this one, and show what they found.");
    expect(w.heldCrossTableSentence({ crossTableRowsWhileHeld: 0, crossTableShownWhileHeld: 0 })).toBe("");
  });
});

describe("Q2: the collection page's cross-table row", () => {
  it("names the declaring table and what it reads, and takes the declaring table's copy", () => {
    dashboard = loadDashboard();
    const check = (status) => ({ check_id: "x1", key: "investigation_id.closed_case_investigation_hygiene_dbt",
      name: "Closed-case hygiene", tool_ref: "dbt:expression", status, history: [{ run_id: "r", status }],
      between: { declared_on: "cp-investigations", reads: ["cp-clients"] } });
    const col = { datasets: [
      { id: "cp-clients", name: "Client Register", columns: [{ scope: "cross-table", checks: [check("nodata")] }] },
      { id: "cp-investigations", name: "Investigations", columns: [{ scope: "cross-table", checks: [check("red")] }] },
    ] };
    const [entry] = dashboard.window.collectionCrossTableChecks(col);
    expect(entry.dataset.id).toBe("cp-investigations");
    expect(dashboard.window.crossTableSource(col, entry)).toBe("Investigations → Client Register · dbt");
  });
});

describe("Q3, as K3 = C left it: every evaluation is a point for the comparison and the run count", () => {
  // REQ-PIPE-279 (Keith, K3 = C): a delivery whose files were checked at two
  // instants is two points, so the panel counts four here where #258 Q3's
  // same-day rule counted two, and compares with the newest earlier point.
  const own = (d, t, s) => ({ run_id: `own_${d}`, run_date: d, status: s, recorded_by: null,
    recorded_at: `${d}T${t}+08:00`, supply_id: `n@${d}`, cause: `arrival:${d}@${t}` });
  const other = (d, t, s, by = "cp-clients", inn = "arrival") => ({ run_id: `oth_${d}_${t}`, run_date: d, status: s,
    recorded_by: by, recorded_in: inn, recorded_at: `${d}T${t}+08:00`, supply_id: `n@${d}`,
    cause: inn === "re-check" ? `decision:${d}` : `arrival:${d}@${t}` });
  const history = [own("2020-05-01", "01:00:00", "green"), other("2020-05-01", "01:08:00", "green"),
                   own("2020-08-01", "01:00:00", "red"), other("2020-08-01", "01:05:00", "red")];

  it("compares with the newest earlier point, the same delivery's other evaluation included", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.defaultCompareIndex(history)).toBe(2);
  });

  it("counts every point", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.deliveryCount(history)).toBe(4);
  });

  it("keeps a same-day resupply of the dataset's own as two runs", () => {
    dashboard = loadDashboard();
    const resupplied = [own("2020-05-01", "01:00:00", "red"), { ...own("2020-05-01", "09:00:00", "green"), run_id: "own_b" }];
    expect(dashboard.window.deliveryCount(resupplied)).toBe(2);
    expect(dashboard.window.defaultCompareIndex(resupplied)).toBe(0);
  });

  it("labels a row that came from another table's run with its cause and when", () => {
    dashboard = loadDashboard();
    const col = { datasets: [{ id: "cp-clients", name: "Client Register" }] };
    expect(dashboard.window.historySource(col, history[1]))
      .toBe("from the Client Register's run, 1:08am Friday, 1 May 2020");
    expect(dashboard.window.historySource(col, other("2020-11-02", "11:00:00", "green", "cp-clients", "re-check")))
      .toBe("from the Client Register's re-check, 11:00am Monday, 2 November 2020");
    expect(dashboard.window.historySource(col, history[0])).toBe("");
  });
});

describe("Q4: a sparkline point is dated by when its result was recorded", () => {
  // REQ-PIPE-279 criteria 10 and 12: each cause its own point, dated by its
  // lowest-ranked result. The same-day result no longer replaces the own run's
  // verdict (REQ-DASH-264 criterion 12, retired): it is another arrival's.
  it("gives a same-day result of another cause a point of its own, and a later one too", () => {
    dashboard = loadDashboard();
    const at = (run_id, day, status, recorded_by, cause, rank, time) => ({ run_id, run_date: "2020-11-01",
      date: new Date(`${day}T00:00:00Z`), status, recorded_by, recorded_at: `${day}T${time}+08:00`,
      supply_id: "n@1", cause, rank });
    const own = at("own_1", "2020-11-01", "red", null, "arrival:a", 1, "08:20:00");
    const sameDay = at("oth_a", "2020-11-01", "amber", "cp-clients", "arrival:b", 2, "08:30:00");
    const later = at("oth_r1", "2020-11-02", "green", "cp-clients", "decision:1", 3, "11:00:00");
    const units = [
      { name: "a_column", checks: [{ history: [{ ...own, status: "green" }] }] },
      { name: "Cross-table", scope: "cross-table", checks: [{ history: [own, sameDay, later] }] },
    ];
    const counts = dashboard.window.unitCounts(units);
    expect(counts).toHaveLength(3);
    expect(counts[0]).toMatchObject({ counted: 2, red: 1, amber: 0 });
    expect(counts[1]).toMatchObject({ counted: 2, red: 0, amber: 1 });
    expect(counts[2].date.toISOString().slice(0, 10)).toBe("2020-11-02");
    expect(counts[2]).toMatchObject({ counted: 2, red: 0, amber: 0 });
  });
});

// REQ-PIPE-265: a check carried from a sibling of the same delivery has no
// result under this dataset's own run at all - only the sibling's. Found by the
// gate (TestColumnsNotGreenMatchesTheDatasetPage, Notifications 9 of 10): the
// row skipped it, while the page showed it.
describe("REQ-PIPE-265: a check with only a carried result", () => {
  // The point is the supply and the cause it was recorded under (REQ-PIPE-279
  // criterion 10) - a carried result is the zip's, so it is the supply's own
  // point. These keyed it by a read_run and the day until then.
  const at = (run_id, day, status, recorded_by, supply, cause, rank) => ({ run_id, run_date: day,
    date: new Date(`${day}T00:00:00Z`), status, recorded_by, recorded_at: `${day}T09:00:00+08:00`,
    supply_id: supply, cause, rank });
  it("still counts on the dataset's own point of that delivery", () => {
    dashboard = loadDashboard();
    const own = at("own_1", "2020-11-01", "green", null, "n@1", "arrival:zip", 1);
    const carried = at("cp_clients__1", "2020-11-01", "red", "cp-clients", "n@1", "arrival:zip", 2);
    const units = [
      { name: "a_column", checks: [{ history: [own] }] },
      { name: "Cross-table", scope: "cross-table", checks: [{ history: [carried] }] },
    ];
    const counts = dashboard.window.unitCounts(units);
    expect(counts).toHaveLength(1);
    expect(counts[0]).toMatchObject({ runId: "own_1", counted: 2, red: 1, amber: 0 });
  });

  it("counts on the later delivery's point when an earlier one judged it itself", () => {
    dashboard = loadDashboard();
    const units = [
      { name: "a_column", checks: [{ history: [at("own_may", "2026-05-27", "green", null, "n@may", "arrival:may", 1),
                                               at("own_aug", "2026-08-01", "green", null, "n@aug", "arrival:aug", 2)] }] },
      { name: "Cross-table", scope: "cross-table",
        checks: [{ history: [at("own_may", "2026-05-27", "green", null, "n@may", "arrival:may", 1),
                             at("cp_clients__aug", "2026-08-01", "red", "cp-clients", "n@aug", "arrival:aug", 3)] }] },
    ];
    const counts = dashboard.window.unitCounts(units);
    expect(counts.map(c => c.runId)).toEqual(["own_may", "own_aug"]);
    expect(counts[1]).toMatchObject({ counted: 2, red: 1, amber: 0 });
  });
});

// post-build-review #258's UX points (minor polish, 2026-10-20).
describe("the cross-table rows on a dataset page", () => {
  it("keep each relationship's three tools together, dbt first", () => {
    dashboard = loadDashboard();
    const col = { datasets: [{ id: "cp-clients", name: "Client Register" },
                             { id: "cp-investigations", name: "Investigations" },
                             { id: "cp-notifications", name: "Notifications" }] };
    const row = (tool, from, name) => ({ ck: { name, tool_ref: `${tool}:x`,
      between: { declared_on: from, reads: ["cp-clients"] } } });
    const rows = [row("dbt", "cp-investigations", "Client reference"), row("dbt", "cp-notifications", "Client reference"),
                  row("soda", "cp-investigations", "Client reference"), row("soda", "cp-notifications", "Client reference"),
                  row("datacontract", "cp-investigations", "Client reference"), row("datacontract", "cp-notifications", "Client reference")];
    const got = dashboard.window.crossTableRowOrder(col, rows)
      .map((r) => `${r.ck.between.declared_on}/${r.ck.tool_ref.split(":")[0]}`);
    expect(got).toEqual(["cp-investigations/dbt", "cp-investigations/soda", "cp-investigations/datacontract",
                         "cp-notifications/dbt", "cp-notifications/soda", "cp-notifications/datacontract"]);
  });
});

describe("the panel's default comparison", () => {
  it("skips a result that could not be evaluated", () => {
    dashboard = loadDashboard();
    const h = (d, s, extra = {}) => ({ run_id: `own_${d}`, run_date: d, status: s, recorded_by: null,
                                       recorded_at: `${d}T01:00:00+08:00`, ...extra });
    const history = [h("2020-05-01", "green"), h("2020-08-01", "red", { not_evaluated: "not yet supplied" }),
                     h("2020-11-01", "green")];
    expect(dashboard.window.defaultCompareIndex(history)).toBe(0);
  });
});
