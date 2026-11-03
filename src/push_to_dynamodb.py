"""Push: write data/ to the DynamoDB table, safely. The only table writer.

Run by .github/workflows/push-to-dynamodb.yml. A dry run (the default) goes down
the same code path and stops short of put_item.

    python -m push_to_dynamodb [--write] [--force NAMES] [--allow-move-removal NAMES]

NAMES are comma-separated item names, i.e. data/ filenames without .json
(e.g. "akiha-C,ciel-H").

Per item (named by its data/ file), the plan is one of:
  insert     - no table item yet
  update     - table item differs from data/ (a per-move diff is printed)
  unchanged  - table item already equals data/
  table-only - table item with no data/ file: reported, NEVER deleted
  refused    - not written, with the reason:
      drift        - the live item matches no version of its data/ file recorded
                     at or after the baseline commit, so it was changed outside
                     the pipeline and overwriting it could lose that change.
                     Override per item with --force.
      move-removal - the update would remove moves. Allow per item with
                     --allow-move-removal.

The drift baseline is the git tag `dynamodb-deployed` (moved by the workflow
after a successful real push). The live item is "known" when it equals its
data/ file at the tag commit or at any commit after it on the pushed history,
which covers pull PRs merged since the last push. With no tag yet, every commit
in the pushed history counts, so the bootstrap pull is the baseline: a console
edit made after that pull is still refused.

Every write is conditional on the live item being exactly what was read, so a
change between the read and the write fails instead of being overwritten.
"""
import argparse
import os
import sys
from typing import Dict, List, Optional, Set

import dataset
import dynamo
from baseline import ABSENT, BASELINE_TAG, known_states, state_of  # noqa: F401 (re-exported)

WRITE_STATUSES = ("insert", "update")
REPORT_ORDER = ("insert", "update", "unchanged", "table-only", "refused")


# --- planning ----------------------------------------------------------------------

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


def plan(desired: Dict[str, dict], live: Dict[str, dict], known: Dict[str, Set[str]],
         force: Set[str] = frozenset(), allow_move_removal: Set[str] = frozenset()) -> List[dict]:
    """Decide what to do with every item, touching nothing.

    desired: {filename: item} from data/. live: {filename: item} from the table,
    already passed through dataset.item_from_table. known: from known_states().
    Returns one dict per item: {name, file, status, reason, detail, item}.
    """
    plans = []
    for file in sorted(desired):
        name = dataset.item_name(file)
        want, have = desired[file], live.get(file)
        entry = {"name": name, "file": file, "item": want, "reason": None, "detail": []}
        plans.append(entry)

        if have == want:
            entry["status"] = "unchanged"
            continue

        drifted = state_of(have) not in known.get(file, set())
        if drifted and name not in force:
            entry["status"], entry["reason"] = "refused", "drift"
            entry["detail"] = [
                "the live item matches no version of this file recorded since the baseline; "
                "it was changed outside the pipeline. Run the pull workflow to capture it, "
                "or name it in force to overwrite it."
            ] + (diff_items(have, want) if have is not None else ["(the live item was deleted)"])
            continue
        forced_note = ["forced past drift guard"] if drifted else []

        if have is None:
            entry["status"] = "insert"
            entry["detail"] = forced_note + [f"new item, {len(want.get('moves', []))} moves"]
            continue

        detail = forced_note + diff_items(have, want)
        removed = [i for i in dataset.move_identities(have.get("moves", []))
                   if i not in set(dataset.move_identities(want.get("moves", [])))]
        if removed and name not in allow_move_removal:
            entry["status"], entry["reason"] = "refused", "move-removal"
            entry["detail"] = [f"would remove {len(removed)} move(s); name it in "
                               "allow_move_removal to permit this"] + detail
            continue
        entry["status"], entry["detail"] = "update", detail

    for file in sorted(set(live) - set(desired)):
        plans.append({"name": dataset.item_name(file), "file": file, "item": live[file],
                      "status": "table-only", "reason": None,
                      "detail": ["in the table but not in data/; left untouched (never deleted)"]})
    return plans


# --- writing -----------------------------------------------------------------------

def condition_for(live_raw: Optional[dict]) -> dict:
    """put_item kwargs that make the write fail if the item moved since it was read."""
    names = {"#pk": dataset.PARTITION_KEY}
    if live_raw is None:
        return {"ConditionExpression": "attribute_not_exists(#pk)", "ExpressionAttributeNames": names}
    terms, values = ["attribute_exists(#pk)"], {}
    for index, attr in enumerate(sorted(a for a in live_raw if a not in (dataset.PARTITION_KEY, dataset.SORT_KEY))):
        names[f"#a{index}"] = attr
        values[f":v{index}"] = live_raw[attr]
        terms.append(f"#a{index} = :v{index}")
    kwargs = {"ConditionExpression": " AND ".join(terms), "ExpressionAttributeNames": names}
    if values:
        kwargs["ExpressionAttributeValues"] = values
    return kwargs


