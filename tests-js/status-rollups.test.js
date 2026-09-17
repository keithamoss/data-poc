// Status rollup logic: worstOf/rollupStatuses/rollup/checkStatus -
// "worst-of, so nothing silently hides behind a healthy average"
// (renderExec()'s own view-sub text) plus the "nodata" special case
// (STATUS_ORDER's own comment: nodata must never win a worstOf() reduce
// against a real status, but also must never silently vanish one level up).
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

describe("checkStatus", () => {
  it("is red once current exceeds the fail threshold", () => {
    const w = load();
    expect(w.checkStatus({ current: 11, warn: 5, fail: 10 })).toBe("red");
  });

  it("is amber once current exceeds warn but not fail", () => {
    const w = load();
    expect(w.checkStatus({ current: 7, warn: 5, fail: 10 })).toBe("amber");
  });

  it("is green at or below the warn threshold", () => {
    const w = load();
    expect(w.checkStatus({ current: 5, warn: 5, fail: 10 })).toBe("green");
  });
});

describe("worstOf", () => {
  it("picks the worst real status in the list", () => {
    const w = load();
    expect(w.worstOf(["green", "amber", "green"])).toBe("amber");
    expect(w.worstOf(["green", "amber", "red"])).toBe("red");
  });

  it("defaults to green for an empty list", () => {
    const w = load();
    expect(w.worstOf([])).toBe("green");
  });

  it("never lets nodata win, even against only nodata entries - by design, per its own docstring", () => {
    const w = load();
    // worstOf() itself is documented as NOT the right tool for a list
    // that might contain "nodata" (STATUS_ORDER.nodata sits below green,
    // so it can only ever lose) - rollupStatuses() below is the function
    // that actually handles nodata correctly; this pins worstOf()'s own
    // behaviour so a future edit can't quietly change which one does that.
    expect(w.worstOf(["nodata", "nodata"])).toBe("green");
  });
});

describe("rollupStatuses (worstOf's nodata-aware counterpart)", () => {
  it("returns nodata only when every input is nodata", () => {
    const w = load();
    expect(w.rollupStatuses(["nodata", "nodata"])).toBe("nodata");
  });

  it("returns green for an empty list, same as worstOf", () => {
    const w = load();
    expect(w.rollupStatuses([])).toBe("green");
  });

  it("a real status among nodata entries wins - nodata never masks a real problem", () => {
    const w = load();
    expect(w.rollupStatuses(["nodata", "red", "nodata"])).toBe("red");
    expect(w.rollupStatuses(["nodata", "green", "amber"])).toBe("amber");
  });
});

describe("rollup (dataset-list -> worst-of-columns rollup)", () => {
  function dataset(status, { noDataAsOf = false } = {}) {
    return { noDataAsOf, columns: [{ status }] };
  }

  it("green across the board rolls up to green", () => {
    const w = load();
    expect(w.rollup([dataset("green"), dataset("green")])).toBe("green");
  });

  it("one red column anywhere makes the whole rollup red", () => {
    const w = load();
    expect(w.rollup([dataset("green"), dataset("red")])).toBe("red");
  });

  it("datasets with noDataAsOf are excluded before rolling up", () => {
    const w = load();
    // the one real dataset is green; the nodata one must not drag this
    // down to "nodata" or otherwise change the real outcome
    expect(w.rollup([dataset("green"), dataset("red", { noDataAsOf: true })])).toBe("green");
  });

  it("returns nodata only when every dataset has no data as of the selected date", () => {
    const w = load();
    expect(w.rollup([dataset("green", { noDataAsOf: true })])).toBe("nodata");
  });

  it("returns green for a genuinely empty dataset list", () => {
    const w = load();
    expect(w.rollup([])).toBe("green");
  });
});
