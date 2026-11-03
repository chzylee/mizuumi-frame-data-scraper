/**
 * Lock / stage state for editing, as a pure reducer.
 *
 * `image` is edited directly: every keystroke is staged. Every other field is
 * locked by default; unlocking opens a draft, and re-locking stages the draft
 * (or drops it if nothing changed). Drafts that are still open are not part of
 * the pending changes and are never saved.
 */
import { setKey, valueKey, type Json } from "./pyjson";
import { cloneJson, type Workspace } from "./workspace";

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
  | { type: "setImage"; itemId: string; uid: string; value: string };

export function draftKey(uid: string, field: string): string {
  return `${uid}\u0000${field}`;
}

/** Only strings and lists of strings are editable here; anything else is shown read-only. */
export function isEditable(field: string, value: Json | undefined): boolean {
  if (field === "image" || value === undefined) return false;
  return typeof value === "string" || (Array.isArray(value) && value.every((v) => typeof v === "string"));
}

function currentValue(ws: Workspace, itemId: string, uid: string, field: string): Json | undefined {
  const move = ws.items.find((item) => item.id === itemId)?.moves.find((m) => m.uid === uid);
  return move?.fields[field];
}

export function setField(ws: Workspace, itemId: string, uid: string, field: string, value: Json): Workspace {
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
              setKey(fields, field, cloneJson(value));
              return { ...move, fields };
            }),
          },
    ),
  };
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
      return { ws, drafts };
    }
    case "setImage":
      return { ...state, ws: setField(state.ws, action.itemId, action.uid, "image", action.value) };
  }
}

export function openDrafts(state: EditorState): number {
  return Object.keys(state.drafts).length;
}
