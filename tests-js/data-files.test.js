// REQ-DASH-291 criteria 5, 8, 9, 10 and 17 (and REQ-DASH-293 criterion 3):
// the page assembles COLLECTION_DATA from what its data files register,
// renders a page-level error naming any file that is missing or from
// another build, and - as the raw template - behaves exactly as it always
// did, with no data file and no error.
//
// The page is built here the way dashboard/data_files.py builds it: the
// template's `const DATA_FILES = null;` replaced with a list of expected
// files and `const COLLECTION_DATA = null;` with the assembling expression.
// A file's registration arrives as an inline script after the data-file
// marker - the form an archived snapshot carries it in (REQ-DASH-292) -
// because jsdom fetches no <script src> at all. Real loading from file://
// is proven in a real browser by tests/test_dashboard_e2e.py.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, MINIMAL_HIERARCHY, TEMPLATE_PATH } from "./support/loadDashboard.js";

const raw = (id, name) => ({
  id, name, provider: "P", deliveryFormat: "CSV", sla: null, runs: [], columns: [],
  closedSlots: [], runStates: {}, promotionTimeline: {points: [], standing: []},
});

const PAYLOAD = {
  "civil-registration": {datasets: [raw("birth-registrations", "Birth Registrations")]},
  "child-protection": {datasets: [raw("cp-clients", "Client Register")]},
};

const entry = (collection, part, parts, build) => ({
  key: `collection-${collection}`, kind: "collection", collection, part, parts,
  name: `collection-${collection}${parts > 1 ? `.part${part}` : ""}.aaaaaaaaaaaa.js`,
  bytes: 1, sha256: "0".repeat(64), build,
});
const REQS = {key: "requirements-plans", kind: "requirements-plans", part: 1, parts: 1,
  name: "requirements-plans.bbbbbbbbbbbb.js", bytes: 1, sha256: "0".repeat(64), build: "rrrrrrrrrrrr"};

const register = (key, part, build, text) =>
  `(window.MOTHMAN_DATA=window.MOTHMAN_DATA||{})[${JSON.stringify(`${key}#${part}`)}]=` +
  `{build:${JSON.stringify(build)},text:${JSON.stringify(text)}};`;

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

function load({files, registrations = [], url}) {
  let html = readFileSync(TEMPLATE_PATH, "utf-8");
  const marker = "<!-- mothman:data-files -->\n";
  expect(html.split(marker).length, "the template carries one data-file marker").toBe(2);
  expect(html).toContain("const DATA_FILES = null;\n");
  html = html
    .replace("const DATA_FILES = null;\n", `const DATA_FILES = ${JSON.stringify({build: "pppppppppppp", files})};\n`)
    .replace("const COLLECTION_DATA = null;\n", "const COLLECTION_DATA = assembleCollectionData();\n")
    .replace(marker, marker + registrations.map(r => `<script>${r}</script>\n`).join(""));
  dashboard = loadDashboard({html, hierarchy: MINIMAL_HIERARCHY, url});
  return dashboard.window;
}

const view = w => w.document.getElementById("view");
const errorBox = w => w.document.querySelector('[data-testid="data-file-error"]');

describe("REQ-DASH-291: assembling COLLECTION_DATA from the data files", () => {
  it("assembles every collection, in the list's order, from one JSON string each", () => {
    const w = load({
      files: [entry("civil-registration", 1, 1, "b1"), entry("child-protection", 1, 1, "b2")],
      registrations: [
        register("collection-civil-registration", 1, "b1", JSON.stringify(PAYLOAD["civil-registration"])),
        register("collection-child-protection", 1, "b2", JSON.stringify(PAYLOAD["child-protection"])),
      ],
    });
    expect(errorBox(w)).toBeNull();
    expect(w.rawRealDatasets().map(d => d.id)).toEqual(["birth-registrations", "cp-clients"]);
    expect(dashboard.errors).toEqual([]);
  });

  it("joins a payload's parts in order and parses the joined text once (REQ-DASH-293)", () => {
    const text = JSON.stringify(PAYLOAD["child-protection"]);
    const cut = Math.floor(text.length / 2);
    const w = load({
      files: [entry("child-protection", 1, 2, "b2"), entry("child-protection", 2, 2, "b2")],
      // Registered out of order on purpose: the list says the order, not
      // the order the scripts happened to run in.
      registrations: [
        register("collection-child-protection", 2, "b2", text.slice(cut)),
        register("collection-child-protection", 1, "b2", text.slice(0, cut)),
      ],
    });
    expect(errorBox(w)).toBeNull();
    expect(w.rawRealDatasets().map(d => d.id)).toEqual(["cp-clients"]);
  });
});

