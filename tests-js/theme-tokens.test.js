// Every colour the page asks for by name is one its theme defines
// (road-testing #20, post-build-review #121). A var(--name) the theme does
// not define falls back to its hard-coded default in BOTH themes - or to
// nothing - silently: `--red` once had no red in it at all, and the
// "awaiting a correction" border never followed dark mode. This reads the
// template's own text because there is no behaviour to drive: a missing
// token renders without an error.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const TEMPLATE = readFileSync(fileURLToPath(new URL(
  "../dashboard/qa-reporting-dashboard.template.html", import.meta.url)), "utf8");

describe("theme tokens", () => {
  it("every var(--name) the page uses is defined by the theme", () => {
    const defined = new Set([...TEMPLATE.matchAll(/(--[a-z][a-z0-9-]*)\s*:/g)].map(m => m[1]));
    const used = new Set([...TEMPLATE.matchAll(/var\(\s*(--[a-z][a-z0-9-]*)/g)].map(m => m[1]));
    expect(defined.size).toBeGreaterThan(10);
    expect(used.size).toBeGreaterThan(10);
    const undefinedTokens = [...used].filter(name => !defined.has(name)).sort();
    expect(undefinedTokens).toEqual([]);
  });
});
