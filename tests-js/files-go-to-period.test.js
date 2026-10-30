// REQ-DASH-326: on an authored calendar the page names the period each supply
// is FOR, and a dataset's current cycle is the one whose claim window most
// recently opened - read from the slots the build embeds
// (pipeline/period_slots.py), never from a period's own date.
//
// The fixture is a collection at files_go_to_period 1: the round dated
// 1 February 2026 (2026-Q1's date) fills 2026-Q2.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const at = (day) => `${day}T09:00:00+08:00`;
const SLOT = (period, date, round, opens) =>
  ({ period, date, round, owed: true, opens: at(opens), due: at(round), closes: null });
const Q1 = SLOT("2026-Q1", "2026-02-01", "2025-11-01", "2025-10-18");
const Q2 = SLOT("2026-Q2", "2026-05-01", "2026-02-01", "2026-01-18");
const Q3 = SLOT("2026-Q3", "2026-08-01", "2026-05-01", "2026-04-17");
const QUARTERLY = { type: "quarterly", anchor_months: [2, 5, 8, 11], day_of_month: 1,
                    expected_time: "09:00", latency_minutes: 480 };

function raw(extra = {}) {
  return {
    id: "cp-clients", name: "Clients", sla: { cadence: QUARTERLY },
    periodSlots: { filesGo: "Files go into the next period (set for Child Protection, since the 2 February 2015 round)",
                   filesGoValue: 1,
                   first: { period: "2026-Q1", due: Q1.due, opens: Q1.opens },
                   slots: [Q1, Q2, Q3] },
    owedNothing: [],
    ...extra,
  };
}

function load(r = raw()) {
  dashboard = loadDashboard();
  const w = dashboard.window;
  w.rawRealDatasetById = (id) => (id === r.id ? r : null);
  return { w, r };
}

describe("the current cycle is the one whose claim window most recently opened (criterion 5)", () => {
  it("moves to 2026-Q2 the day its claim window opens, a fortnight before it is due", () => {
    const { w } = load();
    expect(w.currentPeriodOn("cp-clients", "2026-01-17").period).toBe("2026-Q1");
    expect(w.currentPeriodOn("cp-clients", "2026-01-18").period).toBe("2026-Q2");
  });

  it("is 2026-Q2 in March, whose date falls after 2026-Q1's - never the period the date falls in", () => {
    const { w } = load();
    expect(w.periodNameFor("cp-clients", "2026-03-01")).toBe("2026-Q1");
    expect(w.currentPeriodOn("cp-clients", "2026-03-01").period).toBe("2026-Q2");
  });

  it("stays on the doubly-fed period while a round after a fall opens no slot (criterion 15)", () => {
    // A fall from 1 to 0 from the 1 May round: that round would fill 2026-Q2
    // again, so it opens no slot, and the next one opened is August's.
    const Q3_AFTER_FALL = SLOT("2026-Q3", "2026-08-01", "2026-08-01", "2026-07-18");
    const { w } = load(raw({ periodSlots: { ...raw().periodSlots, slots: [Q1, Q2, Q3_AFTER_FALL] } }));
    expect(w.currentPeriodOn("cp-clients", "2026-05-10").period).toBe("2026-Q2");
    expect(w.currentPeriodOn("cp-clients", "2026-07-18").period).toBe("2026-Q3");
  });

  it("keeps the period the date falls in on a cadence-rule calendar, where the build embeds no slots (criterion 3)", () => {
    const { w } = load(raw({ periodSlots: null }));
    expect(w.currentPeriodOn("cp-clients", "2026-03-01").period).toBe("2026-Q1");
  });
});

