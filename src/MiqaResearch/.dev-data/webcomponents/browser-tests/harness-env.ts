// Environment for the Django process(es) the harness runs: harness settings (DEBUG, demo keys),
// and an isolated database and media dir so the harness never migrates or writes into your dev database.
// Database: VIEWER_HARNESS_DATABASE_URL, else MIRES_DATABASE_URL from src/MiqaResearch/.env with
// `_viewer_harness` appended to the database name (created + migrated by global-setup).
import { readFileSync } from "node:fs";

export const DJANGO_DIR = new URL("../../../", import.meta.url).pathname;

function devDatabaseUrl(): string {
  if (process.env.MIRES_DATABASE_URL) return process.env.MIRES_DATABASE_URL;
  const line = readFileSync(`${DJANGO_DIR}.env`, "utf8")
    .split("\n")
    .find((l) => l.startsWith("MIRES_DATABASE_URL="));
  if (!line) throw new Error("MIRES_DATABASE_URL not found in src/MiqaResearch/.env; set VIEWER_HARNESS_DATABASE_URL");
  return line.slice("MIRES_DATABASE_URL=".length).trim().replace(/^["']|["']$/g, "");
}

function harnessDatabaseUrl(): string {
  if (process.env.VIEWER_HARNESS_DATABASE_URL) return process.env.VIEWER_HARNESS_DATABASE_URL;
  const url = new URL(devDatabaseUrl());
  url.pathname = `${url.pathname.replace(/\/$/, "")}_viewer_harness`;
  return url.toString();
}

export function harnessEnv(): Record<string, string> {
  return {
    // DEBUG on + demo encryption keys (no Vault needed); see that module's docstring.
    DJANGO_SETTINGS_MODULE: "MiqaResearch.settings_viewer_harness",
    MIRES_USE_VAULT: "False",
    MIRES_DEBUG: "True",
    MIRES_DATABASE_URL: harnessDatabaseUrl(),
    MIRES_DICOM_STORAGE_BACKEND: "local",
    MIRES_MEDIA_ROOT: `${DJANGO_DIR}.dev-data/viewer-harness-media`,
  };
}
