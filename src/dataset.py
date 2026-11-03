"""The committed `data/` directory: canonical format, paths, and validation.

`data/` is the canonical record of what is in the DynamoDB table: one JSON file
per table item at path_for(key), written in one deterministic format so a git diff only ever
shows real changes. Every reader and writer of `data/` goes through this module.

Run from `src` to validate `data/` (the PR check does this):

    python -m dataset check
"""
import json
import math
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import filehelper
from data import mizuumi

PARTITION_KEY = "character_name"
SORT_KEY = "moon"
# Bookkeeping attribute stored on table items; never part of data/.
HASH_ATTR = "content_hash"

DATA_DIRECTORY = os.path.join(filehelper.REPO_ROOT, "data")

# Key order used when writing. Known keys come first in this order (the same
# order the scraper emits), any other keys follow alphabetically. List order is
# always preserved: move order is display order.
_TOP_LEVEL_ORDER = (PARTITION_KEY, SORT_KEY, "moves")
_MOVE_ORDER = (
    "input", "image", "first_active", "active", "recovery", "frame_adv",
    "proration", "guard", "invuln", "alts",
)
# Every move must carry these. `guard` is deliberately absent: items written
# before the guard scrape don't have it yet.
REQUIRED_MOVE_KEYS = (
    "input", "image", "first_active", "active", "recovery", "frame_adv",
    "proration", "invuln", "alts",
)


# --- values ------------------------------------------------------------------

def to_plain(value: Any) -> Any:
    """Convert a DynamoDB (boto3 resource) value into plain JSON types.

    boto3 returns every number as Decimal. Integral numbers become int; others
    become float only when that float round-trips to the same Decimal, so no
    precision is ever silently lost. Sets and binary are rejected: nothing in
    this table uses them, and JSON can't represent them faithfully.
    """
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        as_float = float(value)
        if Decimal(repr(as_float)) != value:
            raise ValueError(f"number {value} cannot be stored in JSON without losing precision")
        return as_float
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"unsupported value of type {type(value).__name__}: {value!r}")


