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
