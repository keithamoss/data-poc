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
  reason: "not part of the agreement for 2013-Q2", period: "2013-Q2",
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

// REQ-DASH-337 criterion 12 as amended by REQ-DASH-299 (A2): every reason
// begins 'Not checked: '.
describe("what the section says", () => {
  it("words each entry from its structured code, never its text (REQ-DASH-337 c12)", () => {
    const w = load();
    expect(w.notInAgreementReason({code: "not_in_agreement", period: "2013-Q2",
                                   reason: "anything at all"}))
      .toBe("Not checked: not part of the agreement for 2013-Q2.");
    expect(w.notInAgreementReason({code: "not_supplied_by_decision", period: "2026-Q2",
                                   dataset: "no-such", reason: "not part of the agreement for 2026-Q2"}))
      .toBe("Not checked: no-such not supplied for 2026-Q2, by decision.");
    expect(w.notInAgreementReason({code: "calendar_differs", period: "2026-Q2",
                                   dataset: "no-such", calendar: "monthly"}))
      .toBe("Not checked: no-such was on the monthly calendar for 2026-Q2.");
  });

  it("reads an entry recorded before the codes as not part of the agreement", () => {
    const w = load();
    expect(w.notInAgreementReason({reason: "not part of the agreement for 2013-Q2", period: "2013-Q2"}))
      .toBe("Not checked: not part of the agreement for 2013-Q2.");
  });

  it("never words an entry from its reason text (REQ-DASH-337 c12)", () => {
    const w = load();
    expect(w.notInAgreementReason({code: "not_supplied_by_decision", period: "2026-Q2", dataset: "x",
      reason: "not part of the agreement for 2013-Q2"})).toBe("Not checked: x not supplied for 2026-Q2, by decision.");
    expect(w.notInAgreementReason({reason: "not part of the agreement for 2013-Q2"}))
      .not.toContain("2013-Q2");
  });

  // A1: no separate block - each left-out check is a quiet row in the list it
  // belongs to, tagged 'Not checked' where a run check has its pill.
  it("is a quiet row tagged Not checked, in the section's own list, with no block", () => {
    const w = load();
    const rows = w.notInAgreementShown(COL, dataset(["n__2013"], LEFT_OUT));
    const host = w.document.createElement("div");
    host.innerHTML = w.crossTableGridHtml([], w.leftOutRowModels(COL, rows)).html;
    w.wireNotInAgreement(host, COL, rows);
    expect(host.querySelector(".not-in-agreement")).toBeNull();
    const left = host.querySelectorAll(".xt-left-out");
    expect(left).toHaveLength(3);
    expect(host.querySelectorAll("button")).toHaveLength(0);
    const first = left[0];
    expect(first.querySelector(".nm").textContent).toBe("Assigned worker reference");
    expect(first.querySelector(".bt").textContent).toBe("Notifications → Case Workers");
    expect(first.querySelector(".tr").textContent).toBe("dbt:relationships");
    expect(first.querySelector(".why").textContent).toBe("Not checked: not part of the agreement for 2013-Q2.");
    expect(first.querySelector(".pill").textContent).toBe("Not checked");
    expect(first.querySelector(".pill").classList.contains("notchecked")).toBe(true);
    expect(host.querySelectorAll("[data-not-checked-note]")).toHaveLength(1);
    expect(host.textContent).toMatch(/neither a Fail nor a result/);
  });

  it("sets authored names as text, never as markup", () => {
    const w = load();
    const ds = dataset(["n__2013"], LEFT_OUT);
    ds.columns[0].checks[2].name = "<img src=x onerror=alert(1)>";
    const rows = w.notInAgreementShown(COL, ds);
    const host = w.document.createElement("div");
    host.innerHTML = w.crossTableGridHtml([], w.leftOutRowModels(COL, rows)).html;
    w.wireNotInAgreement(host, COL, rows);
    expect(host.querySelector("img")).toBeNull();
    expect(host.querySelector(".xt-left-out .nm").textContent).toBe("<img src=x onerror=alert(1)>");
  });

  it("draws no note for no left-out rows", () => {
    const w = load();
    expect(w.crossTableGridHtml([], []).html).not.toContain("data-not-checked-note");
  });
});
