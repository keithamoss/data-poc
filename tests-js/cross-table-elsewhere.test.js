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
// own supply is held, its cross-table rows show what they found since the held
// supply's receipt; its own checks, and any cross-table row with nothing since,
// read not run.
describe("a held table's page", () => {
  function held() {
    const entry = (at, status) => ({ run_id: `r_${at}`, run_date: at.slice(0, 10), value: status === "red" ? 40 : 0,
                                     status, recorded_at: at, recorded_by: "cp-notifications" });
    return {
      columns: [
        { name: "cp_client_id", checks: [{ key: "not_null", history: [entry("2020-08-01T09:00:00+08:00", "green")],
                                           current_status: "green" }] },
        { name: "Cross-table", scope: "cross-table", checks: [
          { key: "client_reference", history: [entry("2020-08-01T09:00:00+08:00", "green"),
                                               entry("2020-11-01T08:20:00+08:00", "red")], current_status: "red" },
          { key: "closed_case", history: [entry("2020-08-01T09:00:00+08:00", "green")], current_status: "green" },
        ] },
      ],
    };
  }

  it("shows a cross-table result recorded since the held receipt, and nothing older", () => {
    dashboard = loadDashboard();
    const ds = held();
    const shown = dashboard.window.blockChecksWhileHeld(ds, "2020-11-01T08:20:00+08:00");
    const [own, cross] = ds.columns;
    expect(shown).toBe(1);
    expect(dashboard.window.checkStatus(own.checks[0])).toBe("nodata");
    expect(dashboard.window.checkStatus(cross.checks[0])).toBe("red");
    expect(dashboard.window.checkStatus(cross.checks[1])).toBe("nodata");
    expect(own.status).toBe("nodata");
  });

  it("shows none when nothing was recorded since", () => {
    dashboard = loadDashboard();
    const ds = held();
    expect(dashboard.window.blockChecksWhileHeld(ds, "2020-11-02T00:00:00+08:00")).toBe(0);
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
  it("counts it on the dataset's own run it follows, replacing that run's verdict", () => {
    dashboard = loadDashboard();
    const own = { run_id: "own_1", run_date: "2020-11-01", status: "red", recorded_at: "2020-11-01T08:20:00+08:00",
                  recorded_by: null };
    const later = { run_id: "other_r1", run_date: "2020-11-01", status: "green",
                    recorded_at: "2020-11-02T11:00:00+08:00", recorded_by: "cp-clients" };
    const units = [
      { name: "a_column", checks: [{ history: [{ ...own, status: "green" }] }] },
      { name: "Cross-table", scope: "cross-table", checks: [{ history: [own, later] }] },
    ];
    const counts = dashboard.window.unitCounts(units);
    expect(counts.map((c) => c.runId)).toEqual(["own_1"]);
    expect(counts[0]).toMatchObject({ counted: 2, red: 0, amber: 0 });
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

  it("says nothing for the dataset's own run or another table's arrival", () => {
    dashboard = loadDashboard();
    expect(dashboard.window.recheckNote(col, { recorded_by: null, recorded_at: "2020-11-01T08:20:00+08:00" })).toBe("");
    expect(dashboard.window.recheckNote(col, {
      recorded_by: "cp-notifications", recorded_in: "arrival", recorded_at: "2020-11-01T08:20:00+08:00",
    })).toBe("");
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
