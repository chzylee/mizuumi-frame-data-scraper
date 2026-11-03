import { describe, expect, it } from "vitest";
import { dumps, moveIdentities } from "../shared/dataset";
import { loads, PyNumber, type JsonObject } from "../shared/pyjson";
import {
  buildWorkspace,
  countChanges,
  displayValue,
  groupCharacters,
  itemStatus,
  moveLabels,
  pendingChanges,
  rollup,
  saveRequest,
  type ItemState,
  type Workspace,
} from "../shared/workspace";
import { setField } from "../shared/editing";
import { file, item, move, snapshot } from "./helpers";

const inputs = (it: ItemState) => it.moves.map((m) => m.fields.input);
const only = (ws: Workspace) => {
  expect(ws.items).toHaveLength(1);
  return ws.items[0]!;
};
const statusOf = (it: ItemState, index: number) => itemStatus(it).moves.get(it.moves[index]!.uid)!;

describe("rollup", () => {
  it("ranks red > blue > green > none", () => {
    expect(rollup([])).toBe("none");
    expect(rollup(["none", "green"])).toBe("green");
    expect(rollup(["green", "blue", "none"])).toBe("blue");
    expect(rollup(["blue", "red", "green"])).toBe("red");
  });
});

describe("field diffs on matched moves", () => {
  it("green when equal, red when different, nothing for data-only fields", () => {
    const ws = buildWorkspace(
      snapshot(
        [item([move("5A", { active: "3", recovery: "8", note: "mine" })])],
        [item([move("5A", { active: "3", recovery: "99", guard: "LH" })])],
      ),
    );
    const s = statusOf(only(ws), 0);
    expect(s.fields.active).toBe("green");
    expect(s.fields.recovery).toBe("red");
    expect(s.scraped!.recovery).toBe("99");
    expect(s.fields.note).toBe("none");
    expect(s.status).toBe("red");
  });

  it("compares alts as a list", () => {
    const ws = buildWorkspace(
      snapshot([item([move("5A", { alts: ["a", "b"] }), move("5B", { alts: ["x"] })])],
        [item([move("5A", { alts: ["a", "b"] }), move("5B", { alts: ["y"] })])]),
    );
    expect(statusOf(only(ws), 0).fields.alts).toBe("green");
    expect(statusOf(only(ws), 1).fields.alts).toBe("red");
  });

  it("never compares, colors or copies image", () => {
    const ws = buildWorkspace(
      snapshot([item([move("5A", { image: "HAND_FIXED.png" })])], [item([move("5A", { image: "scraped.png" })])]),
    );
    const it0 = only(ws);
    const s = statusOf(it0, 0);
    expect(s.fields.image).toBe("none");
    expect(s.status).toBe("green");
    expect(it0.moves[0]!.fields.image).toBe("HAND_FIXED.png");
    expect(pendingChanges(ws)).toEqual([]);
  });

  it("does not add image to a data move that lacks it", () => {
    const data = move("5A");
    delete data.image;
    const ws = buildWorkspace(snapshot([item([data])], [item([move("5A")])]));
    expect(only(ws).moves[0]!.fields).not.toHaveProperty("image");
    expect(pendingChanges(ws)).toEqual([]);
  });
});

describe("new fields from the scrape (guard backfill)", () => {
  it("shows a scrape-only field as a blue preview, never staged or counted", () => {
    const ws = buildWorkspace(
      snapshot([item([move("5A"), move("5B")])], [item([move("5A", { guard: "LH" }), move("5B", { guard: "H" })])]),
    );
    const it0 = only(ws);
    expect(it0.moves.map((m) => m.fields.guard)).toEqual([undefined, undefined]); // not copied into data
    expect(it0.moves.map((m) => m.scrapeOnlyFields)).toEqual([["guard"], ["guard"]]);
    expect(statusOf(it0, 0).fields.guard).toBe("blue");
    expect(statusOf(it0, 0).scraped!.guard).toBe("LH");
    expect(statusOf(it0, 0).status).toBe("blue");
    expect(pendingChanges(ws)).toEqual([]);
    expect(countChanges(pendingChanges(ws))).toBe(0);
  });

  it("matches repeated inputs by occurrence", () => {
    const ws = buildWorkspace(
      snapshot(
        [item([move("2C"), move("5A"), move("2C")])],
        [item([move("2C", { guard: "L" }), move("2C", { guard: "H" }), move("5A", { guard: "LH" })])],
      ),
    );
    const it0 = only(ws);
    const pairedGuard = it0.moves.map((m, i) => [m.fields.input, statusOf(it0, i).scraped!.guard]);
    expect(pairedGuard).toEqual([["2C", "L"], ["5A", "LH"], ["2C", "H"]]);
    expect(moveLabels(it0)).toEqual(["2C", "5A", "2C (#2)"]);
  });

  it("blue outranks green but not red in the rollup", () => {
    const ws = buildWorkspace(
      snapshot([item([move("5A", { active: "1" })])], [item([move("5A", { active: "2", guard: "LH" })])]),
    );
    expect(statusOf(only(ws), 0).status).toBe("red");
    expect(itemStatus(only(ws)).status).toBe("red");
  });
});

