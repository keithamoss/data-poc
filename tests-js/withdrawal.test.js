// REQ-PIPE-166 criteria 12, 13, 15 and 16 - a withdrawn acknowledgement or
// mark as not supplied reads as standing up to the withdrawal's instant and
// not from it, and the withdrawal is shown in words beside what it withdrew.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

function withRaw(raw){
  const w = loadDashboard().window;
  w.rawRealDatasetById = () => raw;
  return w;
}

const WITHDRAWN = {at: "2026-03-08T01:00:00+00:00", actor: "Ana", reason: "wrong supply"};
const ACK = {at: "2026-03-05T01:00:00+00:00", actor: "Keith", reason: "looked, acceptable",
             withdrawn: WITHDRAWN};
const PROMOTED = {supply: "s", period: "2026-Q1", promotedAt: "2026-03-01T01:00:00+00:00",
                  lapsedAt: null};

describe("a withdrawn acknowledgement", () => {
  it("is shown standing, with its reason as visible text, before the withdrawal", () => {
    const w = withRaw({acknowledgements: {r1: {...PROMOTED, acks: [ACK]}}});
    const html = w.acknowledgementBadge("cp-carers", "r1", "2026-03-06");
    expect(html).toContain("Acknowledged by Keith");
    expect(html).toContain(">looked, acceptable<");
    expect(html).not.toContain("withdrawn");
  });

  it("from the withdrawal on, awaits acknowledgement again with the withdrawn one beneath", () => {
    const w = withRaw({acknowledgements: {r1: {...PROMOTED, acks: [ACK]}}});
    const html = w.acknowledgementBadge("cp-carers", "r1", "2026-03-09");
    expect(html).toContain("awaiting acknowledgement");
    expect(html).toContain("Acknowledged by Keith");
    expect(html).toContain("withdrawn by Ana");
    expect(html).toContain("wrong supply");
    expect(html.indexOf("awaiting acknowledgement")).toBeLessThan(html.indexOf("withdrawn by Ana"));
  });

  it("acknowledged again, the newer one stands (criterion 17)", () => {
    const again = {at: "2026-03-10T01:00:00+00:00", actor: "Bo", reason: "second look",
                   withdrawn: null};
    const w = withRaw({acknowledgements: {r1: {...PROMOTED, acks: [ACK, again]}}});
    const html = w.acknowledgementBadge("cp-carers", "r1", "2026-03-11");
    expect(html).toContain("Acknowledged by Bo");
    expect(html).not.toContain("awaiting acknowledgement");
  });
});

const slot = (period, index, extra) => ({period, index,
  closesAt: `${period}T16:00:00+00:00`, changes: [], filedAt: null,
  marks: [], rejected: null, ...extra});
const MARK = {at: "2026-03-05T02:00:00+00:00", actor: "k", reason: "supplier outage",
              withdrawn: {at: "2026-03-08T02:00:00+00:00", actor: "Ana", reason: "it came"}};

describe("a withdrawn mark as not supplied", () => {
  it("is accepted up to the withdrawal and open from it", () => {
    const w = loadDashboard().window;
    const s = slot("2026-03-01", 10, {marks: [MARK]});
    expect(w.closedGapsInPlaceOn([s], "2026-03-06").accepted).toHaveLength(1);
    const after = w.closedGapsInPlaceOn([s], "2026-03-09");
    expect(after.accepted).toHaveLength(0);
    expect(after.open).toHaveLength(1);
  });

  it("is said in the shape an excuse's withdrawal is", () => {
    const w = loadDashboard().window;
    const note = w.markWithdrawalNotes([MARK], "2026-03-09");
    expect(note).toContain("Not supplied (accepted)");
    expect(note).toContain(`· withdrawn by Ana, ${w.fmtInstant(MARK.withdrawn.at)}: it came`);
    expect(w.markWithdrawalNotes([MARK], "2026-03-06")).toBe("");
  });
});

describe("the page's words for every decision (criterion 12)", () => {
  it("names both withdrawals", () => {
    const w = loadDashboard().window;
    expect(w.eval("DECISION_DONE")["withdraw-acknowledgement"]).toBe("no longer acknowledged");
    expect(w.eval("DECISION_DONE")["withdraw-not-supplied"]).toBe("no longer marked not supplied");
  });
});
