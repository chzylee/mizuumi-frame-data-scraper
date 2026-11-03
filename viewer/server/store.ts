/**
 * All file reads and writes. The viewer's only side effect is writing item
 * files under the data root; it never creates the data root itself (data/
 * comes only from the DynamoDB pull), never touches the scrape, and runs no
 * git or AWS operations.
 */
import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { mkdir, open, rename, rm } from "node:fs/promises";
import { dirname, join, relative, resolve, sep } from "node:path";
import type { SaveRequest, SaveResult, Snapshot, SourceFile, UnreadableFile } from "../shared/api";
import { SaveRefused } from "../shared/api";
import { dumps, isUnmapped, loads, parseCharMappings, pathFor, validateItem } from "../shared/dataset";
import { listJsonFiles, readUtf8, sha256 } from "../shared/files";
import { isObject, JsonParseError } from "../shared/pyjson";
import type { ViewerConfig } from "./config";

function isDir(path: string): boolean {
  return existsSync(path) && statSync(path).isDirectory();
}

function readRoot(root: string): { files: SourceFile[]; unreadable: UnreadableFile[] } {
  const files: SourceFile[] = [];
  const unreadable: UnreadableFile[] = [];
  for (const path of listJsonFiles(root)) {
    try {
      const { bytes, text } = readUtf8(join(root, path));
      files.push({ path, text, hash: sha256(bytes) });
    } catch (error) {
      unreadable.push({ path, error: error instanceof TypeError ? "not valid UTF-8" : String(error) });
    }
  }
  return { files, unreadable };
}

export function loadSnapshot(config: ViewerConfig): Snapshot {
  const charMappings = parseCharMappings(readFileSync(config.mappingsFile, "utf-8"));
  let data: Snapshot["data"] = { status: "missing" };
  if (isDir(config.dataDir)) {
    const root = readRoot(config.dataDir);
    data = root.files.length || root.unreadable.length ? { status: "ok", ...root } : { status: "empty" };
  }
  const scrapedRoot = isDir(config.scrapedDir) ? readRoot(config.scrapedDir) : null;
  return {
    dataRoot: config.dataDir,
    scrapedRoot: config.scrapedDir,
    data,
    scraped: scrapedRoot && (scrapedRoot.files.length || scrapedRoot.unreadable.length) ? scrapedRoot : null,
    charMappings,
  };
}

const sleep = (ms: number) => new Promise((done) => setTimeout(done, ms));

export interface WriteOps {
  rename: (from: string, to: string) => Promise<void>;
}

/**
 * Write bytes atomically: a temp file in the same directory, flushed, then
 * renamed over the target. A failure at any point leaves the old file intact
 * and removes the temp file. Windows can briefly refuse a rename while another
 * process (indexer, antivirus) holds the target, so EPERM/EBUSY/EACCES retry.
 */
export async function atomicWrite(path: string, bytes: Uint8Array, ops: WriteOps = { rename }): Promise<void> {
  const tmp = join(dirname(path), `.${randomBytes(6).toString("hex")}.viewer.tmp`);
  try {
    const handle = await open(tmp, "wx");
    try {
      await handle.writeFile(bytes);
      await handle.sync();
    } finally {
      await handle.close();
    }
    for (let attempt = 0; ; attempt++) {
      try {
        await ops.rename(tmp, path);
        return;
      } catch (error) {
        const code = (error as NodeJS.ErrnoException).code;
        if (attempt >= 4 || !["EPERM", "EBUSY", "EACCES"].includes(code ?? "")) throw error;
        await sleep(50 * (attempt + 1));
      }
    }
  } catch (error) {
    await rm(tmp, { force: true });
    throw error;
  }
}

interface Planned {
  path: string;
  absolute: string;
  bytes: Buffer;
  existed: boolean;
  unchanged: boolean;
}

/**
 * Validate every file first; write nothing unless all pass. Each file must
 * parse, pass dataset.validate_item, map (via pathFor) to the path it claims,
 * and still match the version the viewer loaded (or, for a new item, not exist).
 */
