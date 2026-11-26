// REQ-DASH-407 - the page says, in its footer and in the as-of panel, that a
// synthetic asset's supplies were generated up to and including a date (R3:
// say the date, do not warn), from BUILD_PROVENANCE, which the build reads
// from the anchor recorded in the qa schema. Mock data, the real template.
import { afterEach, describe, expect, it } from "vitest";
import { loadDashboard, TEMPLATE_PATH } from "./support/loadDashboard.js";
import { readFileSync } from "node:fs";

let dashboard;

afterEach(() => {
  dashboard?.close();
  dashboard = undefined;
});

function withProvenance(provenance) {
  const source = readFileSync(TEMPLATE_PATH, "utf-8")
    .replace("const BUILD_PROVENANCE = null;",
             `const BUILD_PROVENANCE = ${JSON.stringify(provenance)};`)
    .replace("const BUILT_AT = null;", `const BUILT_AT = "2026-11-16T04:00:00+08:00";`);
  return loadDashboard({ html: source });
}

const ENV = { id: "sandbox", label: "Claude Code sandbox", publishes: false };
const lines = (d) => ({
  footer: d.window.document.getElementById("footer-generated-up-to"),
  panel: d.window.document.getElementById("in-place-on-generated-up-to"),
});

describe("REQ-DASH-407 - the date synthetic supplies were generated up to", () => {
  it("states it in the footer and under the as-of picker, as a plain date", () => {
    dashboard = withProvenance({ environment: ENV, commit: null, synthetic: true,
                                 generated_up_to: "2026-09-25" });
    const { footer, panel } = lines(dashboard);
    expect(footer.hidden).toBe(false);
    expect(footer.textContent).toBe(
      "The synthetic supplies on this page were generated up to and including " +
      "Friday, 25 September 2026; a period after that date has no supply.");
    expect(panel.hidden).toBe(false);
    expect(panel.textContent).toBe("Synthetic supplies run up to and including Friday, 25 September 2026");
    // Criterion 1: after the synthetic wording, before the codename line.
    const html = footer.parentElement.innerHTML;
    expect(html.indexOf("generated synthetic supplies")).toBeLessThan(html.indexOf("footer-generated-up-to"));
    expect(html.indexOf("footer-generated-up-to")).toBeLessThan(html.indexOf("codename"));
  });

  it("says the date was not recorded rather than guessing one", () => {
    dashboard = withProvenance({ environment: ENV, commit: null, synthetic: true,
                                 generated_up_to: null });
    const { footer, panel } = lines(dashboard);
    for (const el of [footer, panel]) {
      expect(el.hidden).toBe(false);
      expect(el.textContent).toBe("The date this synthetic data was generated up to was not recorded.");
    }
  });

  it("shows neither line on a real asset", () => {
    dashboard = withProvenance({ environment: ENV, commit: null, synthetic: false,
                                 generated_up_to: null });
    const { footer, panel } = lines(dashboard);
    expect(footer.hidden).toBe(true);
    expect(panel.hidden).toBe(true);
    expect(footer.textContent).toBe("");
  });

  it("leaves the as-of default and the picker's range untouched by an anchor weeks old", () => {
    // Criterion 6: the anchor is not an input to either.
    const before = withProvenance({ environment: ENV, commit: null, synthetic: false,
                                    generated_up_to: null });
    const plain = { def: before.window.DEFAULT_IN_PLACE_ON ?? before.window.defaultInPlaceOn(),
                    range: JSON.stringify(before.window.coveredDateRange()) };
    before.close();
    dashboard = withProvenance({ environment: ENV, commit: null, synthetic: true,
                                 generated_up_to: "2026-09-25" });
    expect(dashboard.window.defaultInPlaceOn()).toBe(plain.def);
    expect(JSON.stringify(dashboard.window.coveredDateRange())).toBe(plain.range);
  });
});
