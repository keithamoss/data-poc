// REQ-PIPE-081 criterion 6: where a decision made later has changed what an
// earlier date shows, the page says so and names the decision. "Later" is
// the plain reading - recorded after the date on show, effective on or
// before it - which became meaningful once a replay stamps its records
// with its own time (criteria 27-31, Keith 2026-10-06).
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const RAW = {id: "cp-carers", name: "Carers",
  runs: [{run_id: "r1", run_date: "2026-01-10", arrivedAt: "2026-01-10T01:00:00+00:00"}],
  runStates: {r1: [
    // Replayed: recorded as it took effect - changes no earlier date.
    {at: "2026-01-12T01:00:00+00:00", recordedAt: "2026-01-12T01:00:05+00:00",
     state: "promoted", action: "promote", by: "rule"},
    // A person's later correction, back to 1 February.
    {at: "2026-02-01T01:00:00+00:00", recordedAt: "2026-03-20T02:00:00+00:00",
     state: "withdrawn", action: "reject", by: "person"}]}};

function page(){
  const w = loadDashboard().window;
  w.rawRealDatasets = () => [RAW];
  return w;
}

describe("decisions that changed an earlier date", () => {
  it("names a decision recorded after the date that took effect on or before it", () => {
    const w = page();
    const found = w.decisionsChangingDate("2026-02-15");
    expect(found.length).toBe(1);
    expect(found[0].action).toBe("reject");
    expect(found[0].datasetName).toBe("Carers");
  });

  it("finds none where every decision was recorded as it took effect", () => {
    const w = page();
    expect(w.decisionsChangingDate("2026-01-20").length).toBe(0);
  });

  it("finds none once the date on show is after it was recorded", () => {
    const w = page();
    expect(w.decisionsChangingDate("2026-03-25").length).toBe(0);
  });

  it("is said in the past-date notice, naming the dataset, the decision and when it was made", () => {
    const w = page();
    w.eval("CURRENT_IN_PLACE_ON = '2026-02-15'");
    let notice = w.document.getElementById("in-place-on-past-notice");
    if(!notice){
      notice = w.document.createElement("div");
      notice.id = "in-place-on-past-notice";
      w.document.body.appendChild(notice);
    }
    w.renderInPlaceOnPastNotice();
    const said = notice.querySelector("[data-changed-since]");
    expect(said).not.toBeNull();
    expect(said.textContent).toContain("Carers");
    expect(said.textContent).toContain("rejected");
    expect(said.textContent).toContain("20 March 2026");
  });
});
