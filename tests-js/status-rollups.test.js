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
  function dataset(status, { noDataInPlaceOn = false } = {}) {
    return { noDataInPlaceOn, columns: [{ status }] };
  }

  it("green across the board rolls up to green", () => {
    const w = load();
    expect(w.rollup([dataset("green"), dataset("green")])).toBe("green");
  });

  it("one red column anywhere makes the whole rollup red", () => {
    const w = load();
    expect(w.rollup([dataset("green"), dataset("red")])).toBe("red");
  });

  it("datasets with noDataInPlaceOn are excluded before rolling up", () => {
    const w = load();
    // the one real dataset is green; the nodata one must not drag this
    // down to "nodata" or otherwise change the real outcome
    expect(w.rollup([dataset("green"), dataset("red", { noDataInPlaceOn: true })])).toBe("green");
  });

  it("returns nodata only when every dataset has no data as of the selected date", () => {
    const w = load();
    expect(w.rollup([dataset("green", { noDataInPlaceOn: true })])).toBe("nodata");
  });

  it("returns green for a genuinely empty dataset list", () => {
    const w = load();
    expect(w.rollup([])).toBe("green");
  });
});

// ---------------------------------------------------------------------------
// A dataset nobody has agreed a delivery schedule for (REQ-PIPE-106).
// ---------------------------------------------------------------------------
describe("a dataset with no agreed schedule is in no rollup", () => {
  function ds(id, status, extra = {}) {
    return { id, name: id, columns: [{ name: "a", status }], ...extra };
  }

  it("is left out of its collection's rollup entirely", () => {
    const w = load();
    // A red dataset nobody agreed must not make the collection red -
    // criterion 9's whole point: a dataset nobody agreed cannot turn an
    // agreed one's status.
    const green = ds("agreed", "green");
    const redUnagreed = ds("sample", "red", { scheduleNotAgreed: "not-yet-agreed" });
    expect(w.rollup([green, redUnagreed])).toBe("green");
  });

  it("keeps its OWN status, which is the real verdict its checks found", () => {
    const w = load();
    // Criterion 7. Developing a check means seeing whether it passes, so
    // its own tile must not be softened to a quiet state.
    const redUnagreed = ds("sample", "red", { scheduleNotAgreed: "not-yet-agreed" });
    expect(w.rollupStatuses(redUnagreed.columns.map((c) => c.status))).toBe("red");
    expect(w.inNoRollup(redUnagreed)).toBe(true);
  });

  it("a collection of only unagreed datasets reads Not counted - never green", () => {
    const w = load();
    // post-build-review #135 (Keith, 2026-10-10). This used to expect
    // green, which pinned the false green itself. Their verdicts still do
    // not count (REQ-PIPE-106 criterion 9), but a group with nothing
    // counted must not claim to be healthy either.
    expect(w.rollup([ds("a", "red", { scheduleNotAgreed: "not-yet-agreed" }),
                      ds("b", "amber", { scheduleNotAgreed: "never" })])).toBe("notcounted");
  });

  it("a Not counted group says why, in words, by reason - and nothing else does", () => {
    const w = load();
    // post-build-review #135: the pill never stands alone. Counts by
    // reason, never a list of names.
    const group = [ds("a", "red", { scheduleNotAgreed: "not-yet-agreed" }),
                   ds("b", "amber", { scheduleNotAgreed: "not-yet-agreed" }),
                   ds("c", "green", { scheduleNotAgreed: "never" })];
    const line = w.notCountedMarker("notcounted", group).replace(/\s+/g, " ");
    expect(line).toContain("3 datasets not counted: 2 no schedule agreed yet, 1 one-off extraction");
    expect(w.notCountedMarker("green", group)).toBe("");
  });

  it("an ordinary dataset is unaffected", () => {
    const w = load();
    expect(w.inNoRollup(ds("agreed", "red"))).toBe(false);
    expect(w.rollup([ds("agreed", "red"), ds("other", "green")])).toBe("red");
  });

  it("an exhausted schedule still comes back when it is all there is", () => {
    const w = load();
    // The contrast, asserted so the new exclusion cannot be mistaken for
    // the old one: exhausted is a real answer about the group.
    expect(w.rollup([{ id: "x", columns: [], scheduleExhausted: "quarterly" }]))
      .toBe("exhausted");
  });
});

describe("it says so in words rather than by colour", () => {
  function ds(kind) {
    return { id: "sample", name: "Sample", scheduleNotAgreed: kind, status: "red" };
  }

  it("names the outstanding job for a dataset that will graduate", () => {
    const w = load();
    const markup = w.unagreedMarker(ds("not-yet-agreed"));
    expect(markup).toContain("No delivery schedule agreed yet");
  });

  it("says something DIFFERENT for a one-off extraction", () => {
    const w = load();
    // Criterion 3: presenting a finished decision as an outstanding job
    // would put a permanent item on somebody's list.
    const markup = w.unagreedMarker(ds("never"));
    expect(markup).toContain("One-off extraction");
    expect(markup).not.toContain("agreed yet");
  });

  it("says nothing at all for an ordinary dataset", () => {
    const w = load();
    expect(w.unagreedMarker({ id: "agreed", status: "green" })).toBe("");
  });

  it("carries the whole meaning in the label, never in the colour", () => {
    const w = load();
    // The rule nodata and inactive already follow. Asserted because a
    // marker distinguished only by a dashed border is one a colour-blind
    // reader, or a printed page, cannot read at all.
    const markup = w.unagreedMarker(ds("not-yet-agreed"));
    const withoutMarkup = markup.replace(/<[^>]*>/g, "").trim();
    expect(withoutMarkup.length).toBeGreaterThan(10);
  });
});
