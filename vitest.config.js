import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Each test file builds its own real jsdom Window via
    // tests-js/support/loadDashboard.js (not Vitest's built-in jsdom
    // environment) so it can load the actual committed template rather
    // than a blank document - the default "node" environment is correct
    // here, jsdom itself is a plain dependency, not a Vitest environment.
    environment: "node",
    include: ["tests-js/**/*.test.js"],
  },
});