describe("new moves", () => {
  it("inserts after the preceding matched move, in scrape order", () => {
    const ws = buildWorkspace(
      snapshot([item([move("5A"), move("5B"), move("5C")])],
        [item([move("5A"), move("N1"), move("N2"), move("5B"), move("5C"), move("N3")])]),
    );
    const it0 = only(ws);
    expect(inputs(it0)).toEqual(["5A", "N1", "N2", "5B", "5C", "N3"]);
    expect(it0.moves.map((m) => m.isNew)).toEqual([false, true, true, false, false, true]);
    expect(statusOf(it0, 1).status).toBe("blue");
    expect(statusOf(it0, 1).fields.image).toBe("none");
  });

  it("goes first when nothing precedes it, and follows data order when orders differ", () => {
    const ws = buildWorkspace(snapshot([item([move("B"), move("A")])], [item([move("N0"), move("A"), move("B"), move("N")])]));
    expect(inputs(only(ws))).toEqual(["N0", "B", "N", "A"]);
  });

  it("never lands before a move with the same input, so existing identities hold", () => {
    // Scrape: X, B, X. Data: B, X. The second scraped X follows B in the scrape,
    // but inserting it after B would make it X#1's predecessor and renumber.
    const data = [move("B", { active: "d-B" }), move("X", { active: "d-X0" })];
    const scraped = [move("X", { active: "d-X0" }), move("B", { active: "d-B" }), move("X", { active: "s-X1" })];
    const ws = buildWorkspace(snapshot([item(data)], [item(scraped)]));
    const it0 = only(ws);
    expect(it0.moves.map((m) => m.fields.active)).toEqual(["d-B", "d-X0", "s-X1"]);
    const ids = moveIdentities(it0.moves.map((m) => m.fields));
    expect(ids[2]).toBe(moveIdentities(scraped)[2]); // the preview keeps its scrape identity
    expect(it0.moves.map((m) => m.isNew)).toEqual([false, false, true]);
    expect(pendingChanges(ws)).toEqual([]); // a preview is never saved
  });

  it("adds extra occurrences of a repeated input in scrape order, after the existing ones", () => {
    const ws = buildWorkspace(snapshot([item([move("2C"), move("5A")])], [item([move("2C"), move("2C"), move("5A"), move("2C")])]));
    expect(inputs(only(ws))).toEqual(["2C", "2C", "5A", "2C"]);
    expect(moveLabels(only(ws))).toEqual(["2C", "2C (#2)", "5A", "2C (#3)"]);
    expect(only(ws).moves.map((m) => m.isNew)).toEqual([false, true, false, true]);
  });

  it("never stages or saves a new move, even when the item has other edits", () => {
    const ws = buildWorkspace(snapshot([item([move("5A")])], [item([move("5A"), move("6C", { guard: "H" })])]));
    expect(pendingChanges(ws)).toEqual([]);
    const it0 = only(ws);
    const edited = setField(ws, it0.id, it0.moves[0]!.uid, "active", "9");
    const [saved] = saveRequest(pendingChanges(edited)).files;
    expect((loads(saved!.text) as JsonObject).moves).toHaveLength(1); // 6C left out
  });

  it("leaves data-only moves alone and uncolored", () => {
    const ws = buildWorkspace(snapshot([item([move("5A"), move("mine")])], [item([move("5A")])]));
    expect(statusOf(only(ws), 1).status).toBe("none");
    expect(pendingChanges(ws)).toEqual([]);
  });
});

describe("new items", () => {
  it("shows a scrape-only moon and character as preview items at pathFor, never saved", () => {
    const ws = buildWorkspace(
      snapshot(
        [item([move("5A")], "Kouma_Kishima", "Crescent_Moon")],
        [
          item([move("5A")], "Kouma_Kishima", "Crescent_Moon"),
          item([move("5A"), move("5B")], "Kouma_Kishima", "Full_Moon"),
          item([move("5A")], "Ciel", "Half_Moon"),
          item([move("5A")], "Brand: New", "Half_Moon"),
        ],
      ),
    );
    const byPath = Object.fromEntries(ws.items.map((it) => [it.path, it]));
    expect(Object.keys(byPath).sort()).toEqual([
      "_unmapped/Brand%3A New/Half_Moon.json", "ciel/half_ciel.json", "kouma/crescent_kouma.json", "kouma/full_kouma.json",
    ]);
    const fullKouma = byPath["kouma/full_kouma.json"]!;
    expect(fullKouma.isNew).toBe(true);
    expect(itemStatus(fullKouma).status).toBe("blue");
    const groups = groupCharacters(ws);
    const kouma = groups.find((g) => g.name === "Kouma_Kishima")!;
    expect(kouma.items.map((it) => it.key.moon)).toEqual(["Crescent_Moon", "Full_Moon"]);
    expect(rollup(kouma.items.map((it) => itemStatus(it).status))).toBe("blue");
    // Previews only: nothing is staged, so no new file is ever written.
    expect(pendingChanges(ws)).toEqual([]);
  });

  it("leaves data-only items alone", () => {
    const ws = buildWorkspace(snapshot([item([move("5A")]), item([move("5A")], "Ciel", "Half_Moon")], [item([move("5A")])]));
    expect(itemStatus(ws.items.find((it) => it.key.character_name === "Ciel")!).status).toBe("none");
    expect(pendingChanges(ws)).toEqual([]);
  });
});

