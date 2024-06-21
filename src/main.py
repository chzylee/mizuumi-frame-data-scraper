import requests
from scraper import Scraper
from typing import List
from data import melty
from models.dynamodb import MeltyChar

def get_melty_char_frame_data(char_path: str, moon_path: str) -> MeltyChar:
    base_url = "https://wiki.gbl.gg"
    wiki_url = f"{base_url}/w/Melty_Blood/MBAACC/{char_path}/{moon_path}"
    # TODO: implement scraping.
    # Placeholder to avoid accidentally making requests on runs during development.
    response = None
    # response = requests.get(wiki_url)
    scraper = Scraper(base_url=base_url, isLoggingOn=True)
    melty_char = scraper.scrape_frame_data(wiki_html=response.text)
    return melty_char

def get_melty_frame_data():
    for char in melty.char_paths:
        for moon in melty.moon_paths:
            data = get_melty_char_frame_data(char, moon)

if __name__ == '__main__':
    get_melty_frame_data()
