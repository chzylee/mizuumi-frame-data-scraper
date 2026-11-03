/**
 * Lock / stage state for editing, as a pure reducer.
 *
 * `image` is edited directly: every keystroke is staged. Every other field is
 * locked by default; unlocking opens a draft, and re-locking stages the draft
 * (or drops it if nothing changed). Drafts that are still open are not part of
 * the pending changes and are never saved.
 */
import { setKey, valueKey, type Json, type JsonObject } from "./pyjson";
import { cloneJson, type MoveState, type Workspace } from "./workspace";

export interface EditorState {
  ws: Workspace;
  /** Open drafts, keyed by draftKey(uid, field). */
  drafts: Record<string, Json>;
}

export type EditorAction =
  | { type: "load"; ws: Workspace }
  | { type: "unlock"; itemId: string; uid: string; field: string }
  | { type: "draft"; uid: string; field: string; value: Json }
  | { type: "relock"; itemId: string; uid: string; field: string }
  | { type: "setImage"; itemId: string; uid: string; value: string }
  /** Type into a field the move was missing: no lock. Clearing a text field makes it missing again. */
  | { type: "fill"; itemId: string; uid: string; field: string; value: Json };

export function draftKey(uid: string, field: string): string {
  return `${uid}\u0000${field}`;
}

/** Only strings and lists of strings are editable here; anything else is shown read-only. */
export function isEditable(field: string, value: Json | undefined): boolean {
  if (field === "image" || value === undefined) return false;
  return typeof value === "string" || (Array.isArray(value) && value.every((v) => typeof v === "string"));
}

/** The data/ move being edited; undefined for a scrape-only preview, which is read-only. */
function editableMove(ws: Workspace, itemId: string, uid: string): MoveState | undefined {
  const item = ws.items.find((it) => it.id === itemId);
  const move = item?.moves.find((m) => m.uid === uid);
  if (!item || !move || item.isNew || move.isNew) return undefined;
  return move;
}

function currentValue(ws: Workspace, itemId: string, uid: string, field: string): Json | undefined {
  return editableMove(ws, itemId, uid)?.fields[field];
}

function updateMove(ws: Workspace, itemId: string, uid: string, update: (fields: JsonObject) => void): Workspace {
  return {
    ...ws,
    items: ws.items.map((item) =>
      item.id !== itemId
        ? item
        : {
            ...item,
            moves: item.moves.map((move) => {
              if (move.uid !== uid) return move;
              const fields = cloneJson(move.fields);
              update(fields);
              return { ...move, fields };
            }),
          },
    ),
  };
}

export function setField(ws: Workspace, itemId: string, uid: string, field: string, value: Json): Workspace {
  return updateMove(ws, itemId, uid, (fields) => setKey(fields, field, cloneJson(value)));
}

function removeField(ws: Workspace, itemId: string, uid: string, field: string): Workspace {
  return updateMove(ws, itemId, uid, (fields) => {
    delete fields[field];
  });
}

export function initialEditor(ws: Workspace): EditorState {
  return { ws, drafts: {} };
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "load":
      return initialEditor(action.ws);
    case "unlock": {
      const key = draftKey(action.uid, action.field);
      const value = currentValue(state.ws, action.itemId, action.uid, action.field);
      if (key in state.drafts || !isEditable(action.field, value)) return state;
      return { ...state, drafts: { ...state.drafts, [key]: cloneJson(value!) } };
    }
    case "draft": {
      const key = draftKey(action.uid, action.field);
      if (!(key in state.drafts)) return state; // locked: ignore
      return { ...state, drafts: { ...state.drafts, [key]: action.value } };
    }
    case "relock": {
      const key = draftKey(action.uid, action.field);
      if (!(key in state.drafts)) return state;
      const { [key]: draft, ...drafts } = state.drafts;
      const current = currentValue(state.ws, action.itemId, action.uid, action.field);
      const ws = valueKey(draft) === valueKey(current) ? state.ws : setField(state.ws, action.itemId, action.uid, action.field, draft!);
      return { ...state, ws, drafts };
    }
    case "setImage":
      if (!editableMove(state.ws, action.itemId, action.uid)) return state;
      return { ...state, ws: setField(state.ws, action.itemId, action.uid, "image", action.value) };
    case "fill": {
      if (!editableMove(state.ws, action.itemId, action.uid)) return state;
      // An emptied text field is removed again, so it reads as missing instead of saving "".
      const ws =
        action.value === ""
          ? removeField(state.ws, action.itemId, action.uid, action.field)
          : setField(state.ws, action.itemId, action.uid, action.field, action.value);
      return { ...state, ws };
    }
  }
}

export function openDrafts(state: EditorState): number {
  return Object.keys(state.drafts).length;
}
