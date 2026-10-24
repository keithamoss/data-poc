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
  headline: "A newer cp-case-workers could be carried forward into 2024-Q4.",
  sentences: ["A newer cp-case-workers could be carried forward into 2024-Q4. 2024-Q4 carries forward the supply received 9:00am Monday, 1 July 2024; the one received 9:00am Thursday, 3 October 2024 has been promoted into 2024-Q3 since.",
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
    expect(block.textContent).toContain("A newer cp-case-workers could be carried forward into 2024-Q4.");
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
