// Covers renderPlansMarkdown()'s fenced-code-block handling - added
// 2026-09-22 alongside the fix.
//
// The bug: the renderer split on blank lines FIRST and had no fence
// handling at all, so every ```yaml config sketch in plans/*.md rendered
// as a run-on paragraph with stray backticks, torn into several pieces
// wherever the sketch had a blank line in it. plans/supply-model.md
// Thread C has carried such sketches since it was written.
//
// Same failure Keith reported on 2026-09-19 for numbered sub-lists,
// whose own fix comment sits inside the function being tested here -
// which is why these tests also assert the list and paragraph behaviour
// still holds. A fence fix that quietly broke lists would be a poor
// trade, and nothing else covers that function.
import { describe, it, expect, beforeAll } from "vitest";
import { loadDashboard } from "./support/loadDashboard.js";

let win;
beforeAll(() => { win = loadDashboard().window || loadDashboard(); });

describe("renderPlansMarkdown - fenced code blocks", () => {
  it("renders a fence as a <pre><code> rather than a paragraph", () => {
    const html = win.renderPlansMarkdown("Intro.\n\n```yaml\nkey: value\n```\n\nAfter.");
    expect(html).toContain("<pre");
    expect(html).toContain("<code>key: value</code>");
    expect(html).toContain("<p>Intro.</p>");
    expect(html).toContain("<p>After.</p>");
  });

  it("keeps a fence intact when it contains blank lines", () => {
    // The actual shape that broke: plans/supply-model.md's own calendar
    // sketch has a blank line between the asset and dataset halves.
    const md = "Sketch:\n\n```yaml\ncalendar:\n  - date: 2026-02-02\n\ndelivery_months: [February]\n```\n\nEnd.";
    const html = win.renderPlansMarkdown(md);
    expect(html.match(/<pre/g)).toHaveLength(1);
    expect(html).toContain("calendar:");
    expect(html).toContain("delivery_months: [February]");
    // The blank line must survive inside the block, not split it.
    expect(html).toContain("2026-02-02\n\ndelivery_months");
  });

  it("never wraps a fence in a paragraph", () => {
    // <pre> inside <p> is invalid; browsers close the paragraph early
    // and the surrounding flow breaks.
    const html = win.renderPlansMarkdown("```\nplain\n```");
    expect(html).not.toContain("<p><pre");
    expect(html.startsWith("<pre")).toBe(true);
  });

  it("escapes markup inside a fence instead of letting the DOM eat it", () => {
    const html = win.renderPlansMarkdown("```\n<not-a-tag> & <other>\n```");
    expect(html).toContain("&lt;not-a-tag&gt; &amp; &lt;other&gt;");
    expect(html).not.toContain("<not-a-tag>");
  });

  it("tags the language so a diagram renderer can find it later", () => {
    const html = win.renderPlansMarkdown("```mermaid\ngraph TD;\nA-->B;\n```");
    expect(html).toContain('class="lang-mermaid"');
    // Until a renderer is vendored the source itself is the fallback,
    // which is readable rather than blank.
    expect(html).toContain("graph TD;");
  });

  it("handles several fences in one body without crossing them over", () => {
    const html = win.renderPlansMarkdown("```yaml\nfirst: 1\n```\n\nMiddle.\n\n```yaml\nsecond: 2\n```");
    expect(html.match(/<pre/g)).toHaveLength(2);
    expect(html.indexOf("first: 1")).toBeLessThan(html.indexOf("Middle."));
    expect(html.indexOf("Middle.")).toBeLessThan(html.indexOf("second: 2"));
  });
});

describe("renderPlansMarkdown - behaviour the fence fix must not break", () => {
  it("still renders a bullet block as one <ul>", () => {
    const html = win.renderPlansMarkdown("- one\n- two");
    expect(html).toBe("<ul><li>one</li><li>two</li></ul>");
  });

  it("still renders an all-numbered block as an <ol>", () => {
    const html = win.renderPlansMarkdown("1. one\n2. two");
    expect(html).toBe("<ol><li>one</li><li>two</li></ol>");
  });

  it("still joins a wrapped paragraph onto one line", () => {
    const html = win.renderPlansMarkdown("a line that\nwraps in source");
    expect(html).toBe("<p>a line that wraps in source</p>");
  });

  it("still renders bold and inline code outside fences", () => {
    const html = win.renderPlansMarkdown("**bold** and `code`");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<code>code</code>");
  });
});
