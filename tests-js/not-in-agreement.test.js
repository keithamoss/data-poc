// A cross-table check left out for the agreement, on the dataset page
// (REQ-PIPE-270 criterion 9, the page half).
//
// The build carries each dataset's notInAgreement list - {runId, supplyId,
// checkId, reason} per check a run left out because a table it reads is not
// part of the agreement for the run's period. The page says so in the
// cross-table section, for the run on show only. The built page is driven in
// a real browser in tests/test_dashboard_e2e.py's TestNotInTheAgreementOnThePage.
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

const COL = {
  id: "child-protection",
  datasets: [
    { id: "cp-notifications", name: "Notifications" },
    { id: "cp-case-workers", name: "Case Workers" },
  ],
};

function workerRef(tool) {
  return {
    check_id: `n.assigned_worker_id.relationships_${tool}`,
    key: `assigned_worker_id.relationships_${tool}`,
    name: "Assigned worker reference",
    tool_ref: `${tool}:relationships`,
    between: { declared_on: "cp-notifications", reads: ["cp-case-workers"] },
    history: [],
  };
}

function dataset(runs, entries) {
  return {
    id: "cp-notifications",
    runs: runs.map((run_id) => ({ run_id })),
    columns: [{ name: "Cross-table checks", scope: "cross-table",
                checks: ["datacontract", "soda", "dbt"].map(workerRef) }],
    notInAgreement: entries,
  };
}

const LEFT_OUT = ["dbt", "soda", "datacontract"].map((tool) => ({
  runId: "n__2013", supplyId: "cp-notifications@2013",
  checkId: `n.assigned_worker_id.relationships_${tool}`,
  reason: "not part of the agreement for 2013-Q2",
}));

describe("which checks the page names", () => {
  it("names the checks the run on show left out, in the section's row order", () => {
    const w = load();
    const rows = w.notInAgreementShown(COL, dataset(["n__2013"], LEFT_OUT));
    expect(rows.map((r) => r.ck.tool_ref)).toEqual(
      ["dbt:relationships", "soda:relationships", "datacontract:relationships"]);
    expect(rows.every((r) => r.ck.name === "Assigned worker reference")).toBe(true);
  });

  it("says nothing once a later run is on show", () => {
    // A later supply ran the checks, so its page shows their results.
    const w = load();
    expect(w.notInAgreementShown(COL, dataset(["n__2013", "n__2014"], LEFT_OUT))).toEqual([]);
  });

  it("says nothing with no list at all", () => {
    const w = load();
    expect(w.notInAgreementShown(COL, dataset(["n__2013"], undefined))).toEqual([]);
  });

  it("keeps a check the dataset does not carry, by its id", () => {
    const w = load();
    const rows = w.notInAgreementShown(COL, dataset(["n__2013"], [
      { runId: "n__2013", checkId: "unknown.check", reason: "not part of the agreement for 2013-Q2" }]));
    expect(rows).toHaveLength(1);
    expect(rows[0].ck.name).toBe("unknown.check");
  });
});

describe("what the section says", () => {
  it("says the reason as a sentence", () => {
    const w = load();
    expect(w.notInAgreementReason("not part of the agreement for 2013-Q2"))
      .toBe("Not part of the agreement for 2013-Q2.");
    expect(w.notInAgreementReason("")).toBe("");
  });

  it("is neither red nor a result: no status pill, a Not run tag", () => {
    const w = load();
    const rows = w.notInAgreementShown(COL, dataset(["n__2013"], LEFT_OUT));
    const host = w.document.createElement("div");
    host.innerHTML = w.notInAgreementBlock(rows);
    w.wireNotInAgreement(host, COL, rows);
    const block = host.querySelector(".not-in-agreement");
    expect(block.dataset.notInAgreement).toBe("3");
    expect(host.querySelectorAll(".pill")).toHaveLength(0);
    const first = host.querySelector(".nia-row");
    expect(first.querySelector(".nm").textContent).toBe("Assigned worker reference");
    expect(first.querySelector(".bt").textContent).toBe("Notifications → Case Workers");
    expect(first.querySelector(".tr").textContent).toBe("dbt:relationships");
    expect(first.querySelector(".why").textContent).toBe("Not part of the agreement for 2013-Q2.");
    expect(first.querySelector(".nia-tag").textContent).toBe("Not run");
    expect(block.textContent).toMatch(/neither red nor a result/);
  });

  it("sets authored names as text, never as markup", () => {
    const w = load();
    const ds = dataset(["n__2013"], LEFT_OUT);
    ds.columns[0].checks[2].name = "<img src=x onerror=alert(1)>";
    const rows = w.notInAgreementShown(COL, ds);
    const host = w.document.createElement("div");
    host.innerHTML = w.notInAgreementBlock(rows);
    w.wireNotInAgreement(host, COL, rows);
    expect(host.querySelector("img")).toBeNull();
    expect(host.querySelector(".nia-row .nm").textContent).toBe("<img src=x onerror=alert(1)>");
  });

  it("draws nothing for no rows", () => {
    const w = load();
    expect(w.notInAgreementBlock([])).toBe("");
  });
});
