// Real-browser viewer tests (spec #271): headless Chromium + SwiftShader WebGL against Django.
// Local only, not wired into CI. Run: `npm run test:browser` (builds the viewer bundle first).
// Needs the Django dev setup (src/MiqaResearch/.env, Postgres, `uv`). See src/viewer/README.md.
import { defineConfig, devices } from "@playwright/test";

import { DJANGO_DIR, harnessEnv } from "./browser-tests/harness-env.ts";

const PORT = Number(process.env.VIEWER_HARNESS_PORT ?? 8278);
const BASE_URL = process.env.VIEWER_HARNESS_BASE_URL ?? `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./browser-tests",
  globalSetup: "./browser-tests/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-swiftshader",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
        },
      },
    },
  ],
  // Django on the harness database (see browser-tests/harness-env.ts). With
  // VIEWER_HARNESS_BASE_URL set, no server is started: point it at one using the same database.
  webServer: process.env.VIEWER_HARNESS_BASE_URL
    ? undefined
    : {
        // Create + migrate the harness database first (webServer starts before globalSetup).
        command: `uv run python manage.py viewer_harness_seed --prepare-db > /dev/null && uv run python manage.py runserver 127.0.0.1:${PORT} --noreload`,
        cwd: DJANGO_DIR,
        env: harnessEnv(),
        url: `${BASE_URL}/accounts/login/`,
        reuseExistingServer: false,
        timeout: 120_000,
      },
});