describe("a cycle's heading names the period it is for (criteria 1, 2 and 4)", () => {
  it("reads 'For 2026-Q2 · received Sunday, 1 February 2026' for a supply received on its round", () => {
    const { w } = load();
    expect(w.cycleLabel(QUARTERLY, "2026-05-01", "cp-clients", "2026-02-01"))
      .toBe("For 2026-Q2 · received Sunday, 1 February 2026");
  });

  it("reads 'open for files, due <instant>' while it holds nothing and is not yet due", () => {
    const { w } = load();
    w.eval("CURRENT_IN_PLACE_ON = '2026-01-25'");
    const label = w.cycleLabel(QUARTERLY, "2026-05-01", "cp-clients");
    expect(label.startsWith("For 2026-Q2 · open for files, due ")).toBe(true);
    expect(label).toContain(w.fmtInstant(Q2.due));
    // Never the period's own date as a due date (REQ-PIPE-167 criterion 5's
    // old 'Cycle due ... (period dated ...)' is replaced).
    expect(label).not.toContain("May");
    expect(label).not.toContain("period dated");
  });

  it("shows the empty current cycle as that heading, tagged current, in place of the bare line", () => {
    const { w, r } = load();
    w.eval("CURRENT_IN_PLACE_ON = '2026-01-25'");
    const html = w.emptyCurrentCycle(r);
    expect(html).toContain("For 2026-Q2 · open for files, due");
    expect(html).toContain("Current cycle");
    expect(html).not.toContain("No deliveries in the current cycle yet.");
  });
});

describe("calm until due (criterion 5): late or 'nothing has landed' only once the due instant passes", () => {
  it("judges the supply in place against 2026-Q1 until 2026-Q2 is due, and against 2026-Q2 after", () => {
    const { w, r } = load();
    expect(w.owedPeriodStart(r, "2026-01-25")).toBe("2026-02-01");   // 2026-Q1's date
    expect(w.owedPeriodStart(r, "2026-02-01")).toBe("2026-05-01");   // 2026-Q2's date, due that morning
  });

  it("names the missed period and the instant it was due, not the day a cycle 'started' (criterion 6)", () => {
    const { w, r } = load();
    w.eval("CURRENT_IN_PLACE_ON = '2026-02-10'");
    const words = w.nothingLandedWords(r);
    expect(words).toContain("2026-Q2");
    expect(words).toContain(w.fmtInstant(Q2.due));
    expect(words).not.toContain("started");
  });
});

describe("the period is named wherever a supply or a dataset's timing is shown", () => {
  it("Latest arrival reads 'For <period> · <instant>' (criterion 12)", () => {
    const { w } = load();
    const ds = { id: "cp-clients", lastArrival: { slot: "2026-Q2", arrivedAt: at("2026-02-01") } };
    expect(w.latestArrivalWords(ds)).toBe(`For 2026-Q2 · ${w.fmtInstant(at("2026-02-01"))}`);
  });

  it("the SLA tile says where files go, with the collection and its round (criterion 7)", () => {
    const { w, r } = load();
    const html = w.slaTileHtml(r, "2026-03-01");
    expect(html).toContain("Files go into the next period (set for Child Protection, since the 2 February 2015 round)");
  });

  it("'Not owed yet' names the first period and its first due instant (REQ-DASH-182 criterion 3 as amended)", () => {
    const { w, r } = load();
    expect(w.notOwedYetText("2025-11-01", r)).toBe(`Not owed yet — owes from 2026-Q1, first due ${w.fmtInstant(Q1.due)}`);
    expect(w.slaInPlaceOn(r, "2025-10-01").notOwedYet).toBeTruthy();
    expect(w.slaInPlaceOn(r, "2025-10-18").notOwedYet).toBeFalsy();
  });

  it("an owed-nothing row names rounds, not months (REQ-DASH-182 criterion 2 as amended)", () => {
    const { w } = load();
    expect(w.owedNothingLabel({ kind: "participation", months: [2, 8] }).label)
      .toBe("Not owed — it supplies only in the February and August rounds");
  });
});

describe("a drill lands on a date its period is current (criterion 11)", () => {
  it("goes to the last day 2026-Q2 is current, never 2026-Q2's own date", () => {
    const { w } = load();
    expect(w.drillDateFor("cp-clients", "2026-Q2")).toBe("2026-04-16");
    expect(w.currentPeriodOn("cp-clients", w.drillDateFor("cp-clients", "2026-Q2")).period).toBe("2026-Q2");
  });
});

describe("a supply held after a fall (criterion 15)", () => {
  it("reads as a second supply for the period, its cause our own agreement change from that round", () => {
    const { w } = load();
    const b = { kind: "held", doublyFed: { period: "2026-Q2", round: "2026-05-01" } };
    expect(w.blockerLabel(b)).toBe("Held, would be a second supply for 2026-Q2");
    expect(w.blockerSays(b)).toContain("the agreement change from the 1 May 2026 round");
  });
});
