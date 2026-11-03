// REQ-TEST-361 criterion 1's two surfaces no generated page shows - a
// re-checked-worse supply and a 'Re-checked <t>: became <X>' row - held to the
// colour-word rule here, against mock data (Keith, 2026-11-03, morning report
// 12 Q3, against the recommendation; REJECTED planting a scenario for each,
// and dropping them from criterion 1). The real-page guard
// (tests/test_dashboard_e2e.py::TestNoColourWordIsReadAsAStatus) scans what
// the data shows; these are the two it cannot reach.
//
// THE RULE IS THE REAL-PAGE GUARD'S (_GUARD_SCAN there): every text node's
// value, every title and aria-label, any match of /\b(green|amber|red)\b/i a
// failure - passing over [data-recorded-text] and [data-value-text], and the
// title of [data-recorded-title]. Each case first asserts its surface exists
// and holds text, so none can pass on nothing (CLAUDE.md test rule 3).
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => { dashboard?.close(); dashboard = undefined; });

const COLOUR = /\b(green|amber|red)\b/i;
const SKIP = "[data-recorded-text], [data-value-text]";

function colourWords(w, root) {
  const hits = [];
  let scanned = 0;
  const walker = w.document.createTreeWalker(root, w.NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || el.closest(SKIP)) continue;
    const text = n.nodeValue || "";
    scanned += text.trim().length;
    if (COLOUR.test(text)) hits.push(text.trim());
  }
  root.querySelectorAll("[title], [aria-label]").forEach((el) => {
    if (el.closest(SKIP)) return;
    for (const attr of ["title", "aria-label"]) {
      if (attr === "title" && el.closest("[data-recorded-title]")) continue;
      const v = el.getAttribute(attr);
      if (v && COLOUR.test(v)) hits.push(`@${attr} ${v}`);
    }
  });
  return { scanned, hits };
}

function render(w, html) {
  const div = w.document.createElement("div");
  div.innerHTML = html;
  w.document.body.appendChild(div);
  return div;
}

const PROMOTED = "2024-07-26T01:00:00+00:00";
const RC = "2024-08-09T02:30:00+00:00";
const ACK = "2024-08-10T02:30:00+00:00";

// A promoted supply, its re-checks and acknowledgements as the build embeds them.
function raw({ to, acks = [], promotedOn = "green" }) {
  return {
    id: "cp-notifications", name: "Notifications",
    runs: [{ run_id: "r1", run_date: "2024-07-25", supply_id: "s1", status: promotedOn }],
    runStates: { r1: [{ at: PROMOTED, state: "promoted", action: "promote" }] },
    promotedHealth: { r1: { promotedOn, promotedAt: PROMOTED,
      timeline: [{ at: "2024-07-25T02:00:00+00:00", status: promotedOn, cause: "its arrival" },
                 { at: RC, status: to, cause: "a re-check" }] } },
    rechecks: {
      supplies: { s1: [{ at: RC, person: "Keith Moss", reason: "the red flag was green", before: promotedOn, after: to }] },
      acks: { s1: acks } },
  };
}

function load(data) {
  dashboard = loadDashboard();
  dashboard.window.rawRealDatasetById = () => data;
  dashboard.window.rawRealDatasets = () => [data];
  return dashboard.window;
}

describe("a re-checked-worse supply reads no colour word", () => {
  it("re-checked to failing: the promoted-failing badge's re-check form", () => {
    const w = load(raw({ to: "red" }));
    const root = render(w, w.redPromotedBadge("cp-notifications", "r1", "2024-08-15"));
    expect(root.querySelector("[data-red-promoted-recheck]")).not.toBeNull();
    const { scanned, hits } = colourWords(w, root);
    expect(scanned).toBeGreaterThan(0);
    expect(hits).toEqual([]);
  });

  it.each([
    ["awaiting", []],
    ["acknowledged", [{ at: ACK, actor: "Ana Lee", reason: "amber is fine here" }]],
  ])("re-checked to warning, %s", (state, acks) => {
    const w = load(raw({ to: "amber", acks }));
    const root = render(w, w.recheckedAmberTag("cp-notifications", "r1", "2024-08-15"));
    expect(root.querySelector(`[data-rechecked-amber="${state}"]`)).not.toBeNull();
    const { scanned, hits } = colourWords(w, root);
    expect(scanned).toBeGreaterThan(0);
    expect(hits).toEqual([]);
  });
});

describe("a 'Re-checked <t>: became <X>' row reads no colour word", () => {
  // Shown on a date before the re-check, for a supply it turns from passing to
  // warning: the quiet forward note.
  it.each(["amber", "red"])("became the label for %s, never the word", (to) => {
    const w = load({ ...raw({ to }), runStates: {} });
    const html = w.recheckedRowStatus("cp-notifications", { run_id: "r1", status: "green" }, "2024-08-01");
    const root = render(w, html);
    const tag = root.querySelector("[data-rechecked-later]");
    expect(tag).not.toBeNull();
    expect(tag.textContent).toMatch(/^Re-checked .+: became \S+/);
    const { scanned, hits } = colourWords(w, root);
    expect(scanned).toBeGreaterThan(0);
    expect(hits).toEqual([]);
  });
});

describe("the rule can fail", () => {
  it("catches a raw stored value printed on the row", () => {
    const w = load({ ...raw({ to: "red" }), runStates: {} });
    w.statusWords = (s) => s;
    const root = render(w, w.recheckedRowStatus("cp-notifications", { run_id: "r1", status: "green" }, "2024-08-01"));
    expect(root.querySelector("[data-rechecked-later]")).not.toBeNull();
    expect(colourWords(w, root).hits.some((h) => /became red/.test(h))).toBe(true);
  });
});
