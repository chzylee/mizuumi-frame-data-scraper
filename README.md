# mizuumi-frame-data-scraper

Scrapes MBAACC frame data from the Mizuumi wiki (`requests` + `BeautifulSoup4`) and
keeps the `MBAACC-Frame-Data` DynamoDB table that
[melty-frame-data-bot](https://github.com/chzylee/melty-frame-data-bot) reads.

**`data/` on `main` is the truth.** The *Push to DynamoDB* workflow makes the table
match it. Nothing on a local machine writes to DynamoDB; every change goes through
`data/` on `main`.

There is exactly one table, shared by the dev and prod bot. **A push is live for both
bots right away.** Every workflow is manually triggered: merging to `main` changes
nothing in the table until someone runs *Push to DynamoDB*. Run it with `dry_run`
checked first; that plan is the only preview.

## Start the viewer

The viewer is a local app for browsing and editing `data/`. It needs Node.js 22 or newer.

```sh
cd viewer
npm start
```

Then open http://127.0.0.1:5174. The first time, run `npm install` in `viewer/` before
`npm start`. Keep the terminal open while you use it; saving needs the local server.

To ship an edit: **Save edits** in the viewer, commit and push the `data/` change to
`main` (or merge a PR), then run *Push to DynamoDB* from the Actions tab, with `dry_run`
checked first. More in [Viewer](#viewer).

## Layout

| Path | Committed | What it is |
| --- | --- | --- |
| `data/` | yes | One JSON file per table item: the item as stored, minus the `content_hash` bookkeeping attribute. Canonical format, checked by CI. |
| `local-data/scraped/` | no | `main.py` scrape output, same layout as `data/`. Raw material, never pushed as-is. |
| `src/` | yes | Scraper and pipeline code; run everything from here. |
| `viewer/` | yes | Local web app to browse and edit `data/` (see [Viewer](#viewer)). |

**Paths.** An item lives at `data/<short>/<moon>_<short>.json`, where `<short>` is the
bot's short character name (the first alias for that character in
`src/data/mizuumi.py` `CHAR_MAPPINGS`) and `<moon>` is `crescent`, `half` or `full`.
For example: `data/akiha/crescent_akiha.json`, `data/hime/half_hime.json`,
`data/maids/full_maids.json`. **Reordering the aliases in `CHAR_MAPPINGS` renames files.**
A key with no short name, or with an unknown moon, still gets a file, at
`data/_unmapped/<character_name>/<moon key>.json`, with Windows-illegal characters
(`<>:"/\|?*`) percent-encoded. Validation reports these as warnings, not errors. The key
stored inside each file is authoritative; paths are never decoded back into keys, and
validation checks that each file sits at the path its key maps to (`dataset.path_for`).

**Format.** 2-space-indented UTF-8 JSON with an LF newline at the end. Keys come in a
fixed order (`character_name`, `moon`, `moves`; each move as `input`, `image`,
`first_active`, `active`, `recovery`, `frame_adv`, `proration`, `guard`, `invuln`, `alts`;
any other keys after those, alphabetically), and move order is preserved because it is
display order. A move is identified by `(input, occurrence)`, since an input can repeat
within one item (variants). If you hand-edit a file, run `python -m dataset format` and
then `python -m dataset check` before opening a PR.

## Setup

```sh
python -m venv .venv
.venv/Scripts/activate      # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
```

## Scraping

Run from the `src` directory:

```sh
python main.py
```

`main.py` scrapes every character/moon, and is built to be **resilient** and **additive**:

- **Resilient:** each page is scraped in isolation (`try/except` per character/moon). A
  missing page (404), a transient server error (retried with exponential backoff), or a
  parse error is recorded and the run continues instead of aborting. The run ends with a
  summary counting `created` / `updated` / `unchanged` / `failed`, and lists the failed
  pages so nothing is dropped silently.
- **Additive:** results are written with `filehelper.write_json_if_changed`, which only
  rewrites a file when its data actually changed (compared by a canonical content hash)
  and writes atomically (temp file + `os.replace`). Re-scraping data that hasn't moved is
  a no-op.
- **Polite:** a single `requests.Session` with connection pooling, a descriptive
  `User-Agent` (with a contact URL), a request timeout, retry/backoff on 429/5xx, and a
  jittered delay between requests.

Output is written to `local-data/scraped/` (gitignored). Scraping never touches `data/`
or the table. To carry scraped fields into `data/`, use `fill_from_scrape` (below).

### Data captured per move

`input`, `image` (hitbox URL), `alts` (input aliases), and frame data:
`first_active`, `active`, `recovery`, `frame_adv`, `proration`, `guard`, `invuln`.
`guard` is the **Guard** column on the move's top table row (two columns past Proration,
after Cancel), e.g. `L`, `H`, `LH`.

## The pipeline

```
           pull (read role)                       push (write role, manual)       
DynamoDB ──────────────────► PR to data/ ─► main ──────────────────────────────────► DynamoDB
                                   ▲               (manual dispatch from main) 
local-data/scraped/ ─ fill_from_scrape, the viewer, or a hand edit
```

### Pull: [pull-from-dynamodb.yml](./.github/workflows/pull-from-dynamodb.yml)

A pull brings the table into `data/`, for the initial sync and whenever the table might
have been edited outside the pipeline (for example in the console). It scans the whole
table (paginated, read-only) and rewrites `data/` to mirror it exactly; a file whose item
no longer exists is deleted.

Locally, using boto3's default credential chain:

```sh
cd src
AWS_PROFILE=mizuumi-read python -m pull_from_dynamodb   # or: python src/pull_from_dynamodb.py from the repo root
```

It rewrites `data/` in your working copy, prints the created / updated / unchanged /
removed files, and runs no git commands. Review with `git diff data/` and open a PR.

The workflow (manually dispatched, main only) runs the same entrypoint and, if anything
changed, opens a PR from a fresh `dynamodb-pull/<run id>-<attempt>` branch. It never
pushes to `main`.

A pull makes `data/` match the table, so it undoes any `data/` edit that hasn't reached
the table yet, i.e. anything merged to `main` but not pushed. The PR diff shows it;
push pending `data/` changes before pulling.

### Fill fields from the scrape: `fill_from_scrape`

```sh
python main.py                                       # refresh local-data/scraped/
python -m fill_from_scrape --fields guard --dry-run
python -m fill_from_scrape --fields guard
git diff data/                                       # review, then open a PR
```

For each move in `data/`, it sets only the named fields from the scraped move at the same
path with the same input and occurrence. It never touches `image` unless you name it. It
reports unmatched moves on both sides, scraped moves that lack a named field, and files
that exist on only one side, and it never guesses.

### Push: [push-to-dynamodb.yml](./.github/workflows/push-to-dynamodb.yml)

Manual dispatch only, from `main`, with `dry_run` (default **true**). Uncheck
`dry_run` to write.
Concurrent runs queue rather than race.

- The `plan` job (read role, no environment) prints every insert/update with a per-move
  diff to the log and the job summary. A dry run stops there.
- The `write` job (write role) re-plans against the live table and writes the items
  that differ. There is no approval step: merging a `data/` change to `main` is the
  approval.

Per item, the plan is `insert`, `update`, `unchanged`, or `table-only` (in the table with
no `data/` file: reported, **never deleted**). An item counts as unchanged when its
content hash, computed the same way over the table item (minus its stored
`content_hash`) and the `data/` file, matches. So a console edit is noticed and
overwritten with `data/`. Each write is a plain `put_item` of the `data/` item plus
`content_hash`.

Logic: `src/push_to_dynamodb.py` (`--write` to write; without it, a dry run of the same
code path).

### Check: [check.yml](./.github/workflows/check.yml)

Runs on every PR and every push to `main`, without AWS: the unit tests, plus
`python -m dataset check` (every file parses, has the required keys, has a unique key,
sits at the path its key maps to, and is byte-for-byte canonical; `_unmapped/` files are
warnings). A badly formatted hand edit fails CI. A second job checks the viewer:
typecheck, unit tests, and the parity test against `src/dataset.py`.

PRs opened by the pull workflow use `GITHUB_TOKEN`, so GitHub holds their check runs
until someone with write access clicks **Approve workflows to run** on the PR. The pull
workflow also runs the data check itself and puts the result in the PR body.

## Viewer

A local web app in `viewer/` for browsing and editing `data/`. It only reads and writes
files: no git, no AWS, no Python needed to run it. The sync to DynamoDB stays manual.

```sh
cd viewer
npm ci          # once; Node 22+
npm start       # API on 127.0.0.1:5175, UI on http://127.0.0.1:5174
```

Both servers bind `127.0.0.1` only. `VIEWER_DATA_DIR` and `VIEWER_SCRAPED_DIR` point it
at other directories (default `data/` and `local-data/scraped/`, from the repo root
wherever you run it). If `data/` is missing or empty, the viewer says so and edits
nothing: `data/` only ever comes from a pull. A `data/` file that can't be loaded (a
merge conflict, say) is listed at the top with its error; fix or restore it and reload.
Until then it is skipped, and its scraped copy isn't shown in its place, so the rest can
still be saved.

**Browse.** Pick a character, then a moon. Each move shows its hitbox image and every
field it has, known fields in canonical order and any others after them.

**Edit.** `image` is edited directly, with a live preview. Every other field (including
`input` and `alts`) has a lock: click to unlock, edit, click again (or press Enter) to
lock, which stages the edit. Fields still unlocked when you save are not saved.

**Diffs.** With a scrape in `local-data/scraped/` (`python main.py` from `src`), **Show
diffs** compares `data/` with it, matching items by key and moves by input and
occurrence, as `fill_from_scrape` does. Moves are paired once, when the viewer loads;
editing a move (even its `input`) never re-pairs it or any other move. Green matches, red differs (the scraped value
in red italics beside it), blue exists only in the scrape. `image` is never compared or
colored. Things only in `data/` are left uncolored. Characters, moons and moves take
their children's worst status (red, then blue, then green).

**What only the scrape has is a preview, never saved.** The scraper gets things wrong
(unlabelled variants, mislabelled chains), so nothing from it reaches `data/` on its
own. With **Show diffs** on, an item, move, or field (such as `guard`) that exists only
in the scrape is shown in blue, read-only, marked "preview, not saved". A preview move
sits right after the move that precedes it in the scrape (at the top if none does), and
never before a move with the same input. A save writes only your own edits. New moves
(for example a release adding Shield Bunker, Heat or Arc Drives) are added to `data/`
by hand, and `python -m fill_from_scrape --fields guard` fills a field on moves that
already exist.

**Save.** **Save edits** lists every pending change by character, moon and move, old
value to new. On confirm, the server re-checks every file (the `dataset.py` validation
rules, the right path for its key, and that the file hasn't changed on disk since it was
loaded) and writes nothing if any check fails; otherwise it writes each file in the
canonical format, atomically (temp file, then rename). The viewer warns before you close
or reload the page with unsaved changes.

Then ship it like any other `data/` change:

1. Review `git diff data/` and commit.
2. Push to `main`, or open a PR and merge it once CI passes.
3. Run *Push to DynamoDB* with `dry_run` checked, check the plan, then run it again
   unchecked to write.

Its TypeScript copies of the `dataset.py` serializer, `path_for` and validation must
match Python byte for byte; `npm run test:parity` (Python on `PATH`, or set `PYTHON`)
compares them over the test fixtures and, when present, every file in
`local-data/scraped/`. Run `npm run typecheck` and `npm test` for the rest.

## What the workflows need to run

- Repo secrets `DYNAMODB_READ_ROLE_ARN` (used by pull and the push `plan` job; the role
  trusts `repo:chzylee/mizuumi-frame-data-scraper:ref:refs/heads/main`) and
  `DYNAMODB_WRITE_ROLE_ARN` (used by the push `write` job; the role trusts
  `repo:chzylee/mizuumi-frame-data-scraper:ref:refs/heads/main`). Region `us-east-2`.
  The code calls only `dynamodb:Scan` (both roles) and `dynamodb:PutItem` (write role).
- Settings → Actions → General → "Allow GitHub Actions to create and approve pull
  requests" turned on, so the pull workflow can open its PR.

## Bootstrap procedure

`data/` must come from the table, never from the scrape: the table holds hand-fixed image
URLs that exist nowhere else.

1. **Pull:** locally, on a new branch, run `AWS_PROFILE=mizuumi-read python -m pull_from_dynamodb`
   from `src`, commit `data/`, and open a PR. (Or run *Pull from DynamoDB* on `main`.)
2. **Merge:** let CI pass, review the PR (it's the whole table), and merge it. A dry-run
   push should report every item `unchanged`.
3. **Backfill guard:** run `python main.py`, then `python -m fill_from_scrape --fields guard`.
   Review `git diff data/` and the reported unmatched moves, and open a PR. (The viewer can
   do this too, but its save also writes any moves or items that exist only in the
   scrape, so the plan in step 4 would show more than `guard`.)
4. **Merge**, then run *Push to DynamoDB* with `dry_run` checked and confirm the
   `plan` summary shows only `guard` changes.
5. **Push:** run it again with `dry_run` unchecked to write.

## Testing

Run unit tests from the `src` directory:

```sh
python -m unittest discover -s tests -p "*_tests.py"
```

The viewer's tests run from `viewer/`: `npm run typecheck`, `npm test`, and
`npm run test:parity` (see [Viewer](#viewer)).

- The pipeline is unit-tested without AWS against an in-memory fake table
  (`tests/fakes.py`, with scan pagination). The scraper tests need `beautifulsoup4`
  (`pip install -r requirements.txt`) and are skipped without it; CI installs it.
- `tests/scraper_regression_tests.py` parses saved wiki snapshots in `tests/fixtures/`
  and asserts known frame data (including `guard`). These snapshots exist because a
  MediaWiki **heading-markup change** (the section `id` moved from a child
  `<span class="mw-headline">` onto the heading element, now wrapped in
  `<div class="mw-heading">`, and move images moved from class `lazyimg` to
  `mw-file-element`) silently broke parsing for **every** character. The scraper now
  tolerates both the old and new markup, and the fixtures turn the next such change into a
  failing test instead of a silent outage.
- `tests/fixtures/neco_F.html` pins a second layout quirk: Neco-Arc Full Moon places its
  standing normals directly under the `Normal Moves` h3 with no `Standing Normals` h4,
  which used to crash the whole page. The scraper falls back to the h3, and missing
  sections now degrade to empty instead of raising.

To run the scraper with logging against one live wiki page (from `src`):
`python scraper_integrationtest.py`
