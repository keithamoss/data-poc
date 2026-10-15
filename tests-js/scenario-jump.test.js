// REQ-DASH-208 - a scenario link lands with the thing it is about on screen:
// the chip is a real link carrying scenario=<id>, the parameter is matched
// against the panel's own ids before any use, a reload repeats the jump, a
// stale one says so and is removed, any date change drops it, and the
// subject is marked with a labelled left rule rather than the focus ring.
import { afterEach, describe, expect, it } from "vitest";
import { MINIMAL_HIERARCHY, loadDashboard } from "./support/loadDashboard.js";

const ENTRY = {id: "TS-75a", mode: "INJECT", title: "t", section: "s", demonstrates: "",
               requirements: [],
               coordinates: {dataset: "cp-clients", period: "2025-Q1", inPlaceOn: "2025-03-10",
                             supplies: ["cp_run_009"], subject: "standing-in-pill"}};

let page;
afterEach(()=> page && page.close());

function load(url, entries = [ENTRY]){
  const html = (s => s.replace("const SCENARIO_MAP = [];",
    `const SCENARIO_MAP = ${JSON.stringify(entries)};`))(
    require("node:fs").readFileSync(
      require("node:path").join(__dirname, "..", "dashboard", "qa-reporting-dashboard.template.html"),
      "utf-8"));
  page = loadDashboard({html, hierarchy: MINIMAL_HIERARCHY, url});
  return page.window;
}

describe("the parameter is matched before it is used (criterion 11)", () => {
  it("matches an id in any case, and nothing else", () => {
    const w = load();
    expect(w.scenarioIndexById("ts-75A")).toBe(0);
    expect(w.scenarioIndexById("TS-75")).toBe(-1);
    expect(w.scenarioIndexById("<img src=x>")).toBe(-1);
    expect(w.scenarioIndexById(null)).toBe(-1);
  });

  it("reads the parameter's name in any case", () => {
    const w = load();
    w.history.replaceState(null, "", "/?Scenario=TS-75A");
    expect(w.scenarioParamFromUrl()).toBe("TS-75A");
  });

  it("writes it lowercase, and removes every spelling of it", () => {
    const w = load();
    const url = new w.URL("http://localhost/?SCENARIO=x&scenario=y&a=1");
    expect(w.withScenarioParam(url, "TS-75a").search).toBe("?a=1&scenario=ts-75a");
    expect(w.withScenarioParam(url, null).search).toBe("?a=1");
  });
});

describe("a chip is a real link (criterion 10)", () => {
  it("carries the scenario's date and id, and the dataset's route", () => {
    const w = load();
    const href = w.scenarioChipHref(ENTRY);
    expect(href).toContain("in-place-on=2025-03-10");
    expect(href).toContain("scenario=ts-75a");
    expect(href).toContain("cp-clients");
  });

  it("renders as an anchor with that address", () => {
    const w = load();
    const div = w.document.createElement("div");
    w.renderScenariosPanel(div);
    const a = div.querySelector("a[data-scenario]");
    expect(a).not.toBeNull();
    expect(a.getAttribute("href")).toContain("scenario=ts-75a");
  });
});

describe("a stale parameter (criterion 9)", () => {
  it("opens at the top, says so in one line, shows no bar and removes the parameter", () => {
    const w = load("http://localhost/?scenario=TS-999#/exec");
    const notice = w.document.querySelector("[data-scenario-not-found]");
    expect(notice).not.toBeNull();
    expect(notice.textContent).not.toContain("TS-999");
    expect(w.document.querySelector('[data-testid="scenario-jump-bar"]')).toBeNull();
    expect(w.location.search).not.toContain("scenario");
    expect(page.errors).toEqual([]);
  });

  it("names a matched scenario whose subject is not on the page, with its date", () => {
    const w = load();
    const view = w.document.getElementById("view");
    view.innerHTML = "";
    expect(w.landOnScenarioSubject(ENTRY, "2025-03-10")).toBe(false);
    const notice = view.querySelector("[data-scenario-not-found]");
    expect(notice.textContent).toContain("TS-75a");
    expect(notice.textContent).toContain("2025");
  });
});

describe("the mark (criterion 4)", () => {
  it("is a labelled left rule on the subject, '<id> · in place on <date>'", () => {
    const w = load();
    const view = w.document.getElementById("view");
    view.innerHTML = `<div class="view-head"><span class="pill" data-testid="standing-in">Substituted</span></div>`;
    w.eval(`STATE = {...STATE, scenarioJump: {id: "TS-75a", from: "2026-01-01", to: "2025-03-10"}}`);
    const el = w.markScenarioSubject();
    expect(el.classList.contains("scenario-subject")).toBe(true);
    const label = view.querySelector("[data-scenario-label]");
    expect(label.textContent).toMatch(/^TS-75a · in place on .*2025/);
    // Never the focus ring.
    expect(el.style.outline).toBe("");
  });

  it("expands collapsed supply history and focuses the subject without scrolling again", () => {
    const entry = {...ENTRY, coordinates: {...ENTRY.coordinates, subject: "supply-history-row"}};
    const w = load(undefined, [entry]);
    const view = w.document.getElementById("view");
    view.innerHTML = `<div class="supply-history"><button id="supply-history-toggle"></button>
      <div id="supply-history-older" hidden><table><tbody>
      <tr data-run-id="cp_run_009"><td>a</td></tr></tbody></table></div></div>`;
    view.querySelector("#supply-history-toggle").addEventListener("click", ()=>{
      view.querySelector("#supply-history-older").hidden = false;
    });
    let focusedWith = null;
    const row = view.querySelector("tr");
    row.focus = opts => { focusedWith = opts; };
    w.eval(`STATE = {...STATE, scenarioJump: {id: "TS-75a", from: "2026-01-01", to: "2025-03-10"}}`);
    expect(w.landOnScenarioSubject(entry, "2025-03-10")).toBe(true);
    expect(view.querySelector("#supply-history-older").hidden).toBe(false);
    expect(focusedWith).toEqual({preventScroll: true});
    expect(row.querySelector("[data-scenario-label]")).not.toBeNull();
  });
});

describe("any date change drops the jump (criterion 8)", () => {
  it("removes the parameter and the jump's state", () => {
    const w = load();
    w.eval(`STATE = {...STATE, scenarioJump: {id: "TS-75a", from: "2026-01-01", to: "2025-03-10"}}`);
    w.history.replaceState(null, "", "/?scenario=ts-75a&in-place-on=2025-03-10#/exec");
    w.applyInPlaceOn("2025-03-11");
    expect(w.location.search).not.toContain("scenario");
    expect(w.eval("STATE.scenarioJump")).toBeUndefined();
  });

  it("a navigation leaves it behind", () => {
    const w = load();
    w.history.replaceState(null, "", "/?scenario=ts-75a#/exec");
    w.navigate({tier: "exec"});
    expect(w.location.search).not.toContain("scenario");
  });
});
