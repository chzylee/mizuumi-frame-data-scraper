/** Node-only helpers for reading data/-style directories (server + tests). */
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { compareCodePoints } from "./pyjson";

/** Every .json file under `directory`, as sorted "/"-separated relative paths (dataset.list_files). */
export function listJsonFiles(directory: string): string[] {
  if (!existsSync(directory) || !statSync(directory).isDirectory()) return [];
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile() && entry.name.endsWith(".json")) found.push(relative(directory, full).split(sep).join("/"));
    }
  };
  walk(directory);
  return found.sort(compareCodePoints); // Python's sorted(): code point order
}

const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }); // keep a BOM, as Python does

/** Read a file as Python's open(encoding="utf-8", newline="") would: strict UTF-8, no newline rewriting. */
export function readUtf8(path: string): { bytes: Buffer; text: string } {
  const bytes = readFileSync(path);
  return { bytes, text: decoder.decode(bytes) };
}

export function sha256(bytes: Uint8Array | string): string {
  return createHash("sha256").update(bytes).digest("hex");
}