describe("REQ-DASH-291 criterion 8: a missing or other-build file is a page-level error", () => {
  it("names a file the page lists that never registers, and renders no tier", () => {
    const w = load({
      files: [entry("civil-registration", 1, 1, "b1"), entry("child-protection", 1, 1, "b2")],
      registrations: [register("collection-civil-registration", 1, "b1", JSON.stringify(PAYLOAD["civil-registration"]))],
    });
    const box = errorBox(w);
    expect(box).not.toBeNull();
    expect(box.textContent).toContain("collection-child-protection.aaaaaaaaaaaa.js");
    expect(box.textContent).toMatch(/missing/i);
    expect(box.textContent).not.toContain("collection-civil-registration.aaaaaaaaaaaa.js");
    expect(box.textContent).toContain("mothman dashboard embed");
    expect(box.textContent).toMatch(/publish is incomplete/i);
    expect(view(w).children.length, "nothing but the error is rendered").toBe(1);
    expect(view(w).textContent).not.toContain("Registry Services");
  });

  it("names a file registered under another build", () => {
    const w = load({
      files: [entry("civil-registration", 1, 1, "b1")],
      registrations: [register("collection-civil-registration", 1, "zz", JSON.stringify(PAYLOAD["civil-registration"]))],
    });
    const box = errorBox(w);
    expect(box.textContent).toContain("collection-civil-registration.aaaaaaaaaaaa.js");
    expect(box.textContent).toMatch(/another build/i);
  });

  it("says which in its heading, never just 'not right' (post-build-review #268)", () => {
    const heading = files => {
      const w = load({files, registrations: [
        register("collection-civil-registration", 1, "zz", JSON.stringify(PAYLOAD["civil-registration"]))]});
      return errorBox(w).querySelector("h2").textContent;
    };
    expect(heading([entry("child-protection", 1, 1, "b2")]))
      .toBe("This dashboard cannot be shown: one of its data files is missing");
    expect(heading([entry("civil-registration", 1, 1, "b1")]))
      .toBe("This dashboard cannot be shown: one of its data files is from another build");
    expect(heading([entry("civil-registration", 1, 1, "b1"), entry("child-protection", 1, 1, "b2")]))
      .toBe("This dashboard cannot be shown: some of its data files are from another build or missing");
  });

  it("is styled by the stylesheet in the page's own tokens, not an inline --red (#268 V1, V4)", () => {
    const w = load({files: [entry("child-protection", 1, 1, "b2")]});
    const box = errorBox(w);
    expect(box.getAttribute("style")).toBeNull();
    expect(box.classList.contains("data-file-error")).toBe(true);
    expect(box.querySelector("code.data-file-name").textContent).toBe("collection-child-protection.aaaaaaaaaaaa.js");
    const css = [...w.document.querySelectorAll("style")].map(el => el.textContent).join("\n");
    expect(css).toMatch(/\.data-file-error\{border:1px solid var\(--bad\)/);
    expect(css).not.toMatch(/var\(--red/);
  });

  it("names one missing part of a payload (REQ-DASH-293 criterion 3)", () => {
    const w = load({
      files: [entry("child-protection", 1, 2, "b2"), entry("child-protection", 2, 2, "b2")],
      registrations: [register("collection-child-protection", 1, "b2", "{")],
    });
    const box = errorBox(w);
    expect(box.textContent).toContain("collection-child-protection.part2.aaaaaaaaaaaa.js");
    expect(box.textContent).not.toContain("part1");
  });

  it("stays the error on every tier the address could name", () => {
    const w = load({files: [entry("civil-registration", 1, 1, "b1")],
      url: "http://localhost/agency/registry-services"});
    expect(errorBox(w)).not.toBeNull();
    expect(view(w).children.length).toBe(1);
  });
});

describe("REQ-DASH-291 criteria 7 and 9: Requirements and Plans load on demand", () => {
  const ok = () => load({
    files: [entry("civil-registration", 1, 1, "b1"), REQS],
    registrations: [register("collection-civil-registration", 1, "b1", JSON.stringify(PAYLOAD["civil-registration"]))],
  });

  it("does not load the Requirements and Plans file with the page", () => {
    const w = ok();
    expect(w.document.querySelector('script[src*="requirements-plans"]')).toBeNull();
    expect(errorBox(w)).toBeNull();
  });

  it("shows the Requirements panel as loading, never as an empty register, until it registers", () => {
    const w = ok();
    w.document.getElementById("requirements-btn").click();
    const body = w.document.getElementById("requirements-panel-body");
    expect(body.querySelector('[data-testid="data-file-loading"]')).not.toBeNull();
    expect(body.textContent).not.toContain("No requirements yet");
    const inserted = w.document.querySelector('script[src="data/requirements-plans.bbbbbbbbbbbb.js"]');
    expect(inserted, "the file is requested by a classic script element").not.toBeNull();
    expect(inserted.async).toBe(false);
    expect(inserted.type).toBe("");
  });

  it("shows the Plans tab as loading, never as zero entries, until it registers", () => {
    const w = ok();
    w.document.getElementById("plans-btn").click();
    expect(view(w).querySelector('[data-testid="data-file-loading"]')).not.toBeNull();
    expect(view(w).textContent).not.toMatch(/0 of 0/);
  });

  it("loads from an inline block when the page carries one, and renders the register", () => {
    const payload = JSON.stringify({requirements: [{id: "REQ-X-001", title: "A requirement", status: "built",
      moscow: "must", story: "s", acceptance_criteria: ["c"]}], plans: {items: [], threads: []}});
    let html = readFileSync(TEMPLATE_PATH, "utf-8");
    const marker = "<!-- mothman:data-files -->\n";
    html = html
      .replace("const DATA_FILES = null;\n", `const DATA_FILES = ${JSON.stringify({build: "p", files: [REQS]})};\n`)
      .replace("const COLLECTION_DATA = null;\n", "const COLLECTION_DATA = assembleCollectionData();\n")
      .replace(marker, marker + `<script type="text/plain" data-mothman-key="requirements-plans" ` +
        `data-mothman-file="${REQS.name}">${register("requirements-plans", 1, REQS.build, payload)}</script>\n`);
    dashboard = loadDashboard({html, hierarchy: MINIMAL_HIERARCHY});
    const w = dashboard.window;
    w.document.getElementById("requirements-btn").click();
    return new Promise(r => setTimeout(r, 0)).then(() => {
      const body = w.document.getElementById("requirements-panel-body");
      expect(body.textContent).toContain("REQ-X-001");
      expect(w.document.querySelector('script[src*="requirements-plans"]')).toBeNull();
    });
  });

  it("names the file inside the panel when it registers under another build", () => {
    let html = readFileSync(TEMPLATE_PATH, "utf-8");
    const marker = "<!-- mothman:data-files -->\n";
    html = html
      .replace("const DATA_FILES = null;\n", `const DATA_FILES = ${JSON.stringify({build: "p", files: [REQS]})};\n`)
      .replace("const COLLECTION_DATA = null;\n", "const COLLECTION_DATA = assembleCollectionData();\n")
      .replace(marker, marker + `<script type="text/plain" data-mothman-key="requirements-plans" ` +
        `data-mothman-file="${REQS.name}">${register("requirements-plans", 1, "other", "{}")}</script>\n`);
    dashboard = loadDashboard({html, hierarchy: MINIMAL_HIERARCHY});
    const w = dashboard.window;
    w.document.getElementById("requirements-btn").click();
    return new Promise(r => setTimeout(r, 0)).then(() => {
      const body = w.document.getElementById("requirements-panel-body");
      const box = body.querySelector('[data-testid="data-file-error"]');
      expect(box.textContent).toContain(REQS.name);
      // One panel, so "its" agrees (post-build-review #268).
      expect(box.querySelector("h2").textContent)
        .toBe("The Requirements panel cannot be shown: one of its data files is from another build");
      expect(body.textContent).not.toContain("No requirements yet");
    });
  });
});

describe("REQ-DASH-291 criterion 10: the raw template is unchanged", () => {
  it("lists no files, shows no error and loads nothing", () => {
    dashboard = loadDashboard({hierarchy: MINIMAL_HIERARCHY});
    const w = dashboard.window;
    expect(errorBox(w)).toBeNull();
    expect(w.document.querySelector("script[data-mothman-file]")).toBeNull();
    w.document.getElementById("requirements-btn").click();
    expect(w.document.getElementById("requirements-panel-body").textContent).toContain("No requirements yet");
    expect(w.document.querySelector('script[src*="data/"]')).toBeNull();
    expect(dashboard.errors).toEqual([]);
  });
});

describe("post-build-review #268: the Demo tab says which half is missing", () => {
  const demo = cast => {
    let html = readFileSync(TEMPLATE_PATH, "utf-8");
    expect(html).toContain("const DEMO_CAST = null;");
    if(cast) html = html.replace("const DEMO_CAST = null;", `const DEMO_CAST = ${JSON.stringify(cast)};`);
    dashboard = loadDashboard({html, hierarchy: MINIMAL_HIERARCHY});
    const w = dashboard.window;
    w.document.getElementById("demo-btn").click();
    return w.document.querySelector('[data-testid="demo-unavailable"]').textContent;
  };

  it("names the player, not the recording, when only the player is missing - as in a snapshot", () => {
    // jsdom loads no <script src>, so the vendored player is absent here
    // exactly as it is beside an archived snapshot.
    const said = demo('{"version": 2, "width": 80, "height": 24}\n');
    expect(said).toMatch(/the player that plays it is not/);
    expect(said).not.toMatch(/No demo recording/);
  });

  it("still says there is no recording when there is none", () => {
    expect(demo(null)).toMatch(/No demo recording embedded yet/);
  });
});
