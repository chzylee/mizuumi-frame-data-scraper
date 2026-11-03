import os
import json
import hashlib
import tempfile
from typing import Any

# Paths are anchored at the repo root so it doesn't matter where you run from.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# local-data/ is gitignored working space, never the record of the table:
#   scraped/   - main.py's scrape output (one file per char/moon)
#   overrides/ - reserved for local hand edits (future local web app)
LOCAL_DATA_DIRECTORY = os.path.join(REPO_ROOT, "local-data")
SCRAPED_DIRECTORY = os.path.join(LOCAL_DATA_DIRECTORY, "scraped")
OVERRIDES_DIRECTORY = os.path.join(LOCAL_DATA_DIRECTORY, "overrides")

def ensure_local_data_dirs_exist() -> None:
    for directory in (SCRAPED_DIRECTORY, OVERRIDES_DIRECTORY):
        os.makedirs(directory, exist_ok=True)

def content_hash(data: Any) -> str:
    # Canonical hash of the data's meaning, independent of key order or formatting,
    # so re-serializing identical data never looks like a change. default=str keeps
    # the hash stable when DynamoDB hands numbers back as Decimal on read.
    canonical = json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def write_json_if_changed(file_path: str, data: Any) -> str:
    """Additive local write: only touch the file when the data actually changed.

    Frame data is effectively immutable per game version, so re-scrapes should be
    no-ops for data that hasn't moved. Returns "created", "updated", or "unchanged".
    Writes atomically (temp file + os.replace) so a crash mid-write can't corrupt
    a good file.
    """
    new_hash = content_hash(data)
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding="utf-8") as json_file:
                existing = json.load(json_file)
            if content_hash(existing) == new_hash:
                return "unchanged"
            status = "updated"
        except (json.JSONDecodeError, OSError):
            # Unreadable/corrupt existing file: treat as a rewrite.
            status = "updated"
    else:
        status = "created"

    directory = os.path.dirname(file_path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, indent=4, ensure_ascii=False)
        os.replace(tmp_path, file_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return status

def get_scraped_path(file_name: str) -> str:
    return os.path.join(SCRAPED_DIRECTORY, file_name)
