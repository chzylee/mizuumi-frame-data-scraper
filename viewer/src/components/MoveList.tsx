import type { Dispatch } from "react";
import type { EditorAction } from "../../shared/editing";
import type { Json } from "../../shared/pyjson";
import { moonLabel, moveLabels, type CharacterGroup, type ItemState, type ItemStatus, type Status } from "../../shared/workspace";
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
              {it.isNew && <span className="tag">new</span>}
              <StatusDot status={props.statusOfItem(it.id)} show={showDiffs} />
            </button>
          ))}
        </div>
        <p className="path">
          <code>data/{item.path}</code> {item.isNew && <span className="tag">new file, written on save</span>} ·{" "}
          {item.moves.length} moves
        </p>
      </div>
      <div className="moves">
        {item.moves.map((move, index) => (
          <MoveCard
            key={move.uid}
            itemId={item.id}
            move={move}
            label={labels[index]!}
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
