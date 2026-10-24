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
