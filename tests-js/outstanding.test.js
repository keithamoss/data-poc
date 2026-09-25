// Outstanding decisions, and the arrival fallback they exposed
// (REQ-DASH-070).
//
// The queue's own data is passed to each function rather than assigned
// onto the window, for the reason schedule-runway.test.js gives: a
// top-level `const` in a classic script lives in script scope, not on
// globalThis, so assigning OUTSTANDING here would create a NEW global
// the page's own code never reads and every assertion would be made
// against the embedded empty default.
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

function item(overrides) {
  return {
    kind: "held-supply", severity: "needs-action", blocking: true,
    headline: "cp-clients has a held supply in 'monday'",
    detail: "Two files in this delivery are all cp-clients.",
    agencyId: "dcp", collectionId: "child-protection", datasetId: "cp-clients",
    observedAt: "2026-09-01T09:00:00+08:00",
    responses: ["assign one of the files to the slot", "reject the supply"],
    actionable: false, ambiguity: null,
    ...overrides,
  };
}

function queueOf(items) {
  const byScope = (key) => items.reduce((acc, i) => {
    if (i[key]) acc[i[key]] = (acc[i[key]] || 0) + 1;
    return acc;
  }, {});
  return {
    items,
    total: items.length,
    blockingCount: items.filter((i) => i.blocking).length,
    byAgency: byScope("agencyId"),
    byCollection: byScope("collectionId"),
    byDataset: byScope("datasetId"),
    summary: "",
  };
}

const HELD = item({});
const UNRECOGNISED = item({
  kind: "unrecognised-file", severity: "warning", blocking: false,
  headline: "note.pdf in 'monday' matched no dataset",
  detail: "This did not fail the delivery.",
  datasetId: null,
  responses: ["confirm it is not a supply"],
});
const UNCERTAIN = item({
  kind: "uncertain-assignment", severity: "warning", blocking: false,
  headline: "Clients' supply 2026-09-01 was filed under uncertainty",
  detail: "An earlier slot was also unfilled.",
  ambiguity: "an earlier slot, 2026-Q2, was also unfilled",
  responses: ["confirm the slot"],
});

describe("one element, not one per producing rule", () => {
  it("renders ONE queue carrying the total, whatever produced the items", () => {
    const w = load();
    const html = w.outstandingQueue(null, null, queueOf([HELD, UNRECOGNISED, UNCERTAIN]));
    // One element. Three items inside it, not three notices.
    expect(html.match(/notice-queue/g)).toHaveLength(1);
    expect(html.match(/queue-item /g)).toHaveLength(3);
    expect(html).toContain("3 things waiting for a person");
  });

  it("states the blocking and needs-review split in the heading", () => {
    const w = load();
    const html = w.outstandingQueue(null, null, queueOf([HELD, UNRECOGNISED, UNCERTAIN]));
    expect(html).toContain("1</b> blocking a supply");
    expect(html).toContain("2</b> needing review");
  });

  it("says so rather than rendering an empty element when nothing is waiting", () => {
    const w = load();
    const html = w.outstandingQueue(null, null, queueOf([]));
    expect(html).toContain("Nothing is waiting for a person");
    // Still an element - "nothing outstanding" and "this panel is
    // broken" look identical if the page renders neither.
    expect(html).toContain("notice-queue");
  });
});

describe("blocking is a second axis, not a third severity", () => {
  it("marks a blocking item differently from one needing review", () => {
    const w = load();
    const blocking = w.outstandingQueue(null, null, queueOf([HELD]));
    const review = w.outstandingQueue(null, null, queueOf([UNRECOGNISED]));
    expect(blocking).toContain("queue-item blocking");
    expect(blocking).toContain("Blocks a supply");
    expect(review).toContain("queue-item review");
    expect(review).toContain("Needs review");
  });

  it("carries the distinction in WORDS, not only in the left bar", () => {
    const w = load();
    const html = w.outstandingQueue(null, null, queueOf([HELD, UNRECOGNISED]));
    expect(html).toContain("Blocks a supply");
    expect(html).toContain("Needs review");
  });
});

