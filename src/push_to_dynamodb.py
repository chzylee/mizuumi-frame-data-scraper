"""Push: make the DynamoDB table match data/. The only table writer.

Run by .github/workflows/push-to-dynamodb.yml (manual dispatch). Plan mode is the
default: the same code path, stopping short of put_item. --apply writes.

    python -m push_to_dynamodb [--apply]

Per item (named by its data/ path without .json), the plan is one of:
  insert     - no table item yet
  update     - table item differs from data/ (a per-move diff is printed)
  unchanged  - table item already matches data/
  table-only - table item with no data/ file: reported, NEVER deleted

"Differs" compares a content hash computed the same way over both sides (the
table side minus its stored content_hash, which a console edit leaves stale),
so a console edit is noticed and overwritten with data/.
"""
import argparse
import os
import sys
from typing import Dict, List

import dataset
import dynamo

WRITE_STATUSES = ("insert", "update")
REPORT_ORDER = ("insert", "update", "unchanged", "table-only")


def diff_items(old: dict, new: dict) -> List[str]:
    """Readable per-move diff of two versions of one item."""
    lines = []
    for key in sorted(set(old) | set(new)):
        if key in ("moves", dataset.HASH_ATTR) or old.get(key) == new.get(key):
            continue
        lines.append(f"attribute {key}: {_show(old, key)} -> {_show(new, key)}")

    old_moves, new_moves = old.get("moves", []), new.get("moves", [])
    old_ids, new_ids = dataset.move_identities(old_moves), dataset.move_identities(new_moves)
    old_by_id, new_by_id = dict(zip(old_ids, old_moves)), dict(zip(new_ids, new_moves))
    for identity in old_ids:
        if identity not in new_by_id:
            lines.append(f"- removed move {dataset.describe_identity(identity)}")
    for identity in new_ids:
        if identity not in old_by_id:
            lines.append(f"+ added move {dataset.describe_identity(identity)}")
    for identity in new_ids:
        if identity in old_by_id and old_by_id[identity] != new_by_id[identity]:
            old_move, new_move = old_by_id[identity], new_by_id[identity]
            changes = [
                f"{field}: {_show(old_move, field)} -> {_show(new_move, field)}"
                for field in sorted(set(old_move) | set(new_move))
                if old_move.get(field) != new_move.get(field) or (field in old_move) != (field in new_move)
            ]
            lines.append(f"~ {dataset.describe_identity(identity)}: {'; '.join(changes)}")
    common_old = [i for i in old_ids if i in new_by_id]
    common_new = [i for i in new_ids if i in old_by_id]
    if common_old != common_new:
        lines.append("move order changed")
    return lines


def _show(obj: dict, key: str) -> str:
    return repr(obj[key]) if key in obj else "(absent)"


def plan(desired: Dict[str, dict], live: Dict[str, dict]) -> List[dict]:
    """Decide what to do with every item, touching nothing.

    desired: {path: item} from data/. live: {path: item} from the table, already
    passed through dataset.item_from_table. Returns one dict per item:
    {name, path, status, detail, item}.
    """
    plans = []
    for path in sorted(desired):
        want, have = desired[path], live.get(path)
        entry = {"name": dataset.item_name(path), "path": path, "item": want}
        if have is None:
            entry["status"], entry["detail"] = "insert", [f"new item, {len(want.get('moves', []))} moves"]
        elif dataset.item_hash(have) == dataset.item_hash(want):
            entry["status"], entry["detail"] = "unchanged", []
        else:
            entry["status"], entry["detail"] = "update", diff_items(have, want)
        plans.append(entry)
    for path in sorted(set(live) - set(desired)):
        plans.append({"name": dataset.item_name(path), "path": path, "item": live[path],
                      "status": "table-only",
                      "detail": ["in the table but not in data/; left untouched (never deleted)"]})
    return plans


def execute(table, plans: List[dict], apply: bool) -> None:
    """Write every insert/update when applying. Sets entry["result"] on each."""
    for entry in plans:
        if entry["status"] not in WRITE_STATUSES:
            entry["result"] = "not written"
        elif not apply:
            entry["result"] = "would write"
        else:
            item = entry["item"]
            table.put_item(Item=dataset.to_dynamo({**item, dataset.HASH_ATTR: dataset.item_hash(item)}))
            entry["result"] = "written"


def run(table, data_dir: str, apply: bool = False) -> List[dict]:
    """Validate data/, read the table, plan, and (when applying) write."""
    errors = dataset.validate_dir(data_dir)
    if errors:
        raise ValueError("data/ is invalid, refusing to push:\n" + "\n".join(errors))
    desired = dataset.load_dir(data_dir)
    live = {}
    for raw in dynamo.scan_all(table):
        live[dataset.path_for(raw)] = dataset.item_from_table(raw)
    plans = plan(desired, live)
    execute(table, plans, apply)
    return plans


def _counts(plans: List[dict]) -> str:
    return ", ".join(f"{s}: {sum(1 for p in plans if p['status'] == s)}" for s in REPORT_ORDER)


def format_text(plans: List[dict], apply: bool) -> str:
    lines = [f"=== Push to DynamoDB: {'APPLY' if apply else 'PLAN, nothing written'} ==="]
    for entry in plans:
        if entry["status"] == "unchanged":
            continue
        lines.append(f"{entry['status']:11} {entry['name']}  [{entry['result']}]")
        lines.extend(f"    {line}" for line in entry["detail"])
    lines.append(_counts(plans))
    return "\n".join(lines)


def format_markdown(plans: List[dict], apply: bool) -> str:
    lines = [f"## Push to DynamoDB: {'apply' if apply else 'plan (nothing written)'}",
             "", f"**{_counts(plans)}**", ""]
    for entry in plans:
        if entry["status"] == "unchanged":
            continue
        lines += [f"<details><summary><code>{entry['name']}</code>: {entry['status']}, "
                  f"{entry['result']}</summary>", "", "```", *entry["detail"], "```", "</details>"]
    return "\n".join(lines) + "\n"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Make the DynamoDB table match data/ (plan mode by default).")
    parser.add_argument("--apply", action="store_true", help="write the planned changes (default: plan only)")
    parser.add_argument("--data-dir", default=dataset.DATA_DIRECTORY)
    parser.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args(argv)

    plans = run(dynamo.get_table(), args.data_dir, args.apply)
    print(format_text(plans, args.apply))
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as summary:
            summary.write(format_markdown(plans, args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
