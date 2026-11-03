/**
 * TypeScript port of the parts of `src/dataset.py` the viewer needs: the
 * canonical serializer, `path_for`, move identity and `validate_item`.
 *
 * These must agree with Python byte for byte; `tests/parity.test.ts` runs both
 * over real and fixture files. Change them only together with dataset.py.
 */
import {
  compareCodePoints,
  encodeJson,
  has,
  isObject,
  loads,
  pyRepr,
  type Json,
  type JsonObject,
  type KeyOrder,
} from "./pyjson";

export const PARTITION_KEY = "character_name";
export const SORT_KEY = "moon";
export const HASH_ATTR = "content_hash";

const TOP_LEVEL_ORDER = [PARTITION_KEY, SORT_KEY, "moves"] as const;
/** Canonical move key order (dataset._MOVE_ORDER). Other keys follow, sorted. */
export const MOVE_ORDER = [
  "input", "image", "first_active", "active", "recovery", "frame_adv",
  "proration", "guard", "invuln", "alts",
] as const;
/** dataset.REQUIRED_MOVE_KEYS: `guard` is deliberately absent. */
export const REQUIRED_MOVE_KEYS = [
  "input", "image", "first_active", "active", "recovery", "frame_adv",
  "proration", "invuln", "alts",
] as const;

// --- canonical serialization ----------------------------------------------------

/** Known keys first in `preferred` order, the rest sorted by code point (dataset._ordered). */
export function orderedKeys(obj: JsonObject, preferred: readonly string[] = []): string[] {
  const known = preferred.filter((key) => has(obj, key));
  const rest = Object.keys(obj).filter((key) => !preferred.includes(key)).sort(compareCodePoints);
  return [...known, ...rest];
}

/** dataset._canonical + dumps: the item in TOP_LEVEL_ORDER, each move in MOVE_ORDER, all else sorted. */
const canonicalOrder: KeyOrder = (obj, path) => {
  if (path.length === 0) return orderedKeys(obj, TOP_LEVEL_ORDER);
  if (path.length === 2 && path[0] === "moves" && typeof path[1] === "number") return orderedKeys(obj, MOVE_ORDER);
  return orderedKeys(obj);
};

/** dataset.dumps: the one serialization of an item that data/ accepts. */
export function dumps(item: Json): string {
  if (!isObject(item)) throw new TypeError("an item must be a JSON object");
  return encodeJson(item, canonicalOrder) + "\n";
}

export { loads };

// --- paths --------------------------------------------------------------------------

/** CHAR_MAPPINGS as ordered (alias, wiki name) pairs. Order matters: first alias wins. */
export type CharMappings = ReadonlyArray<readonly [string, string]>;

const MOON_FILE: Record<string, string> = { Crescent_Moon: "crescent", Half_Moon: "half", Full_Moon: "full" };
export const MOON_ORDER = Object.keys(MOON_FILE);
export const UNMAPPED_DIR = "_unmapped";
const ILLEGAL = new Set(['<', '>', ':', '"', '/', '\\', '|', '?', '*']);

/**
 * Read CHAR_MAPPINGS out of `src/data/mizuumi.py`, so the Python file stays the
 * single source. Only the plain `"alias": "Wiki_Name",` form it uses today is
 * accepted; anything else fails loudly rather than mapping paths wrongly.
 */
