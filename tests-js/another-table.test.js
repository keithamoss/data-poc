// REQ-DASH-204: a dataset turned red because another table it reads could not
// be read says so at the top of its page. The build works out each line
// (pipeline/cross_table_notices.py); the page words it. These pin the wording
// rules the page owns: one wording for every cause, the "not a fault" clause
// only where the supply has no red check of its own (criterion 3, the
// false-green direction), the package forms, and every name set as text.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const CLIENTS = { datasetId: "cp-clients", name: "Client Register",
  agencyId: "child-protection-family-support", collectionId: "child-protection",
  period: "2024-Q4", n: 3 };

function lineHtml(line, ownRed = false) {
  dashboard = loadDashboard();
  return dashboard.window.noPromotedLineHtml(line, ownRed);
}

function text(html) {
  const div = dashboard.window.document.createElement("div");
  div.innerHTML = html;
  return div.textContent.replace(/\s+/g, " ").trim();
}

describe("the one wording", () => {
  it("names the table and the period, and says the checks run again", () => {
    const html = lineHtml({ ...CLIENTS, form: "general" });
    expect(text(html)).toBe(
      "No promoted Client Register for 2024-Q4. 3 of this supply's checks need it, so they "
      + "could not run. That is not a fault in this supply's own data. They run again by "
      + "themselves once a 2024-Q4 Client Register supply is promoted.");
  });

  it("leaves out 'not a fault' where the supply has a red check of its own", () => {
    const html = lineHtml({ ...CLIENTS, form: "general" }, true);
    expect(text(html)).not.toContain("not a fault");
    expect(text(html)).toContain("No promoted Client Register for 2024-Q4.");
  });

  it("names the package-mate held back with it, then turned down, then replaced", () => {
    const partner = { partnerReceived: "2024-11-03T02:00:00+00:00" };
    expect(text(lineHtml({ ...CLIENTS, ...partner, form: "package" }))).toContain(
      "The Client Register received with this supply (10:00am Sunday, 3 November 2024) was "
      + "held back, so 3 of this supply's checks could not run.");
    expect(text(lineHtml({ ...CLIENTS, ...partner, form: "joined" }))).toContain(
      "The Client Register waiting for a decision (received 10:00am Sunday, 3 November 2024) "
      + "is held back, so 3 of this supply's checks could not run.");
    expect(text(lineHtml({ ...CLIENTS, ...partner, form: "turned-down" }))).toContain(
      "was turned down, so 3 of this supply's checks could not run.");
    expect(text(lineHtml({ ...CLIENTS, ...partner, form: "replaced",
      replacedReceived: "2024-11-07T10:00:00+08:00" }))).toContain(
      "has been replaced by the one received 10:00am Thursday, 7 November 2024, so 3 of");
  });

  it("words the owed re-check and the settled pair as criterion 7 does", () => {
    expect(text(lineHtml({ ...CLIENTS, form: "owed", promotedAt: "2024-11-04T02:00:00+00:00" })))
      .toBe("Not yet re-checked against the Client Register promoted 10:00am Monday, 4 November "
        + "2024. 3 of this supply's checks read it; the re-check runs on the next processing pass.");
    expect(text(lineHtml({ ...CLIENTS, form: "settled", settledOn: "2024-11-02" })))
      .toBe("Client Register's pair for 2024-Q4 was settled on Saturday, 2 November 2024. 3 of "
        + "this supply's checks have not run again since; the re-check runs on the next "
        + "processing pass.");
  });
});

describe("every name is text, never markup", () => {
  it("escapes a dataset name", () => {
    const html = lineHtml({ ...CLIENTS, name: "<img src=x onerror=alert(1)>", form: "general" });
    const div = dashboard.window.document.createElement("div");
    div.innerHTML = html;
    expect(div.querySelector("img")).toBeNull();
    expect(div.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("one line per table", () => {
  it("renders one line for each table the build names, however many checks read it", () => {
    dashboard = loadDashboard();
    const ds = { noPromotedOn: { on: "2024-11-03", ownRed: false, lines: [
      { ...CLIENTS, form: "general", n: 6 },
      { ...CLIENTS, datasetId: "cp-notifications", name: "Notifications", form: "general", n: 3 }] } };
    const div = dashboard.window.document.createElement("div");
    div.innerHTML = dashboard.window.noPromotedNotice(ds);
    expect(div.querySelector("[data-no-promoted]").dataset.noPromoted).toBe("2");
    expect(div.querySelectorAll(".np-line")).toHaveLength(2);
  });
});
