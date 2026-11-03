import { describe, expect, it } from "vitest";
import { draftKey, editorReducer, initialEditor, isEditable, openDrafts, type EditorState } from "../shared/editing";
import { PyNumber } from "../shared/pyjson";
import { buildWorkspace, countChanges, itemStatus, pendingChanges, saveRequest } from "../shared/workspace";
import { item, move, snapshot } from "./helpers";

function setup(): { state: EditorState; itemId: string; uid: string } {
  const ws = buildWorkspace(snapshot([item([move("5A", { active: "3" })])], [item([move("5A", { active: "3" })])]));
  const it = ws.items[0]!;
  return { state: initialEditor(ws), itemId: it.id, uid: it.moves[0]!.uid };
}
const fields = (s: EditorState) => s.ws.items[0]!.moves[0]!.fields;
const count = (s: EditorState) => countChanges(pendingChanges(s.ws));

describe("lock / stage", () => {
  it("fields start locked: drafts are ignored until unlocked", () => {
    const { state, uid } = setup();
    const next = editorReducer(state, { type: "draft", uid, field: "active", value: "9" });
    expect(next).toBe(state);
  });

  it("unlock, edit, relock stages the edit", () => {
    const { state, itemId, uid } = setup();
    let s = editorReducer(state, { type: "unlock", itemId, uid, field: "active" });
    expect(s.drafts[draftKey(uid, "active")]).toBe("3");
    s = editorReducer(s, { type: "draft", uid, field: "active", value: "9" });
    expect(fields(s).active).toBe("3"); // not staged while unlocked
    expect(count(s)).toBe(0);
    expect(openDrafts(s)).toBe(1);
    s = editorReducer(s, { type: "relock", itemId, uid, field: "active" });
    expect(fields(s).active).toBe("9");
    expect(openDrafts(s)).toBe(0);
    expect(count(s)).toBe(1);
    expect(itemStatus(s.ws.items[0]!).moves.get(uid)!.fields.active).toBe("red");
  });

  it("relocking without a change stages nothing", () => {
    const { state, itemId, uid } = setup();
    let s = editorReducer(state, { type: "unlock", itemId, uid, field: "active" });
    s = editorReducer(s, { type: "relock", itemId, uid, field: "active" });
    expect(s.ws).toBe(state.ws);
  });

  it("editing a value back to the original clears the pending change", () => {
    const { state, itemId, uid } = setup();
    const edit = (s: EditorState, value: string) => {
      s = editorReducer(s, { type: "unlock", itemId, uid, field: "active" });
      s = editorReducer(s, { type: "draft", uid, field: "active", value });
      return editorReducer(s, { type: "relock", itemId, uid, field: "active" });
    };
    const changed = edit(state, "9");
    expect(count(changed)).toBe(1);
    expect(count(edit(changed, "3"))).toBe(0);
  });

  it("image is staged directly, no lock", () => {
    const { state, itemId, uid } = setup();
    const s = editorReducer(state, { type: "setImage", itemId, uid, value: "https://img.test/fixed.png" });
    expect(fields(s).image).toBe("https://img.test/fixed.png");
    expect(count(s)).toBe(1);
    expect(isEditable("image", "x")).toBe(false); // never behind a lock
    expect(editorReducer(s, { type: "unlock", itemId, uid, field: "image" })).toBe(s);
  });

  it("alts are edited as a list", () => {
    const { state, itemId, uid } = setup();
    let s = editorReducer(state, { type: "unlock", itemId, uid, field: "alts" });
    s = editorReducer(s, { type: "draft", uid, field: "alts", value: ["5a", "jab"] });
    s = editorReducer(s, { type: "relock", itemId, uid, field: "alts" });
    expect(fields(s).alts).toEqual(["5a", "jab"]);
    expect(saveRequest(pendingChanges(s.ws)).files[0]!.text).toContain('"alts": [\n        "5a",\n        "jab"\n      ]');
  });

  it("an input edit changes identity: the move re-matches the scrape", () => {
    const ws = buildWorkspace(snapshot([item([move("5a")])], [item([move("5A")])]));
    const it = ws.items[0]!;
    // The typo'd data move matches nothing, and the scrape's 5A is staged as new.
    expect(it.moves.map((m) => [m.fields.input, m.isNew])).toEqual([["5A", true], ["5a", false]]);
    const uid = it.moves[1]!.uid;
    let s = editorReducer(initialEditor(ws), { type: "unlock", itemId: it.id, uid, field: "input" });
    s = editorReducer(s, { type: "draft", uid, field: "input", value: "5A" });
    s = editorReducer(s, { type: "relock", itemId: it.id, uid, field: "input" });
    const status = itemStatus(s.ws.items[0]!).moves.get(uid)!;
    expect(status.fields.input).toBe("none"); // now 5A#1: the scrape has no second 5A
  });

  it("non-string values are read-only", () => {
    expect(isEditable("active", PyNumber.fromLexeme("3"))).toBe(false);
    expect(isEditable("alts", ["a", PyNumber.fromLexeme("1")])).toBe(false);
    expect(isEditable("alts", [])).toBe(true);
    expect(isEditable("guard", "LH")).toBe(true);
  });

  it("open drafts are not saved", () => {
    const { state, itemId, uid } = setup();
    let s = editorReducer(state, { type: "unlock", itemId, uid, field: "active" });
    s = editorReducer(s, { type: "draft", uid, field: "active", value: "9" });
    expect(saveRequest(pendingChanges(s.ws)).files).toEqual([]);
  });
});
