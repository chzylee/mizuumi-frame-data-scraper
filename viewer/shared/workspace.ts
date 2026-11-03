/**
 * The viewer's model: data/ as the base, the scrape merged in for comparison,
 * and every pending change. Pure functions, no DOM and no I/O, so the display
 * and the tests share them.
 *
 * Merge rule (the same as fill_from_scrape): items match by key
 * (character_name + moon), moves by identity (input + occurrence of that input).
 * Move pairing is computed once, at load, on data/ as loaded; edits (even to
 * `input`) never re-pair moves. A data/ file that fails to load is reported in
 * `dataErrors` and nothing from the scrape is ever staged at its path.
 *
 * What the scrape adds is staged automatically (blue) and written only on save:
 *   - an item only in the scrape becomes a new item, at pathFor(key);
 *   - a move only in the scrape is inserted (see insertion rule below);
 *   - a field only in the scrape is added to the matched data move.
 * `image` is never compared, colored, or copied onto an existing move.
 * Anything only in data/ is left alone and uncolored.
 *
 * Insertion rule for new moves: walk the scrape in order; a new move goes right
 * after the data move matched by the scrape move before it (or after the new
 * move inserted just before it, or at the top when nothing precedes it) -- but
 * never before a move with the same input, since that would renumber the
 * occurrences and so change the identity of existing moves.
 */
import type { Snapshot } from "./api";
import {
  dumps,
  inputKey,
  loads,
  MOON_ORDER,
  MOVE_ORDER,
  moveIdentities,
  orderedKeys,
  pathFor,
  shortName,
  type CharMappings,
  type ItemKey,
} from "./dataset";
import { encodeJson, has, isObject, PyNumber, setKey, valueKey, type Json, type JsonObject } from "./pyjson";

export type Status = "none" | "green" | "blue" | "red";
const RANK: Record<Status, number> = { none: 0, green: 1, blue: 2, red: 3 };

/** Children roll up with precedence red > blue > green (> none). */
export function rollup(statuses: Iterable<Status>): Status {
  let best: Status = "none";
  for (const status of statuses) if (RANK[status] > RANK[best]) best = status;
  return best;
}

export interface MoveState {
  /** Stable across edits (an edit to `input` changes identity, not uid). */
  uid: string;
  /** Only in the scrape: staged for insertion. */
  isNew: boolean;
  /** Index in the data/ item's moves; null for a new move. */
  dataIndex: number | null;
  fields: JsonObject;
  /** Fields copied in from the scrape onto this data move (staged, blue). */
  addedFields: readonly string[];
  /**
   * Index of the scraped move this move is compared with, fixed at load by
   * (input, occurrence) on data/ as loaded; null when it has none. Edits never
   * change it, so renaming one move's input never re-pairs the others.
   */
  scrapedIndex: number | null;
}

export interface ItemState {
  id: string;
  key: ItemKey;
  /** Existing file path, or pathFor(key) for a new item. */
  path: string;
  isNew: boolean;
  baseHash: string | null;
  /** The item as on disk; null for a new item. */
  base: JsonObject | null;
  /** The scraped item, for comparison; null when there is none. */
  scraped: JsonObject | null;
  moves: MoveState[];
}

/** A data/ file the viewer could not load. It is not shown, compared or saved. */
export interface DataFileError {
  path: string;
  error: string;
}

export interface Workspace {
  items: ItemState[];
  scrapedAvailable: boolean;
  /** data/ files that could not be loaded; they must be fixed or restored by hand. */
  dataErrors: DataFileError[];
  /** Other things that could not be loaded or compared (scrape side), as lines. */
  problems: string[];
  charMappings: CharMappings;
}

export function cloneJson<T extends Json>(value: T): T {
  if (Array.isArray(value)) return value.map(cloneJson) as T;
  if (!isObject(value)) return value; // strings, literals, PyNumber (immutable)
  const out: JsonObject = {};
  for (const key of Object.keys(value)) setKey(out, key, cloneJson(value[key]!));
  return out as T;
}

export function itemId(key: ItemKey): string {
  return JSON.stringify([key.character_name, key.moon]);
}