describe("loading", () => {
  it("has no comparison and no changes without a scrape", () => {
    const ws = buildWorkspace(snapshot([item([move("5A")])], null));
    expect(ws.scrapedAvailable).toBe(false);
    expect(itemStatus(only(ws)).status).toBe("none");
    expect(pendingChanges(ws)).toEqual([]);
  });

  it("never turns the scrape into data/ when data/ is missing", () => {
    const ws = buildWorkspace(snapshot(null, [item([move("5A")])]));
    expect(ws.items).toEqual([]);
    expect(pendingChanges(ws)).toEqual([]);
  });

  it("reports unparseable and duplicate files instead of guessing", () => {
    const snap = snapshot([item([move("5A")])], [item([move("5A")])]);
    if (snap.data.status !== "ok") throw new Error("setup");
    snap.data.files.push({ path: "broken.json", text: "{", hash: "x" });
    snap.data.files.push({ path: "copy.json", text: dumps(item([move("5A")])), hash: "y" });
    const ws = buildWorkspace(snap);
    expect(ws.items).toHaveLength(1);
    expect(ws.dataErrors).toHaveLength(2);
    expect(ws.dataErrors[0]!.path).toBe("broken.json");
    expect(ws.dataErrors[0]!.error).toMatch(/^not valid JSON/);
    expect(ws.dataErrors[1]!.path).toBe("copy.json");
    expect(ws.dataErrors[1]!.error).toMatch(/^duplicate key .* also in data\/kouma\/crescent_kouma\.json$/);
    expect(ws.problems).toEqual([]);
  });

  it("never shows a scraped item over a data/ file that failed to load", () => {
    const snap = snapshot([item([move("5A")])], [item([move("5A", { guard: "LH" })]), item([move("5A")], "Aoko_Aozaki", "Full_Moon")]);
    if (snap.data.status !== "ok") throw new Error("setup");
    snap.data.files.push({ path: "aoko/full_aoko.json", text: "<<<<<<< HEAD\n{}", hash: "x" });
    snap.data.unreadable.push({ path: "aoko/half_aoko.json", error: "not valid UTF-8" });
    snap.scraped!.files.push(file(item([move("5A")], "Aoko_Aozaki", "Half_Moon")));
    const ws = buildWorkspace(snap);
    expect(ws.items.map((it) => it.path)).toEqual(["kouma/crescent_kouma.json"]);
    expect(ws.dataErrors).toEqual([
      { path: "aoko/half_aoko.json", error: "not valid UTF-8" },
      { path: "aoko/full_aoko.json", error: "not valid JSON (Expecting value at char 0)" },
    ]);
    expect(ws.problems).toEqual([
      "scraped/aoko/full_aoko.json: not compared or added, because data/aoko/full_aoko.json could not be loaded; fix or restore it",
      "scraped/aoko/half_aoko.json: not compared or added, because data/aoko/half_aoko.json could not be loaded; fix or restore it",
    ]);
    // The rest stays saveable: an edit saves only the loaded item.
    const kouma = ws.items[0]!;
    const request = saveRequest(pendingChanges(setField(ws, kouma.id, kouma.moves[0]!.uid, "guard", "LH")));
    expect(request.files.map((f) => f.path)).toEqual(["kouma/crescent_kouma.json"]);
  });

  it("saves the changed item byte-identical to what Python would write, extras kept", () => {
    const data = item([move("5A", { zz_extra: "keep" })]);
    (data as Record<string, unknown>).top_extra = "keep too";
    const loaded = buildWorkspace(snapshot([data], [item([move("5A", { guard: "LH" })])]));
    const it0 = only(loaded);
    const ws = setField(loaded, it0.id, it0.moves[0]!.uid, "guard", "LH"); // added by hand
    const [file] = saveRequest(pendingChanges(ws)).files;
    expect(file!.path).toBe("kouma/crescent_kouma.json");
    const expected = loads(dumps(data)) as JsonObject;
    ((expected.moves as JsonObject[])[0]!).guard = "LH";
    expect(file!.text).toBe(dumps(expected));
    expect(file!.text).toContain('"top_extra": "keep too"');
  });
});

describe("displayValue", () => {
  it("shows lists, empty lists and numbers readably", () => {
    expect(displayValue(["a", "b"])).toBe("a, b");
    expect(displayValue([])).toBe("[]");
    expect(displayValue(PyNumber.fromLexeme("2.50"))).toBe("2.5");
    expect(displayValue(undefined)).toBe("");
  });
});
