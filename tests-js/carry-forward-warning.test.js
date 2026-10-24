// REQ-PIPE-271 criterion 7: a newer supply that could be carried forward is
// shown on the dataset's page for the later period, and as one line on its
// collection card, as at the date on show. The words are the build's
// (qa_tools/common/carry_forward.for_dashboard); the page only chooses which
// warnings stand on the date, and escapes every word it shows.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const COMMAND = "mothman supply decide --operation carry-forward --dataset cp-case-workers --period 2024-Q4 --reason '<why>'";
const WARNING = {
  id: 7, period: "2024-Q4", supply: "cp-case-workers@q3", promotedInto: "2024-Q3",
  carried: "cp-case-workers@q2", from: "2024-10-03", until: "2024-11-20",
  headline: "A newer Case Workers could be carried forward into 2024-Q4.",
  sentences: ["A newer Case Workers could be carried forward into 2024-Q4. 2024-Q4 carries forward the supply received 9:00am Monday, 1 July 2024; the one received 9:00am Thursday, 3 October 2024 has been promoted into 2024-Q3 since.",
              "A person can carry that one forward instead, in one step:"],
  command: COMMAND, door: "or from the 2024-Q4 door.",
};

function load(periodOnShow) {
  dashboard = loadDashboard();
  const w = dashboard.window;
  const raw = { id: "cp-case-workers", name: "Case Worker Register", carryForwardWarnings: [WARNING] };
  w.rawRealDatasetById = (id) => (id === raw.id ? raw : null);
  w.periodNameFor = () => periodOnShow;
  return { w, raw };
}

describe("which warnings stand on the date on show", () => {
  it("stands from the day it was raised until the day it cleared", () => {
    const { w, raw } = load("2024-Q4");
    expect(w.carryForwardWarningsOn(raw, "2024-10-02")).toEqual([]);
    expect(w.carryForwardWarningsOn(raw, "2024-10-03")).toHaveLength(1);
    expect(w.carryForwardWarningsOn(raw, "2024-11-19")).toHaveLength(1);
    expect(w.carryForwardWarningsOn(raw, "2024-11-20")).toEqual([]);
  });

  it("stands with no end while it has not cleared", () => {
    const { w, raw } = load("2024-Q4");
    raw.carryForwardWarnings = [{ ...WARNING, until: null }];
    expect(w.carryForwardWarningsOn(raw, "2030-01-01")).toHaveLength(1);
  });
});

describe("on the dataset's page for the later period", () => {
  it("gives the sentences, then the command on a line of its own, then the door", () => {
    const { w } = load("2024-Q4");
    const host = w.document.createElement("div");
    host.innerHTML = w.carryForwardWarningBlock({ id: "cp-case-workers" }, "2024-10-10");
    const block = host.querySelector("[data-carry-forward-warning='2024-Q4']");
    expect(block).not.toBeNull();
    expect(block.textContent).toContain("A newer Case Workers could be carried forward into 2024-Q4.");
    expect(block.querySelector("[data-carry-forward-command]").textContent).toBe(COMMAND);
    expect(block.textContent).toContain("or from the 2024-Q4 door.");
    expect(block.textContent).not.toContain("un-inherit");
  });

  it("is not shown on a page for another period", () => {
    const { w } = load("2024-Q3");
    expect(w.carryForwardWarningBlock({ id: "cp-case-workers" }, "2024-10-10")).toBe("");
  });

  it("escapes the words, so a placeholder reads as written", () => {
    const { w } = load("2024-Q4");
    const host = w.document.createElement("div");
    host.innerHTML = w.carryForwardWarningBlock({ id: "cp-case-workers" }, "2024-10-10");
    expect(host.querySelector("[data-carry-forward-command]").textContent).toContain("'<why>'");
  });
});

describe("on its collection card", () => {
  it("is one line per standing warning, its headline", () => {
    const { w } = load("2024-Q4");
    const host = w.document.createElement("div");
    host.innerHTML = w.collectionCarryForwardLines({ datasets: [{ id: "cp-case-workers" }] }, "2024-10-10");
    const lines = host.querySelectorAll("[data-collection-carry-forward]");
    expect(lines).toHaveLength(1);
    expect(lines[0].textContent).toBe(WARNING.headline);
    host.innerHTML = w.collectionCarryForwardLines({ datasets: [{ id: "cp-case-workers" }] }, "2024-12-01");
    expect(host.querySelectorAll("[data-collection-carry-forward]")).toHaveLength(0);
  });
});

