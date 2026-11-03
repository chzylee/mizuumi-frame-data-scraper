"""The committed `data/` directory: canonical format, filenames, and validation.

`data/` is the canonical record of what is in the DynamoDB table: one JSON file
per table item, written in one deterministic format so a git diff only ever
shows real changes. Every reader and writer of `data/` goes through this module.

Run from `src` to validate `data/` (the PR check does this):

    python -m dataset check
"""
import hashlib
import json
import math
import os
import re
import sys
from decimal import Decimal
from typing import Any, Dict, List, Tuple

import filehelper
from data import melty, mizuumi

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
UNMAPPED_PREFIX = "unmapped--"


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


# --- filenames ------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "_"


def filename_for_key(character_name: str, moon: str) -> str:
    """Filename for an item key: the scrape's convention (e.g. akiha-C.json).

    A key that doesn't map to a known character/moon still gets a stable, safe
    filename (rather than being dropped): prefixed, slugged, and suffixed with a
    hash of the exact key so two odd keys can never collide.
    """
    if character_name in mizuumi.CHAR_MAPPINGS.values() and moon in melty.moon_paths:
        return filehelper.get_filename(char_name=character_name, moon=moon)
    digest = hashlib.sha256(f"{character_name}\x00{moon}".encode("utf-8")).hexdigest()[:8]
    return f"{UNMAPPED_PREFIX}{_slug(str(character_name))}--{_slug(str(moon))}--{digest}.json"


def filename_for_item(item: dict) -> str:
    return filename_for_key(item[PARTITION_KEY], item[SORT_KEY])


def item_name(filename: str) -> str:
    """The short name used in reports and workflow inputs (filename minus .json)."""
    return filename[:-5] if filename.endswith(".json") else filename


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
    if not os.path.isdir(directory):
        return []
    return sorted(name for name in os.listdir(directory) if name.endswith(".json"))


def read_file(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def load_dir(directory: str) -> Dict[str, dict]:
    """{filename: item} for every JSON file in a directory."""
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
    source exactly. Returns lists of filenames under "created", "updated",
    "unchanged" and "removed".
    """
    by_name: Dict[str, dict] = {}
    for item in items:
        name = filename_for_item(item)
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
    """Every problem with data/: parse, required keys, key uniqueness,
    filename-matches-key, and canonical formatting (byte for byte)."""
    errors = []
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
        expected = filename_for_item(item)
        if expected != name:
            errors.append(f"{name}: key {key} belongs in {expected}")
        if text != dumps(item):
            errors.append(f"{name}: not in canonical format (run `python -m dataset format` from src)")
    return errors


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
        errors = validate_dir(directory)
        for error in errors:
            print(f"ERROR {error}")
        print(f"{len(list_files(directory))} file(s) checked, {len(errors)} problem(s)")
        return 1 if errors else 0
    if command == "format":
        for name in format_dir(directory):
            print(f"formatted {name}")
        return 0
    print("usage: python -m dataset [check|format] [directory]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