describe("event severity is not a data verdict", () => {
  it("uses none of the status vocabulary for any severity", () => {
    const w = load();
    for (const severity of ["needs-action", "warning", "informational"]) {
      const pill = w.eventSeverityPill(severity);
      expect(pill).not.toMatch(/pill [^"]*\b(green|amber|red)\b/);
      expect(pill).toContain("ev-");
    }
  });

  it("labels every severity in words, never colour alone", () => {
    const w = load();
    expect(w.eventSeverityPill("needs-action")).toContain("Needs action");
    expect(w.eventSeverityPill("warning")).toContain("Warning");
    expect(w.eventSeverityPill("informational")).toContain("For information");
  });

  it("renders a severity it does not recognise at the LOUDEST weight, not the quietest", () => {
    // A new producer's needs-action item must not arrive looking like
    // a footnote because this page has not been taught its name yet.
    const w = load();
    const pill = w.eventSeverityPill("something-new");
    expect(pill).toContain("ev-action");
    expect(pill).toContain("something-new");
  });
});

describe("a rollup cannot absorb it", () => {
  it("puts a per-scope count on an affected agency and collection", () => {
    const w = load();
    const source = queueOf([HELD]);
    expect(w.outstandingMarker("agency", "dcp", source)).toContain("1 thing waiting");
    expect(w.outstandingMarker("collection", "child-protection", source))
      .toContain("1 thing waiting");
  });

  it("renders nothing for a scope with nothing outstanding", () => {
    const w = load();
    expect(w.outstandingMarker("agency", "bdm", queueOf([HELD]))).toBe("");
  });

  it("scopes the queue itself to one dataset when asked", () => {
    const w = load();
    const source = queueOf([HELD, UNRECOGNISED]);
    const html = w.outstandingQueue("dataset", "cp-clients", source);
    expect(html).toContain("1 thing waiting for a person here");
    expect(html).not.toContain("matched no dataset");
  });
});

describe("responses are named, never offered as controls", () => {
  it("names what would resolve an item", () => {
    const w = load();
    const html = w.outstandingQueue(null, null, queueOf([HELD]));
    expect(html).toContain("assign one of the files to the slot");
    expect(html).toContain("reject the supply");
  });

  it("renders no button or link for a response that cannot yet be taken", () => {
    const w = load();
    const html = w.outstandingQueue(null, null, queueOf([HELD]));
    expect(html).not.toMatch(/<button|<a\s/);
    expect(html).toContain("not yet possible from this page");
  });
});

describe("the qualifier travels with the assignment (criterion 9)", () => {
  it("renders the uncertainty chip for a dataset with an uncertain filing", () => {
    const w = load();
    const chip = w.ambiguityChip("cp-clients", null, queueOf([UNCERTAIN]));
    expect(chip).toContain("Uncertain filing");
    expect(chip).toContain("an earlier slot, 2026-Q2, was also unfilled");
  });

  it("renders nothing where the assignment was certain", () => {
    const w = load();
    expect(w.ambiguityChip("cp-clients", null, queueOf([HELD]))).toBe("");
  });

  it("is a qualifier, not a status pill - it never uses the verdict vocabulary", () => {
    const w = load();
    const chip = w.ambiguityChip("cp-clients", null, queueOf([UNCERTAIN]));
    expect(chip).not.toMatch(/pill [^"]*\b(green|amber|red)\b/);
  });
});

// ---------------------------------------------------------------------
// CRITERION 10 - the real collision with built code.
//
// arrivalStatusLabel()/arrivalPill() mapped anything that was not
// "early" or "late" to a GREEN "On time" pill. REQ-PIPE-066's
// "unfiled" means there is no slot to be punctual against at all, so
// that fallback rendered a confident punctuality verdict out of an
// absence - in three places at once. These fail against the
// pre-REQ-DASH-070 template, which is how they were checked.
// ---------------------------------------------------------------------
describe("an absent or unrecognised arrival classification is not a punctuality verdict", () => {
  it("does not call an unfiled supply 'On time'", () => {
    const w = load();
    expect(w.arrivalStatusLabel("unfiled")).not.toBe("On time");
    expect(w.arrivalStatusLabel("unfiled")).toBe("Not filed to a slot");
  });

  it("does not render an unfiled supply in the GREEN pill a passing arrival uses", () => {
    const w = load();
    expect(w.arrivalPill("unfiled")).not.toContain("pill green");
    expect(w.arrivalPill("unfiled")).toContain("pill nodata");
  });

  it("renders a classification it does not recognise as unknown", () => {
    const w = load();
    expect(w.arrivalStatusLabel("something-nobody-taught-it")).toBe("Unknown");
    expect(w.arrivalPill("something-nobody-taught-it")).not.toContain("pill green");
  });

  it("still reads both spellings of on-time as on time", () => {
    // pipeline/cadence.py writes "onTime"; qa_tools/common/
    // arrival_classification.py writes "on_time". A reader should not
    // be told punctuality is unknown because two modules disagree
    // about a capital letter.
    const w = load();
    expect(w.arrivalStatusLabel("onTime")).toBe("On time");
    expect(w.arrivalStatusLabel("on_time")).toBe("On time");
    expect(w.arrivalPill("on_time")).toContain("pill green");
  });

  it("still reads early and late as before", () => {
    const w = load();
    expect(w.arrivalStatusLabel("early")).toBe("Early");
    expect(w.arrivalPill("early")).toContain("pill amber");
    expect(w.arrivalStatusLabel("late")).toBe("Late");
    expect(w.arrivalPill("late")).toContain("pill red");
  });
});
