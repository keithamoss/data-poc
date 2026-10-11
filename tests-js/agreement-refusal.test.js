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

describe("the wording (delivery-critic on 173, #10)", () => {
  it("names data-asset.yaml as well as calendar.yaml", () => {
    const w = withRefusal({"cp-clients": REFUSAL});
    expect(w.agreementNotice(DATA_)).toContain("contract/data-asset.yaml");
  });
});

// Keith, 2026-10-11 (morning-report (g)): a refusal shows only on in-place-on
// dates on or after the earliest period it affects, and sits BESIDE another
// blocker rather than replacing it.
describe("when and where a refusal shows", () => {
  const FROM = {...REFUSAL, from: "2024-02-01"};

  it("shows only on dates on or after its earliest affected period", () => {
    const w = withRefusal({"cp-clients": FROM});
    expect(w.refusalInPlaceOn("cp-clients", "2024-01-31")).toBe(null);
    expect(w.refusalInPlaceOn("cp-clients", "2024-02-01")).toBe(FROM);
    expect(w.refusalInPlaceOn("cp-clients", "2025-06-01")).toBe(FROM);
  });

  it("shows on every date where the record names no period", () => {
    const w = withRefusal({"cp-clients": REFUSAL});
    expect(w.refusalInPlaceOn("cp-clients", "2020-01-01")).toBe(REFUSAL);
  });

  it("the asset notice follows the date the page is built for", () => {
    const w = withRefusal({"cp-clients": FROM});
    const data = {agencies: [{id: "a", name: "A", collections: [{id: "c", name: "C", datasets: [
      {id: "cp-clients", name: "Clients", refusalEvaluated: true, refusal: null}]}]}]};
    expect(w.agreementNotice(data)).toBe("");
  });

  it("alone, it is the dataset's blocker", () => {
    const w = withRefusal({});
    const ds = {id: "cp-clients", columns: []};
    expect(w.applyRefusal(ds, REFUSAL, null)).toBe(true);
    expect(ds.blocked.kind).toBe("agreement-refused");
    expect(ds.status).toBe("red");
  });

  it("beside another blocker, that blocker stays and the refusal is added", () => {
    const w = withRefusal({});
    const held = {kind: "held", count: 1, openedAt: "2024-03-01T00:00:00Z", reason: "two files"};
    const ds = {id: "cp-clients", columns: []};
    expect(w.applyRefusal(ds, REFUSAL, held)).toBe(false);
    expect(ds.blocked).toBeUndefined();
    expect(ds.alsoRefused).toBe(REFUSAL);
    expect(ds.status).toBe("red");
    const banner = w.refusedBesideBanner(ds);
    expect(banner).toContain("Refused: the delivery agreement changed");
    expect(banner).toContain("data-agreement-refused-beside");
  });
});

// delivery-critic on (f)-(i), finding 1: beside another blocker the last
// verdict was still shown as current, and the refusal's OWN hold counted as
// "another blocker", giving two banners for one cause.
describe("a refusal beside another blocker (critic finding 1)", () => {
  it("still blanks every check - the last verdict is never current", () => {
    const w = withRefusal({});
    const held = {kind: "held", count: 1, openedAt: "2024-03-01T00:00:00Z", reason: "two files"};
    const ds = {id: "cp-clients", columns: [{status: "green", checks: [{status: "green"}]}]};
    w.applyRefusal(ds, REFUSAL, held);
    expect(ds.columns[0].status).toBe("nodata");
    expect(ds.columns[0].checks[0].blockedThisPeriod).toBe(true);
  });

  it("does not count the refusal's own hold as another blocker", () => {
    const w = withRefusal({});
    w.blockersOpenInPlaceOn = () => [
      {kind: "held", openedAt: "2024-03-01", agreementRefused: true},
      {kind: "contested", openedAt: "2024-04-01"}];
    expect(w.otherBlockerThan("cp-clients", "2024-06-01").kind).toBe("contested");
    w.blockersOpenInPlaceOn = () => [{kind: "held", openedAt: "2024-03-01", agreementRefused: true}];
    expect(w.otherBlockerThan("cp-clients", "2024-06-01")).toBe(null);
  });
});

// Keith, 2026-10-11 (on the critic's finding 7): an exhausted schedule and an
// unmarked no-supply gap stay visible beside a refusal - each is a separate
// thing someone must fix.
describe("other states beside a refusal", () => {
  it("an exhausted schedule is still marked and counted", () => {
    const w = withRefusal({});
    const ds = {id: "cp-clients", status: "red"}, col = {exhaustedCount: 0}, ag = {exhaustedCount: 0};
    w.markBesideRefusal(ds, {lastDate: "2027-11-01"}, col, ag);
    expect(ds.scheduleExhausted).toEqual({lastDate: "2027-11-01"});
    expect(ds.status).toBe("red");
    expect([col.exhaustedCount, ag.exhaustedCount]).toEqual([1, 1]);
  });

  it("a no-supply gap's banner shows under a refusal, never under another blocker", () => {
    const w = withRefusal({});
    expect(w.noSupplyShown({noSupply: [1], blocked: {kind: "agreement-refused"}})).toBe(true);
    expect(w.noSupplyShown({noSupply: [1], blocked: {kind: "held"}})).toBe(false);
    expect(w.noSupplyShown({noSupply: [1]})).toBe(true);
    expect(w.noSupplyShown({noSupply: null})).toBe(false);
  });
});
