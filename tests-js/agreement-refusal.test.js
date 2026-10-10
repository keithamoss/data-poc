// REQ-PIPE-173 criteria 4, 7 and 8 - a refused dataset reads RED through the
// blocked banner, worded as our configuration problem; one asset-level
// notice names every refused dataset as a link; cards count it once by kind.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

const REFUSAL = {datasetId: "cp-clients", remedy: "restore the recorded value ... or declare the change",
  drifts: [{datasetId: "cp-clients", slot: "2023-Q3", supplies: 1,
            changes: [{item: "grace_seconds", recorded: 28800, current: 3600}]}]};

function withRefusal(byId){
  const w = loadDashboard().window;
  w.rawRealDatasetById = id => ({agreementRefusal: byId[id] || null});
  return w;
}

const DATA_ = {agencies: [{id: "a", name: "A", collections: [{id: "c", name: "C", datasets: [
  {id: "cp-clients", name: "Clients"}, {id: "cp-carers", name: "Carers"},
  {id: "cp-placements", name: "Placements"}]}]}]};

describe("a refused dataset", () => {
  it("is labelled as our configuration problem, not the supplier's", () => {
    const w = withRefusal({});
    const b = {kind: "agreement-refused", count: 1, openedAt: null};
    expect(w.blockerLabel(b)).toBe("Refused: the delivery agreement changed");
    expect(w.blockerSays(b)).toContain("configuration problem on our side");
    expect(w.blockerUntil(b)).toContain("restored or the change is declared");
    expect(w.blockerReceivedText(b)).not.toContain("Invalid");
  });

  it("names each change with its recorded and current values, and the remedy", () => {
    const w = withRefusal({});
    const text = w.refusalReasonText(REFUSAL);
    expect(text).toContain("2023-Q3: grace_seconds was 28800, is now 3600");
    expect(text).toContain("To fix: restore the recorded value");
  });
});

describe("one asset-level notice (criterion 7)", () => {
  it("is absent when nothing is refused", () => {
    const w = withRefusal({});
    expect(w.agreementNotice(DATA_)).toBe("");
  });

  it("lists every refused dataset once, each a link, with one action", () => {
    const w = withRefusal({"cp-clients": REFUSAL, "cp-carers": {...REFUSAL, datasetId: "cp-carers"}});
    const html = w.agreementNotice(DATA_);
    expect(html).toContain("2 datasets are refused");
    expect((html.match(/dataset-link/g) || []).length).toBe(2);
    expect(html).toContain(">Clients</a>");
    expect(html).not.toContain("Placements");
    expect(html).toContain("mothman schedule check-agreement");
    expect(html).toContain("configuration problem on our side");
  });

  it("names regenerating where the asset is synthetic (criterion 8)", () => {
    const w = withRefusal({"cp-clients": {...REFUSAL, remedy: "... `mothman env reset-synthetic` ..."}});
    expect(w.agreementNotice(DATA_)).toContain("regenerate its history");
  });

  it("counts refusals once by kind on a card", () => {
    const w = withRefusal({});
    expect(w.refusedMarker(0)).toBe("");
    expect(w.refusedMarker(3)).toContain("3\n    refused: agreement changed");
  });
});
