/**
 * The one boundary between the display and where data comes from.
 *
 * The local app reads and writes through the Express API (src/httpSource.ts).
 * A future read-only static viewer can implement `DataSource` by fetching the
 * committed data/ files and leaving `save` undefined; nothing else changes.
 * Files travel as their exact text, so number formatting and key order survive.
 */
import type { CharMappings } from "./dataset";

export interface SourceFile {
  /** Path relative to its root, "/"-separated, e.g. "akiha/crescent_akiha.json". */
  path: string;
  text: string;
  /** sha256 of the file's bytes as read; echoed back on save to detect edits on disk. */
  hash: string;
}

export interface UnreadableFile {
  path: string;
  error: string;
}

export type DataRootState =
  | { status: "ok"; files: SourceFile[]; unreadable: UnreadableFile[] }
  /** No data/ (or nothing in it): pull from DynamoDB first. Never filled from the scrape. */
  | { status: "missing" | "empty" };

export interface Snapshot {
  dataRoot: string;
  scrapedRoot: string;
  data: DataRootState;
  /** null when there is no scrape to compare against. */
  scraped: { files: SourceFile[]; unreadable: UnreadableFile[] } | null;
  charMappings: CharMappings;
}

export interface SaveFile {
  /** The existing file this replaces, or null for a new item. */
  path: string | null;
  /** Hash of the existing file when it was loaded; null for a new item. */
  baseHash: string | null;
  /** The item; the server re-serializes it canonically. */
  text: string;
}

export interface SaveRequest {
  files: SaveFile[];
}

export interface SaveResult {
  written: { path: string; status: "created" | "updated" | "unchanged" }[];
  warnings: string[];
}

export class SaveRefused extends Error {
  constructor(message: string, readonly problems: string[]) {
    super(message);
  }
}

export interface DataSource {
  load(): Promise<Snapshot>;
  /** Absent for read-only sources. Throws SaveRefused when the server refuses. */
  save?(request: SaveRequest): Promise<SaveResult>;
}
