// Seeds the harness database (Django `viewer_harness_seed`; the webServer command already
// created + migrated it) and hands the session cookie + UIDs to the tests via an env var.
import { execFileSync } from "node:child_process";

import { DJANGO_DIR, harnessEnv } from "./harness-env.ts";

export default function globalSetup(): void {
  const out = execFileSync("uv", ["run", "python", "manage.py", "viewer_harness_seed"], {
    cwd: DJANGO_DIR,
    env: { ...process.env, ...harnessEnv() },
    encoding: "utf8",
    stdio: ["ignore", "pipe", "inherit"],
  });
  // The seed JSON is the last stdout line.
  const json = out.trim().split("\n").pop()!;
  JSON.parse(json);
  process.env.VIEWER_HARNESS_SEED = json;
}