// THE REFUSED CASE, AND A PERIOD WARNED IN TWO RUNS OF DAYS (post-build-review
// #267, T1 and D1): the build gives one run per period on any day, its words
// as the period stood then; the page shows the run standing on the date.
const REFUSED = {
  id: 9, period: "2024-Q4", supply: "cp-case-workers@q3", promotedInto: "2024-Q3", carried: null,
  from: "2024-10-03", until: null,
  headline: "A newer Case Workers could be carried forward into 2024-Q4.",
  sentences: ["2024-Q4 carries nothing forward for Case Workers: there was no earlier promoted supply when it opened. The one received 9:00am Thursday, 3 October 2024 has been promoted into 2024-Q3 since, and a person can carry it forward, in one step:"],
  command: COMMAND, door: "or from the 2024-Q4 door.",
};

describe("the refused case", () => {
  it("shows its own sentence, the command and the same one-line headline", () => {
    const { w, raw } = load("2024-Q4");
    raw.carryForwardWarnings = [REFUSED];
    const host = w.document.createElement("div");
    host.innerHTML = w.carryForwardWarningBlock({ id: "cp-case-workers" }, "2024-10-10");
    const block = host.querySelector("[data-carry-forward-warning='2024-Q4']");
    expect(block.textContent).toContain("2024-Q4 carries nothing forward for Case Workers: there was no earlier promoted supply when it opened.");
    expect(block.querySelector("[data-carry-forward-command]").textContent).toBe(COMMAND);
    host.innerHTML = w.collectionCarryForwardLines({ datasets: [{ id: "cp-case-workers" }] }, "2024-10-10");
    expect(host.querySelector("[data-collection-carry-forward]").textContent).toBe(REFUSED.headline);
  });

  it("shows one block on a date where the build gave two runs for the period", () => {
    const { w, raw } = load("2024-Q4");
    raw.carryForwardWarnings = [{ ...WARNING, until: "2024-11-01" },
                                { ...REFUSED, id: 7, from: "2024-11-01",
                                  sentences: ["2024-Q4 carries nothing forward for Case Workers. The one received 9:00am Thursday, 3 October 2024, promoted into 2024-Q3, could be carried forward:"] }];
    const host = w.document.createElement("div");
    host.innerHTML = w.carryForwardWarningBlock({ id: "cp-case-workers" }, "2024-10-20");
    expect(host.querySelectorAll("[data-carry-forward-warning]")).toHaveLength(1);
    expect(host.textContent).toContain("carries forward the supply received");
    host.innerHTML = w.carryForwardWarningBlock({ id: "cp-case-workers" }, "2024-11-05");
    expect(host.querySelectorAll("[data-carry-forward-warning]")).toHaveLength(1);
    expect(host.textContent).toContain("2024-Q4 carries nothing forward for Case Workers. The one received");
  });
});

// A CARRY-FORWARD IS ONE OF THE PERIOD'S STAND-IN DECISIONS (post-build-review
// #267): recorded after the date it took effect on, it is named among the
// decisions that changed that date, as an inherit or a substitute is.
describe("a carry-forward recorded late is named as changing the date", () => {
  it("is listed by decisionsChangingDate beside the period's other stand-ins", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const raw = { id: "cp-case-workers", name: "Case Workers", runs: [], runStates: {},
      promotionTimeline: { points: [], standing: [{ on: "2024-10-05", period: "2024-Q4",
        decisions: [{ id: 5, action: "carry-forward", supply: "cp-case-workers@q3",
                      at: "2024-10-05T09:00:00+08:00", recordedAt: "2024-10-20T09:00:00+08:00" }] }] } };
    w.rawRealDatasets = () => [raw];
    w.promotionStateOn = () => ({});
    w.periodNameFor = () => "2024-Q4";
    const got = w.decisionsChangingDate("2024-10-10", null);
    expect(got.map(e => e.action)).toContain("carry-forward");
  });
});
