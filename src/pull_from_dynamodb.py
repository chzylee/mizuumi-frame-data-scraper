"""Pull: make data/ an exact mirror of the DynamoDB table (read-only).

Local use (e.g. the initial sync): credentials come from boto3's default chain, so

    cd src
    AWS_PROFILE=mizuumi-read python -m pull_from_dynamodb

reads the table, rewrites data/ in your working copy, and prints what changed.
It never writes to the table and runs no git commands. Review with
`git diff data/` and open a PR yourself. The pull workflow
(.github/workflows/pull-from-dynamodb.yml) runs this same entrypoint, then
commits to a fresh branch and opens the PR.

A pull makes data/ match the table, so it undoes any data/ edit that hasn't
been pushed yet; the PR diff shows that.
"""
import argparse
import sys
from typing import Dict, List

import dataset
import dynamo

STATUSES = ("created", "updated", "unchanged", "removed")


def pull(table, data_dir: str) -> Dict[str, List[str]]:
    """Scan the whole table and mirror it into data_dir.

    Each item is written as stored, minus content_hash. A file whose item no
    longer exists in the table is removed, so the PR shows the deletion.
    """
    items = [dataset.item_from_table(raw) for raw in dynamo.scan_all(table)]
    return dataset.mirror(data_dir, items)


def format_report(report: Dict[str, List[str]]) -> str:
    lines = ["=== Pull summary ==="]
    for status in STATUSES:
        lines.append(f"{status:>9}: {len(report[status])}")
    for status in ("created", "updated", "removed"):
        if report[status]:
            lines.append(f"  {status}: {', '.join(report[status])}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Mirror the DynamoDB table into data/ (read-only).")
    parser.add_argument("--data-dir", default=dataset.DATA_DIRECTORY)
    args = parser.parse_args(argv)
    print(format_report(pull(dynamo.get_table(), args.data_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
