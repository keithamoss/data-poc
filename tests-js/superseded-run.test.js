// A SUPERSEDED RUN ON THE DATES IT WAS CURRENT (post-build-review #266, Keith
// 2026-10-24, answer A). A page lists each supply by its CURRENT run, so once a
// full re-check of a supply is recorded its arrival run was on no page - and on
// the dates between the arrival and the re-check the page had nothing for the
// supply at all, while the gate (supply_status.results_about) counted the
// arrival's result. Example: Clients received 12 Oct 2023, re-checked 21 Oct;
// as at 15 Oct the Client reference card was empty.
//
// The build now gives each card its superseded runs' entries apart from its
// history (`superseded`), each naming the run that replaced it and the supply's
// current run; the page shows one from when it was recorded until the run that
// replaced it is recorded, exactly as it clips everything else.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1, expected_time: "09:00" };
const C = "cp-clients@202310121000000800";
const ARRIVAL = "cp_clients__a", RECHECK = "cp_clients__a__r1";
const INV_ARRIVAL = "cp_investigations__a", INV_RECHECK = "cp_investigations__a__r1";
const RECEIVED = "2023-10-12T10:00:00+08:00", RECHECKED = "2023-10-21T10:00:00+08:00";

function own(run_id, rank, at, status, extra = {}) {
  return { run_id, run_date: "2023-10-12", rank, supply_id: C, value: status === "red" ? 3 : 0,
    status, recorded_at: at, recorded_by: null, cause: `c:${run_id}`, ...extra };
}
function reader(run_id, rank, at, status, extra = {}) {
  return { run_id, run_date: at.slice(0, 10), rank, supply_id: C, read_state: "READ",
    value: status === "red" ? 3 : 0, status, recorded_at: at, recorded_by: "cp-investigations",
    recorded_in: "arrival", cause: `c:${run_id}`, ...extra };
}

function clients({ counted = true } = {}) {
  const runs = [{ run_id: RECHECK, run_date: "2023-10-12", received_at: RECEIVED, supply_id: C }];
  return {
    id: "cp-clients", name: "Client Register", sla: { cadence: QUARTERLY },
    runs, rowCount: 10, prevRowCount: 10,
    arrivalHistory: [{ run_id: RECHECK, run_date: "2023-10-12", arrivalStatus: "onTime" }],
    arrivalByRun: {},
    columns: [
      { name: "cp_client_id", stats: { current: {}, previous: {}, byRun: {} }, checks: [{
        key: "not_null", name: "Not null", warn: 0, fail: 0,
        history: [own(RECHECK, 4, RECHECKED, "green")],
        superseded: [own(ARRIVAL, 1, RECEIVED, "red", { replaced_by: RECHECK, supply_run: RECHECK })],
      }] },
      { name: "Cross-table", scope: "cross-table", stats: { current: {}, previous: {}, byRun: {} }, checks: [{
        key: "client_reference", name: "Client reference", warn: 0, fail: 0,
        history: [reader(INV_RECHECK, 3, RECHECKED, "green", { recorded_in: "re-check" })],
        superseded: [reader(INV_ARRIVAL, 2, RECEIVED, "red", { replaced_by: INV_RECHECK })],
        ...(counted ? { counted: { [C]: [{ on: "2023-10-12", rank: 2, reason: null },
                                          { on: "2023-10-21", rank: 3, reason: null }] } } : {}),
      }] },
    ],
  };
}

function clip(ds, date) {
  dashboard = loadDashboard();
  return dashboard.window.clipDatasetToInPlaceOn(ds, date);
}

describe("between the arrival and its full re-check", () => {
  it("shows the arrival run's own result", () => {
    const ck = clip(clients(), "2023-10-15").columns[0].checks[0];
    expect(ck).toBeDefined();
    expect(ck.history.map((h) => h.run_id)).toEqual([ARRIVAL]);
    expect(ck.current_status).toBe("red");
  });

  it("shows the cross-table result the build counts on that date", () => {
    const ck = clip(clients(), "2023-10-15").columns[1].checks[0];
    expect(ck).toBeDefined();
    expect(ck.history.map((h) => h.run_id)).toEqual([INV_ARRIVAL]);
    expect(ck.current_status).toBe("red");
  });

  it("counts the supply's point in the dataset list", () => {
    const clipped = clip(clients(), "2023-10-15");
    const counts = dashboard.window.unitCounts(clipped.columns);
    expect(counts.at(-1)).toMatchObject({ counted: 2, red: 2 });
  });
});

describe("once the re-check is recorded", () => {
  it("shows the re-check alone, the superseded run gone from the history", () => {
    const clipped = clip(clients(), "2023-10-22");
    expect(clipped.columns[0].checks[0].history.map((h) => h.run_id)).toEqual([RECHECK]);
    expect(clipped.columns[0].checks[0].current_status).toBe("green");
    expect(clipped.columns[1].checks[0].history.map((h) => h.run_id)).toEqual([INV_RECHECK]);
    expect(clipped.columns[1].checks[0].current_status).toBe("green");
  });

  it("keeps a superseded result the build still counts", () => {
    // The re-check's result does not count (it read a supply not in the
    // warehouse), so the gate falls back to the newest counted - the arrival's.
    const ds = clients();
    ds.columns[1].checks[0].counted[C][1].rank = 2;
    const ck = clip(ds, "2023-10-22").columns[1].checks[0];
    expect(ck.history.map((h) => h.run_id)).toEqual([INV_ARRIVAL, INV_RECHECK]);
    expect(ck.current_status).toBe("red");
  });
});

describe("before the supply arrived", () => {
  it("shows nothing", () => {
    expect(clip(clients(), "2023-10-11")).toBe(null);
  });
});
