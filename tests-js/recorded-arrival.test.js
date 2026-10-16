/**
 * How long a supply waited, and whose fact is whose (REQ-PIPE-080
 * criteria 3, 9, 10 and 11).
 *
 * The page now renders two instants that are easy to confuse - when
 * the supplier delivered, and when we acted - plus the gap between
 * them. These cover the part a reader can actually be misled by.
 */
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

describe("fmtWaited", () => {
  it("says a closed wait plainly", () => {
    const win = load();
    expect(win.fmtWaited(90 * 60, false)).toBe("2h");
    expect(win.fmtWaited(30 * 60, false)).toBe("30m");
    expect(win.fmtWaited(5 * 86400, false)).toBe("5d");
  });

  it("SAYS an open wait is open rather than leaving it to be inferred", () => {
    const win = load();
    // Criterion 10. The whole point: a supply nobody has decided on is
    // the one worth looking at, and a bare duration reads identically
    // to a finished one.
    expect(win.fmtWaited(90 * 60, true)).toBe("waiting 2h");
  });

  it("renders nothing where there is nothing to say", () => {
    const win = load();
    // NOT "0m" - absent and zero both read as "dealt with instantly",
    // which is the opposite of what an unknown wait means.
    expect(win.fmtWaited(null, false)).toBe("");
    expect(win.fmtWaited(undefined, true)).toBe("");
  });

  it("never renders a negative wait", () => {
    const win = load();
    expect(win.fmtWaited(-60, false)).toBe("0m");
  });
});

describe("waitedChip", () => {
  it("names both instants so neither stands in for the other", () => {
    const win = load();
    // Criterion 11. "4h" beside an arrival time reads as part of the
    // arrival unless something says otherwise.
    const html = win.waitedChip({
      waitedSeconds: 4 * 3600, awaiting: false,
      arrivedAt: "2026-08-01T09:00:00+08:00",
      filledAt: "2026-08-01T13:00:00+08:00",
    });
    expect(html).toContain("Received");
    expect(html).toContain("promoted");
    expect(html).toContain("4h");
  });

  it("says nothing has promoted it, where nothing has", () => {
    const win = load();
    const html = win.waitedChip({
      waitedSeconds: 3 * 86400, awaiting: true,
      arrivedAt: "2026-08-01T09:00:00+08:00", filledAt: null,
    });
    expect(html).toContain("waiting 3d");
    expect(html).toContain("Nothing has promoted it yet");
    expect(html).not.toContain("promoted " + "2026");
  });

  it("on a past date, counts to that date - and a later promotion is still to come (#123 A4)", () => {
    const win = load();
    win.eval("CURRENT_IN_PLACE_ON = '2026-08-04'");
    const html = win.waitedChip({
      waitedSeconds: 20 * 86400, awaiting: false,
      arrivedAt: "2026-08-01T09:00:00+08:00", filledAt: "2026-08-21T09:00:00+08:00",
    });
    expect(html).toContain("waiting 4d");   // 1 Aug 09:00 to the end of 4 Aug
    expect(html).not.toContain("20d");
  });

  it("on a past date, an open wait counts to that date, not to today (#123 A4)", () => {
    const win = load();
    win.eval("CURRENT_IN_PLACE_ON = '2026-08-04'");
    const html = win.waitedChip({
      waitedSeconds: 60 * 86400, awaiting: true,
      arrivedAt: "2026-08-01T09:00:00+08:00", filledAt: null,
    });
    expect(html).toContain("waiting 4d");   // 1 Aug 09:00 to the end of 4 Aug
  });

  it("is empty rather than an empty chip where there is no wait", () => {
    const win = load();
    expect(win.waitedChip({ waitedSeconds: null, awaiting: false })).toBe("");
  });
});

describe("a resupply keeps its own verdict", () => {
  // Criterion 3. The supply history used to blank the verdict and the
  // receipt instant on every attempt in a chain but the first, which was
  // right about the arrival-date derivation it was written for and wrong
  // about the recorded verdict, which every attempt has its own of.
  function redThenResupplied() {
    const history = [
      { run_id: "r1", run_date: "2026-01-01", value: 3 },  // red: opens a chain
      { run_id: "r2", run_date: "2026-01-02", value: 0 },  // green: its resupply
    ];
    return {
      id: "birth-registrations",
      sla: { cadence: { type: "daily", expected_time: "14:00" } },
      runs: history.map(({ run_id, run_date }) => ({ run_id, run_date })),
      arrivalByRun: {
        r1: { slot: "2026-01-01", arrivalStatus: "on_time", arrivedAt: "2026-01-01T09:00:00+08:00" },
        r2: { slot: "2026-01-01", arrivalStatus: "late", arrivedAt: "2026-01-02T16:30:00+08:00" },
      },
      columns: [{ checks: [{ warn: 1, fail: 2, history }] }],
    };
  }

  it("carries the resupply's own recorded verdict and receipt instant", () => {
    const win = load();
    const chains = win.buildSupplyHistory(redThenResupplied());
    const entries = chains.flatMap(c => c.entries);
    const resupply = entries.find(e => e.run_id === "r2");
    expect(resupply.isResupply).toBe(true);   // the precondition: it IS a resupply
    expect(resupply.arrivalStatus).toBe("late");
    expect(resupply.arrivedAt).toBe("2026-01-02T16:30:00+08:00");
  });
});
