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
  it("is a labelled left rule on the subject, '<id> · in the warehouse on <date>'", () => {
    const w = load();
    const view = w.document.getElementById("view");
    view.innerHTML = `<div class="view-head"><span class="pill" data-testid="standing-in">Substituted</span></div>`;
    onItsPage(w);
    const el = w.markScenarioSubject();
    expect(el.classList.contains("scenario-subject")).toBe(true);
    const label = view.querySelector("[data-scenario-label]");
    expect(label.textContent).toMatch(/^TS-75a · in the warehouse on .*2025/);
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
    onItsPage(w);
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

// post-build-review #202 - the REQ-DASH-208 critic's findings, each seen
// failing first.
function onItsPage(w, extra = ""){
  w.eval(`STATE = {...scenarioTarget(SCENARIO_MAP[0]).nav,
                   scenarioJump: {id: "TS-75a", from: "2026-01-01", to: "2025-03-10"}${extra}};
          CURRENT_IN_PLACE_ON = "2025-03-10";`);
}
function historyRow(w, runId){
  const view = w.document.getElementById("view");
  view.innerHTML = `<div class="supply-history"><table><tbody>
    <tr data-run-id="${runId}"><td>a</td></tr></tbody></table></div>`;
  return view.querySelector("tr");
}
const ROW_ENTRY = {...ENTRY, coordinates: {...ENTRY.coordinates, subject: "supply-history-row"}};

describe("#202 F1 - a supply's row is found by its run id's own prefix", () => {
  it("finds the row of a supply whose run id carries a run suffix", () => {
    const w = load(undefined, [ROW_ENTRY]);
    onItsPage(w);
    const row = historyRow(w, "cp_run_009__1__r1");
    expect(w.scenarioSubjectEl(ROW_ENTRY)).toBe(row);
  });

  it("never a different supply that only shares the first characters", () => {
    const w = load(undefined, [ROW_ENTRY]);
    onItsPage(w);
    historyRow(w, "cp_run_0091__r1");
    expect(w.scenarioSubjectEl(ROW_ENTRY)).toBeNull();
  });
});

describe("a scenario with no supply lands on its period's gap row (post-build-review #290)", () => {
  // TS-96: no release came, so the placement names no supply - its row is
  // the period's gap, marked not supplied.
  const GAP_ENTRY = {...ENTRY, coordinates: {...ENTRY.coordinates, supplies: [],
                                             subject: "supply-history-row"}};
  function gapRows(w){
    const view = w.document.getElementById("view");
    view.innerHTML = `<div class="supply-history"><table><tbody>
      <tr data-gap="accepted"><td><a data-period-link>2024-Q4</a></td></tr>
      <tr data-gap="accepted"><td><a data-period-link>2025-Q1</a></td></tr></tbody></table></div>`;
    return [...view.querySelectorAll("tr")];
  }

  it("finds the gap row of the placement's own period", () => {
    const w = load(undefined, [GAP_ENTRY]);
    onItsPage(w);
    const [, own] = gapRows(w);
    expect(w.scenarioSubjectEl(GAP_ENTRY)).toBe(own);
  });

  it("never another period's gap", () => {
    const entry = {...GAP_ENTRY, coordinates: {...GAP_ENTRY.coordinates, period: "2023-Q2"}};
    const w = load(undefined, [entry]);
    onItsPage(w);
    gapRows(w);
    expect(w.scenarioSubjectEl(entry)).toBeNull();
  });
});

describe("#202 F4 - the subject counts only on the scenario's own page and date", () => {
  it("is not found on another dataset's page", () => {
    const w = load();
    w.eval(`STATE = {...scenarioTarget(SCENARIO_MAP[0]).nav, datasetId: "birth-registrations",
                     collectionId: "civil-registration", agencyId: "registry-services"};
            CURRENT_IN_PLACE_ON = "2025-03-10";`);
    w.document.getElementById("view").innerHTML =
      `<span class="pill" data-testid="standing-in">Substituted</span>`;
    expect(w.scenarioSubjectEl(ENTRY)).toBeNull();
  });

  it("is not found on another date", () => {
    const w = load();
    onItsPage(w);
    w.eval(`CURRENT_IN_PLACE_ON = "2025-03-11"`);
    w.document.getElementById("view").innerHTML =
      `<span class="pill" data-testid="standing-in">Substituted</span>`;
    expect(w.scenarioSubjectEl(ENTRY)).toBeNull();
  });

  it("is found on its own page and date", () => {
    const w = load();
    onItsPage(w);
    w.document.getElementById("view").innerHTML =
      `<span class="pill" data-testid="standing-in">Substituted</span>`;
    expect(w.scenarioSubjectEl(ENTRY)).not.toBeNull();
  });
});

describe("#202 F3 - a jump under an open panel or drawer does not take focus", () => {
  it("marks the subject but leaves focus to the panel", () => {
    const w = load(undefined, [ROW_ENTRY]);
    onItsPage(w, `, panel: "activity"`);
    const row = historyRow(w, "cp_run_009");
    let focused = false;
    row.focus = ()=> { focused = true; };
    expect(w.landOnScenarioSubject(ROW_ENTRY, "2025-03-10")).toBe(true);
    expect(focused).toBe(false);
    expect(row.classList.contains("scenario-subject")).toBe(true);
  });
});


describe("#202 F1 - a pair nobody checked lands on its blocker row", () => {
  it("finds the 'two files for one table' row by the supply's key", () => {
    const entry = {...ROW_ENTRY, coordinates: {...ROW_ENTRY.coordinates,
                   supplies: ["birth_registrations__202608211320000800"]}};
    const w = load(undefined, [entry]);
    onItsPage(w);
    const view = w.document.getElementById("view");
    view.innerHTML = `<div class="supply-history"><table><tbody>
      <tr data-blocker="contested" data-supply="birth-registrations@202608211320000800#1"><td>a</td></tr>
      <tr data-blocker="contested" data-supply="birth-registrations@202608211320000801#1"><td>b</td></tr>
      </tbody></table></div>`;
    expect(w.scenarioSubjectEl(entry)).toBe(view.querySelector("tr"));
  });
});

// post-build-review #259: on CI, TS-78a's subject ended 0.28px past the fold
// after a cold reload, though the jump had left a pixel to spare - something
// laid out after the jump (the fonts are the likely one) pushed it down. Once
// the fonts are in, a subject that has crossed the fold is brought back inside.
describe("a subject pushed past the fold after the jump", () => {
  it("is scrolled back a whole pixel inside it", () => {
    page = loadDashboard();
    const w = page.window;
    const calls = [];
    w.scrollBy = (o) => calls.push(o.top);
    const el = { getBoundingClientRect: () => ({ top: 656.78, bottom: 799.28, height: 142.5 }) };
    w.keepSubjectInsideFold(el, 800);
    // Scrolling DOWN brings a subject below the fold up into view.
    expect(calls).toEqual([1]);
  });

  it("is left alone when it is already inside", () => {
    page = loadDashboard();
    const w = page.window;
    const calls = [];
    w.scrollBy = (o) => calls.push(o.top);
    w.keepSubjectInsideFold({ getBoundingClientRect: () => ({ top: 655.5, bottom: 798.03, height: 142.5 }) }, 800);
    expect(calls).toEqual([]);
  });
});

// post-build-review #290: the head came back to -0.5px - a fractional scroll
// rounds down to the pixel - so a head that fits was left half a pixel above
// the window. Whole pixels, rounded up, never more than the room below.
describe("the head is brought back by whole pixels", () => {
  it("rounds up, so a head that fits is wholly in view", () => {
    page = loadDashboard();
    expect(page.window.headBackBy(-300.5, 400)).toBe(301);
  });

  it("never scrolls back more than the room below the subject", () => {
    page = loadDashboard();
    expect(page.window.headBackBy(-300.5, 49)).toBe(49);
  });

  it("does nothing when the head is already in view", () => {
    page = loadDashboard();
    expect(page.window.headBackBy(4, 49)).toBe(0);
  });
});