export function planSave(config: ViewerConfig, request: SaveRequest): { planned: Planned[]; warnings: string[] } {
  if (!isDir(config.dataDir)) {
    throw new SaveRefused(`No data directory at ${config.dataDir}. Pull from DynamoDB first; the viewer never creates it.`, []);
  }
  if (!request || !Array.isArray(request.files) || request.files.length === 0) {
    throw new SaveRefused("Nothing to save.", []);
  }
  const mappings = parseCharMappings(readFileSync(config.mappingsFile, "utf-8"));
  const problems: string[] = [];
  const warnings: string[] = [];
  const planned: Planned[] = [];
  const seen = new Set<string>();
  for (const [index, file] of request.files.entries()) {
    const label = typeof file?.path === "string" ? file.path : `new item #${index + 1}`;
    if (typeof file?.text !== "string") {
      problems.push(`${label}: no item text`);
      continue;
    }
    let item;
    try {
      item = loads(file.text);
    } catch (error) {
      problems.push(`${label}: not valid JSON (${error instanceof JsonParseError ? error.message : String(error)})`);
      continue;
    }
    const errors = validateItem(label, item);
    if (errors.length || !isObject(item)) {
      problems.push(...errors);
      continue;
    }
    let target: string;
    let text: string;
    try {
      target = pathFor({ character_name: item.character_name as string, moon: item.moon as string }, mappings);
      text = dumps(item);
    } catch (error) {
      problems.push(`${label}: ${(error as Error).message}`);
      continue;
    }
    if (file.path !== null && file.path !== target) {
      problems.push(`${label}: its key belongs at ${target}`);
      continue;
    }
    if (seen.has(target)) {
      problems.push(`${target}: appears twice in one save`);
      continue;
    }
    seen.add(target);
    const absolute = resolve(config.dataDir, ...target.split("/"));
    const rel = relative(config.dataDir, absolute);
    if (rel.startsWith("..") || rel.split(sep).includes("..")) {
      problems.push(`${target}: resolves outside the data directory`);
      continue;
    }
    const existed = existsSync(absolute);
    let current: Buffer | null = null;
    if (existed) current = readFileSync(absolute);
    if (file.baseHash === null && existed) {
      problems.push(`${target}: already exists on disk (created since the viewer loaded?). Reload.`);
      continue;
    }
    if (file.baseHash !== null && (!current || sha256(current) !== file.baseHash)) {
      problems.push(`${target}: changed on disk since the viewer loaded it. Reload and redo the edit.`);
      continue;
    }
    if (isUnmapped(target)) {
      warnings.push(`${target}: no short name in CHAR_MAPPINGS or an unknown moon, so it lives under _unmapped/`);
    }
    const bytes = Buffer.from(text, "utf-8");
    planned.push({ path: target, absolute, bytes, existed, unchanged: current !== null && current.equals(bytes) });
  }
  if (problems.length) throw new SaveRefused(`Refused: ${problems.length} problem(s). Nothing was written.`, problems);
  return { planned, warnings };
}

let queue: Promise<unknown> = Promise.resolve();

/** Save, one request at a time. */
export function saveFiles(config: ViewerConfig, request: SaveRequest, ops?: WriteOps): Promise<SaveResult> {
  const run = queue.then(async () => {
    const { planned, warnings } = planSave(config, request);
    const written: SaveResult["written"] = [];
    for (const file of planned) {
      if (file.unchanged) {
        written.push({ path: file.path, status: "unchanged" });
        continue;
      }
      try {
        await mkdir(dirname(file.absolute), { recursive: true }); // only below the existing data root
        await atomicWrite(file.absolute, file.bytes, ops);
      } catch (error) {
        // Each file is atomic; the batch is not. Say exactly what landed.
        const done = written.filter((w) => w.status !== "unchanged").map((w) => `written: ${w.path}`);
        throw new SaveRefused(
          `Writing ${file.path} failed (${(error as Error).message}); it is unchanged. ` +
            `${done.length} file(s) were written before that. Reload to see the current state.`,
          done,
        );
      }
      written.push({ path: file.path, status: file.existed ? "updated" : "created" });
    }
    return { written, warnings };
  });
  queue = run.catch(() => undefined);
  return run;
}
