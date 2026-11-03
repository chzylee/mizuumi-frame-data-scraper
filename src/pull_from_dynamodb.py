"""Pull: make data/ an exact mirror of the DynamoDB table (read-only).

Run by .github/workflows/pull-from-dynamodb.yml, which then opens a PR with
whatever changed. Never writes to the table.

    python -m pull_from_dynamodb [--data-dir DIR]
"""
import argparse
import sys
from typing import Dict, List

import dataset
import dynamo


def pull(table, data_dir: str) -> Dict[str, List[str]]:
    """Scan the whole table and mirror it into data_dir.

    Each item is written as stored, minus content_hash. A file whose item no
    longer exists in the table is removed, so the PR shows the deletion.
    """
    items = [dataset.item_from_table(raw) for raw in dynamo.scan_all(table)]
    return dataset.mirror(data_dir, items)


def format_report(report: Dict[str, List[str]]) -> str:
    lines = ["=== Pull summary ==="]
    for status in ("written", "unchanged", "removed"):
        lines.append(f"{status:>9}: {len(report[status])}")
    for status in ("written", "removed"):
        if report[status]:
            lines.append(f"  {status}: {', '.join(report[status])}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=dataset.DATA_DIRECTORY)
    args = parser.parse_args(argv)
    report = pull(dynamo.get_table(), args.data_dir)
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
