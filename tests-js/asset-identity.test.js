// Each asset's dashboard names itself and says where a moved collection went
// (REQ-PIPE-354 criteria 2, 6, 10 and 11).
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { MINIMAL_HIERARCHY, loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const TEMPLATE = readFileSync(new URL("../dashboard/qa-reporting-dashboard.template.html", import.meta.url), "utf8");
const MOVED = [{id: "birth-registrations", name: "Birth Registrations", asset_name: "Daily data asset",
                address: "https://data-poc-daily.pages.dev"}];
function built({ name = "Quarterly data asset", moved = MOVED, caption = null, url, hierarchy } = {}){
  let html = TEMPLATE;
  for(const [k, v] of [["ASSET_DISPLAY_NAME", name], ["MOVED_TO", moved], ["DEMO_CAPTION", caption]]){
    const placeholder = new RegExp(`const ${k} = .*?;\\n`);
    if(!placeholder.test(html)) throw new Error(`${k} placeholder not found`);
    html = html.replace(placeholder, `const ${k} = ${JSON.stringify(v)};\n`);
  }
  return loadDashboard({ html, url, hierarchy });
}

describe("the asset names itself (criterion 2)", () => {
  it("in the masthead and the title", () => {
    dashboard = built();
    const w = dashboard.window;
    expect(w.document.getElementById("masthead-asset").textContent).toBe("Quarterly data asset · Quality Assurance");
    expect(w.eval("SITE_NAME")).toBe("Quarterly data asset · Data Asset QA Register");
  });
});

describe("the moved notice (criterion 6)", () => {
  it("names what moved and links its new address with the route, never redirecting", () => {
    dashboard = built({ url: "https://data-poc-quarterly.pages.dev/?in-place-on=2026-09-01&period=2026-Q3&cmp=a&panel=x#/agency/registry-services/collection/civil-registration/dataset/birth-registrations" });
    const w = dashboard.window;
    const view = w.document.getElementById("view");
    w.renderMovedNotice(view, w.movedEntryForRoute({tier: "dataset", agencyId: "registry-services",
      collectionId: "civil-registration", datasetId: "birth-registrations"}));
    expect(view.querySelector("h2").textContent).toBe("Birth Registrations has moved to the Daily data asset's dashboard");
    const href = new URL(view.querySelector("[data-moved-link]").getAttribute("href"));
    expect(href.origin).toBe("https://data-poc-daily.pages.dev");
    expect(href.hash).toBe("#/agency/registry-services/collection/civil-registration/dataset/birth-registrations");
    expect(href.searchParams.get("in-place-on")).toBe("2026-09-01");
    for(const dropped of ["period", "cmp", "panel"]) expect(href.searchParams.has(dropped)).toBe(false);
    expect(view.querySelector("[data-moved-signin]").textContent).toBe("That dashboard has its own sign-in.");
  });

  it("is the not-found page for any other missing route", () => {
    dashboard = built({ moved: [] });
    const w = dashboard.window;
    const view = w.document.getElementById("view");
    w.renderNotFound(view, "Agency", "nowhere");
    expect(view.querySelector("h2").textContent).toBe("Agency not found");
  });
});

describe("a Feedback card's link to a route this asset does not hold (criterion 11)", () => {
  const link = href => ({kind: "link", label: "the page", href, inPlaceOn: null});
  it("is kept where moved_to covers it", () => {
    dashboard = built({ hierarchy: {agencies: []} });
    expect(dashboard.window.feedbackEvidence(link("#/agency/registry-services/collection/civil-registration/dataset/birth-registrations")))
      .toContain("data-fb-link");
  });
  it("is the label alone where nothing covers it", () => {
    dashboard = built({ moved: [], hierarchy: {agencies: []} });
    const html = dashboard.window.feedbackEvidence(link("#/agency/elsewhere"));
    expect(html).toContain("data-fb-unlinked");
    expect(html).not.toContain("<a ");
  });
  it("is a link to a route the asset holds", () => {
    dashboard = built({ moved: [], hierarchy: MINIMAL_HIERARCHY });
    expect(dashboard.window.feedbackEvidence(link("#/agency/registry-services"))).toContain("data-fb-link");
  });
});

describe("the Demo caption (criterion 10)", () => {
  it("is shown where the build captions it", () => {
    dashboard = built({ caption: "Recorded on the daily asset: these commands are run with MOTHMAN_ASSET=daily" });
    const view = dashboard.window.document.getElementById("view");
    dashboard.window.renderDemo(view);
    expect(view.querySelector("[data-demo-caption]").textContent)
      .toBe("Recorded on the daily asset: these commands are run with MOTHMAN_ASSET=daily");
  });
  it("is absent on the recording's own asset", () => {
    dashboard = built({ caption: null });
    const view = dashboard.window.document.getElementById("view");
    dashboard.window.renderDemo(view);
    expect(view.querySelector("[data-demo-caption]")).toBeNull();
  });
});
