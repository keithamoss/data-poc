/**
 * Verifies the front-end half of `requirements.yaml`'s `implemented_by:` field
 * (plans/tooling.md #18, Keith's call 2026-09-20).
 *
 * `qa_tools/common/validate_requirements.py` AST-verifies every `.py`
 * symbol and REQUIRES one - a bare Python path is rejected, because
 * `Path.exists()` stays green while the code inside a file is gutted or
 * renamed, which is exactly how `touches:` lines in `plans/*.md` rotted
 * while continuing to look authoritative.
 *
 * It cannot do the same for the dashboard template: there is no JS parser
 * in the Python toolchain, and this project's own validator docstring
 * rules out a regex for precisely this job ("never a regex/string match,
 * which could be fooled by a comment or a docstring mentioning the same
 * name"). So the Python side allows a `::` on a front-end file and simply
 * does not check it - and this file is what makes that honest rather than
 * a hole.
 *
 * The check here is stronger than the AST one it stands in for, not
 * weaker: `tests-js/support/loadDashboard.js` already loads the REAL
 * committed template into a real jsdom window with `runScripts:
 * "dangerously"`, so every top-level `function foo(){}` in its inline
 * script genuinely becomes `window.foo`. Asserting the symbol resolves
 * there is real execution, not a reading of the source - a name that only
 * appears in a comment cannot pass.
 *
 * Keith's own framing when scoping this: symbols for Python now, and
 * "for the HTML we'll probably end up with a separate TypeScript or
 * JavaScript file, and maybe we can take it up later". When that happens
 * this file keeps working unchanged - the symbols just move into a real
 * module the loader already evaluates.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { parse } from "yaml";
import { loadDashboard } from "./support/loadDashboard.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, "..");
const TEMPLATE_REL = "dashboard/qa-reporting-dashboard.template.html";

/** Every `implemented_by:` entry that names a symbol inside the template. */
function templateSymbols() {
  const doc = parse(readFileSync(path.join(REPO_ROOT, "requirements.yaml"), "utf-8"));
  const found = [];
  for (const req of doc.requirements ?? []) {
    for (const entry of req.implemented_by ?? []) {
      const [file, ...qualname] = entry.split("::");
      if (file === TEMPLATE_REL && qualname.length) {
        found.push({ id: req.id, entry, symbol: qualname.join("::") });
      }
    }
  }
  return found;
}

describe("requirements.yaml implemented_by: front-end symbols", () => {
  let page;
  afterEach(() => {
    page?.close();
    page = undefined;
  });

  it("names at least one real template symbol, so this test is not vacuous", () => {
    // A test that silently passes on an empty list would stop guarding the
    // moment someone rewrote an entry into a bare path - the same silent
    // failure mode this whole field exists to remove.
    expect(templateSymbols().length).toBeGreaterThan(0);
  });

  it("resolves every claimed symbol on the real, loaded template", () => {
    page = loadDashboard();
    const missing = templateSymbols().filter(
      ({ symbol }) => typeof page.window[symbol] !== "function",
    );
    expect(
      missing.map((m) => `${m.id}: ${m.entry}`),
      "requirements.yaml claims these template symbols, but they do not exist " +
        "on the loaded page - rename them in requirements.yaml, or restore them",
    ).toEqual([]);
  });
});