interface Parsed {
  path: string;
  hash: string;
  item: JsonObject;
  key: ItemKey;
  moves: JsonObject[];
}

/** Parse a root's files into items the viewer can show; the rest are reported as failed. */
function parseRoot(label: string, files: { path: string; text: string; hash: string }[], failed: DataFileError[]) {
  const byId = new Map<string, Parsed>();
  for (const file of files) {
    const fail = (error: string) => failed.push({ path: file.path, error });
    let item: Json;
    try {
      item = loads(file.text);
    } catch (error) {
      fail(`not valid JSON (${(error as Error).message})`);
      continue;
    }
    if (!isObject(item) || typeof item.character_name !== "string" || typeof item.moon !== "string") {
      fail("no string character_name and moon");
      continue;
    }
    const moves = item.moves;
    if (!Array.isArray(moves) || !moves.every(isObject)) {
      fail("'moves' is not a list of objects");
      continue;
    }
    const key = { character_name: item.character_name, moon: item.moon };
    const id = itemId(key);
    const earlier = byId.get(id);
    if (earlier) {
      fail(`duplicate key ${id}, also in ${label}/${earlier.path}`);
      continue;
    }
    byId.set(id, { path: file.path, hash: file.hash, item, key, moves: moves as JsonObject[] });
  }
  return byId;
}

function mergeMoves(id: string, dataMoves: JsonObject[], scrapedMoves: JsonObject[] | null): MoveState[] {
  const merged: MoveState[] = dataMoves.map((move, index) => ({
    uid: `${id}|d${index}`,
    isNew: false,
    dataIndex: index,
    fields: cloneJson(move),
    addedFields: [],
    scrapedIndex: null,
  }));
  if (!scrapedMoves) return merged;

  const uidByIdentity = new Map(moveIdentities(dataMoves).map((identity, index) => [identity, merged[index]!.uid]));
  const scrapedIds = moveIdentities(scrapedMoves);
  let cursor = 0;
  scrapedMoves.forEach((scrapedMove, k) => {
    const matchedUid = uidByIdentity.get(scrapedIds[k]!);
    if (matchedUid !== undefined) {
      const at = merged.findIndex((move) => move.uid === matchedUid);
      const move = merged[at]!;
      const added = Object.keys(scrapedMove).filter((field) => field !== "image" && !has(move.fields, field));
      const fields = cloneJson(move.fields);
      for (const field of added) setKey(fields, field, cloneJson(scrapedMove[field]!));
      merged[at] = { ...move, fields, addedFields: added, scrapedIndex: k };
      cursor = at + 1;
      return;
    }
    const input = inputKey(scrapedMove);
    let lastSameInput = -1;
    merged.forEach((move, index) => {
      if (inputKey(move.fields) === input) lastSameInput = index;
    });
    const at = Math.max(cursor, lastSameInput + 1);
    merged.splice(at, 0, newMove(id, scrapedMove, k));
    cursor = at + 1;
  });
  return merged;
}

function newMove(id: string, scrapedMove: JsonObject, k: number): MoveState {
  return { uid: `${id}|s${k}`, isNew: true, dataIndex: null, fields: cloneJson(scrapedMove), addedFields: [], scrapedIndex: k };
}

