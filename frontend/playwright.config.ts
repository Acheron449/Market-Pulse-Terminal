import { defineConfig } from "@playwright/test";

/**
 * End-to-end and accessibility suite (timeline Phase 5).
 *
 * One command, one origin, no mocks: `pnpm e2e` builds the SPA and Playwright starts the
 * real backend in replay mode, which serves that build from `frontend/dist`. Providers are
 * never contacted (`ENABLE_LIVE_DATA=false`), so every assertion runs against the recorded
 * fixture. A dedicated port keeps the suite from colliding with a running `pnpm dev`
 * (5173) or the default API port (8000).
 */
const PORT = 8010;
const baseURL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // The suite drives a single backend and asserts on shared cooldown state, so keep the
  // ordering and the process count fixed.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: false,
  timeout: 30_000,
  expect: { timeout: 8_000 },
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    // The UI honours this; keeps animation-driven states out of the screenshots.
    reducedMotion: "reduce",
  },
  webServer: {
    command: `cd ../backend && uv run uvicorn app.main:app --host 127.0.0.1 --port ${PORT} --log-level warning`,
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...(process.env as Record<string, string>),
      APP_ENV: "development",
      ENABLE_LIVE_DATA: "false",
      LOG_LEVEL: "WARNING",
    },
  },
});
