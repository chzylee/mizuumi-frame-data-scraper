import time
import random

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import filehelper
from scraper import Scraper
from data import melty
from models.dynamodb import MeltyChar

BASE_URL = "https://wiki.gbl.gg"
# Identify the scraper honestly and give the wiki a contact point.
USER_AGENT = (
    "mizuumi-frame-data-scraper/1.0 "
    "(+https://github.com/chzylee/mizuumi-frame-data-scraper)"
)
REQUEST_TIMEOUT = 20  # seconds, per request
# Politeness: a small randomized gap between requests so a full run doesn't
# hammer the wiki in a tight loop.
MIN_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 2.0


def build_session() -> requests.Session:
    # One pooled session for the whole run, with automatic retry + exponential
    # backoff on the transient status codes a wiki actually returns under load.
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=4,
        backoff_factor=1.0,  # waits ~0s, 1s, 2s, 4s between attempts
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_melty_char_frame_data(session: requests.Session, char_path: str, moon_path: str) -> MeltyChar:
    wiki_url = f"{BASE_URL}/w/Melty_Blood/MBAACC/{char_path}/{moon_path}"
    print(f"Scraping data from {wiki_url}")
    response = session.get(wiki_url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()  # a 404/5xx that survived retries becomes a failure

    scraper = Scraper(base_url=BASE_URL, isLoggingOn=False)
    melty_char = scraper.scrape_frame_data(wiki_html=response.text)
    melty_char.character_name = char_path
    melty_char.moon = moon_path
    return melty_char


def _format_report(report: dict) -> str:
    lines = ["", "=== Scrape summary ==="]
    for status in ("created", "updated", "unchanged", "failed"):
        lines.append(f"{status:>9}: {len(report[status])}")
    if report["failed"]:
        lines.append(f"  failed (need a look): {', '.join(report['failed'])}")
    return "\n".join(lines)


def get_all_melty_frame_data() -> dict:
    filehelper.ensure_local_data_dirs_exist()
    session = build_session()

    # Resilient: each page is scraped in isolation; one failure doesn't abort the
    # run. Additive: write_json_if_changed only rewrites a file when the data moved.
    report = {"created": [], "updated": [], "unchanged": [], "failed": []}
    for char in melty.char_paths:
        for moon in melty.moon_paths:
            file_name = filehelper.get_filename(char_name=char, moon=moon)
            try:
                data = get_melty_char_frame_data(session, char, moon)
                file_path = filehelper.get_scraped_path(file_name)
                status = filehelper.write_json_if_changed(file_path, data.to_dict())
                report[status].append(file_name)
                print(f"{status:9} {file_name}")
            except Exception as error:
                report["failed"].append(file_name)
                print(f"{'failed':9} {file_name}: {error}")
            time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))

    print(_format_report(report))
    return report


if __name__ == "__main__":
    get_all_melty_frame_data()
