import { setField } from "../shared/editing";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { request as httpRequest, type Server } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SaveRequest, Snapshot } from "../shared/api";
import { dumps } from "../shared/dataset";
import { sha256 } from "../shared/files";
import { createApp } from "../server/app";
import { MAPPINGS_FILE, type ViewerConfig } from "../server/config";
import { atomicWrite, type WriteOps } from "../server/store";
import { buildWorkspace, pendingChanges, saveRequest } from "../shared/workspace";
import { item, move } from "./helpers";

let root: string;
let config: ViewerConfig;
let server: Server | null = null;

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), "viewer-server-"));
  config = { dataDir: join(root, "data"), scrapedDir: join(root, "scraped"), mappingsFile: MAPPINGS_FILE, port: 0 };
});
afterEach(async () => {
  if (server) await new Promise((done) => server!.close(done));
  server = null;
  rmSync(root, { recursive: true, force: true });
});

function put(dir: string, path: string, text: string) {
  mkdirSync(join(dir, path, ".."), { recursive: true });
  writeFileSync(join(dir, path), text, "utf-8");
}

const KOUMA = "kouma/crescent_kouma.json";
const kouma = () => item([move("5A"), move("5B")]);

async function start(ops?: WriteOps): Promise<string> {
  server = createApp(config, ops).listen(0, "127.0.0.1");
  await new Promise((done) => server!.once("listening", done));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("no port");
  return `http://127.0.0.1:${address.port}`;
}

async function save(base: string, body: SaveRequest) {
  const res = await fetch(`${base}/api/save`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return { status: res.status, body: await res.json() };
}

const read = (path: string) => readFileSync(join(config.dataDir, path), "utf-8");
const listAll = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? listAll(join(dir, e.name)) : [join(dir, e.name)]));

describe("GET /api/snapshot", () => {
  it("reports a missing data root without creating it", async () => {
    const base = await start();
    const snap = (await (await fetch(`${base}/api/snapshot`)).json()) as Snapshot;
    expect(snap.data).toEqual({ status: "missing" });
    expect(snap.scraped).toBeNull();
    expect(existsSync(config.dataDir)).toBe(false);
  });

  it("returns exact text and byte hashes for data and scrape", async () => {
    put(config.dataDir, KOUMA, dumps(kouma()));
    put(config.scrapedDir, KOUMA, JSON.stringify(kouma(), null, 4));
    const base = await start();
    const snap = (await (await fetch(`${base}/api/snapshot`)).json()) as Snapshot;
    if (snap.data.status !== "ok") throw new Error("expected data");
    expect(snap.data.files).toEqual([{ path: KOUMA, text: dumps(kouma()), hash: sha256(dumps(kouma())) }]);
    expect(snap.scraped!.files[0]!.path).toBe(KOUMA);
    expect(snap.charMappings[0]).toEqual(["akiha", "Akiha_Tohno"]);
  });

  it("calls an existing but empty data root empty", async () => {
    mkdirSync(config.dataDir);
    const base = await start();
    expect(((await (await fetch(`${base}/api/snapshot`)).json()) as Snapshot).data).toEqual({ status: "empty" });
  });
});