export function buildWorkspace(snapshot: Snapshot): Workspace {
  const problems: string[] = [];
  const dataErrors: DataFileError[] = [];
  const mappings = snapshot.charMappings;
  if (snapshot.data.status !== "ok") {
    return { items: [], scrapedAvailable: snapshot.scraped !== null, dataErrors, problems, charMappings: mappings };
  }
  for (const file of snapshot.data.unreadable) dataErrors.push({ path: file.path, error: file.error });
  const data = parseRoot("data", snapshot.data.files, dataErrors);
  const scrapedErrors: DataFileError[] = [...(snapshot.scraped?.unreadable ?? [])];
  const scraped = snapshot.scraped ? parseRoot("scraped", snapshot.scraped.files, scrapedErrors) : new Map<string, Parsed>();
  for (const failed of scrapedErrors) problems.push(`scraped/${failed.path}: ${failed.error}; not compared`);
  // Every data/ path on disk, loaded or not: a new item must never land on one.
  const onDisk = new Set([...snapshot.data.files.map((f) => f.path), ...snapshot.data.unreadable.map((f) => f.path)]);
  const failedPaths = new Set(dataErrors.map((f) => f.path));

  const items: ItemState[] = [];
  for (const [id, entry] of data) {
    const match = scraped.get(id) ?? null;
    items.push({
      id,
      key: entry.key,
      path: entry.path,
      isNew: false,
      baseHash: entry.hash,
      base: entry.item,
      scraped: match?.item ?? null,
      moves: mergeMoves(id, entry.moves, match?.moves ?? null),
    });
  }
  for (const [id, entry] of scraped) {
    if (data.has(id)) continue;
    let path: string;
    try {
      path = pathFor(entry.key, mappings);
    } catch (error) {
      problems.push(`scraped/${entry.path}: no valid data/ path for ${id} (${(error as Error).message}); not added`);
      continue;
    }
    if (onDisk.has(path)) {
      // Typically the data/ file failed to load (a merge conflict, say). Staging the
      // scraped copy as "new" would collide with it and block every save.
      problems.push(
        failedPaths.has(path)
          ? `scraped/${entry.path}: not compared or added, because data/${path} could not be loaded; fix or restore it`
          : `scraped/${entry.path}: not added, because data/${path} exists but holds a different key`,
      );
      continue;
    }
    items.push({
      id,
      key: entry.key,
      path,
      isNew: true,
      baseHash: null,
      base: null,
      scraped: entry.item,
      moves: entry.moves.map((move, k) => newMove(id, move, k)),
    });
  }
  const scrapedAvailable = snapshot.scraped !== null && snapshot.scraped.files.length > 0;
  return { items, scrapedAvailable, dataErrors, problems, charMappings: mappings };
}

// --- diff status -------------------------------------------------------------------

export interface MoveStatus {
  status: Status;
  fields: Record<string, Status>;
  /** The matched scraped move (for showing scraped values); null when none. */
  scraped: JsonObject | null;
}

export interface ItemStatus {
  status: Status;
  moves: Map<string, MoveStatus>;
}

/**
 * Diff status of every move and field. Each move is compared with the scraped
 * move it was paired with at load (MoveState.scrapedIndex), so an edit, even to
 * `input`, changes only the edited move's colors.
 */
export function itemStatus(item: ItemState): ItemStatus {
  const scrapedMoves = (item.scraped?.moves ?? []) as JsonObject[];
  const moves = new Map<string, MoveStatus>();
  item.moves.forEach((move) => {
    const paired = move.isNew || move.scrapedIndex === null ? undefined : scrapedMoves[move.scrapedIndex];
    const scraped = paired && isObject(paired) ? paired : null;
    const fields: Record<string, Status> = {};
    for (const field of Object.keys(move.fields)) {
      if (field === "image") fields[field] = "none";
      else if (move.isNew || move.addedFields.includes(field)) fields[field] = "blue";
      else if (!scraped || !has(scraped, field)) fields[field] = "none";
      else fields[field] = valueKey(move.fields[field]) === valueKey(scraped[field]) ? "green" : "red";
    }
    moves.set(move.uid, { status: move.isNew ? "blue" : rollup(Object.values(fields)), fields, scraped });
  });
  return { status: item.isNew ? "blue" : rollup([...moves.values()].map((m) => m.status)), moves };
}

// --- navigation ----------------------------------------------------------------------

export interface CharacterGroup {
  name: string;
  short: string | null;
  label: string;
  items: ItemState[];
}

/** "Hisui_%26_Kohaku" -> "Hisui & Kohaku". Display only. */
export function displayName(characterName: string): string {
  return characterName.replace(/%26/g, "&").replace(/_/g, " ");
}

export function moonLabel(moon: string): string {
  return moon.replace(/_/g, " ");
}

export function groupCharacters(ws: Workspace): CharacterGroup[] {
  const groups = new Map<string, CharacterGroup>();
  for (const item of ws.items) {
    const name = item.key.character_name;
    let group = groups.get(name);
    if (!group) {
      group = { name, short: shortName(name, ws.charMappings), label: displayName(name), items: [] };
      groups.set(name, group);
    }
    group.items.push(item);
  }
  const moonRank = (moon: string) => (MOON_ORDER.includes(moon) ? MOON_ORDER.indexOf(moon) : MOON_ORDER.length);
  for (const group of groups.values()) {
    group.items.sort((a, b) => moonRank(a.key.moon) - moonRank(b.key.moon) || a.key.moon.localeCompare(b.key.moon));
  }
  return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label));
}

