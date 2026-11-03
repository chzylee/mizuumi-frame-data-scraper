import type { CharacterGroup, Status } from "../../shared/workspace";

/** The status already reflects the diff toggle (missing fields are red regardless). */
export function StatusDot({ status }: { status: Status }) {
  if (status === "none") return null;
  return <span className={`dot ${status}`} aria-label={STATUS_TEXT[status]} title={STATUS_TEXT[status]} />;
}

export const STATUS_TEXT: Record<Status, string> = {
  none: "",
  green: "matches the scrape",
  red: "differs from the scrape, or has missing fields",
  blue: "only in the scrape (preview, not saved)",
};

export function CharacterList(props: {
  groups: CharacterGroup[];
  selected: string | null;
  onSelect: (name: string) => void;
  statusOf: (group: CharacterGroup) => Status;
  showDiffs: boolean;
}) {
  return (
    <nav className="sidebar" aria-label="Characters">
      <ul>
        {props.groups.map((group) => (
          <li key={group.name}>
            <button
              className={`char${group.name === props.selected ? " active" : ""}`}
              aria-current={group.name === props.selected ? "true" : undefined}
              onClick={() => props.onSelect(group.name)}
            >
              <span className="char-label">{group.label}</span>
              {group.short && <span className="char-short">{group.short}</span>}
              <StatusDot status={props.statusOf(group)} />
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
