/**
 * Parity: the TS ports in shared/dataset.ts against src/dataset.py, byte for byte.
 *
 * Runs Python (tests/parity_helper.py) and TS over the same files and compares
 * canonical bytes, path_for, validation messages and error classes:
 *   - every edge-case fixture in tests/fixtures/parity/ and the sample fixtures,
 *   - every file in local-data/scraped/ when it exists (not in CI),
 *   - a seeded batch of generated files with awkward strings and numbers,
 *   - path_for for every CHAR_MAPPINGS name x moon, plus awkward keys.
 * Python is a dev/test dependency only. Set PYTHON to pick the interpreter.
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { dumps, loads, MOON_ORDER, parseCharMappings, pathFor, validateItem, type CharMappings } from "../shared/dataset";
import { listJsonFiles, readUtf8 } from "../shared/files";
import { isObject, JsonEncodeError, JsonParseError } from "../shared/pyjson";
import { MAPPINGS_FILE, REPO_ROOT } from "../server/config";
import { saveFiles } from "../server/store";
import { buildWorkspace, pendingChanges, saveRequest } from "../shared/workspace";
import { item, move, snapshot } from "./helpers";

const FIXTURES = join(import.meta.dirname, "fixtures");
const SCRAPED = join(REPO_ROOT, "local-data", "scraped");
const HELPER = join(import.meta.dirname, "parity_helper.py");
const mappings: CharMappings = parseCharMappings(readFileSync(MAPPINGS_FILE, "utf-8"));

type Described = Record<string, unknown>;

function errorName(error: unknown): string {
  if (error instanceof JsonEncodeError) return error.pyError;
  if (error instanceof RangeError) return "ValueError";
  if (error instanceof TypeError) return "TypeError";
  throw error;
}

function pathOrError(key: { character_name: string; moon: string }): Described {
  try {
    return { path: pathFor(key, mappings) };
  } catch (error) {
    return { path_error: errorName(error) };
  }
}

function describeFile(path: string): Described {
  let text: string;
  try {
    text = readUtf8(path).text;
  } catch (error) {
    if (error instanceof TypeError) return { read_error: "UnicodeDecodeError" };
    throw error;
  }
  let item;
  try {
    item = loads(text);
  } catch (error) {
    if (error instanceof JsonParseError) return { parse_error: "JSONDecodeError" };
    throw error;
  }
  const out: Described = { validation: validateItem("item", item) };
  try {
    out.bytes = Buffer.from(dumps(item), "utf-8").toString("base64");
  } catch (error) {
    out.dumps_error = errorName(error);
  }
  if (isObject(item) && typeof item.character_name === "string" && typeof item.moon === "string") {
    Object.assign(out, pathOrError({ character_name: item.character_name, moon: item.moon }));
  }
  return out;
}

// --- generated files ------------------------------------------------------------

function rng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const PIECES = [
  "a", "Z", "5", " ", "%", "_", ":", "/", "\\", '"', "'", "\n", "\t", "\u0001", "\u001f", "\u007f", "é",
  "→", " ", "​", " ", "̀", "Ａ", "ﬁ", "�", "\u{1F600}", "\u{10000}", "~",
];
const NUMBERS = [
  "0", "-0", "7", "-12", "2.0", "-0.0", "0.1", "1e5", "1E-5", "2.5e+3", "123456789012345678901234567890",
  "1e16", "1e15", "9007199254740993", "0.00001", "0.0001", "1.7976931348623157e308", "5e-324", "3.14159",
];

function generate(random: () => number, names: string[]): string {
  const pick = <T,>(list: readonly T[]): T => list[Math.floor(random() * list.length)]!;
  const str = () => Array.from({ length: Math.floor(random() * 6) }, () => pick(PIECES)).join("");
  const quote = (text: string) => JSON.stringify(text); // a valid JSON string literal
  const value = (depth: number): string => {
    const r = random();
    if (r < 0.45) return quote(str());
    if (r < 0.6) return pick(NUMBERS);
    if (r < 0.66) return pick(["true", "false", "null"]);
    if (depth > 2) return quote(str());
    if (r < 0.83) return `[${Array.from({ length: Math.floor(random() * 3) }, () => value(depth + 1)).join(", ")}]`;
    return obj(depth + 1, []);
  };
  const obj = (depth: number, required: [string, string][]) => {
    const entries = required.map(([k, v]) => `${quote(k)}: ${v}`);
    for (let i = Math.floor(random() * 4); i > 0; i--) entries.push(`${quote(str() || "x")}: ${value(depth)}`);
    entries.sort(() => random() - 0.5);
    const sep = pick([", ", ",\n  ", ","]);
    return `{${entries.join(sep)}}`;
  };
  const moveKeys = ["input", "image", "first_active", "active", "recovery", "frame_adv", "proration", "guard", "invuln"];
  const moves = Array.from({ length: Math.floor(random() * 4) }, () =>
    obj(1, [
      ...moveKeys.filter(() => random() < 0.85).map((k): [string, string] => [k, random() < 0.9 ? quote(str()) : value(2)]),
      ...(random() < 0.9 ? [["alts", random() < 0.9 ? `[${quote(str())}]` : value(2)] as [string, string]] : []),
    ]),
  );
  const character = random() < 0.6 ? pick(names) : str() || "x";
  const moon = random() < 0.7 ? pick([...MOON_ORDER, "Blood_Moon"]) : str() || "y";
  return obj(0, [["character_name", quote(character)], ["moon", quote(moon)], ["moves", `[${moves.join(", ")}]`]]);
}

// --- the comparison ----------------------------------------------------------------

const tempDir = mkdtempSync(join(tmpdir(), "viewer-parity-"));
afterAll(() => rmSync(tempDir, { recursive: true, force: true }));

describe("parity with src/dataset.py", () => {
  const random = rng(20261102);
  const wikiNames = [...new Set(mappings.map(([, wiki]) => wiki))];
  const generated = Array.from({ length: 400 }, (_, i) => {
    const path = join(tempDir, `generated-${i}.json`);
    writeFileSync(path, generate(random, wikiNames), "utf-8");
    return path;
  });
  const fixtureFiles = listJsonFiles(FIXTURES).map((rel) => join(FIXTURES, rel));
  const scrapedFiles = listJsonFiles(SCRAPED).map((rel) => join(SCRAPED, rel));
  const files = [...fixtureFiles, ...scrapedFiles, ...generated];
  const keys = [
    ...wikiNames.flatMap((name) => [...MOON_ORDER, "Blood_Moon"].map((moon) => ({ character_name: name, moon }))),
    ...["Some: Weird/Char?", "..", ".", "a.b", "New_%26_Char", "tab\there", "\u{1F600}", "<>|*\"\\"].map((name) => ({
      character_name: name,
      moon: "Full_Moon",
    })),
    { character_name: "Ciel", moon: ".." },
    { character_name: "Ciel", moon: "full" },
  ];

  const run = spawnSync(process.env.PYTHON ?? "python", [HELPER], {
    input: JSON.stringify({ files, keys }),
    encoding: "utf-8",
    maxBuffer: 256 * 1024 * 1024,
  });
  if (run.error || run.status !== 0) {
    throw new Error(`parity helper failed (set PYTHON?): ${run.error ?? run.stderr}`);
  }
  const python = JSON.parse(run.stdout) as {
    mappings: [string, string][];
    files: Record<string, Described>;
    keys: Described[];
  };

  it("covers the fixtures, and local-data/scraped when present", () => {
    expect(fixtureFiles.length).toBeGreaterThan(30);
    if (existsSync(SCRAPED)) expect(scrapedFiles.length).toBeGreaterThan(0);
    console.log(`parity: ${fixtureFiles.length} fixture, ${scrapedFiles.length} scraped, ${generated.length} generated files`);
  });

  it("reads CHAR_MAPPINGS from mizuumi.py in the same order", () => {
    expect(mappings).toEqual(python.mappings);
  });

  it("path_for agrees for every mapped name x moon and awkward keys", () => {
    expect(keys.map(pathOrError)).toEqual(python.keys);
  });

  it("a data dir written by the viewer server passes `python -m dataset check`", async () => {
    const dataDir = join(tempDir, "server-data");
    const data = [item([move("5A"), move("2C"), move("2C")]), item([move("5A")], "Ciel", "Half_Moon")];
    const scraped = [
      item([move("5A", { guard: "LH" }), move("2C", { guard: "L" }), move("NEW"), move("2C", { guard: "H" })]),
      item([move("5A", { guard: "H" })], "Ciel", "Full_Moon"),
      item([move("5A", { guard: "H" })], "Not: Mapped", "Half_Moon"),
    ];
    const snap = snapshot(data, scraped);
    if (snap.data.status !== "ok") throw new Error("setup");
    for (const f of snap.data.files) {
      mkdirSync(join(dataDir, f.path, ".."), { recursive: true });
      writeFileSync(join(dataDir, f.path), f.text, "utf-8");
    }
    const request = saveRequest(pendingChanges(buildWorkspace(snap)));
    expect(request.files).toHaveLength(3);
    const config = { dataDir, scrapedDir: join(tempDir, "none"), mappingsFile: MAPPINGS_FILE, port: 0 };
    const result = await saveFiles(config, request);
    expect(result.written.map((w) => w.status).sort()).toEqual(["created", "created", "updated"]);
    const check = spawnSync(process.env.PYTHON ?? "python", ["-m", "dataset", "check", dataDir], {
      cwd: join(REPO_ROOT, "src"),
      encoding: "utf-8",
    });
    expect(check.stdout).toContain("4 file(s) checked, 0 problem(s), 1 warning(s)");
    expect(check.status).toBe(0);
  });

  it.each(files.map((path) => [path.replace(REPO_ROOT, "").replace(tempDir, "<generated>"), path]))(
    "%s",
    (_label, path) => {
      expect(describeFile(path)).toEqual(python.files[path]);
    },
  );
});