/** dataset.describe_identity for display: "5A", or "2C (#2)" for the second 2C. */
export function moveLabels(item: ItemState): string[] {
  const seen = new Map<string, number>();
  return item.moves.map((move) => {
    const key = inputKey(move.fields);
    const occurrence = seen.get(key) ?? 0;
    seen.set(key, occurrence + 1);
    const input = move.fields.input;
    const text = typeof input === "string" ? input : encodeJson(input ?? null);
    return occurrence === 0 ? text : `${text} (#${occurrence + 1})`;
  });
}

/** Fields in display order: the canonical move order, then extras sorted. */
export function fieldOrder(fields: JsonObject): string[] {
  return orderedKeys(fields, MOVE_ORDER);
}

/** How a value reads in the UI. */
export function displayValue(value: Json | undefined): string {
  if (value === undefined) return "";
  if (typeof value === "string") return value;
  if (value instanceof PyNumber) return value.text;
  if (Array.isArray(value) && value.length === 0) return "[]";
  if (Array.isArray(value) && value.every((v) => typeof v === "string")) return value.join(", ");
  return encodeJson(value);
}

// --- pending changes -------------------------------------------------------------

export interface FieldChange {
  field: string;
  /** undefined when the field is new on this move. */
  old: Json | undefined;
  /** undefined when the field was removed (not possible from the UI today). */
  new: Json | undefined;
}

export interface MoveChange {
  uid: string;
  label: string;
  isNew: boolean;
  /** For a new move: all of its fields. */
  fields: FieldChange[];
}

export interface ItemChanges {
  item: ItemState;
  moves: MoveChange[];
}

/** The item as it will be written: data/ (or the scrape, for a new item) with the current moves. */
export function buildItem(item: ItemState): JsonObject {
  const template = item.base ?? item.scraped!;
  const out: JsonObject = {};
  for (const key of Object.keys(template)) if (key !== "moves") setKey(out, key, cloneJson(template[key]!));
  setKey(out, "moves", item.moves.map((move) => move.fields));
  return out;
}

export function pendingChanges(ws: Workspace): ItemChanges[] {
  const result: ItemChanges[] = [];
  for (const item of ws.items) {
    const labels = moveLabels(item);
    const baseMoves = (item.base?.moves ?? []) as JsonObject[];
    const moves: MoveChange[] = [];
    item.moves.forEach((move, index) => {
      if (move.isNew) {
        const fields = fieldOrder(move.fields).map((field) => ({ field, old: undefined, new: move.fields[field] }));
        moves.push({ uid: move.uid, label: labels[index]!, isNew: true, fields });
        return;
      }
      const base = baseMoves[move.dataIndex!]!;
      const fields: FieldChange[] = [];
      for (const field of orderedKeys({ ...base, ...move.fields } as JsonObject, MOVE_ORDER)) {
        const before = has(base, field) ? base[field] : undefined;
        const after = has(move.fields, field) ? move.fields[field] : undefined;
        if (valueKey(before) !== valueKey(after)) fields.push({ field, old: before, new: after });
      }
      if (fields.length) moves.push({ uid: move.uid, label: labels[index]!, isNew: false, fields });
    });
    if (item.isNew || moves.length) result.push({ item, moves });
  }
  return result;
}

/** The Save edits count: one per changed field on an existing move, one per new move. */
export function countChanges(changes: ItemChanges[]): number {
  let count = 0;
  for (const { item, moves } of changes) {
    if (item.isNew && moves.length === 0) count += 1;
    for (const move of moves) count += move.isNew ? 1 : move.fields.length;
  }
  return count;
}

export function saveRequest(changes: ItemChanges[]) {
  return {
    files: changes.map(({ item }) => ({
      path: item.isNew ? null : item.path,
      baseHash: item.baseHash,
      text: dumps(buildItem(item)),
    })),
  };
}
