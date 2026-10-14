// REQ-DASH-182: every period a dataset owes nothing in is a quiet, labelled
// row in its supply history, and its SLA tile gives the delivery time in
// force on the date on show.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });
function load() { dashboard = loadDashboard(); return dashboard.window; }

const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1,
                    expected_time: "09:00", latency_minutes: 480 };
const REASON = "A staffing register rather than casework, so it is resupplied twice a year.";
const MAY = { period: "2026-Q2", date: "2026-05-01", kind: "participation", reason: REASON,
              months: [2, 8] };

function dataset(extra = {}) {
  const dates = ["2025-08-01", "2026-02-01"];
  const runs = dates.map((d, i) => ({ run_id: `r${i + 1}`, run_date: d }));
  return {
    id: "cp-case-workers", name: "Case Workers",
    sla: { cadence: QUARTERLY, owesFrom: "2023-01-01",
           versions: [{ from: "2023-01-01", reason: REASON,
                        cadence: { ...QUARTERLY, anchor_months: [2, 8] } }] },
    owedNothing: [MAY],
    runs, rowCount: 100, prevRowCount: 100,
    arrivalHistory: runs.map((r) => ({ run_id: r.run_id, run_date: r.run_date, arrivalStatus: "onTime" })),
    arrivalByRun: Object.fromEntries(runs.map((r) => [r.run_id,
      { arrivedAt: `${r.run_date}T09:00:00+08:00`, arrivalStatus: "onTime" }])),
    lastArrival: { run_date: "2026-02-01", arrivedAt: "2026-02-01T09:00:00+08:00", arrivalStatus: "onTime" },
    columns: [{ name: "c", stats: { current: {}, previous: {}, byRun: {} },
                checks: [{ warn: 1, fail: 2,
                           history: runs.map((r) => ({ run_id: r.run_id, run_date: r.run_date, value: 0 })) }] }],
    ...extra,
  };
}

function withRaw(w, raw) {
  w.rawRealDatasetById = () => raw;
  return w;
}

describe("one function words every owed-nothing period (criterion 14)", () => {
  it("names each kind with the page's em dash", () => {
    const w = load();
    expect(w.owedNothingLabel(MAY).label).toBe("Not owed — outside its agreed months (Feb, Aug)");
    expect(w.owedNothingLabel({ kind: "not_expected", reason: "migration" }).label)
      .toBe("Not expected — migration");
    expect(w.owedNothingLabel({ kind: "turned_off", reason: "supplier paused" }).label)
      .toBe("Turned off — supplier paused");
  });
});

