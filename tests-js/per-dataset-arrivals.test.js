// Supply history and as-of viewing when a collection's tables arrive on
// their own schedules (REQ-DASH-041).
//
// WHY THIS EXISTS SEPARATELY, in the requirement's own words: the
// chain-building half was already driven in a real browser against a
// doctored dataset and held up. What was never tested is the AS-OF
// PICKER and the rendered supply history over datasets whose arrival
// dates do not line up - and a correct builder says nothing about a
// template with its own transform, which is the lesson item 74 and
// REQ-DASH-032 both landed on.
//
// The real committed history cannot exercise this: all six Child
// Protection datasets arrive together, 18 runs each on the same dates,
// because the generator emits one six-table delivery per period. So
// the divergence is constructed here deliberately rather than waited
// for.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load() {
  dashboard = loadDashboard();
  return dashboard.window;
}

const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1, expected_time: "17:00" };
const DAILY = { type: "daily", expected_time: "14:00" };

// One dataset, arriving on exactly the dates given. Each run carries a
// green check so status rollups have something real to read.
function datasetArrivingOn(id, dates, cadence = QUARTERLY) {
  const runs = dates.map((d, i) => ({ run_id: `${id}_r${i + 1}`, run_date: d }));
  return {
    id,
    name: id,
    sla: { cadence },
    runs,
    rowCount: 100,
    prevRowCount: 100,
    arrivalHistory: runs.map((r, i) => ({ run_id: r.run_id, run_date: dates[i], arrivalStatus: "onTime" })),
    arrivalByRun: Object.fromEntries(runs.map((r, i) => [r.run_id,
      { arrivedAt: `${dates[i]}T09:00:00+08:00`, arrivalStatus: "onTime" }])),
    lastArrival: { run_date: dates[dates.length - 1], arrivedAt: `${dates[dates.length - 1]}T09:00:00+08:00`, arrivalStatus: "onTime" },
    columns: [{
      name: "a_column",
      stats: { current: {}, previous: {}, byRun: {} },
      checks: [{
        warn: 1, fail: 2,
        history: runs.map((r) => ({ run_id: r.run_id, run_date: r.run_date, value: 0 })),
      }],
    }],
  };
}

// A collection whose six tables genuinely do not line up: one is a
// quarter behind, one has never supplied at all since the as-of dates
// under test, and the rest are current.
const CURRENT = ["2026-02-01", "2026-05-01", "2026-08-01"];
const BEHIND = ["2026-02-01", "2026-05-01"];
const LATE_STARTER = ["2026-08-01"];

describe("each dataset's supply history comes from its own arrivals alone", () => {
  it("does not borrow a sibling dataset's runs", () => {
    const w = load();
    const current = datasetArrivingOn("cp-clients", CURRENT);
    const behind = datasetArrivingOn("cp-carers", BEHIND);

    const currentChains = w.buildSupplyHistory(current);
    const behindChains = w.buildSupplyHistory(behind);

    const runIds = (chains) => chains.flatMap((c) => c.entries.map((e) => e.run_id));
    expect(runIds(currentChains)).toHaveLength(3);
    expect(runIds(behindChains)).toHaveLength(2);
    // The sibling's ids appear nowhere in the other's history.
    expect(runIds(behindChains).some((id) => id.startsWith("cp-clients"))).toBe(false);
    expect(runIds(currentChains).some((id) => id.startsWith("cp-carers"))).toBe(false);
  });

  it("a dataset with a single arrival still builds a well-formed history", () => {
    const w = load();
    const chains = w.buildSupplyHistory(datasetArrivingOn("cp-case-workers", LATE_STARTER));
    expect(chains.flatMap((c) => c.entries)).toHaveLength(1);
  });
});

