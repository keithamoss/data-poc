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

  it("is empty rather than an empty chip where there is no wait", () => {
    const win = load();
    expect(win.waitedChip({ waitedSeconds: null, awaiting: false })).toBe("");
  });
});

describe("a resupply keeps its own verdict", () => {
  it("the blanking path is gone from the template", () => {
    const win = load();
    // Criterion 3, asserted against the real committed template. It
    // used to blank every attempt in a chain but the first, which was
    // right about the derivation it was written for and wrong about
    // the recorded one.
    const src = win.document.documentElement.outerHTML;
    expect(src).not.toContain("arrivalStatus: idx===0");
  });
});
