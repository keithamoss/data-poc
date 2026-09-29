// Drilling through a standing-in period to the one that earned its
// results (REQ-DASH-085 criteria 9-11, REQ-DASH-100 criteria 8-10).
//
// THE FAILURE THESE CLOSE is subtler than the qualifier's own. A reader
// who has been told "2026-Q3 stands on 2026-Q2" still has a page full
// of check results in front of them, and nothing on it says whose those
// results are. Clicking into one and reading it as 2026-Q3's own is the
// same false green the qualifier exists to stop, arriving one click
// later.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, MINIMAL_HIERARCHY } from "./support/loadDashboard.js";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function load(url) {
  dashboard = loadDashboard({ hierarchy: MINIMAL_HIERARCHY, url });
  return dashboard.window;
}

function ds(standingIn) {
  return { id: "cp-carers", status: "green", promotionState: { standingIn } };
}

const SUBSTITUTED = {
  kind: "substituted", level: "warning", period: "2026-Q3", standsOn: "2026-Q2",
  supply: "cp-carers@202605010100000000", decidedBy: "Keith", byAPerson: true,
  reason: "the supplier confirmed no extract will be sent for this quarter",
};

const INHERITED = {
  kind: "inherited", level: "information", period: "2026-Q3", standsOn: "2026-Q1",
  supply: "cp-carers@202602010100000000", decidedBy: null, byAPerson: false,
  reason: "carers are supplied annually, so no quarterly file is due",
};

describe("periodDateFor", () => {
  it("is the exact inverse of periodNameFor for an authored calendar", () => {
    // Round-trip, because the drill sets an as-of date and the page
    // then decides which period that date is in. If the two disagree
    // the reader lands on a neighbouring quarter.
    const w = load();
    for (const name of ["2025-Q3", "2026-Q1", "2026-Q2", "2026-Q3"]) {
      const date = w.periodDateFor("cp-carers", name);
      expect(date).toBeTruthy();
      expect(w.periodNameFor("cp-carers", date)).toBe(name);
    }
  });

  it("is the inverse on a daily calendar too, where a period IS a date", () => {
    const w = load();
    expect(w.periodDateFor("birth-registrations", "2026-05-14")).toBe("2026-05-14");
  });

  it("answers null for a period the embedded sequence does not carry", () => {
    // A snapshot built before that period existed. A button that
    // navigates nowhere is worse than no button.
    const w = load();
    expect(w.periodDateFor("cp-carers", "2031-Q4")).toBeNull();
    expect(w.periodDateFor("cp-carers", null)).toBeNull();
  });
});

describe("standingInDrill", () => {
  it("says whose results these are, in words rather than only as a link", () => {
    // A reader who never clicks still reads the checks below as this
    // period's, which is the whole false green.
    const w = load();
    const html = w.standingInDrill(ds(SUBSTITUTED));
    const flat = html.replace(/\s+/g, " ");
    expect(flat).toContain("ran against 2026-Q2's supply");
    expect(flat).toContain("They are not 2026-Q3's own results");
  });

  it("offers a way into the period that earned them", () => {
    const w = load();
    const html = w.standingInDrill(ds(SUBSTITUTED));
    expect(html).toContain('data-testid="standing-in-drill"');
    // 2026-Q2's own date on the embedded quarterly calendar.
    expect(html).toContain('data-to="2026-05-01"');
    expect(html).toContain('data-from="2026-Q3"');
  });

  it("does the same for an inherited period", () => {
    const w = load();
    const html = w.standingInDrill(ds(INHERITED));
    expect(html).toContain('data-to="2026-02-01"');
    expect(html).toContain('data-from="2026-Q3"');
  });

  it("keeps the sentence and drops the button when the date is unknown", () => {
    const w = load();
    const html = w.standingInDrill(ds({ ...SUBSTITUTED, standsOn: "2031-Q4" }));
    expect(html).toContain("ran against");
    expect(html).not.toContain("standing-in-drill");
  });

  it("renders nothing at all for a period holding its own supply", () => {
    const w = load();
    expect(w.standingInDrill(ds(null))).toBe("");
  });

  it("is part of the detail block, not a separate thing to find", () => {
    const w = load();
    expect(w.standingInDetail(ds(SUBSTITUTED))).toContain("standing-in-drill");
  });
});

