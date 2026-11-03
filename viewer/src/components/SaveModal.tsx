import { useEffect, useRef } from "react";
import type { Json } from "../../shared/pyjson";
import { displayName, displayValue, moonLabel, type ItemChanges } from "../../shared/workspace";

export type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "error"; message: string; problems: string[] };

function show(value: Json | undefined) {
  return value === undefined ? <span className="muted">(none)</span> : <code>{displayValue(value) || '""'}</code>;
}

/** Every pending change, grouped character -> moon -> move, confirmed or cancelled. */
export function SaveModal(props: {
  changes: ItemChanges[];
  /** The user's own edits since load. */
  edits: number;
  /** Scrape additions staged at load (new characters, moons, moves, fields). */
  additions: number;
  openDrafts: number;
  state: SaveState;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { changes, edits, additions, openDrafts, state, onCancel, onConfirm } = props;
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const byCharacter = new Map<string, ItemChanges[]>();
  for (const change of changes) {
    const name = change.item.key.character_name;
    byCharacter.set(name, [...(byCharacter.get(name) ?? []), change]);
  }
  const saving = state.kind === "saving";

  return (
    <dialog ref={dialog} className="modal" aria-labelledby="save-title" onCancel={(e) => { e.preventDefault(); if (!saving) onCancel(); }}>
      <header className="modal-head">
        <h2 id="save-title">
          Save {edits} edit{edits === 1 ? "" : "s"}
          {additions > 0 && <> and {additions} new from the scrape</>} to {changes.length} file{changes.length === 1 ? "" : "s"}?
        </h2>
        <p className="muted">Written to data/ only. Nothing is committed or pushed.</p>
      </header>
      <div className="modal-body">
        {openDrafts > 0 && (
          <p className="banner banner-warn">
            {openDrafts} field{openDrafts === 1 ? " is" : "s are"} still unlocked. Unlocked edits are not staged: they are not saved, and
            they are discarded when the viewer reloads after saving. Cancel and lock them first to include them.
          </p>
        )}
        {state.kind === "error" && (
          <div className="banner banner-error" role="alert">
            <strong>{state.message}</strong>
            {state.problems.length > 0 && <ul>{state.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>}
          </div>
        )}
        {[...byCharacter.entries()].map(([name, items]) => (
          <section key={name} className="change-char">
            <h3>{displayName(name)}</h3>
            {items.map(({ item, moves }) => (
              <div key={item.id} className="change-moon">
                <h4>
                  {moonLabel(item.key.moon)} <code className="muted">data/{item.path}</code>
                  {item.isNew && <span className="tag new">new file</span>}
                </h4>
                <ul className="change-moves">
                  {moves.map((move) => (
                    <li key={move.uid}>
                      <span className="change-move">{move.label}</span>
                      {move.isNew && <span className="tag new">new move</span>}
                      <ul className="change-fields">
                        {move.fields.map((f) => (
                          <li key={f.field}>
                            <span className="field-name">{f.field}</span>{" "}
                            {move.isNew ? show(f.new) : <>{show(f.old)} → {show(f.new)}</>}
                            {!move.isNew && f.old === undefined && <span className="tag new">new</span>}
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        ))}
      </div>
      <footer className="modal-foot">
        <button onClick={onCancel} disabled={saving}>Cancel</button>
        <button className="primary" onClick={onConfirm} disabled={saving || changes.length === 0} autoFocus>
          {saving ? "Saving…" : "Confirm and write files"}
        </button>
      </footer>
    </dialog>
  );
}
