"""What git knows about data/ relative to the `dynamodb-deployed` baseline tag.

Read-only git queries shared by push (drift guard) and pull (pending-edit
warning). Nothing here commits, checks out, or moves refs.
"""
import os
import subprocess
from typing import Dict, List, Optional, Set, Tuple

import dataset

BASELINE_TAG = "dynamodb-deployed"
# Marker in a known-states set meaning "no item / no file".
ABSENT = "<absent>"


def git(repo_dir: str, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_dir, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def resolve_tag(repo_dir: str, tag: str) -> Optional[str]:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
        cwd=repo_dir, capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def files_at(repo_dir: str, commit: str, data_path: str = "data") -> Dict[str, str]:
    """{filename: blob id} for the JSON files directly under data_path at a commit."""
    files = {}
    for entry in git(repo_dir, "ls-tree", "-r", "-z", commit, "--", f"{data_path}/").split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        name = path[len(data_path) + 1:]
        if "/" not in name and name.endswith(".json"):
            files[name] = meta.split()[2]
    return files


def canonical_text(text: str) -> Optional[str]:
    """Canonical form of a file's text, or None when it doesn't parse."""
    try:
        return dataset.dumps(dataset.loads(text))
    except (ValueError, TypeError):
        return None


def known_states(repo_dir: str, head: str, tag: str = BASELINE_TAG,
                 data_path: str = "data") -> Tuple[Dict[str, Set[str]], str]:
    """Canonical text of every recorded version of each data/ file since the baseline.

    The baseline is the tag commit plus every later commit up to head; with no
    tag, every commit in head's history. Returns
    ({filename: {canonical text or ABSENT}}, description of the baseline).
    """
    tag_commit = resolve_tag(repo_dir, tag)
    if tag_commit is None:
        commits = git(repo_dir, "rev-list", head).split()
        description = f"no `{tag}` tag yet: every commit in the pushed history ({len(commits)})"
    else:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", tag_commit, head], cwd=repo_dir
        )
        if ancestor.returncode != 0:
            raise RuntimeError(
                f"tag {tag} ({tag_commit[:7]}) is not an ancestor of {head}; "
                "main's history was rewritten. Re-establish the baseline (see README)."
            )
        commits = [tag_commit] + git(repo_dir, "rev-list", f"{tag_commit}..{head}").split()
        description = f"`{tag}` at {tag_commit[:7]} plus {len(commits) - 1} later commit(s)"

    blobs_by_file: Dict[str, Set[str]] = {}
    present_in: List[Set[str]] = []
    for commit in commits:
        files = files_at(repo_dir, commit, data_path)
        present_in.append(set(files))
        for name, blob in files.items():
            blobs_by_file.setdefault(name, set()).add(blob)

    states: Dict[str, Set[str]] = {}
    texts: Dict[str, Optional[str]] = {}
    for name, blobs in blobs_by_file.items():
        for blob in blobs:
            if blob not in texts:
                # An unparseable version can't match a live item.
                texts[blob] = canonical_text(git(repo_dir, "cat-file", "-p", blob))
            if texts[blob] is not None:
                states.setdefault(name, set()).add(texts[blob])
        if any(name not in present for present in present_in):
            states.setdefault(name, set()).add(ABSENT)
    return states, description


def state_of(item: Optional[dict]) -> str:
    return ABSENT if item is None else dataset.dumps(item)


def pending_edits(data_dir: str, current: Dict[str, str],
                  tag: str = BASELINE_TAG) -> Tuple[Optional[Set[str]], str]:
    """Files whose current content differs from data/ at the baseline tag:
    edits recorded locally or on main that haven't been pushed to the table.

    current: {filename: raw text} of data_dir as it is now. Returns
    (set of filenames, description) or (None, why the check was skipped).
    """
    try:
        top = git(data_dir if os.path.isdir(data_dir) else os.path.dirname(data_dir),
                  "rev-parse", "--show-toplevel").strip()
    except (RuntimeError, OSError):
        return None, "skipped: not inside a git repository"
    tag_commit = resolve_tag(top, tag)
    if tag_commit is None:
        return None, f"skipped: no `{tag}` tag yet, so there is no pushed baseline to compare with"
    data_path = os.path.relpath(os.path.abspath(data_dir), os.path.abspath(top)).replace(os.sep, "/")

    at_tag = {name: canonical_text(git(top, "cat-file", "-p", blob))
              for name, blob in files_at(top, tag_commit, data_path).items()}
    now = {name: canonical_text(text) for name, text in current.items()}
    pending = {name for name in set(at_tag) | set(now)
               if name not in at_tag or name not in now or at_tag[name] != now[name]}
    return pending, f"compared with `{tag}` at {tag_commit[:7]}"
