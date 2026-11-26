// REQ-DASH-272 criterion 25: a grid cell's word is the WORST of its marks,
// through rollupStatuses, never the first tool's (dashboard UX review v4 S1,
// the false-green direction), and a tool with no such check holds its place
// with '·' (S2: the key only decodes if every check shows all three positions).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const SUPPLY = "cp-notifications@202408051000000800";
const RUN = { run_id: "cp_notifications__202408051000000800", supply_id: SUPPLY };
const NOTE = [{ dataset: "cp-clients" }, { text: " received Monday, 5 August 2024" }];

function card(tool, status) {
  return {
    key: `cp_client_id.relationships_${tool}`, name: "Client reference",
    tool_ref: `${tool}:relationships`, current_status: status,
    between: { declared_on: "cp-notifications", reads: ["cp-clients"] },
    history: [{ run_id: RUN.run_id, rank: 3, supply_id: SUPPLY, status }],
    placed: { 3: [{ on: "2024-08-05", bucket: "warehouse", note: NOTE, sentence: NOTE }] },
  };
}

function cell(cards) {
  dashboard = loadDashboard();
  const w = dashboard.window;
  const col = { datasets: [{ id: "cp-notifications", name: "Notifications" },
    { id: "cp-clients", name: "Client Register" }] };
  const row = w.xtRowModel(col, cards, RUN, "2024-08-05");
  return w.xtCellText(row, "warehouse");
}

describe("a grid cell", () => {
  it("reads Fail where its tools disagree, whichever tool comes first", () => {
    const c = cell([card("dbt", "green"), card("soda", "red"), card("datacontract", "green")]);
    expect(c.word).toBe("Fail");
    expect(c.marks).toBe("✓ ✗ ✓");
  });

  it("holds a missing tool's place with '·'", () => {
    const c = cell([card("dbt", "green"), card("soda", "green")]);
    expect(c.word).toBe("Pass");
    expect(c.marks).toBe("✓ ✓ ·");
  });
});

// UX critic on 7093c20, B1 (Keith Q1 = a, PROVISIONAL): a result that could
// not be evaluated is not a failure on the data, and the grid said "Fail ✗ ✗
// ✗" beside a notice and a panel saying the checks could not run.
describe("a cell whose results could not be evaluated", () => {
  function notRun(tool) {
    const c = card(tool, "red");
    c.history[0].not_evaluated = "could not run - cp_clients was held back";
    return c;
  }

  it("reads Not evaluated with the could-not-run mark, never Fail or ✗", () => {
    const c = cell([notRun("dbt"), notRun("soda"), notRun("datacontract")]);
    expect(c.word).toBe("Not evaluated");
    expect(c.marks).toBe("○ ○ ○");
    expect(c.marks).not.toContain("✗");
  });

  it("still reads Fail where a tool's evaluated result failed", () => {
    const c = cell([notRun("dbt"), card("soda", "red"), notRun("datacontract")]);
    expect(c.word).toBe("Fail");
    expect(c.marks).toBe("○ ✗ ○");
  });
});

// Functional critic on 7093c20, D1 (Keith Q2 = A, PROVISIONAL): "— why it is
// held back" and the red it brings come ONLY from the gate's structured
// hold-back naming the check, never from the warehouse cell being worse than
// the staged one (cp-placements, 2 February 2020, read Red with nothing held
// back).
describe("a row whose warehouse result is worse than its staged one", () => {
  function both(tool) {
    const c = card(tool, "green");
    c.check_id = `x.y.z.cp-notifications.cp_client_id.relationships_${tool}`;
    c.history = [
      { run_id: "older", rank: 2, supply_id: SUPPLY, status: "red" },
      { run_id: RUN.run_id, rank: 3, supply_id: SUPPLY, status: "green" },
    ];
    c.placed = {
      2: [{ on: "2024-08-05", bucket: "warehouse", note: NOTE, sentence: NOTE }],
      3: [{ on: "2024-08-05", bucket: "staged", note: NOTE, sentence: NOTE }],
    };
    return c;
  }
  function row(held) {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const col = { datasets: [{ id: "cp-notifications", name: "Notifications" },
      { id: "cp-clients", name: "Client Register" }] };
    const cards = [both("dbt"), both("soda"), both("datacontract")];
    return w.xtRowModel(col, cards, RUN, "2024-08-05", "cp-notifications", held);
  }

  it("is not held back, and keeps its own status, with no hold-back recorded", () => {
    const r = row(new Set());
    expect(r.heldBack).toBe(false);
    expect(r.status).toBe("green");
  });

  it("is held back where the gate's hold-back names its check", () => {
    const r = row(new Set(["x.y.z.cp-notifications.cp_client_id.relationships_soda"]));
    expect(r.heldBack).toBe(true);
    expect(r.status).toBe("red");
  });
});