def execute(table, plans: List[dict], live_raw: Dict[str, dict], dry_run: bool) -> None:
    """Write every insert/update (unless dry_run). Sets entry["result"] on each."""
    for entry in plans:
        if entry["status"] not in WRITE_STATUSES:
            entry["result"] = "not written"
            continue
        if dry_run:
            entry["result"] = "would write"
            continue
        item = entry["item"]
        try:
            table.put_item(Item=dataset.to_dynamo({**item, dataset.HASH_ATTR: dataset.item_hash(item)}),
                           **condition_for(live_raw.get(entry["file"])))
            entry["result"] = "written"
        except Exception as error:
            if not dynamo.is_conditional_check_failure(error):
                raise
            entry["result"] = "conflict"
            entry["detail"] = ["CONFLICT: the item changed between read and write; nothing "
                               "was overwritten. Re-run."] + entry["detail"]


def run(table, data_dir: str, known: Dict[str, Set[str]], dry_run: bool = True,
        force: Set[str] = frozenset(), allow_move_removal: Set[str] = frozenset()) -> List[dict]:
    """Validate data/, read the table, plan, and (unless dry_run) write."""
    errors = dataset.validate_dir(data_dir)
    if errors:
        raise ValueError("data/ is invalid, refusing to push:\n" + "\n".join(errors))
    desired = dataset.load_dir(data_dir)
    live_raw = {}
    for raw in dynamo.scan_all(table):
        live_raw[dataset.filename_for_key(raw[dataset.PARTITION_KEY], raw[dataset.SORT_KEY])] = raw
    live = {file: dataset.item_from_table(raw) for file, raw in live_raw.items()}

    names = {dataset.item_name(file) for file in set(desired) | set(live)}
    for label, chosen in (("force", force), ("allow_move_removal", allow_move_removal)):
        unknown = sorted(set(chosen) - names)
        if unknown:
            raise ValueError(f"{label} names unknown item(s): {', '.join(unknown)}")

    plans = plan(desired, live, known, force, allow_move_removal)
    execute(table, plans, live_raw, dry_run)
    return plans


def succeeded(plans: List[dict]) -> bool:
    """True when nothing was refused or conflicted: the table now mirrors data/
    for every data/ file, so the baseline tag may move."""
    return all(p["status"] != "refused" and p.get("result") != "conflict" for p in plans)


# --- reporting ---------------------------------------------------------------------

def _label(entry: dict) -> str:
    label = entry["status"] + (f" ({entry['reason']})" if entry["reason"] else "")
    if entry.get("result") == "conflict":
        label = "CONFLICT"
    return label


def format_text(plans: List[dict], dry_run: bool, baseline: str) -> str:
    lines = [f"=== Push plan ({'DRY RUN, nothing written' if dry_run else 'WRITE'}) ===",
             f"baseline: {baseline}"]
    for entry in plans:
        if entry["status"] == "unchanged":
            continue
        lines.append(f"{_label(entry):24} {entry['name']}  [{entry.get('result', '')}]")
        lines.extend(f"    {line}" for line in entry["detail"])
    lines.append(_counts(plans))
    return "\n".join(lines)


def format_markdown(plans: List[dict], dry_run: bool, baseline: str) -> str:
    lines = [f"## Push to DynamoDB: {'dry run (nothing written)' if dry_run else 'write'}",
             "", f"Baseline: {baseline}", "", f"**{_counts(plans)}**", ""]
    for entry in plans:
        if entry["status"] == "unchanged":
            continue
        lines.append(f"<details><summary><code>{entry['name']}</code>: {_label(entry)}, "
                     f"{entry.get('result', '')}</summary>")
        lines.append("")
        lines.append("```")
        lines.extend(entry["detail"])
        lines.append("```")
        lines.append("</details>")
    return "\n".join(lines) + "\n"


def _counts(plans: List[dict]) -> str:
    counts = {status: sum(1 for p in plans if p["status"] == status) for status in REPORT_ORDER}
    conflicts = sum(1 for p in plans if p.get("result") == "conflict")
    text = ", ".join(f"{status}: {count}" for status, count in counts.items())
    return text + (f", CONFLICTS: {conflicts}" if conflicts else "")


def _names(value: str) -> Set[str]:
    return {part.strip().removesuffix(".json") for part in value.split(",") if part.strip()}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Push data/ to DynamoDB (dry run by default).")
    parser.add_argument("--write", action="store_true", help="actually write (default: dry run)")
    parser.add_argument("--force", default="", help="items to overwrite despite drift")
    parser.add_argument("--allow-move-removal", default="", help="items allowed to lose moves")
    parser.add_argument("--data-dir", default=dataset.DATA_DIRECTORY)
    parser.add_argument("--head", default="HEAD", help="commit whose history is the record")
    parser.add_argument("--tag", default=BASELINE_TAG)
    parser.add_argument("--summary-file", default=os.environ.get("GITHUB_STEP_SUMMARY"))
    args = parser.parse_args(argv)

    dry_run = not args.write
    known, baseline = known_states(os.path.dirname(os.path.abspath(args.data_dir)), args.head, args.tag)
    plans = run(dynamo.get_table(), args.data_dir, known, dry_run,
                _names(args.force), _names(args.allow_move_removal))
    print(format_text(plans, dry_run, baseline))
    if args.summary_file:
        with open(args.summary_file, "a", encoding="utf-8") as summary:
            summary.write(format_markdown(plans, dry_run, baseline))
    if not succeeded(plans):
        print("Some items were refused or conflicted; see above. The baseline tag will not move.")
        return 0 if dry_run else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
