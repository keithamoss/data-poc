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