describe("the SLA tile's delivery time (criteria 7, 8 and 11)", () => {
  it("names the dataset's own months with a frequency word", () => {
    const w = load();
    expect(w.cadenceLabel({ ...QUARTERLY, anchor_months: [2, 8] }))
      .toBe("Twice a year (Feb, Aug, day 1), by 09:00");
    expect(w.cadenceLabel(QUARTERLY)).toBe("Quarterly (Feb, May, Aug, Nov, day 1), by 09:00");
    expect(w.cadenceLabel({ ...QUARTERLY, anchor_months: [8] })).toBe("Yearly (Aug, day 1), by 09:00");
    expect(w.cadenceLabel({ ...QUARTERLY, anchor_months: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] }))
      .toMatch(/^Monthly \(/);
    expect(w.cadenceLabel({ ...QUARTERLY, anchor_months: [2, 5, 8] })).toMatch(/^3 times a year \(/);
  });

  it("says 'various days' rather than going blank, for an authored calendar too", () => {
    const w = load();
    expect(w.cadenceLabel({ type: "authored", anchor_months: [3, 9], day_of_month: null,
                            expected_time: "09:00" }))
      .toBe("Twice a year (Mar, Sep, various days), by 09:00");
  });

  it("says a supply due before the period's date in both forms", () => {
    const w = load();
    expect(w.cadenceLabel({ type: "daily", expected_time: "22:00", days_before: 1 }))
      .toBe("Daily, by 22:00 the day before");
    expect(w.cadenceLabel({ ...QUARTERLY, expected_time: "22:00", days_before: 3 }))
      .toBe("Quarterly (Feb, May, Aug, Nov, day 1), by 22:00, 3 days before each date");
  });

  it("takes the version in force on the date on show, with the reason muted beneath", () => {
    const w = load();
    const later = { from: "2026-03-01", reason: null, cadence: { ...QUARTERLY, expected_time: "11:00" } };
    const raw = dataset();
    raw.sla.versions.push(later);
    const before = w.slaTileHtml(raw, "2026-02-15");
    expect(before).toContain("Twice a year (Feb, Aug, day 1), by 09:00");
    expect(before).toContain("staffing register");
    const after = w.slaTileHtml(raw, "2026-04-15");
    expect(after).toContain("Quarterly (Feb, May, Aug, Nov, day 1), by 11:00");
    expect(after).not.toContain("staffing register");
  });

  it("says 'Not owed yet' before the first participation version (criterion 3)", () => {
    const w = load();
    const html = w.slaTileHtml(dataset(), "2022-06-01");
    expect(html).toContain("Not owed yet — owes supplies from");
    expect(html).toContain(w.fmtDay("2023-01-01"));
  });

  it("renders a reason as text, never markup (criterion 4)", () => {
    const w = load();
    const raw = dataset();
    raw.sla.versions[0].reason = "<img src=x onerror=alert(1)>";
    expect(w.slaTileHtml(raw, "2026-02-15")).toContain("&lt;img");
  });
});

describe("owed-nothing rows in the supply history (criteria 1, 2, 10, 12 and 13)", () => {
  it("is a quiet label-only block with no pill, only up to the date on show", () => {
    const w = withRaw(load(), dataset());
    const ds = dataset();
    const cycles = w.buildSupplyHistory(ds);
    w.eval("CURRENT_IN_PLACE_ON = '2026-04-15'");
    const before = w.renderSupplyHistorySection(ds, cycles, "2026-02-01");
    expect(before).not.toContain("Not owed —");
    w.eval("CURRENT_IN_PLACE_ON = '2026-06-15'");
    const html = w.renderSupplyHistorySection(ds, cycles, "2026-05-01");
    const doc = new w.DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    const row = doc.querySelector("[data-owed-nothing]");
    expect(row).not.toBeNull();
    expect(row.textContent).toContain("Not owed — outside its agreed months (Feb, Aug)");
    expect(row.querySelector(".pill:not(.tag)")).toBeNull();
    expect(row.querySelector("table")).toBeNull();
    expect(row.textContent).not.toContain("staffing register");
    expect(html).not.toContain("No deliveries in the current cycle yet.");
    expect(row.textContent).toContain("Current cycle");
  });

  it("is shown when the dataset has no supply cycles yet", () => {
    const w = withRaw(load(), dataset());
    w.eval("CURRENT_IN_PLACE_ON = '2026-06-15'");
    const html = w.renderSupplyHistorySection(dataset(), [], "2026-05-01");
    expect(html).toContain("Not owed — outside its agreed months (Feb, Aug)");
  });

  it("is never listed under 'Periods with no supply'", () => {
    const w = withRaw(load(), dataset());
    w.eval("CURRENT_IN_PLACE_ON = '2026-06-15'");
    expect(w.renderSupplyHistorySection(dataset(), [], "2026-05-01")).not.toContain("Periods with no supply");
  });

  it("collapses consecutive periods of one kind and reason into one row", () => {
    const w = load();
    const off = (period, date) => ({ period, date, kind: "turned_off", reason: "paused", months: null });
    const raw = dataset({ owedNothing: [off("2025-Q4", "2025-11-01"), off("2026-Q1", "2026-02-01"),
                                        off("2026-Q2", "2026-05-01")] });
    const runs = w.owedNothingRuns(raw, "2026-06-15");
    expect(runs).toHaveLength(1);
    expect(runs[0].text).toBe("Turned off — paused, 2025-Q4 to 2026-Q2 (3 periods so far)".replace(
      "2025-Q4", w.fmtPeriodOrDay("2025-Q4")).replace("2026-Q2", w.fmtPeriodOrDay("2026-Q2")));
    const closed = w.owedNothingRuns(raw, "2026-09-15");
    expect(closed[0].text).toMatch(/\(3 periods\)$/);
  });

  it("names the period an inherited owed-nothing period stands on, on the same row (criterion 9)", () => {
    const w = load();
    const raw = dataset({ promotionTimeline: { points: [], standing: [
      { on: "2026-05-01", period: "2026-Q2",
        standingIn: { kind: "inherited", period: "2026-Q2", standsOn: "2026-Q1" } }] } });
    const runs = w.owedNothingRuns(raw, "2026-06-15");
    expect(runs[0].inheritedFrom).toBe("2026-Q1");
  });
});

describe("the standing-in heading names the kind (criterion 9)", () => {
  it("reads the kind label today and 'On <date>: <kind label>' on a past date", () => {
    const w = withRaw(load(), dataset());
    const d = (past) => ({ id: "cp-case-workers", promotionState: { past, on: "2026-06-15",
      standingIn: { kind: "inherited", period: "2026-Q2", standsOn: "2026-Q1" } } });
    expect(w.standingInHeading(d(false))).toBe("Not owed — outside its agreed months (Feb, Aug)");
    expect(w.standingInHeading(d(true)))
      .toBe(`On ${w.fmtDay("2026-06-15")}: Not owed — outside its agreed months (Feb, Aug)`);
  });
});

describe("a period owed nothing is not stale (criterion 15)", () => {
  it("does not read a not_expected period as 'nothing has landed yet'", () => {
    const w = load();
    const skipped = { period: "2026-Q2", date: "2026-05-01", kind: "not_expected",
                      reason: "migration", months: null };
    const ds = dataset({ owedNothing: [skipped] });
    expect(w.clipDatasetToInPlaceOn(ds, "2026-06-15").staleInPlaceOn).toBe(false);
    // ...and the same date reads stale for a dataset that owed that period.
    expect(w.clipDatasetToInPlaceOn(dataset({ owedNothing: [] }), "2026-06-15").staleInPlaceOn).toBe(true);
  });
});

describe("the empty notice before the first participation version (criterion 3)", () => {
  it("says 'Not owed yet' and keeps only its way back", () => {
    const w = load();
    const html = w.neverSuppliedNotice(dataset(), "2022-06-01");
    expect(html).toContain(`Not owed yet — owes supplies from ${w.fmtDay("2023-01-01")}`);
    expect(html).toContain("Pick a later date, or reset to the default");
    expect(html).not.toContain("Nothing had been supplied");
    expect(html).not.toContain("freshness window");
  });

  it("is unchanged once the dataset owes supplies", () => {
    const w = load();
    expect(w.neverSuppliedNotice(dataset(), "2023-06-01")).toContain("Nothing had been supplied by this date.");
  });
});

describe("the panel's reason and the history toggle's count", () => {
  it("puts the owed-nothing reason in the standing-in panel's .promo-why (criterion 9)", () => {
    const w = withRaw(load(), dataset());
    const d = { id: "cp-case-workers", promotionState: { past: false, on: "2026-06-15",
      standingIn: { kind: "inherited", period: "2026-Q2", standsOn: "2026-Q1", reason: "rule text" } } };
    const doc = new w.DOMParser().parseFromString(`<div>${w.standingInDetail(d)}</div>`, "text/html");
    expect(doc.querySelector(".promo-why").textContent).toContain("staffing register");
    expect(doc.querySelector(".promo-head").textContent).toBe("Not owed — outside its agreed months (Feb, Aug)");
  });

  it("counts the rows it hides, owed-nothing rows included (criterion 13)", () => {
    const w = withRaw(load(), dataset());
    w.eval("CURRENT_IN_PLACE_ON = '2026-06-15'");
    const ds = dataset();
    const html = w.renderSupplyHistorySection(ds, w.buildSupplyHistory(ds), "2026-05-01");
    // Two older supply cycles hidden; the owed-nothing May row is current.
    expect(html).toContain("Show all history (2 cycles)");
    w.eval("CURRENT_IN_PLACE_ON = '2026-09-15'");
    const later = w.renderSupplyHistorySection(ds, w.buildSupplyHistory(ds), "2026-08-01");
    expect(later).toContain("Show all history (3 cycles)");
  });
});

describe("post-build-review #194", () => {
  it("F1: a current owed-nothing period is not lost when a supply also falls in it", () => {
    const raw = dataset();
    raw.runs.push({ run_id: "r3", run_date: "2026-05-01" });
    const w = withRaw(load(), raw);
    w.eval("CURRENT_IN_PLACE_ON = '2026-06-15'");
    const html = w.renderSupplyHistorySection(raw, w.buildSupplyHistory(raw), "2026-05-01");
    const doc = new w.DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    const owed = [...doc.querySelectorAll("[data-owed-nothing]")];
    expect(owed.map((e) => e.textContent).join(" ")).toContain("Not owed — outside its agreed months");
    expect(owed[0].closest("#supply-history-older")).toBeNull();
  });

  it("F2: a dataset with nothing supplied yet still shows its owed-nothing rows", () => {
    const raw = dataset({ runs: [] });
    const w = withRaw(load(), raw);
    w.eval("CURRENT_IN_PLACE_ON = '2026-06-15'");
    const wrap = w.document.createElement("div");
    wrap.id = "supply-history-wrap";
    w.document.body.appendChild(wrap);
    w.renderBlockedSupplyHistoryOnly(raw);
    expect(wrap.textContent).toContain("Not owed — outside its agreed months (Feb, Aug)");
  });

  it("F4: a daily run is counted in days", () => {
    const w = load();
    const off = (d) => ({ period: d, date: d, kind: "turned_off", reason: "paused", months: null });
    const raw = dataset({ id: "birth-registrations",
                          owedNothing: [off("2026-03-01"), off("2026-03-02"), off("2026-03-03")] });
    const runs = w.owedNothingRuns(raw, "2026-03-10");
    expect(runs).toHaveLength(1);
    expect(runs[0].text).toMatch(/\(3 days\)$/);
    expect(w.owedNothingRuns(raw, "2026-03-03")[0].text).toMatch(/\(3 days so far\)$/);
  });
});
