import type { Dispatch } from "react";
import type { EditorAction } from "../../shared/editing";
import type { Json } from "../../shared/pyjson";
import { fillableFields, moonLabel, moveLabels, type CharacterGroup, type ItemState, type ItemStatus, type Status } from "../../shared/workspace";
import { StatusDot } from "./CharacterList";
import { MoveCard } from "./MoveCard";

export function MoveList(props: {
  group: CharacterGroup;
  item: ItemState;
  status: ItemStatus;
  statusOfItem: (itemId: string) => Status;
  onSelectItem: (itemId: string) => void;
  drafts: Record<string, Json>;
  dispatch: Dispatch<EditorAction>;
  showDiffs: boolean;
}) {
  const { group, item, status, showDiffs } = props;
  const labels = moveLabels(item);
  // Scrape-only moves are previews: visible only while diffs are on.
  const shown = item.moves.map((move, index) => ({ move, label: labels[index]! })).filter(({ move }) => showDiffs || !move.isNew);
  const dataMoves = item.moves.filter((move) => !move.isNew).length;
  return (
    <section>
      <div className="item-head">
        <h2>{group.label}</h2>
        <div className="moons" role="tablist" aria-label="Moons">
          {group.items.map((it) => (
            <button
              key={it.id}
              role="tab"
              aria-selected={it.id === item.id}
              className={`moon${it.id === item.id ? " active" : ""}`}
              onClick={() => props.onSelectItem(it.id)}
            >
              {moonLabel(it.key.moon)}
              {it.isNew && <span className="tag">preview</span>}
              <StatusDot status={props.statusOfItem(it.id)} />
            </button>
          ))}
        </div>
        <p className="path">
          {item.isNew ? (
            <span className="tag">only in scrape · preview, not saved (no data/{item.path})</span>
          ) : (
            <>
              <code>data/{item.path}</code> · {dataMoves} moves
              {showDiffs && dataMoves < item.moves.length && <> · {item.moves.length - dataMoves} more only in scrape</>}
            </>
          )}
        </p>
      </div>
      <div className="moves">
        {shown.map(({ move, label }) => (
          <MoveCard
            key={move.uid}
            itemId={item.id}
            move={move}
            label={label}
            preview={item.isNew || move.isNew}
            fillable={fillableFields(item, move)}
            status={status.moves.get(move.uid)!}
            drafts={props.drafts}
            dispatch={props.dispatch}
            showDiffs={showDiffs}
          />
        ))}
      </div>
    </section>
  );
}