export function parseCharMappings(pythonSource: string): CharMappings {
  const start = pythonSource.search(/^CHAR_MAPPINGS\s*=\s*\{/m);
  if (start < 0) throw new Error("CHAR_MAPPINGS not found in mizuumi.py");
  const open = pythonSource.indexOf("{", start);
  const close = pythonSource.indexOf("}", open);
  if (close < 0) throw new Error("CHAR_MAPPINGS is not closed");
  const pairs = new Map<string, string>();
  const entry = /^\s*(?:"([^"\\]*)"|'([^'\\]*)')\s*:\s*(?:"([^"\\]*)"|'([^'\\]*)')\s*,?\s*(?:#.*)?$/;
  for (const line of pythonSource.slice(open + 1, close).split(/\r?\n/)) {
    if (/^\s*(#.*)?$/.test(line)) continue;
    const match = entry.exec(line);
    if (!match) throw new Error(`unsupported CHAR_MAPPINGS line (update viewer/shared/dataset.ts): ${line.trim()}`);
    // A repeated key in a dict literal keeps its first position and last value.
    pairs.set(match[1] ?? match[2]!, match[3] ?? match[4]!);
  }
  return [...pairs.entries()];
}

function encodeComponent(text: string): string {
  if (text === "." || text === "..") throw new RangeError(`key value '${text}' cannot be used as a path component`);
  let out = "";
  for (const ch of text) {
    out += ILLEGAL.has(ch) ? `%${ch.codePointAt(0)!.toString(16).toUpperCase().padStart(2, "0")}` : ch;
  }
  return out;
}

export function shortName(characterName: string, mappings: CharMappings): string | null {
  for (const [alias, wikiName] of mappings) if (wikiName === characterName) return alias;
  return null;
}

export interface ItemKey {
  character_name: string;
  moon: string;
}

/** dataset.path_for: where an item lives, relative to data/. */
export function pathFor(key: ItemKey, mappings: CharMappings): string {
  const { character_name: characterName, moon } = key;
  if (typeof characterName !== "string" || typeof moon !== "string") throw new TypeError("key values must be strings");
  const short = shortName(characterName, mappings);
  if (short !== null && has(MOON_FILE, moon)) return `${short}/${MOON_FILE[moon]}_${short}.json`;
  return `${UNMAPPED_DIR}/${encodeComponent(characterName)}/${encodeComponent(moon)}.json`;
}

export function isUnmapped(path: string): boolean {
  return path.startsWith(UNMAPPED_DIR + "/");
}

// --- move identity -----------------------------------------------------------------

/** A move's identity: (input, occurrence), as a string usable as a Map key. */
export type Identity = string;

/** The input part of a move's identity, as a string (move.get("input")). */
export function inputKey(move: Json): string {
  const input = isObject(move) && has(move, "input") ? move.input! : null; // move.get("input")
  // Non-string inputs are invalid data; they still get a stable identity.
  return typeof input === "string" ? `s:${input}` : `j:${encodeJson(input)}`;
}

export function identityOf(input: Json | undefined, occurrence: number): Identity {
  return `${inputKey({ input: input ?? null })}#${occurrence}`;
}

/** dataset.move_identities. */
export function moveIdentities(moves: readonly Json[]): Identity[] {
  const seen = new Map<string, number>();
  return moves.map((move) => {
    const key = inputKey(move);
    const occurrence = seen.get(key) ?? 0;
    seen.set(key, occurrence + 1);
    return `${key}#${occurrence}`;
  });
}

// --- validation ------------------------------------------------------------------

/** dataset.validate_item: problems with one parsed item, same messages. */
export function validateItem(name: string, item: Json): string[] {
  if (!isObject(item)) return [`${name}: top level must be a JSON object`];
  const errors: string[] = [];
  for (const key of [PARTITION_KEY, SORT_KEY]) {
    const value = has(item, key) ? item[key] : undefined;
    if (typeof value !== "string" || value === "") errors.push(`${name}: '${key}' must be a non-empty string`);
  }
  if (has(item, HASH_ATTR)) errors.push(`${name}: '${HASH_ATTR}' is table bookkeeping and must not be in data/`);
  let moves = has(item, "moves") ? item.moves : undefined;
  if (!Array.isArray(moves)) {
    errors.push(`${name}: 'moves' must be a list`);
    moves = [];
  }
  moves.forEach((move, index) => {
    const where = `${name}: moves[${index}]`;
    if (!isObject(move)) {
      errors.push(`${where} must be an object`);
      return;
    }
    const input = has(move, "input") ? move.input : undefined;
    const missing = REQUIRED_MOVE_KEYS.filter((key) => !has(move, key));
    if (missing.length) errors.push(`${where} (${pyRepr(input)}) is missing ${missing.join(", ")}`);
    if (has(move, "input") && typeof move.input !== "string") errors.push(`${where}: 'input' must be a string`);
    if (has(move, "alts")) {
      const alts = move.alts;
      if (!(Array.isArray(alts) && alts.every((alt) => typeof alt === "string"))) {
        errors.push(`${where} (${pyRepr(input)}): 'alts' must be a list of strings`);
      }
    }
  });
  return errors;
}
