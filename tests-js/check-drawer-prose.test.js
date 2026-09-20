// REQ-QAC-024 - the two plain-English fields, at the layer a person
// actually reads.
//
// The check drawer is where someone who does not know dbt or Soda finds
// out what a check is for. It now carries two authored blocks: what the
// check verifies, and what a failure most likely means happened
// upstream. It must carry exactly those two and never the third.
//
// `technical_note` is authored for contributors, and this page is
// published publicly. It is excluded at the builders so it never
// reaches the browser - this asserts the render layer would not show it
// even if it somehow did, because a single leak on a public site is not
// undone by the fact that the layer behind it was supposed to catch it.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function drawerHtmlFor(check) {
  dashboard = loadDashboard();
  const w = dashboard.window;
  const full = {
    name: "Sex is one of the accepted values", dimension: "validity",
    unit: "count", warn: null, fail: null, current: 0, current_status: "green",
    previous: 0, changelog: [], note: "Computed by dbt.",
    // Two real points: the drawer's compare block reads the current and
    // comparison runs directly, so an empty history is not a valid
    // check to open - it throws before any prose is rendered.
    history: [
      { value: 0, status: "green", run_date: "2026-09-01", idx: 0, date: new Date("2026-09-01") },
      { value: 0, status: "green", run_date: "2026-09-02", idx: 1, date: new Date("2026-09-02") },
    ],
    ...check,
  };
  const column = { name: "sex", checks: [full], stats: {} };
  const ds = { name: "Birth Registrations", runs: [], columns: [column] };
  // ag/col are the agency and collection OBJECTS the eyebrow renders
  // from, not their ids; pushHistory:false keeps this off the jsdom
  // history stack, which the drawer supports for exactly this reason
  // (re-render after a compare change, restore from popstate).
  w.openCheckPanel({ name: "BDM" }, { name: "Births" }, ds, column, full,
                   { pushHistory: false });
  return w.document.getElementById("check-panel-body").innerHTML;
}

describe("the check drawer's authored prose", () => {
  it("shows what a failure means, alongside what the check does", () => {
    const html = drawerHtmlFor({
      description: "Sex must be one of the values the contract allows.",
      failure_indicates: "The upstream extract probably ran before the day closed.",
    });
    expect(html).toContain("What this check does");
    expect(html).toContain("Sex must be one of the values the contract allows.");
    expect(html).toContain("What a failure means");
    expect(html).toContain("The upstream extract probably ran before the day closed.");
  });

  it("omits the failure section rather than showing an empty heading", () => {
    // The common case, by design: where the cause is self-evident from
    // what the check verifies, authoring a sentence would just restate
    // it in other words.
    const html = drawerHtmlFor({
      description: "Sex must be one of the values the contract allows.",
    });
    expect(html).toContain("What this check does");
    expect(html).not.toContain("What a failure means");
  });

  it("never renders a technical note, even if one reaches the browser", () => {
    const html = drawerHtmlFor({
      description: "Sex must be one of the values the contract allows.",
      technical_note: "Paired with the Soda check on the same column.",
    });
    expect(html).not.toContain("Paired with the Soda check");
    expect(html).not.toContain("technical_note");
  });
});
