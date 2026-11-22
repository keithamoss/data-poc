// A supply-history row that moves the date on show when clicked can be
// reached and used from the keyboard too (post-build-review #493 nit).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

function rowIn(w){
  const host = w.document.createElement("div");
  host.innerHTML = `<div class="supply-history"><table><tbody>
    <tr data-run-date="2026-03-04"><td>Row</td><td><details><summary>tries</summary></details></td></tr>
  </tbody></table></div>`;
  w.document.body.appendChild(host);
  const moved = [];
  w.applyInPlaceOn = d => moved.push(d);
  w.wireSupplyHistorySection(host);
  return { tr: host.querySelector("tr"), moved };
}

describe("a clickable supply row (#493 nit)", () => {
  it("is in the tab order", () => {
    dashboard = loadDashboard();
    const { tr } = rowIn(dashboard.window);
    expect(tr.tabIndex).toBe(0);
  });

  it("moves the date on Enter or Space, as a click does", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const { tr, moved } = rowIn(w);
    tr.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    tr.dispatchEvent(new w.KeyboardEvent("keydown", { key: " ", bubbles: true }));
    expect(moved).toEqual(["2026-03-04", "2026-03-04"]);
  });

  it("leaves a key pressed inside its disclosure to the disclosure", () => {
    dashboard = loadDashboard();
    const w = dashboard.window;
    const { tr, moved } = rowIn(w);
    tr.querySelector("summary").dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(moved).toEqual([]);
  });
});