describe("arrivalBanner", () => {
  it("says nothing to a reader who navigated here directly", () => {
    // The 'only' is half the requirement: telling someone they have
    // left a period they were never on is a false alarm.
    const w = load("http://localhost/");
    expect(w.arrivalBanner(ds(SUBSTITUTED))).toBe("");
  });

  it("names the period the reader left, and offers a way back to it", () => {
    const w = load("http://localhost/?from=2026-Q3");
    const html = w.arrivalBanner(ds(SUBSTITUTED));
    expect(html).toContain("You have left 2026-Q3");
    expect(html).toContain('data-testid="arrival-back"');
    expect(html).toContain('data-to="2026-08-01"');
  });

  it("names which of the two kinds was followed", () => {
    const w = load("http://localhost/?from=2026-Q3");
    expect(w.arrivalBanner(ds(SUBSTITUTED))).toContain("a substitution");
    expect(w.arrivalBanner(ds(INHERITED))).toContain("an inherited period");
  });

  it("still frames a hand-edited or shared link with no standing-in record", () => {
    // Refusing to render unless a matching record exists would drop the
    // framing on exactly the shared links it is meant to survive.
    const w = load("http://localhost/?from=2026-Q3");
    const html = w.arrivalBanner(ds(null));
    expect(html).toContain("You have left 2026-Q3");
    expect(html).toContain('data-to="2026-08-01"');
  });

  it("escapes a period name from the URL rather than trusting it", () => {
    const w = load("http://localhost/?from=%3Cimg%20src%3Dx%3E");
    const html = w.arrivalBanner(ds(null));
    expect(html).toContain("&lt;img");
    expect(html).not.toContain("<img");
  });
});

describe("the arrival context in the URL", () => {
  it("survives a reload, because it is read from the address", () => {
    const w = load("http://localhost/?from=2026-Q3");
    expect(w.arrivalFromUrl()).toBe("2026-Q3");
  });

  it("is dropped by the reader's next navigation, URL and all", () => {
    // It belongs to ONE page. A banner saying 'you have left 2026-Q3'
    // is true of the page it was followed to and a lie everywhere else.
    const w = load("http://localhost/?from=2026-Q3&asof=2026-05-01");
    expect(w.arrivalFromUrl()).toBe("2026-Q3");
    w.navigate({ tier: "agency", agencyId: "registry-services" });
    expect(w.arrivalFromUrl()).toBeNull();
    expect(w.arrivalBanner(ds(SUBSTITUTED))).toBe("");
    // The orthogonal query state a navigation has always kept stays.
    expect(new w.URLSearchParams(w.location.search).get("asof")).toBe("2026-05-01");
    expect(w.location.hash).toBe("#/agency/registry-services");
  });

  it("is dropped by a date the reader picked themselves", () => {
    const w = load("http://localhost/?from=2026-Q3&asof=2026-05-01");
    w.applyAsOf("2026-02-01");
    expect(w.arrivalFromUrl()).toBeNull();
  });

  it("is set by the drill, alongside the date it moves to", () => {
    const w = load("http://localhost/?asof=2026-08-01");
    w.drillToPeriod("2026-05-01", "2026-Q3");
    const params = new w.URLSearchParams(w.location.search);
    expect(params.get("from")).toBe("2026-Q3");
    expect(params.get("asof")).toBe("2026-05-01");
  });

  it("refuses a date that is not a date, changing nothing", () => {
    const w = load("http://localhost/?asof=2026-08-01");
    w.drillToPeriod("not-a-date", "2026-Q3");
    expect(new w.URLSearchParams(w.location.search).get("asof")).toBe("2026-08-01");
    expect(w.arrivalFromUrl()).toBeNull();
  });
});

describe("wireArrivalContext", () => {
  // The markup and the listener are written in two different places,
  // and a selector that no longer matches its own button fails
  // silently - the page renders, the button is there, and nothing
  // happens when it is pressed. So this drives the real markup the two
  // renderers emit through the real wiring.
  function wired(w, html) {
    const host = w.document.createElement("div");
    host.innerHTML = html;
    w.document.body.appendChild(host);
    w.wireArrivalContext(host);
    return host;
  }

  it("makes the drill button actually move the as-of date, and say where from", () => {
    const w = load("http://localhost/?asof=2026-08-01");
    const host = wired(w, w.standingInDrill(ds(SUBSTITUTED)));
    host.querySelector("[data-standing-drill]").click();
    const params = new w.URLSearchParams(w.location.search);
    expect(params.get("asof")).toBe("2026-05-01");
    expect(params.get("from")).toBe("2026-Q3");
  });

  it("makes the back button return to the period the reader left, framing gone", () => {
    const w = load("http://localhost/?asof=2026-05-01&from=2026-Q3");
    const host = wired(w, w.arrivalBanner(ds(SUBSTITUTED)));
    host.querySelector("[data-arrival-back]").click();
    const params = new w.URLSearchParams(w.location.search);
    expect(params.get("asof")).toBe("2026-08-01");
    expect(params.get("from")).toBeNull();
  });
});
