import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/browser",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4179",
    browserName: "chromium",
    serviceWorkers: "block",
    trace: "off",
  },
  webServer: {
    command: "uv run python tests/browser/fixture_server.py",
    url: "http://127.0.0.1:4179/v1/system/health/live",
    reuseExistingServer: false,
    timeout: 10_000,
  },
});
