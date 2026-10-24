// REQ-DASH-220 criterion 12 (post-build-review #187, delivery-critic): card
// text is escaped, and renders only bold and inline code. It was passed
// straight to renderPlansMarkdown, which escapes nothing, so a card line
// holding an <img onerror> ran script on the public page.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let dashboard;
afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});
const load = () => (dashboard = loadDashboard()).window;

const card = (over) => ({
  firstLabel: "You told us", first: "Something", heard: "We heard it", built: null,
  date: "2026-09-24", number: 1, status: "Heard", evidence: [], ...over,
});
const render = (w, c) => {
  const el = w.document.createElement("ul");
  el.innerHTML = w.feedbackCard(c);
  return el;
};

describe("a feedback card's text", () => {
  it("is escaped, so markup in it cannot add an element", () => {
    const w = load();
    const el = render(w, card({ heard: '<img src=x onerror="window.__pwned=1"> and <b>bold</b>' }));
    expect(el.querySelectorAll("img").length).toBe(0);
    expect(el.querySelectorAll("b").length).toBe(0);
    expect(el.textContent).toContain('<img src=x onerror="window.__pwned=1">');
  });

  it("renders bold and inline code, and nothing else", () => {
    const w = load();
    const el = render(w, card({ first: "**strong** and `code`", heard: "1. not a list", built: "- nor this" }));
    expect(el.querySelector(".fb-first strong").textContent).toBe("strong");
    expect(el.querySelector(".fb-first code").textContent).toBe("code");
    expect(el.querySelectorAll("ol, ul ul, .fb-lines ul").length).toBe(0);
  });
});
