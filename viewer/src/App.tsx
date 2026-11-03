/**
 * The app shell: loads a snapshot from a DataSource, holds the editor state,
 * and wires the display components. Display components never see the
 * DataSource, so a read-only static source can reuse them unchanged.
 */
import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import { SaveRefused, type DataSource, type Snapshot } from "../shared/api";
import { editorReducer, initialEditor, openDrafts } from "../shared/editing";
import {
  buildWorkspace,
  countChanges,
  groupCharacters,
  itemStatus,
  pendingChanges,
  rollup,
  saveRequest,
  type ItemStatus,
} from "../shared/workspace";
import { CharacterList } from "./components/CharacterList";
import { MoveList } from "./components/MoveList";
import { Navbar } from "./components/Navbar";
import { SaveModal, type SaveState } from "./components/SaveModal";

export function App({ source }: { source: DataSource }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [state, dispatch] = useReducer(editorReducer, undefined, () =>
    initialEditor(buildWorkspace({ dataRoot: "", scrapedRoot: "", data: { status: "missing" }, scraped: null, charMappings: [] })),
  );
  const [showDiffs, setShowDiffs] = useState(false);
  const [selected, setSelected] = useState<{ character: string | null; itemId: string | null }>({ character: null, itemId: null });
  const [modalOpen, setModalOpen] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });
  const [notice, setNotice] = useState<{ files: number; warnings: string[] } | null>(null);

  const load = useCallback(async () => {
    try {
      const snap = await source.load();
      setSnapshot(snap);
      dispatch({ type: "load", ws: buildWorkspace(snap) });
      setLoadError(null);
    } catch (error) {
      setLoadError((error as Error).message);
    }
  }, [source]);

  useEffect(() => {
    void load();
  }, [load]);

  const ws = state.ws;
  // Characters and moons only in the scrape are previews: listed only while diffs are on.
  const visible = useMemo(() => (showDiffs ? ws : { ...ws, items: ws.items.filter((item) => !item.isNew) }), [ws, showDiffs]);
  const groups = useMemo(() => groupCharacters(visible), [visible]);
  const statuses = useMemo(() => new Map<string, ItemStatus>(ws.items.map((item) => [item.id, itemStatus(item)])), [ws]);
  const changes = useMemo(() => pendingChanges(ws), [ws]);
  const pending = countChanges(changes);
  const drafts = openDrafts(state);

  // Pick a character and moon once data arrives (and keep the pick across reloads).
  useEffect(() => {
    if (!groups.length) return;
    setSelected((current) => {
      const group = groups.find((g) => g.name === current.character) ?? groups[0]!;
      const item = group.items.find((it) => it.id === current.itemId) ?? group.items[0]!;
      return current.character === group.name && current.itemId === item.id ? current : { character: group.name, itemId: item.id };
    });
  }, [groups]);

  // Block refresh/close while edits would be lost.
  useEffect(() => {
    if (pending === 0 && drafts === 0) return;
    const warn = (event: BeforeUnloadEvent) => {
      // preventDefault() is what asks current browsers to prompt. Some older ones
      // prompt only when returnValue is set to a non-empty string; none show the text.
      event.preventDefault();
      event.returnValue = "You have unsaved changes.";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [pending, drafts]);

  const confirmSave = async () => {
    if (!source.save) return;
    setSaveState({ kind: "saving" });
    try {
      const result = await source.save(saveRequest(changes));
      const n = result.written.filter((w) => w.status !== "unchanged").length;
      setModalOpen(false);
      setSaveState({ kind: "idle" });
      setNotice({ files: n, warnings: result.warnings });
      await load();
    } catch (error) {
      const problems = error instanceof SaveRefused ? error.problems : [];
      setSaveState({ kind: "error", message: (error as Error).message, problems });
    }
  };

  const group = groups.find((g) => g.name === selected.character) ?? null;
  const item = group?.items.find((it) => it.id === selected.itemId) ?? null;

  return (
    <div className="app">
      <Navbar
        showDiffs={showDiffs && ws.scrapedAvailable}
        onShowDiffs={setShowDiffs}
        scrapedAvailable={ws.scrapedAvailable}
        pending={pending}
        canSave={Boolean(source.save)}
        onSave={() => {
          setSaveState({ kind: "idle" });
          setModalOpen(true);
        }}
      />
      {notice && (
        <div className="banner banner-ok" role="status">
          <span>
            Saved {notice.files} file{notice.files === 1 ? "" : "s"}. Commit and push to main (or merge your PR), then
            run <em>Push to DynamoDB</em> to sync.
            {notice.warnings.length > 0 && <> Warnings: {notice.warnings.join("; ")}</>}
          </span>
          <button className="link" onClick={() => setNotice(null)}>Dismiss</button>
        </div>
      )}
      {loadError && <div className="banner banner-error">Could not load: {loadError}</div>}
      {ws.dataErrors.length > 0 && (
        <div className="banner banner-error" role="alert">
          <strong>
            {ws.dataErrors.length} data/ file{ws.dataErrors.length === 1 ? "" : "s"} could not be loaded. Fix or restore{" "}
            {ws.dataErrors.length === 1 ? "it" : "each one"} (resolve the merge conflict, or{" "}
            <code>git checkout -- data/&lt;path&gt;</code>), then reload.
          </strong>{" "}
          Until then {ws.dataErrors.length === 1 ? "it is" : "they are"} not shown, not compared, and never written; the
          rest can still be edited and saved.
          <ul>
            {ws.dataErrors.map((f) => (
              <li key={f.path}>
                <code>data/{f.path}</code>: {f.error}
              </li>
            ))}
          </ul>
        </div>
      )}
      {ws.problems.length > 0 && (
        <details className="banner banner-warn">
          <summary>{ws.problems.length} scraped file(s) or item(s) could not be compared</summary>
          <ul>{ws.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </details>
      )}
      {snapshot && snapshot.data.status !== "ok" ? (
        <NoData root={snapshot.dataRoot} empty={snapshot.data.status === "empty"} />
      ) : (
        <div className="layout">
          <CharacterList
            groups={groups}
            selected={selected.character}
            onSelect={(name) => {
              const g = groups.find((x) => x.name === name)!;
              setSelected({ character: name, itemId: g.items[0]?.id ?? null });
            }}
            statusOf={(g) => rollup(g.items.map((it) => statuses.get(it.id)!.status))}
            showDiffs={showDiffs && ws.scrapedAvailable}
          />
          <main className="content">
            {group && item ? (
              <MoveList
                group={group}
                item={item}
                status={statuses.get(item.id)!}
                statusOfItem={(id) => statuses.get(id)!.status}
                onSelectItem={(itemId) => setSelected({ character: group.name, itemId })}
                drafts={state.drafts}
                dispatch={dispatch}
                showDiffs={showDiffs && ws.scrapedAvailable}
              />
            ) : (
              snapshot && <p className="muted">No items.</p>
            )}
          </main>
        </div>
      )}
      {modalOpen && (
        <SaveModal
          changes={changes}
          count={pending}
          openDrafts={drafts}
          state={saveState}
          onCancel={() => setModalOpen(false)}
          onConfirm={() => void confirmSave()}
        />
      )}
    </div>
  );
}

function NoData({ root, empty }: { root: string; empty: boolean }) {
  return (
    <div className="empty-state">
      <h2>{empty ? "data/ is empty" : "No data/ directory"}</h2>
      <p>
        Looked in <code>{root}</code>. <code>data/</code> comes only from the DynamoDB pull, because the table holds
        hand-fixed image URLs; the viewer never builds it from the scrape.
      </p>
      <p>
        Pull it first: from <code>src</code>, run <code>AWS_PROFILE=mizuumi-read python -m pull_from_dynamodb</code>, or
        run <em>Pull from DynamoDB</em> and check out its PR. Then reload.
      </p>
    </div>
  );
}
