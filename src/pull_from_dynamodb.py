"""Pull: make data/ an exact mirror of the DynamoDB table (read-only).

Local use (the initial sync): credentials come from boto3's default chain, so

    cd src
    AWS_PROFILE=mizuumi-read python -m pull_from_dynamodb

reads the table, rewrites data/ in your working copy, and prints what changed.
It never writes to the table and never commits, branches or checks out; it only
reads git to look up the baseline tag. Review with `git diff data/` and open a
PR yourself. The pull workflow (.github/workflows/pull-from-dynamodb.yml) runs
this same entrypoint, then commits to a fresh branch and opens the PR.

Pending-edit warning: data/ edits that differ from the `dynamodb-deployed` tag
haven't been pushed to the table yet, so a pull reverts them. Every such file
the pull changed is listed loudly. The pull itself is not blocked.
"""
import argparse
import os
import sys
from typing import Dict, List

import baseline
import dataset
import dynamo

STATUSES = ("created", "updated", "unchanged", "removed")


def pull(table, data_dir: str, tag: str = baseline.BASELINE_TAG) -> Dict[str, object]:
    """Scan the whole table and mirror it into data_dir.

    Each item is written as stored, minus content_hash. A file whose item no
    longer exists in the table is removed, so the PR shows the deletion.
    Returns the mirror report plus "reverted" (files whose unpushed edits this
    pull undid, or None when the check was skipped) and "pending_check" (what
    that check compared against, or why it was skipped).
    """
    before = {name: dataset.read_file(os.path.join(data_dir, name)) for name in dataset.list_files(data_dir)}
    pending, note = baseline.pending_edits(data_dir, before, tag)

    items = [dataset.item_from_table(raw) for raw in dynamo.scan_all(table)]
    report: Dict[str, object] = dict(dataset.mirror(data_dir, items))

    touched = set(report["created"]) | set(report["updated"]) | set(report["removed"])
    report["reverted"] = None if pending is None else sorted(pending & touched)
    report["pending_check"] = note
    return report


def format_report(report: Dict[str, object]) -> str:
    lines = ["=== Pull summary ==="]
    for status in STATUSES:
        lines.append(f"{status:>9}: {len(report[status])}")
    for status in ("created", "updated", "removed"):
        if report[status]:
            lines.append(f"  {status}: {', '.join(report[status])}")
    lines.append(f"pending-edit check: {report['pending_check']}")
    reverted = report["reverted"]
    if reverted:
        bar = "!" * 72
        lines += [bar,
                  f"WARNING: this pull REVERTED unpushed edits in {len(reverted)} file(s).",
                  f"These files differed from the `{baseline.BASELINE_TAG}` tag (edited but never",
                  "pushed to DynamoDB); data/ now matches the table instead:"]
        lines += [f"  - {name}" for name in reverted]
        lines += ["Committed edits are still in git history; uncommitted ones are gone.",
                  "Do not merge this pull over them unless the table's version should win.",
                  bar]
    return "\n".join(lines)


def format_markdown(report: Dict[str, object]) -> str:
    """Markdown for the job summary and the top of the PR body."""
    reverted = report["reverted"]
    lines = []
    if reverted:
        lines += [f"> [!WARNING]",
                  f"> **This pull reverts unpushed edits in {len(reverted)} file(s).** They differ "
                  f"from the `{baseline.BASELINE_TAG}` tag, so they were approved on main but never "
                  "pushed to DynamoDB. Merging this PR replaces them with the table's version:",
                  ">"]
        lines += [f"> - `{name}`" for name in reverted]
        lines.append("")
    elif reverted is None:
        lines += [f"Pending-edit check {report['pending_check']}.", ""]
    else:
        lines += [f"Pending-edit check: no unpushed edits reverted ({report['pending_check']}).", ""]
    counts = ", ".join(f"{status}: {len(report[status])}" for status in STATUSES)
    lines += [f"**Pull:** {counts}", ""]
    return "\n".join(lines) + "\n"


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Mirror the DynamoDB table into data/ (read-only).")
    parser.add_argument("--data-dir", default=dataset.DATA_DIRECTORY)
    parser.add_argument("--markdown", help="also write a markdown summary to this file")
    args = parser.parse_args(argv)

    report = pull(dynamo.get_table(), args.data_dir)
    print(format_report(report))
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(format_markdown(report))
    if report["reverted"] and os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Pull reverts unpushed edits::{', '.join(report['reverted'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
