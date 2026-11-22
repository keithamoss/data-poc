// Each asset's dashboard names itself (REQ-PIPE-354 criteria 2, 10 and 11).
// Its moved-collection notice was removed at Keith's call, 2026-11-22: an old
// link to something that moved reads as any missing route does.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { MINIMAL_HIERARCHY, loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const TEMPLATE = readFileSync(new URL("../dashboard/qa-reporting-dashboard.template.html", import.meta.url), "utf8");
function built({ name = "Quarterly data asset", caption = null, url, hierarchy } = {}){
  let html = TEMPLATE;
  for(const [k, v] of [["ASSET_DISPLAY_NAME", name], ["DEMO_CAPTION", caption]]){
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

describe("a missing route (criterion 6 retired, Keith 2026-11-22)", () => {
  it("is the not-found page, Birth Registrations' old route included", () => {
    dashboard = built();
    const w = dashboard.window;
    const view = w.document.getElementById("view");
    w.renderNotFound(view, "Dataset", "birth-registrations");
    expect(view.querySelector("h2").textContent).toBe("Dataset not found");
  });
});

describe("a Feedback card's link to a route this asset does not hold (criterion 11)", () => {
  const link = href => ({kind: "link", label: "the page", href, inPlaceOn: null});
  it("is the label alone where nothing covers it", () => {
    dashboard = built({ hierarchy: {agencies: []} });
    const html = dashboard.window.feedbackEvidence(link("#/agency/elsewhere"));
    expect(html).toContain("data-fb-unlinked");
    expect(html).not.toContain("<a ");
  });
  it("is a link to a route the asset holds", () => {
    dashboard = built({ hierarchy: MINIMAL_HIERARCHY });
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
  it("styles the command it names as code, its words unchanged (#493 nit)", () => {
    dashboard = built({ caption: "Recorded on the daily asset: these commands are run with `MOTHMAN_ASSET=daily`" });
    const view = dashboard.window.document.getElementById("view");
    dashboard.window.renderDemo(view);
    const cap = view.querySelector("[data-demo-caption]");
    expect(cap.querySelector("code").textContent).toBe("MOTHMAN_ASSET=daily");
    expect(cap.textContent).toBe("Recorded on the daily asset: these commands are run with MOTHMAN_ASSET=daily");
  });
  it("is absent on the recording's own asset", () => {
    dashboard = built({ caption: null });
    const view = dashboard.window.document.getElementById("view");
    dashboard.window.renderDemo(view);
    expect(view.querySelector("[data-demo-caption]")).toBeNull();
  });
});
