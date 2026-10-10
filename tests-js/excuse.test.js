// REQ-DASH-162 - an excused late supply reads as late AND excused, naming
// the reason; a withdrawn excuse reads late again; a lapsed one says so.
import { describe, it, expect } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

function withRaw(raw){
  const w = loadDashboard().window;
  w.rawRealDatasetById = () => raw;
  return w;
}

const EXCUSED = {at: "2026-03-05T01:00:00+00:00", actor: "Keith", reason: "the supplier's outage",
                 slot: "2026-Q1", withdrawn: null, lapsed: null, lapsedAt: null};

describe("an excused late supply", () => {
  it("is a neutral 'Late (excused)' tag, never green and never the red Late pill", () => {
    const w = withRaw({excuses: {r1: [EXCUSED]}});
    const html = w.arrivalPillFor("cp-carers", "r1", "late", "sm", "2026-03-10");
    expect(html).toContain("Late (excused)");
    expect(html).toContain("pill tag");
    expect(html).not.toContain("pill red");
    expect(html).not.toContain("green");
  });

  it("is told apart from an unexcused late one", () => {
    const w = withRaw({excuses: {r1: [EXCUSED]}});
    expect(w.arrivalPillFor("cp-carers", "r1", "late", "sm", "2026-03-10"))
      .not.toBe(w.arrivalPillFor("cp-carers", "r2", "late", "sm", "2026-03-10"));
    expect(w.arrivalPillFor("cp-carers", "r2", "late", "sm", "2026-03-10")).toContain("pill red");
  });

  it("never excuses a supply that is not late (criterion 7: beside, not instead)", () => {
    const w = withRaw({excuses: {r1: [EXCUSED]}});
    expect(w.arrivalPillFor("cp-carers", "r1", "early", "sm", "2026-03-10")).toContain(">Early<");
  });

  it("shows the reason, person and date as visible text on the history row", () => {
    const w = withRaw({excuses: {r1: [EXCUSED]}});
    const note = w.excuseNote("cp-carers", "r1", "2026-03-10");
    expect(note).toContain("Excused by Keith");
    expect(note).toContain("the supplier's outage");
    expect(note).toContain(w.fmtInstant(EXCUSED.at));
  });

  it("is shown only on in-place-on dates on or after it was recorded (criterion 5)", () => {
    const w = withRaw({excuses: {r1: [EXCUSED]}});
    expect(w.excuseInForce("cp-carers", "r1", "2026-03-01")).toBeNull();
    expect(w.excuseInForce("cp-carers", "r1", "2026-03-05")).not.toBeNull();
    expect(w.excuseNote("cp-carers", "r1", "2026-03-01")).toBe("");
  });
});

describe("a withdrawn excuse (criterion 3)", () => {
  const raw = {excuses: {r1: [{...EXCUSED, withdrawn: {
    at: "2026-04-01T01:00:00+00:00", actor: "Keith", reason: "it was not the outage"}}]}};

  it("reads late again once withdrawn, and excused before", () => {
    const w = withRaw(raw);
    expect(w.arrivalPillFor("cp-carers", "r1", "late", "sm", "2026-04-02")).toContain("pill red");
    expect(w.arrivalPillFor("cp-carers", "r1", "late", "sm", "2026-03-10")).toContain("Late (excused)");
  });

  it("shows the excuse and its withdrawal in the history", () => {
    const w = withRaw(raw);
    const note = w.excuseNote("cp-carers", "r1", "2026-04-02");
    expect(note).toContain("Excused by Keith");
    expect(note).toContain("withdrawn by Keith");
    expect(note).toContain("it was not the outage");
  });
});

describe("a lapsed excuse (criterion 8)", () => {
  it("says 'Excuse lapsed - re-filed to <period>' and reads plainly", () => {
    const w = withRaw({excuses: {r1: [{...EXCUSED, lapsed: "re-filed to 2026-Q2",
                                       lapsedAt: "2026-04-01T01:00:00+00:00"}]}});
    expect(w.excuseNote("cp-carers", "r1", "2026-04-02"))
      .toContain("Excuse lapsed - re-filed to 2026-Q2");
    expect(w.excuseInForce("cp-carers", "r1", "2026-04-02")).toBeNull();
    // before the lapse it was still in force
    expect(w.excuseInForce("cp-carers", "r1", "2026-03-10")).not.toBeNull();
  });

  it("names the correction where a re-judgement lapsed it", () => {
    const w = withRaw({excuses: {r1: [{...EXCUSED, lapsed: "re-judged on time by CHG-7",
                                       lapsedAt: "2026-04-01T01:00:00+00:00"}]}});
    expect(w.excuseNote("cp-carers", "r1", "2026-04-02"))
      .toContain("Excuse lapsed - re-judged on time by CHG-7");
  });
});

describe("a reason with quotes or markup", () => {
  it("cannot break out of the pill's title or the note", () => {
    const w = withRaw({excuses: {r1: [{...EXCUSED, reason: '"><img src=x onerror=1>'}]}});
    const pill = w.arrivalPillFor("cp-carers", "r1", "late", "sm", "2026-03-10");
    expect(pill).not.toContain("<img");
    expect(pill).toContain("&quot;");
    expect(w.excuseNote("cp-carers", "r1", "2026-03-10")).not.toContain("<img");
  });
});
