// Status pills clear WCAG AA (4.5:1) in both themes - Keith, 2026-10-06
// (post-build-review #121 D5): in dark mode Red read 2.61:1 and Green 4.43:1
// against their own pill backgrounds. Read from the template's real tokens,
// so a later colour change is held to the same bar.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { TEMPLATE_PATH } from "./support/loadDashboard.js";

const SOURCE = readFileSync(TEMPLATE_PATH, "utf-8");

function tokens(block){
  const out = {};
  for(const m of block.matchAll(/--([a-z-]+):\s*(#[0-9A-Fa-f]{6})/g)) out[m[1]] = m[2];
  return out;
}
function luminance(hex){
  const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function contrast(a, b){
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const LIGHT_AT = SOURCE.indexOf("\n:root{");
const LIGHT = tokens(SOURCE.slice(LIGHT_AT, SOURCE.indexOf("\n@media (prefers-color-scheme: dark)", LIGHT_AT)));
const DARK = tokens(SOURCE.slice(SOURCE.indexOf("\n:root[data-theme=\"dark\"]{")));
const PAIRS = [["good", "good-soft"], ["bad", "bad-soft"]];

describe("status pill contrast", () => {
  for(const [name, theme] of [["light", LIGHT], ["dark", DARK]]){
    for(const [fg, bg] of PAIRS){
      it(`${name}: --${fg} on --${bg} is at least 4.5:1`, () => {
        expect(theme[fg] && theme[bg]).toBeTruthy();
        expect(contrast(theme[fg], theme[bg])).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});
