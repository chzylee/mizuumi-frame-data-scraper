"""Python half of the parity test (tests/parity.test.ts). Dev/test only.

Reads {"files": [abs paths], "keys": [{character_name, moon}]} on stdin and
prints what src/dataset.py does with each: canonical bytes (base64) or the
error class, path_for, and validate_item's messages. Also prints CHAR_MAPPINGS.
"""
import base64
import json
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
sys.path.insert(0, SRC)

import dataset  # noqa: E402
from data import mizuumi  # noqa: E402


def path_or_error(key):
    try:
        return {"path": dataset.path_for(key)}
    except ValueError as error:
        return {"path_error": type(error).__name__}


def describe_file(path):
    out = {}
    try:
        text = dataset.read_file(path)
    except UnicodeDecodeError:
        return {"read_error": "UnicodeDecodeError"}
    try:
        item = dataset.loads(text)
    except ValueError:  # JSONDecodeError
        return {"parse_error": "JSONDecodeError"}
    out["validation"] = dataset.validate_item("item", item)
    try:
        out["bytes"] = base64.b64encode(dataset.dumps(item).encode("utf-8")).decode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        out["dumps_error"] = type(error).__name__
    if isinstance(item, dict) and isinstance(item.get("character_name"), str) and isinstance(item.get("moon"), str):
        out.update(path_or_error(item))
    return out


def main():
    # Decode stdin as UTF-8 explicitly: the console code page varies (Windows).
    request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    result = {
        "mappings": list(mizuumi.CHAR_MAPPINGS.items()),
        "files": {path: describe_file(path) for path in request["files"]},
        "keys": [path_or_error(key) for key in request["keys"]],
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
