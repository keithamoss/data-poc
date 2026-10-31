// REQ-PIPE-269 and post-build-review #262 R4 (Keith, 2026-10-24: fix it with
// #95's sprint 1, and test this exact case). The as-of clip kept every result
// recorded under another table's run as a cross-table check's newest, whatever
// supply it read - so a late reader of an OLDER Client Register supply showed
// as current on the page of the newer one, while the gate would never use it.
// The build now says, per supply and date, which result counts toward the
// supply on show (pipeline/warehouse_counts.py); the page looks it up.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1, expected_time: "09:00" };
const C1 = "cp-clients@aug", C2 = "cp-clients@nov";

function clients(counted) {
  const run = (supply, day) => ({ run_id: `cp_clients__${day}`, run_date: day, supply_id: supply });
  const runs = [run(C1, "2020-08-01"), run(C2, "2020-11-01")];
  const entry = (rank, supply, at, status) => ({ run_id: `cp_notifications__${rank}`, run_date: at.slice(0, 10),
    rank, supply_id: supply, read_state: "READ", value: status === "red" ? 40 : 0, status,
    recorded_at: at, recorded_by: "cp-notifications", recorded_in: "arrival", cause: `arrival:${rank}` });
  return {
    id: "cp-clients", name: "Client Register", sla: { cadence: QUARTERLY },
    runs, rowCount: 10, prevRowCount: 10,
    arrivalHistory: runs.map((r) => ({ run_id: r.run_id, run_date: r.run_date, arrivalStatus: "onTime" })),
    arrivalByRun: {},
    columns: [{
      name: "Cross-table", scope: "cross-table", stats: { current: {}, previous: {}, byRun: {} },
      checks: [{
        key: "client_reference", name: "Client reference", warn: 0, fail: 0,
        history: [
          entry(1, C1, "2020-08-01T09:00:00+08:00", "green"),
          entry(2, C2, "2020-11-01T09:00:00+08:00", "green"),
          // THE LATE READER: a Notifications supply, checked after the newer
          // Client Register arrived, against the older one.
          entry(3, C1, "2020-11-05T09:00:00+08:00", "red"),
        ],
        ...(counted ? { counted } : {}),
      }],
    }],
  };
}

const COUNTED = {
  [C1]: [{ on: "2020-08-01", rank: 1, reason: null }, { on: "2020-11-05", rank: 3, reason: null }],
  [C2]: [{ on: "2020-11-01", rank: 2, reason: null }],
};

function checkOn(ds, date) {
  dashboard = loadDashboard();
  return dashboard.window.clipDatasetToInPlaceOn(ds, date).columns[0].checks[0];
}

describe("R4: a late reader of an older supply", () => {
  it("is not the current result on the newer supply's page", () => {
    const ck = checkOn(clients(COUNTED), "2020-11-06");
    expect(ck.current_status).toBe("green");
    expect(ck.history.at(-1).rank).toBe(3); // still SHOWN - nothing is deleted
  });

  it("is the current result for the older supply it read", () => {
    const ds = clients(COUNTED);
    ds.runs.pop(); // only the August supply had arrived
    ds.columns[0].checks[0].history.splice(1, 1);
    const ck = checkOn(ds, "2020-11-06");
    expect(ck.current_status).toBe("red");
  });
});

describe("a check with nothing counted toward the supply on show", () => {
  it("reads red where it is owed, with the reason", () => {
    const counted = { ...COUNTED, [C2]: [{ on: "2020-11-01", rank: 2, reason: null },
      { on: "2020-11-03", rank: null, reason: "recheck-owed", owedBy: 9, owedSince: "2020-11-03T10:00:00+08:00" }] };
    const ck = checkOn(clients(counted), "2020-11-04");
    expect(ck.current_status).toBe("red");
    expect(ck.warehouseReason).toBe("recheck-owed");
  });

  it("reads No data where it is owed nothing", () => {
    const counted = { ...COUNTED, [C2]: [{ on: "2020-11-01", rank: null, reason: "not-counted" }] };
    const ck = checkOn(clients(counted), "2020-11-04");
    expect(ck.current_status).toBe("nodata");
  });
});

// IMPOSSIBLE, AND SAID SO (post-build-review #266): a counted rank the history
// on the date does not hold. Taking the newest instead was R4 again - the late
// reader, rank 3, would have been shown as current on the newer supply's page.
describe("a counted result the history does not hold", () => {
  it("reads No data and says so in the console, never the newest result", () => {
    const counted = { ...COUNTED, [C2]: [{ on: "2020-11-01", rank: 99, reason: null }] };
    dashboard = loadDashboard();
    const errors = [];
    dashboard.window.console.error = (...args) => errors.push(args.join(" "));
    const ck = dashboard.window.clipDatasetToInPlaceOn(clients(counted), "2020-11-06")
      .columns[0].checks[0];
    expect(ck.current_status).toBe("nodata");
    expect(ck.warehouseReason).toBe("not-shown");
    expect(ck.current).toBe(null);
    expect(errors.some((e) => e.includes("rank 99") && e.includes("not shown"))).toBe(true);
  });
});

// The dataset list's count and the dataset page's trend are unitCounts() over
// the same clipped page, and its newest point must say what the page says
// (REQ-DASH-225 criterion 18, REQ-DASH-227 criterion 8) - so the late reader's
// point, the newest by rank, does not carry its red into the latest count.
describe("the newest point of the list's count", () => {
  it("agrees with the page on the late reader", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const clipped = w.clipDatasetToInPlaceOn(clients(COUNTED), "2020-11-06");
    const counts = w.unitCounts(clipped.columns);
    expect(counts.at(-1)).toMatchObject({ counted: 1, red: 0, amber: 0 });
  });

  it("leaves out a check counted toward nothing", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const counted = { ...COUNTED, [C2]: [{ on: "2020-11-01", rank: null, reason: "not-counted" }] };
    const ds = clients(counted);
    // Its own column, checked by its own run, beside the cross-table section.
    ds.columns.unshift({ name: "cp_client_id", stats: { current: {}, previous: {}, byRun: {} }, checks: [{
      key: "not_null", name: "Not null", warn: 0, fail: 0, history: [
        { run_id: "cp_clients__2020-11-01", run_date: "2020-11-01", rank: 4, supply_id: C2, value: 0,
          status: "green", recorded_at: "2020-11-01T09:00:00+08:00", recorded_by: null, cause: "arrival:c2" }] }] });
    const clipped = w.clipDatasetToInPlaceOn(ds, "2020-11-04");
    expect(w.unitCounts(clipped.columns).at(-1)).toMatchObject({ counted: 1, red: 0, amber: 0 });
  });
});