def to_dynamo(value: Any) -> Any:
    """Inverse of to_plain for writing: boto3 rejects float, so use Decimal."""
    if isinstance(value, dict):
        return {key: to_dynamo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_dynamo(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number {value} cannot be stored in DynamoDB")
        return Decimal(repr(value))
    return value


def item_from_table(raw_item: dict) -> dict:
    """A table item as data/ records it: plain values, no bookkeeping attribute."""
    item = to_plain(raw_item)
    item.pop(HASH_ATTR, None)
    return item


def item_hash(item: dict) -> str:
    """The content_hash stored alongside an item (same algorithm as before)."""
    payload = {key: value for key, value in item.items() if key != HASH_ATTR}
    return filehelper.content_hash(payload)


# --- canonical serialization --------------------------------------------------

def _ordered(obj: dict, preferred: Tuple[str, ...]) -> dict:
    known = [key for key in preferred if key in obj]
    rest = sorted(key for key in obj if key not in preferred)
    return {key: obj[key] for key in known + rest}


def _canonical(value: Any, preferred: Tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in _ordered(value, preferred).items()}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def dumps(item: dict) -> str:
    """The one serialization of an item that data/ accepts."""
    if not isinstance(item, dict):
        raise TypeError("an item must be a JSON object")
    ordered = _canonical(item, _TOP_LEVEL_ORDER)
    moves = ordered.get("moves")
    if isinstance(moves, list):
        ordered["moves"] = [
            _canonical(move, _MOVE_ORDER) if isinstance(move, dict) else move for move in moves
        ]
    return json.dumps(ordered, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def loads(text: str) -> dict:
    return json.loads(text)


# --- paths ----------------------------------------------------------------------

# Moon key -> lowercase file prefix.
_MOON_FILE = {"Crescent_Moon": "crescent", "Half_Moon": "half", "Full_Moon": "full"}
UNMAPPED_DIR = "_unmapped"
# Windows-illegal filename characters, percent-encoded in the _unmapped fallback.
_ILLEGAL = set(r'<>:"/\|?*')


def _encode(text: str) -> str:
    if text in (".", ".."):
        raise ValueError(f"key value {text!r} cannot be used as a path component")
    return "".join(f"%{ord(ch):02X}" if ch in _ILLEGAL else ch for ch in text)


def short_name(character_name: str) -> Optional[str]:
    """The bot's short name for a character (first alias in CHAR_MAPPINGS), or None.

    NOTE: the first alias for each character in data/mizuumi.py CHAR_MAPPINGS
    names its directory and files. Reordering those aliases renames files.
    """
    for alias, wiki_name in mizuumi.CHAR_MAPPINGS.items():
        if wiki_name == character_name:
            return alias
    return None


def path_for(key: dict) -> str:
    """Where an item lives, relative to data/ (or local-data/scraped/).

    Known character and moon: <short>/<moon>_<short>.json, e.g.
    akiha/crescent_akiha.json. Anything else (no short name, or an unknown moon):
    _unmapped/<character_name>/<moon>.json with Windows-illegal characters
    percent-encoded, so no item is ever dropped (validation warns about these).

    This is the one mapping from key to path. Nothing decodes a path back into a
    key: the key stored inside the file is authoritative.
    """
    character_name, moon = key[PARTITION_KEY], key[SORT_KEY]
    short = short_name(character_name)
    if short is not None and moon in _MOON_FILE:
        return f"{short}/{_MOON_FILE[moon]}_{short}.json"
    return f"{UNMAPPED_DIR}/{_encode(character_name)}/{_encode(moon)}.json"


def is_unmapped(path: str) -> bool:
    return path.startswith(UNMAPPED_DIR + "/")


def item_name(path: str) -> str:
    """The name used in reports: the path minus .json."""
    return path[:-5] if path.endswith(".json") else path


# --- move identity ----------------------------------------------------------------

def move_identities(moves: List[dict]) -> List[Tuple[str, int]]:
    """(input, occurrence) for each move, in order.

    Inputs can repeat within an item (variants), so a move is identified by its
    input plus how many earlier moves share that input.
    """
    seen: Dict[str, int] = {}
    identities = []
    for move in moves:
        move_input = move.get("input")
        occurrence = seen.get(move_input, 0)
        seen[move_input] = occurrence + 1
        identities.append((move_input, occurrence))
    return identities


def describe_identity(identity: Tuple[str, int]) -> str:
    move_input, occurrence = identity
    return move_input if occurrence == 0 else f"{move_input} (#{occurrence + 1})"


# --- reading and writing the directory ---------------------------------------------

def list_files(directory: str) -> List[str]:
    """Every .json file under directory, as sorted relative paths with "/"."""
    found = []
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if name.endswith(".json"):
                rel = os.path.relpath(os.path.join(root, name), directory)
                found.append(rel.replace(os.sep, "/"))
    return sorted(found)


def read_file(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def load_dir(directory: str) -> Dict[str, dict]:
    """{relative path: item} for every JSON file under a directory."""
    return {name: loads(read_file(os.path.join(directory, name))) for name in list_files(directory)}


def write_file(path: str, item: dict) -> bool:
    """Write an item canonically. Returns True if the file's bytes changed."""
    return write_file_status(path, item) != "unchanged"


def write_file_status(path: str, item: dict) -> str:
    """Write an item canonically. Returns "created", "updated" or "unchanged"."""
    text = dumps(item)
    existed = os.path.exists(path)
    if existed and read_file(path) == text:
        return "unchanged"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(tmp_path, path)
    return "updated" if existed else "created"


def mirror(directory: str, items: List[dict]) -> Dict[str, List[str]]:
    """Make `directory` hold exactly these items, one canonical file each.

    Files whose item is not in `items` are removed, so the directory mirrors the
    source exactly (directories left empty are removed too). Returns lists of
    paths under "created", "updated", "unchanged" and "removed".
    """
    by_name: Dict[str, dict] = {}
    for item in items:
        name = path_for(item)
        if name in by_name:
            raise ValueError(f"two items map to the same file {name}")
        by_name[name] = item

    report = {"created": [], "updated": [], "unchanged": [], "removed": []}
    os.makedirs(directory, exist_ok=True)
    for name in sorted(by_name):
        report[write_file_status(os.path.join(directory, name), by_name[name])].append(name)
    for name in list_files(directory):
        if name not in by_name:
            os.remove(os.path.join(directory, name))
            report["removed"].append(name)
            parent = os.path.dirname(os.path.join(directory, name))
            if os.path.abspath(parent) != os.path.abspath(directory) and not os.listdir(parent):
                os.rmdir(parent)
    return report


# --- validation -------------------------------------------------------------------

def validate_item(name: str, item: Any) -> List[str]:
    """Problems with one parsed item (empty list when it's valid)."""
    if not isinstance(item, dict):
        return [f"{name}: top level must be a JSON object"]
    errors = []
    for key in (PARTITION_KEY, SORT_KEY):
        if not isinstance(item.get(key), str) or not item.get(key):
            errors.append(f"{name}: '{key}' must be a non-empty string")
    if HASH_ATTR in item:
        errors.append(f"{name}: '{HASH_ATTR}' is table bookkeeping and must not be in data/")
    moves = item.get("moves")
    if not isinstance(moves, list):
        errors.append(f"{name}: 'moves' must be a list")
        moves = []
    for index, move in enumerate(moves):
        where = f"{name}: moves[{index}]"
        if not isinstance(move, dict):
            errors.append(f"{where} must be an object")
            continue
        missing = [key for key in REQUIRED_MOVE_KEYS if key not in move]
        if missing:
            errors.append(f"{where} ({move.get('input')!r}) is missing {', '.join(missing)}")
        if "input" in move and not isinstance(move["input"], str):
            errors.append(f"{where}: 'input' must be a string")
        if "alts" in move and not (isinstance(move["alts"], list) and all(isinstance(a, str) for a in move["alts"])):
            errors.append(f"{where} ({move.get('input')!r}): 'alts' must be a list of strings")
    return errors


def validate_dir(directory: str) -> List[str]:
    """Every problem with data/ (see check_dir); warnings are not included."""
    return check_dir(directory)[0]


def check_dir(directory: str) -> Tuple[List[str], List[str]]:
    """(errors, warnings) for data/. Errors: parse, required keys, key
    uniqueness, path == path_for(key), canonical formatting (byte for byte).
    Warnings: items that live under _unmapped/."""
    errors, warnings = [], []
    seen_keys: Dict[Tuple[str, str], str] = {}
    for name in list_files(directory):
        text = read_file(os.path.join(directory, name))
        try:
            item = loads(text)
        except json.JSONDecodeError as error:
            errors.append(f"{name}: not valid JSON ({error})")
            continue
        item_errors = validate_item(name, item)
        errors.extend(item_errors)
        if item_errors:
            continue
        key = (item[PARTITION_KEY], item[SORT_KEY])
        if key in seen_keys:
            errors.append(f"{name}: duplicate key {key}, also in {seen_keys[key]}")
        seen_keys[key] = name
        try:
            expected = path_for(item)
        except ValueError as error:
            errors.append(f"{name}: {error}")
            continue
        if expected != name:
            errors.append(f"{name}: key {key} belongs at {expected}")
        if is_unmapped(expected):
            warnings.append(f"{name}: key {key} has no short-name mapping (data/mizuumi.py "
                            "CHAR_MAPPINGS) or an unknown moon, so it lives under _unmapped/")
        if text != dumps(item):
            errors.append(f"{name}: not in canonical format (run `python -m dataset format` from src)")
    return errors, warnings


def format_dir(directory: str) -> List[str]:
    """Rewrite every parseable file canonically. Returns the files changed."""
    changed = []
    for name, item in load_dir(directory).items():
        if write_file(os.path.join(directory, name), item):
            changed.append(name)
    return changed


def main(argv: List[str]) -> int:
    command = argv[0] if argv else "check"
    directory = argv[1] if len(argv) > 1 else DATA_DIRECTORY
    if command == "check":
        errors, warnings = check_dir(directory)
        for error in errors:
            print(f"ERROR {error}")
        for warning in warnings:
            print(f"WARNING {warning}")
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::warning::{warning}")
        print(f"{len(list_files(directory))} file(s) checked, {len(errors)} problem(s), "
              f"{len(warnings)} warning(s)")
        return 1 if errors else 0
    if command == "format":
        for name in format_dir(directory):
            print(f"formatted {name}")
        return 0
    print("usage: python -m dataset [check|format] [directory]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
