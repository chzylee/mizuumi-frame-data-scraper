# mizuumi-frame-data-scraper

Python web scraper using `requests` and `BeautifulSoup4` to scrape MBAACC frame data
from Mizuumi wiki pages.

This project is created with the intent of uploading scraped data to AWS DynamoDB for
use with Discord bots (see [melty-frame-data-bot](https://github.com/chzylee/melty-frame-data-bot)).

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
  a no-op. Frame data is effectively immutable per game version, so re-runs should mostly
  report `unchanged`.
- **Polite:** a single `requests.Session` with connection pooling, a descriptive
  `User-Agent` (with a contact URL), a request timeout, retry/backoff on 429/5xx, and a
  jittered delay between requests.

Output JSON is written to `./json/` (gitignored) and read back from there by the uploader.

### Data captured per move

`input`, `image` (hitbox URL), `alts` (input aliases), and frame data:
`first_active`, `active`, `recovery`, `frame_adv`, `proration`, `guard`, `invuln`.
`guard` is the **Guard** column on the move's top table row (two columns past Proration,
after Cancel) — e.g. `L`, `H`, `LH`.

## Updating DynamoDB

[uploader.py](./src/uploader.py) loops through all characters and uploads the JSON written
by `main.py` (in `./json/`, not committed) to the `MBAACC-Frame-Data` table. The upload is
**idempotent, additive, and image-preserving**:

- **DynamoDB is the source of truth for image URLs.** Image URLs are hand-fixed directly
  in the table, so on every upload the stored `image` of each move is preserved and the
  freshly scraped data supplies everything else (frame data, and new fields like `guard`).
  Moves are matched by `input`; repeated inputs are matched positionally so each variant
  keeps its own image. See `DB_OWNED_MOVE_FIELDS` in `uploader.py` to extend this list if
  you start hand-editing other fields.
- It stores a `content_hash` attribute alongside each item and **skips the write entirely
  when the merged result matches the stored hash**, writes only when something actually
  changed, and **never deletes a character**.
- **Non-destructive guard:** if a scrape would *drop* stored moves for a character (e.g. a
  page that failed to parse and produced a partial movelist), the upload **refuses to write
  it** and reports it as `skipped` instead of shrinking your data.
- **Preview before writing:** `python uploader.py --dry-run` reports exactly what each
  character would do (inserted / updated / unchanged / skipped, images preserved, fields
  added) **without writing anything**. Run it first to confirm the update is safe.
- The key schema (`character_name` partition, `moon` sort) matches the bot's
  `constants.py`. The extra `content_hash` attribute is ignored by the bot, which projects
  only `moves`.

**Backfilling a new field (e.g. `guard`) onto existing records:** run `python main.py` to
regenerate `./json/` with the new field, then `python uploader.py`. Existing characters get
the new field added with their hand-fixed images preserved; previously-skipped characters
are inserted fresh.

[edit_data.py](./src/edit_data.py) is a manual override for one hard-coded Character + Moon.
Unlike the additive uploader, it **force-writes the file verbatim** (no merge), so it's the
way to actually change a hand-owned field such as an image URL.

## Testing

Run unit tests from the `src` directory:

```sh
python -m unittest discover -s tests -p "*_tests.py"
```

- The additive write and upload logic is unit-tested without AWS (an in-memory fake table
  proves that unchanged data is never re-written, and that hand-fixed image URLs survive a
  re-upload that adds a new field). The scraper unit tests need `beautifulsoup4` installed
  (`pip install -r requirements.txt`); they skip otherwise, so make sure CI installs deps.
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

Test run the scraper on saved wiki page HTML directly (from `src`): `python scraper_integrationtest.py`
