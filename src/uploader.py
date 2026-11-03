import os
import sys
import json
from collections import defaultdict, deque, Counter

import filehelper
from data import melty

# DynamoDB key schema. Must match melty-frame-data-bot/src/constants.py.
PARTITION_KEY = "character_name"
SORT_KEY = "moon"
# Attribute that stores the content hash used for idempotent, additive uploads.
HASH_ATTR = "content_hash"
# Per-move fields where DynamoDB is the source of truth and must survive a
# re-upload (image URLs are hand-fixed directly in the table). The freshly
# scraped wiki data wins for everything else.
DB_OWNED_MOVE_FIELDS = ("image",)


def _item_hash(item: dict) -> str:
    # Hash the data only, never the bookkeeping attribute itself.
    payload = {key: value for key, value in item.items() if key != HASH_ATTR}
    return filehelper.content_hash(payload)


def _merge_moves(existing_moves: list, scraped_moves: list) -> list:
    """Carry DB-owned per-move fields (image) forward onto freshly scraped moves.

    Moves are matched by `input`; repeated inputs are matched positionally so a
    move with several variants keeps each variant's stored image. The wiki is
    authoritative for the move list itself, so a move that no longer scrapes is
    dropped and a newly-scraped move is added with its scraped image.
    """
    existing_by_input = defaultdict(deque)
    for move in existing_moves:
        existing_by_input[move.get("input")].append(move)

    merged = []
    for scraped in scraped_moves:
        queue = existing_by_input.get(scraped.get("input"))
        existing = queue.popleft() if queue else None
        move = dict(scraped)
        if existing is not None:
            for field in DB_OWNED_MOVE_FIELDS:
                stored = existing.get(field)
                if stored:  # only preserve a real, non-empty stored value
                    move[field] = stored
        merged.append(move)
    return merged


def merge_item(existing: dict, scraped: dict) -> dict:
    """Merge freshly scraped data onto the stored item.

    A brand-new character (no stored item) is inserted as-is. For an existing
    character, the stored item's hand-edited image URLs are preserved while the
    scrape supplies everything else (including new fields like `guard`). Any
    stored top-level attribute the scrape doesn't know about is kept.
    """
    if existing is None:
        return dict(scraped)
    merged = dict(existing)
    merged.update(scraped)           # scrape wins for known top-level attributes
    merged.pop(HASH_ATTR, None)      # recomputed on write, never carried over
    merged["moves"] = _merge_moves(existing.get("moves", []), scraped.get("moves", []))
    return merged


def _dropped_inputs(existing_moves: list, merged_moves: list) -> list:
    """Inputs present in the stored moves that the merged result would lose.

    Uses multiset counts so a duplicated input (e.g. two 5B variants) can't be
    silently halved. A non-empty result means the write would be destructive.
    """
    existing_counts = Counter(move.get("input") for move in existing_moves)
    merged_counts = Counter(move.get("input") for move in merged_moves)
    return [inp for inp, count in existing_counts.items() if merged_counts[inp] < count]


def _describe(existing: dict, merged: dict) -> str:
    moves = merged.get("moves", [])
    if existing is None:
        return f"new character, {len(moves)} moves"
    existing_moves = existing.get("moves", [])
    preserved = sum(1 for move in existing_moves if move.get("image"))
    existing_keys = set().union(*[set(m) for m in existing_moves]) if existing_moves else set()
    merged_keys = set().union(*[set(m) for m in moves]) if moves else set()
    added = sorted(merged_keys - existing_keys)
    return (f"{len(moves)} moves; {preserved} image(s) preserved; "
            f"added fields: {', '.join(added) if added else 'none'}")


def plan_item(existing: dict, scraped_item: dict) -> dict:
    """Decide what an upload would do, without touching any table.

    Returns {status, merged, hash, detail}. status is one of:
      - "inserted"  : brand-new character
      - "updated"   : data changed (images preserved, new fields added)
      - "unchanged" : merged result already matches the stored hash
      - "skipped"   : the merge would DROP stored moves (e.g. a partial scrape);
                      refused as destructive, nothing is written.
    """
    merged = merge_item(existing, scraped_item)
    new_hash = _item_hash(merged)

    if existing is None:
        return {"status": "inserted", "merged": merged, "hash": new_hash,
                "detail": _describe(None, merged)}

    dropped = _dropped_inputs(existing.get("moves", []), merged.get("moves", []))
    if dropped:
        shown = ", ".join(str(d) for d in dropped[:5]) + ("..." if len(dropped) > 5 else "")
        return {"status": "skipped", "merged": merged, "hash": new_hash,
                "detail": f"REFUSED: would drop {len(dropped)} stored move(s) [{shown}] "
                          f"({len(existing.get('moves', []))} stored -> {len(merged.get('moves', []))} scraped)"}

    if existing.get(HASH_ATTR) == new_hash:
        return {"status": "unchanged", "merged": merged, "hash": new_hash, "detail": "no change"}

    return {"status": "updated", "merged": merged, "hash": new_hash,
            "detail": _describe(existing, merged)}