describe("POST /api/save", () => {
  beforeEach(() => put(config.dataDir, KOUMA, dumps(kouma())));
  const baseHash = () => sha256(read(KOUMA));

  it("writes canonical bytes for an edited item, even from non-canonical text", async () => {
    const edited = item([move("5A", { heat: "x" }), move("5B")]);
    const base = await start();
    const res = await save(base, { files: [{ path: KOUMA, baseHash: baseHash(), text: JSON.stringify(edited, null, 4) }] });
    expect(res).toEqual({ status: 200, body: { written: [{ path: KOUMA, status: "updated" }], warnings: [] } });
    expect(read(KOUMA)).toBe(dumps(edited));
    expect(listAll(config.dataDir)).toHaveLength(1); // no temp files left
  });

  it("creates a new item at pathFor, under the existing data root", async () => {
    const ciel = item([move("5A")], "Ciel", "Half_Moon");
    const base = await start();
    const res = await save(base, { files: [{ path: null, baseHash: null, text: dumps(ciel) }] });
    expect(res.body.written).toEqual([{ path: "ciel/half_ciel.json", status: "created" }]);
    expect(read("ciel/half_ciel.json")).toBe(dumps(ciel));
  });

  it("warns for an _unmapped item", async () => {
    const odd = item([move("5A")], "Brand: New", "Half_Moon");
    const base = await start();
    const res = await save(base, { files: [{ path: null, baseHash: null, text: dumps(odd) }] });
    expect(res.body.written).toEqual([{ path: "_unmapped/Brand%3A New/Half_Moon.json", status: "created" }]);
    expect(res.body.warnings).toHaveLength(1);
  });

  it("refuses an item that fails dataset.py validation, and writes nothing from that save", async () => {
    const bad = item([{ input: "5A" } as never]);
    const ciel = item([move("5A")], "Ciel", "Half_Moon");
    const before = read(KOUMA);
    const base = await start();
    const res = await save(base, {
      files: [
        { path: null, baseHash: null, text: dumps(ciel) },
        { path: KOUMA, baseHash: baseHash(), text: dumps(bad) },
      ],
    });
    expect(res.status).toBe(409);
    expect(res.body.problems).toEqual([
      `${KOUMA}: moves[0] ('5A') is missing image, first_active, active, recovery, frame_adv, proration, invuln, alts`,
    ]);
    expect(read(KOUMA)).toBe(before);
    expect(existsSync(join(config.dataDir, "ciel"))).toBe(false);
  });

  it("refuses content_hash, non-string alts and bad JSON", async () => {
    const withHash = { ...kouma(), content_hash: "abc" };
    const base = await start();
    const res = await save(base, {
      files: [
        { path: KOUMA, baseHash: baseHash(), text: dumps(withHash as never) },
        { path: null, baseHash: null, text: "{" },
      ],
    });
    expect(res.status).toBe(409);
    expect(res.body.problems[0]).toBe(`${KOUMA}: 'content_hash' is table bookkeeping and must not be in data/`);
    expect(res.body.problems[1]).toMatch(/^new item #2: not valid JSON/);
  });

  it("refuses an item whose key belongs at a different path", async () => {
    const base = await start();
    const res = await save(base, { files: [{ path: KOUMA, baseHash: baseHash(), text: dumps(item([move("5A")], "Ciel", "Half_Moon")) }] });
    expect(res.status).toBe(409);
    expect(res.body.problems).toEqual([`${KOUMA}: its key belongs at ciel/half_ciel.json`]);
  });

  it("refuses when the file changed on disk since load", async () => {
    const hash = baseHash();
    put(config.dataDir, KOUMA, dumps(item([move("5A")])));
    const base = await start();
    const res = await save(base, { files: [{ path: KOUMA, baseHash: hash, text: dumps(kouma()) }] });
    expect(res.status).toBe(409);
    expect(res.body.problems[0]).toMatch(/changed on disk since the viewer loaded it/);
  });

  it("refuses a new item whose file already exists", async () => {
    const base = await start();
    const res = await save(base, { files: [{ path: null, baseHash: null, text: dumps(kouma()) }] });
    expect(res.status).toBe(409);
    expect(res.body.problems[0]).toMatch(/already exists/);
  });

  it("refuses to save when there is no data root, and does not create one", async () => {
    rmSync(config.dataDir, { recursive: true });
    const base = await start();
    const res = await save(base, { files: [{ path: null, baseHash: null, text: dumps(kouma()) }] });
    expect(res.status).toBe(409);
    expect(res.body.error).toMatch(/Pull from DynamoDB first/);
    expect(existsSync(config.dataDir)).toBe(false);
  });

  it("still saves the rest when a data/ file has a merge conflict, and leaves that file alone", async () => {
    const conflicted = "<<<<<<< HEAD\n" + dumps(item([move("5A")], "Aoko_Aozaki", "Full_Moon")) + "=======\n>>>>>>> other\n";
    put(config.dataDir, "aoko/full_aoko.json", conflicted);
    put(config.scrapedDir, KOUMA, dumps(item([move("5A", { guard: "LH" }), move("5B", { guard: "H" })])));
    put(config.scrapedDir, "aoko/full_aoko.json", dumps(item([move("5A", { guard: "L" })], "Aoko_Aozaki", "Full_Moon")));
    const base = await start();
    const snap = (await (await fetch(`${base}/api/snapshot`)).json()) as Snapshot;
    const loaded = buildWorkspace(snap);
    expect(loaded.dataErrors.map((f) => f.path)).toEqual(["aoko/full_aoko.json"]);
    const kouma = loaded.items.find((it) => it.path === KOUMA)!;
    const ws = setField(loaded, kouma.id, kouma.moves[0]!.uid, "active", "9");
    const res = await save(base, saveRequest(pendingChanges(ws)));
    expect(res).toEqual({ status: 200, body: { written: [{ path: KOUMA, status: "updated" }], warnings: [] } });
    expect(read("aoko/full_aoko.json")).toBe(conflicted);
  });

  it("explains a new-file collision instead of only blaming a race", async () => {
    const base = await start();
    const res = await save(base, { files: [{ path: null, baseHash: null, text: dumps(kouma()) }] });
    expect(res.body.problems[0]).toMatch(/If the viewer lists it as unloadable, fix or restore it/);
  });

  it("reports unchanged when the bytes already match", async () => {
    const base = await start();
    const res = await save(base, { files: [{ path: KOUMA, baseHash: baseHash(), text: dumps(kouma()) }] });
    expect(res.body.written).toEqual([{ path: KOUMA, status: "unchanged" }]);
  });

  it("keeps the old file and no temp file when the rename fails", async () => {
    const before = read(KOUMA);
    const failing: WriteOps = { rename: async () => { throw Object.assign(new Error("disk on fire"), { code: "EIO" }); } };
    const base = await start(failing);
    const res = await save(base, { files: [{ path: KOUMA, baseHash: baseHash(), text: dumps(item([move("5A")])) }] });
    expect(res.status).toBe(409);
    expect(res.body.error).toMatch(/Writing kouma\/crescent_kouma.json failed \(disk on fire\); it is unchanged/);
    expect(read(KOUMA)).toBe(before);
    expect(listAll(config.dataDir)).toEqual([join(config.dataDir, "kouma", "crescent_kouma.json")]);
  });
});

describe("atomicWrite", () => {
  it("retries a rename Windows briefly refuses", async () => {
    const target = join(root, "x.json");
    writeFileSync(target, "old");
    let calls = 0;
    const { rename } = await import("node:fs/promises");
    await atomicWrite(target, Buffer.from("new"), {
      rename: async (from, to) => {
        if (++calls < 3) throw Object.assign(new Error("busy"), { code: "EPERM" });
        await rename(from, to);
      },
    });
    expect(calls).toBe(3);
    expect(readFileSync(target, "utf-8")).toBe("new");
    expect(readdirSync(root)).toEqual(["x.json"]);
  });
});

describe("local only", () => {
  function raw(base: string, headers: Record<string, string>): Promise<number> {
    return new Promise((done, fail) => {
      const req = httpRequest(`${base}/api/snapshot`, { headers }, (res) => {
        res.resume();
        done(res.statusCode!);
      });
      req.on("error", fail);
      req.end();
    });
  }

  it("rejects a foreign Host (DNS rebinding) or Origin", async () => {
    const base = await start();
    expect(await raw(base, {})).toBe(200);
    expect(await raw(base, { host: "evil.example:80" })).toBe(403);
    expect(await raw(base, { origin: "https://evil.example" })).toBe(403);
    expect(await raw(base, { origin: "http://localhost:5174" })).toBe(200);
  });
});
