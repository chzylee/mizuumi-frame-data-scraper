import { memo, useState, type Dispatch } from "react";
import { draftKey, isEditable, type EditorAction } from "../../shared/editing";
import { has, type Json } from "../../shared/pyjson";
import { displayValue, fieldOrder, type MoveState, type MoveStatus } from "../../shared/workspace";
import { STATUS_TEXT, StatusDot } from "./CharacterList";
import { LockIcon } from "./icons";

interface Props {
  itemId: string;
  move: MoveState;
  label: string;
  status: MoveStatus;
  drafts: Record<string, Json>;
  dispatch: Dispatch<EditorAction>;
  showDiffs: boolean;
}

/** One move: its hitbox image and every field present, rendered generically. */
export const MoveCard = memo(function MoveCard({ itemId, move, label, status, drafts, dispatch, showDiffs }: Props) {
  const image = move.fields.image;
  const fields = fieldOrder(move.fields).filter((field) => field !== "image");
  return (
    <article className={`move${showDiffs ? ` s-${status.status}` : ""}`} aria-label={`Move ${label}`}>
      <header className="move-head">
        <h3>{label}</h3>
        {move.isNew && <span className="tag">new move</span>}
        <StatusDot status={status.status} show={showDiffs} />
      </header>
      <div className="move-body">
        <div className="hitbox">
          <HitboxPreview src={typeof image === "string" ? image : ""} label={label} />
          {typeof image === "string" ? (
            <label className="image-field">
              <span className="field-name">image</span>
              <input
                type="url"
                value={image}
                spellCheck={false}
                onChange={(e) => dispatch({ type: "setImage", itemId, uid: move.uid, value: e.target.value })}
              />
            </label>
          ) : (
            image !== undefined && <code className="readonly">{displayValue(image)}</code>
          )}
        </div>
        <table className="fields">
          <tbody>
            {fields.map((field) => (
              <FieldRow
                key={field}
                itemId={itemId}
                uid={move.uid}
                field={field}
                value={move.fields[field]!}
                draft={drafts[draftKey(move.uid, field)]}
                unlocked={draftKey(move.uid, field) in drafts}
                fieldStatus={showDiffs ? status.fields[field] ?? "none" : "none"}
                scraped={status.scraped && has(status.scraped, field) ? status.scraped[field] : undefined}
                dispatch={dispatch}
              />
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
});

function HitboxPreview({ src, label }: { src: string; label: string }) {
  const [failed, setFailed] = useState<string | null>(null);
  if (!src) return <div className="no-image">no image URL</div>;
  if (failed === src) return <div className="no-image">image did not load</div>;
  return <img src={src} alt={`Hitbox for ${label}`} loading="lazy" onError={() => setFailed(src)} />;
}

function FieldRow(props: {
  itemId: string;
  uid: string;
  field: string;
  value: Json;
  draft: Json | undefined;
  unlocked: boolean;
  fieldStatus: MoveStatus["fields"][string];
  scraped: Json | undefined;
  dispatch: Dispatch<EditorAction>;
}) {
  const { itemId, uid, field, value, draft, unlocked, fieldStatus, scraped, dispatch } = props;
  const editable = isEditable(field, value);
  const toggle = () => dispatch({ type: unlocked ? "relock" : "unlock", itemId, uid, field });
  const setDraft = (next: Json) => dispatch({ type: "draft", uid, field, value: next });
  return (
    <tr className={`field s-${fieldStatus}`} title={STATUS_TEXT[fieldStatus] || undefined}>
      <th scope="row" className="field-name">{field}</th>
      <td className="field-value">
        {unlocked && Array.isArray(draft) ? (
          <ListEditor values={draft as string[]} onChange={setDraft} onDone={toggle} />
        ) : unlocked ? (
          <input
            autoFocus
            value={draft as string}
            spellCheck={false}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && toggle()}
          />
        ) : Array.isArray(value) && editable ? (
          value.length ? (
            <span className="chips">{(value as string[]).map((v, i) => <span key={i} className="chip">{v}</span>)}</span>
          ) : (
            <span className="muted">none</span>
          )
        ) : (
          <span className={editable ? "" : "readonly"}>{displayValue(value) || <span className="muted">empty</span>}</span>
        )}
        {fieldStatus === "red" && <span className="scraped" title="scraped value">{displayValue(scraped)}</span>}
      </td>
      <td className="lock-cell">
        {editable && (
          <button
            className={`lock${unlocked ? " open" : ""}`}
            onClick={toggle}
            aria-label={unlocked ? `Lock ${field} and stage the edit` : `Unlock ${field} to edit`}
            title={unlocked ? "Lock to stage the edit" : "Unlock to edit"}
          >
            <LockIcon open={unlocked} />
          </button>
        )}
      </td>
    </tr>
  );
}

function ListEditor({ values, onChange, onDone }: { values: string[]; onChange: (v: string[]) => void; onDone: () => void }) {
  return (
    <div className="list-editor">
      {values.map((value, i) => (
        <div key={i} className="list-row">
          <input
            autoFocus={i === values.length - 1}
            value={value}
            spellCheck={false}
            onChange={(e) => onChange(values.map((v, j) => (j === i ? e.target.value : v)))}
            onKeyDown={(e) => e.key === "Enter" && onDone()}
            aria-label={`Item ${i + 1}`}
          />
          <button className="icon" onClick={() => onChange(values.filter((_, j) => j !== i))} aria-label={`Remove item ${i + 1}`}>
            ×
          </button>
        </div>
      ))}
      <button className="link" onClick={() => onChange([...values, ""])}>+ add</button>
    </div>
  );
}
