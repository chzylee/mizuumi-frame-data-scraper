"""Fill named move fields in data/ from the local scrape.

    python -m fill_from_scrape --fields guard [--dry-run]

For every move in data/, the named fields are copied from the scraped move with
the same identity: same character file, same input, same occurrence of that
input. Nothing else is touched (`image` only if you name it). Moves that don't
match on either side are reported, never guessed at. Review the result with
`git diff data/`, then open a PR.
"""
import argparse
import os
import sys
from typing import Dict, List

import dataset
import filehelper

# Fields that identify a move or item; filling them from the scrape is meaningless.
UNFILLABLE = {"input", dataset.PARTITION_KEY, dataset.SORT_KEY, "moves"}


def fill_item(item: dict, scraped: dict, fields: List[str]) -> dict:
    """Fill `fields` on item's moves from scraped's moves, in place.

    Returns {changed, data_only, scrape_only, missing_field}: counts and lists of
    move identities so nothing unmatched passes silently.
    """
    moves = item.get("moves", [])
    scraped_moves = scraped.get("moves", [])
    scraped_by_id = dict(zip(dataset.move_identities(scraped_moves), scraped_moves))
    data_ids = dataset.move_identities(moves)

    report = {"changed": 0, "data_only": [], "scrape_only": [], "missing_field": []}
    for identity, move in zip(data_ids, moves):
        source = scraped_by_id.get(identity)
        if source is None:
            report["data_only"].append(dataset.describe_identity(identity))
            continue
        changed = False
        for field in fields:
            if field not in source:
                report["missing_field"].append(f"{dataset.describe_identity(identity)}.{field}")
                continue
            if move.get(field) != source[field] or field not in move:
                move[field] = source[field]
                changed = True
        report["changed"] += changed
    data_id_set = set(data_ids)
    report["scrape_only"] = [dataset.describe_identity(i) for i in scraped_by_id if i not in data_id_set]
    return report


def fill(data_dir: str, scraped_dir: str, fields: List[str], dry_run: bool = False) -> Dict[str, dict]:
    """Fill every data/ file from its scraped counterpart. Returns per-file reports
    plus "_data_files_without_scrape" and "_scrape_files_without_data" lists."""
    bad = sorted(set(fields) & UNFILLABLE)
    if bad:
        raise ValueError(f"cannot fill identity field(s): {', '.join(bad)}")
    if not fields:
        raise ValueError("name at least one field")

    data_files = dataset.list_files(data_dir)
    scraped_files = dataset.list_files(scraped_dir)
    reports: Dict[str, dict] = {
        "_data_files_without_scrape": [f for f in data_files if f not in scraped_files],
        "_scrape_files_without_data": [f for f in scraped_files if f not in data_files],
    }
    for name in data_files:
        if name not in scraped_files:
            continue
        path = os.path.join(data_dir, name)
        item = dataset.loads(dataset.read_file(path))
        scraped = dataset.loads(dataset.read_file(os.path.join(scraped_dir, name)))
        report = fill_item(item, scraped, fields)
        report["written"] = False if dry_run else dataset.write_file(path, item)
        reports[name] = report
    return reports


def format_report(reports: Dict[str, dict], fields: List[str], dry_run: bool) -> str:
    lines = [f"=== Fill {', '.join(fields)} from scrape{' (DRY RUN)' if dry_run else ''} ==="]
    total = 0
    for name, report in reports.items():
        if name.startswith("_"):
            continue
        total += report["changed"]
        problems = [(label, report[key]) for key, label in (
            ("data_only", "in data/ only (not filled)"),
            ("scrape_only", "in scrape only (ignored)"),
            ("missing_field", "field absent in scrape"),
        ) if report[key]]
        if report["changed"] or problems:
            lines.append(f"{name:20} {report['changed']} move(s) changed")
        for label, values in problems:
            lines.append(f"    {label}: {', '.join(values)}")
    if reports["_data_files_without_scrape"]:
        lines.append(f"data/ files with no scrape (untouched): {', '.join(reports['_data_files_without_scrape'])}")
    if reports["_scrape_files_without_data"]:
        lines.append(f"scraped files with no data/ file (ignored): {', '.join(reports['_scrape_files_without_data'])}")
    lines.append(f"total moves changed: {total}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Fill named move fields in data/ from the local scrape.")
    parser.add_argument("--fields", required=True, help="comma-separated, e.g. guard")
    parser.add_argument("--data-dir", default=dataset.DATA_DIRECTORY)
    parser.add_argument("--scraped-dir", default=filehelper.SCRAPED_DIRECTORY)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args(argv)
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    reports = fill(args.data_dir, args.scraped_dir, fields, args.dry_run)
    print(format_report(reports, fields, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
