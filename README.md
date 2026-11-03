# mizuumi-frame-data-scraper

Scrapes MBAACC frame data from the Mizuumi wiki (`requests` + `BeautifulSoup4`) and
keeps the `MBAACC-Frame-Data` DynamoDB table that
[melty-frame-data-bot](https://github.com/chzylee/melty-frame-data-bot) reads.

**The committed `data/` directory is the record of what is in the table.** Nothing on a
local machine writes to DynamoDB. The table is read and written only by manually
triggered GitHub Actions workflows, and every change to it goes through a reviewed PR
to `data/` first.

There is exactly one table, shared by the dev and prod bot. **A push is live for both
bots immediately; the push workflow's dry run is the only preview.**

## Layout

| Path | Committed | What it is |
| --- | --- | --- |
| `data/` | yes | One JSON file per table item (e.g. `akiha-C.json`): the item as stored, minus the `content_hash` bookkeeping attribute. Canonical format, checked by CI. |
| `local-data/scraped/` | no | `main.py` scrape output, one file per char/moon. Raw material, never pushed as-is. |
| `local-data/overrides/` | no | Reserved for local hand edits (a future local web app). Not used yet. |
| `src/` | yes | Scraper and pipeline code; run everything from here. |

`data/` format: 2-space-indented UTF-8 JSON with an LF newline at the end. Keys come in a
fixed order (`character_name`, `moon`, `moves`; each move as `input`, `image`,
`first_active`, `active`, `recovery`, `frame_adv`, `proration`, `guard`, `invuln`, `alts`;
any other keys after those, alphabetically), and move order is preserved because it is
display order. A move is identified by `(input, occurrence)`, since an input can repeat
within one item (variants). An item whose key doesn't map to a known character/moon is
still recorded, as `unmapped--<char>--<moon>--<hash>.json`. If you hand-edit a file, run
`python -m dataset format` and then `python -m dataset check` before opening a PR.

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
           pull workflow (read role)            push workflow (write role, `dynamodb` env)
DynamoDB ─────────────────────────► PR to data/ ─► main ─────────────────────────────────► DynamoDB
                                        ▲
local-data/scraped/ ─ fill_from_scrape ─┘   (or a hand edit)
```

### Pull: [pull-from-dynamodb.yml](./.github/workflows/pull-from-dynamodb.yml)

Manually dispatched, main only. It scans the whole table (paginated, read-only) and
rewrites `data/` to mirror it exactly; a file whose item no longer exists is deleted. If
anything changed, it opens a PR from a fresh `dynamodb-pull/<run id>` branch. It never
pushes to `main`. Use it any time the table may have been edited outside the pipeline
(for example a fix made in the console).

The same entrypoint runs locally, using boto3's default credential chain:

```sh
cd src
AWS_PROFILE=mizuumi-read python -m pull_from_dynamodb   # or: python src/pull_from_dynamodb.py from the repo root
```

It rewrites `data/` in your working copy and prints the created / updated / unchanged /
removed files. It reads git only to look up the baseline tag; it never commits, branches
or checks out. Review with `git diff data/` and open the PR yourself.

**Pending-edit warning.** A pull makes `data/` match the table, so it reverts any `data/`
edit that differs from the `dynamodb-deployed` tag, i.e. an edit approved on `main` (or
made locally) but never pushed. Every file where the pull did that is listed in a loud
warning: in the CLI output, and in the workflow's job summary, a `::warning::`
annotation, and the top of the PR body. The pull is not blocked. Don't merge such a PR
unless the table's version should win; usually you want to push first. With no tag yet,
the check is skipped and the output says so.

Logic: `src/pull_from_dynamodb.py`.

### Fill fields from the scrape: `fill_from_scrape`

```sh
python main.py                                       # refresh local-data/scraped/
python -m fill_from_scrape --fields guard --dry-run
python -m fill_from_scrape --fields guard
git diff data/                                       # review, then open a PR
```

For each move in `data/`, it sets only the named fields from the scraped move with the
same file, input and occurrence. It never touches `image` unless you name it. It reports
unmatched moves on both sides, scraped moves that lack a named field, and files that
exist on only one side, and it never guesses.

### Push: [push-to-dynamodb.yml](./.github/workflows/push-to-dynamodb.yml)

Manually dispatched, main only. Inputs: `dry_run` (default **true**), `force`, and
`allow_move_removal`. The last two take comma-separated item names, which are `data/`
filenames without `.json`, e.g. `akiha-C,ciel-H`.

- The `plan` job always runs: it uses the read role and no environment, and prints the plan
  to the log and the job summary. With `dry_run` true, that's all that happens.
- With `dry_run` false, the `write` job runs after `plan` in the `dynamodb` environment
  (its required reviewers approve it, so read the `plan` summary first). It re-plans
  against the live table and writes.

Per item, the plan is `insert`, `update` (with a per-move diff), `unchanged`,
`table-only` (in the table with no `data/` file: reported, **never deleted**), or
`refused`:

- **drift:** the live item matches no version of its `data/` file recorded at or after
  the baseline (below), so someone changed it outside the pipeline. Run the pull workflow
  to capture the change in a PR instead. Naming the item in `force` overwrites it anyway.
- **move-removal:** the update would remove moves (by `(input, occurrence)`). Name the
  item in `allow_move_removal` to permit it.

Each write is a `put_item` that stores `content_hash` and is conditional on every live
attribute still being exactly what was read. A change made between the read and the
write makes that item fail as a conflict rather than be overwritten. A refused or
conflicted item doesn't stop the other items, but it fails the `write` job.

Logic: `src/push_to_dynamodb.py` (`--write` to write; without it, a dry run of the same
code path).

### The drift baseline: the `dynamodb-deployed` tag

After a `write` run where nothing was refused or conflicted, the workflow moves the
`dynamodb-deployed` tag to the commit it pushed. A live item counts as known (safe to
overwrite) when it equals its `data/` file **at the tag, or at any later commit on
`main`**. So a pull PR merged since the last push counts, and a console edit that was never
pulled does not.

**When the tag doesn't exist yet** (the first push), every commit in `main`'s history
counts. `data/` first enters `main` through the bootstrap pull PR, so that pull is
effectively the baseline: a console edit made after it is refused. No manual tagging is
needed.

If `main`'s history is ever rewritten so that the tag is no longer an ancestor, push
refuses to run. Run a pull, merge it, then delete the tag
(`git push --delete origin dynamodb-deployed`). The next push then falls back to the
no-tag rule above.

### Check: [check.yml](./.github/workflows/check.yml)

Runs on every PR and every push to `main`, without AWS: the unit tests, plus
`python -m dataset check` (every file parses, has the required keys, has a unique key,
has a filename that matches its key, and is byte-for-byte canonical). A badly formatted
hand edit fails CI.

PRs opened by the pull workflow use `GITHUB_TOKEN`, so GitHub holds their check runs
until someone with write access clicks **Approve workflows to run** on the PR. The pull
workflow also runs the data check itself and puts the result in the PR body.

## What the workflows need to run

- Repo secrets `DYNAMODB_READ_ROLE_ARN` (used by pull and the push `plan` job; the role
  trusts `repo:chzylee/mizuumi-frame-data-scraper:ref:refs/heads/main`) and
  `DYNAMODB_WRITE_ROLE_ARN` (used by the push `write` job; the role trusts
  `repo:chzylee/mizuumi-frame-data-scraper:environment:dynamodb`). Region `us-east-2`.
  The code calls only `dynamodb:Scan` (both roles) and `dynamodb:PutItem` (write role).
- GitHub environment `dynamodb`, with required reviewers and a deployment-branch rule
  allowing only `main`.
- Settings → Actions → General → "Allow GitHub Actions to create and approve pull
  requests" turned on, so the pull workflow can open its PR.

## Bootstrap procedure

`data/` must come from the table, never from the scrape: the table holds hand-fixed image
URLs that exist nowhere else.

1. **Pull:** locally, run `AWS_PROFILE=mizuumi-read python -m pull_from_dynamodb` from
   `src` on a new branch, commit `data/`, and open a PR. (Running *Pull from DynamoDB*
   on `main` does the same and opens the PR for you.)
2. **Merge:** let CI pass, review the PR (it's the whole table), and merge it.
3. **Baseline:** nothing to do. With no `dynamodb-deployed` tag, the merged pull is the
   baseline (see above). Don't edit the table in the console from here on; if you do,
   start again at step 1.
4. **Backfill guard:** run `python main.py`, then `python -m fill_from_scrape --fields guard`.
   Review `git diff data/` and the reported unmatched moves, then open a PR.
5. **Merge** that PR once CI passes.
6. **Push, dry run:** run *Push to DynamoDB* with `dry_run` checked. Read the `plan` job
   summary. Expect `update` with only `guard` changes and no `refused` items.
7. **Push for real:** run it again with `dry_run` unchecked, approve the `write` job, and
   confirm the `dynamodb-deployed` tag now points at that commit.

## Testing

Run unit tests from the `src` directory:

```sh
python -m unittest discover -s tests -p "*_tests.py"
```

- The pipeline is unit-tested without AWS against an in-memory fake table
  (`tests/fakes.py`, which supports scan pagination and the push's condition
  expressions). The drift-baseline logic is tested against real throwaway git repos.
  The scraper tests need `beautifulsoup4` (`pip install -r requirements.txt`) and are
  skipped without it; CI installs it.
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
