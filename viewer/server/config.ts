/**
 * Where the viewer reads and writes. Repo paths are anchored at this file, so
 * the cwd never matters. The data and scraped roots can be pointed elsewhere
 * (tests, manual checks against fixture copies):
 *
 *   VIEWER_DATA_DIR     default <repo>/data
 *   VIEWER_SCRAPED_DIR  default <repo>/local-data/scraped
 *   VIEWER_API_PORT     default 5175 (Express, 127.0.0.1 only)
 *
 * Relative env paths resolve against the cwd of the process that sets them.
 */
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const MAPPINGS_FILE = join(REPO_ROOT, "src", "data", "mizuumi.py");
export const DEFAULT_API_PORT = 5175;
export const HOST = "127.0.0.1";

export interface ViewerConfig {
  dataDir: string;
  scrapedDir: string;
  mappingsFile: string;
  port: number;
}

export function configFromEnv(env: NodeJS.ProcessEnv = process.env): ViewerConfig {
  const port = Number(env.VIEWER_API_PORT ?? DEFAULT_API_PORT);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) throw new Error(`bad VIEWER_API_PORT: ${env.VIEWER_API_PORT}`);
  return {
    dataDir: env.VIEWER_DATA_DIR ? resolve(env.VIEWER_DATA_DIR) : join(REPO_ROOT, "data"),
    scrapedDir: env.VIEWER_SCRAPED_DIR ? resolve(env.VIEWER_SCRAPED_DIR) : join(REPO_ROOT, "local-data", "scraped"),
    mappingsFile: MAPPINGS_FILE,
    port,
  };
}