describe("as-of viewing across datasets whose dates do not line up", () => {
  it("shows each dataset as at ITS OWN most recent arrival on or before the date", () => {
    const w = load();
    const asOf = "2026-08-15";

    const current = w.clipDatasetToAsOf(datasetArrivingOn("cp-clients", CURRENT), asOf);
    const behind = w.clipDatasetToAsOf(datasetArrivingOn("cp-carers", BEHIND), asOf);

    expect(current.lastArrival.run_date).toBe("2026-08-01");
    expect(behind.lastArrival.run_date).toBe("2026-05-01");
  });

  it("clips each dataset's own runs, never the union of the collection's", () => {
    const w = load();
    const asOf = "2026-05-15";
    const current = w.clipDatasetToAsOf(datasetArrivingOn("cp-clients", CURRENT), asOf);
    const behind = w.clipDatasetToAsOf(datasetArrivingOn("cp-carers", BEHIND), asOf);

    expect(current.runs.map((r) => r.run_date)).toEqual(["2026-02-01", "2026-05-01"]);
    expect(behind.runs.map((r) => r.run_date)).toEqual(["2026-02-01", "2026-05-01"]);
  });

  it("the as-of view follows ARRIVAL, which today is the only thing it could follow", () => {
    // Criterion 3, and the contradiction recorded on this requirement:
    // Thread H's "as at T = the latest version PROMOTED on or before T"
    // was superseded by Keith's 2026-09-23 decision that the DASHBOARD
    // reports QA rather than warehouse contents. Nothing promotes yet,
    // so the two readings cannot diverge in the data - what this holds
    // is that the function reads `runs`, which are arrivals, and has no
    // promotion input at all to read instead.
    const w = load();
    const d = datasetArrivingOn("cp-clients", CURRENT);
    expect(w.clipDatasetToAsOf(d, "2026-08-15").lastArrival.run_date).toBe("2026-08-01");
    expect(Object.keys(d)).not.toContain("promotedRuns");
  });

  it("an arrival AFTER the as-of date is excluded from the clipped history", () => {
    const w = load();
    const clipped = w.clipDatasetToAsOf(datasetArrivingOn("cp-clients", CURRENT), "2026-05-01");
    expect(clipped.arrivalHistory.map((a) => a.run_date)).toEqual(["2026-02-01", "2026-05-01"]);
  });

  it("a daily dataset and a quarterly one in the same collection each clip on their own cadence", () => {
    const w = load();
    const quarterly = w.clipDatasetToAsOf(datasetArrivingOn("cp-clients", CURRENT, QUARTERLY), "2026-08-15");
    const daily = w.clipDatasetToAsOf(
      datasetArrivingOn("bdm", ["2026-08-13", "2026-08-14", "2026-08-15"], DAILY), "2026-08-15");

    // The quarterly one is inside its own current cycle and is not stale;
    // the daily one's newest run IS the as-of date, so neither is.
    expect(quarterly.staleAsOf).toBe(false);
    expect(daily.staleAsOf).toBe(false);
    expect(daily.runs).toHaveLength(3);
  });
});

describe("a dataset with no arrival on or before the chosen date", () => {
  it("returns the existing no-data-as-of state rather than an empty or stale panel", () => {
    const w = load();
    const clipped = w.clipDatasetToAsOf(datasetArrivingOn("cp-case-workers", LATE_STARTER), "2026-05-15");
    expect(clipped).toBeNull();
  });

  it("introduces no FURTHER quiet state alongside the ones that already exist", () => {
    // Criterion 4 forbids a second mechanism, so what this holds is
    // that the clip has exactly TWO outcomes - a clipped dataset, or
    // null meaning "use the existing no-data state". A third sentinel
    // is how a second quiet state would arrive, and it would arrive
    // from here.
    const w = load();
    const d = datasetArrivingOn("cp-case-workers", LATE_STARTER);
    for (const asOf of ["2026-01-01", "2026-05-15", "2026-08-01", "2026-12-31"]) {
      const clipped = w.clipDatasetToAsOf(d, asOf);
      expect(clipped === null || typeof clipped === "object").toBe(true);
      if (clipped !== null) expect(clipped.noDataAsOf).toBeUndefined();
    }
  });

  it("the no-data state it falls back to is the one the page already had", () => {
    const w = load();
    const d = datasetArrivingOn("cp-case-workers", LATE_STARTER);
    // noDataDataset() takes the identity fields the caller holds, not
    // a dataset - only the caller knows the name, because the feed it
    // would have come from is the thing that is missing.
    const empty = w.noDataDataset(d.id, d.name, "a provider", "CSV", d.sla);
    expect(empty.noDataAsOf).toBe(true);
    expect(empty.status).toBe("nodata");
    expect(empty.id).toBe("cp-case-workers");
  });
});

describe("a collection arriving on six different schedules is not a bug", () => {
  it("every dataset resolves to a real state at one as-of date", () => {
    const w = load();
    const asOf = "2026-06-15";
    const datasets = [
      datasetArrivingOn("cp-clients", CURRENT),
      datasetArrivingOn("cp-carers", BEHIND),
      datasetArrivingOn("cp-case-workers", LATE_STARTER),
      datasetArrivingOn("cp-notifications", CURRENT),
      datasetArrivingOn("cp-investigations", BEHIND),
      datasetArrivingOn("cp-placements", ["2026-05-01"]),
    ];

    const resolved = datasets.map((d) =>
      w.clipDatasetToAsOf(d, asOf) ?? w.noDataDataset(d.id, d.name, "a provider", "CSV", d.sla));

    // Five have supplied by then; the late starter has not.
    expect(resolved.filter((d) => d.noDataAsOf)).toHaveLength(1);
    expect(resolved.filter((d) => !d.noDataAsOf)).toHaveLength(5);
    // And nothing came back undefined - a dataset that resolves to
    // neither state is the "empty panel" criterion 4 forbids.
    expect(resolved.every(Boolean)).toBe(true);
  });
});
