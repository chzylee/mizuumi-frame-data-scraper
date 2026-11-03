import { readFileSync } from "node:fs";
import type { Snapshot, SourceFile } from "../shared/api";
import { dumps, parseCharMappings, pathFor } from "../shared/dataset";
import { sha256 } from "../shared/files";
import { loads, type JsonObject } from "../shared/pyjson";
import { MAPPINGS_FILE } from "../server/config";

export const mappings = parseCharMappings(readFileSync(MAPPINGS_FILE, "utf-8"));

type Fields = Record<string, string | string[]>;

/** A complete move, as data/ holds it: every expected field, so nothing is "missing". */
export function move(input: string, extra: Fields = {}): JsonObject {
  return loads(
    JSON.stringify({
      input,
      image: `https://img.test/${input}.png`,
      first_active: "5",
      active: "3",
      recovery: "8",
      frame_adv: "1",
      proration: "75%",
      guard: "LH",
      invuln: "-",
      alts: [],
      ...extra,
    }),
  ) as JsonObject;
}

export function item(moves: JsonObject[], character = "Kouma_Kishima", moon = "Crescent_Moon"): JsonObject {
  return { character_name: character, moon, moves } as JsonObject;
}

export function file(it: JsonObject): SourceFile {
  const text = dumps(it);
  return { path: pathFor(it as never, mappings), text, hash: sha256(text) };
}

export function snapshot(data: JsonObject[] | null, scraped: JsonObject[] | null): Snapshot {
  return {
    dataRoot: "/data",
    scrapedRoot: "/scraped",
    data: data === null ? { status: "missing" } : { status: "ok", files: data.map(file), unreadable: [] },
    scraped: scraped === null ? null : { files: scraped.map(file), unreadable: [] },
    charMappings: mappings,
  };
}