def upload_item(table, scraped_item: dict, dry_run: bool = False) -> str:
    """Additively upsert one character's frame data.

    Idempotent, image-preserving, and non-destructive:
      - merges the scrape onto the stored item, keeping hand-fixed image URLs,
      - skips the write entirely when nothing changed,
      - REFUSES to write when the scrape would drop stored moves (returns
        "skipped"), so a partial/failed scrape can't shrink existing data,
      - never deletes a character.
    With dry_run=True, computes the same decision but writes nothing.
    Returns "inserted", "updated", "unchanged", or "skipped".
    """
    key = {PARTITION_KEY: scraped_item[PARTITION_KEY], SORT_KEY: scraped_item[SORT_KEY]}
    existing = table.get_item(Key=key).get("Item")
    plan = plan_item(existing, scraped_item)

    if plan["status"] in ("inserted", "updated") and not dry_run:
        table.put_item(Item={**plan["merged"], HASH_ATTR: plan["hash"]})
    return plan["status"]


def force_upload_item(table, item: dict) -> None:
    """Deliberate override: write the item from file verbatim, no merge.

    Used by edit_data.py to push a hand-curated file (e.g. to actually change an
    image URL). Stores the content hash so the next additive run sees it as
    unchanged instead of re-merging.
    """
    table.put_item(Item={**item, HASH_ATTR: _item_hash(item)})


def get_table():
    # boto3 is imported lazily so the additive logic above stays unit-testable
    # without AWS credentials or boto3 installed.
    import boto3
    dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
    return dynamodb.Table("MBAACC-Frame-Data")


REPORT_STATUSES = ("inserted", "updated", "unchanged", "skipped", "missing")


def _format_report(report: dict, dry_run: bool) -> str:
    header = "=== Upload summary (DRY RUN — nothing written) ===" if dry_run else "=== Upload summary ==="
    lines = ["", header]
    for status in REPORT_STATUSES:
        lines.append(f"{status:>9}: {len(report[status])}")
    if report["skipped"]:
        lines.append(f"  skipped as destructive (NOT written): {', '.join(report['skipped'])}")
    if report["missing"]:
        lines.append(f"  missing files (not uploaded): {', '.join(report['missing'])}")
    return "\n".join(lines)


def upload_all_melty_frame_data(table=None, dry_run: bool = False) -> dict:
    """Upload every locally-saved character file. Pass dry_run=True to preview.

    A dry run reports exactly what each character would do (and what it would
    refuse to do) without writing a single item — run it first to confirm the
    update is safe.
    """
    filehelper.ensure_json_dir_exists()
    if table is None:
        table = get_table()

    report = {status: [] for status in REPORT_STATUSES}
    for char in melty.char_paths:
        for moon in melty.moon_paths:
            file_name = filehelper.get_filename(char_name=char, moon=moon)
            file_path = filehelper.get_upload_json_path(file_name)
            if not os.path.exists(file_path):
                # A char/moon combo with no saved file is reported, not skipped silently.
                report["missing"].append(file_name)
                continue
            with open(file_path, encoding="utf-8") as json_file:
                data = json.load(json_file)

            key = {PARTITION_KEY: data[PARTITION_KEY], SORT_KEY: data[SORT_KEY]}
            existing = table.get_item(Key=key).get("Item")
            plan = plan_item(existing, data)
            if plan["status"] in ("inserted", "updated") and not dry_run:
                table.put_item(Item={**plan["merged"], HASH_ATTR: plan["hash"]})

            report[plan["status"]].append(file_name)
            prefix = "[dry-run] " if dry_run else ""
            print(f"{prefix}{plan['status']:9} {file_name:18} {plan['detail']}")

    print(_format_report(report, dry_run))
    return report


if __name__ == "__main__":
    # `python uploader.py --dry-run` previews the changes without writing.
    dry = "--dry-run" in sys.argv[1:]
    upload_all_melty_frame_data(dry_run=dry)
