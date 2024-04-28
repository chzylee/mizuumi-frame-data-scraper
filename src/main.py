import requests
import scraper
from typing import List
from data import melty
from models.framedata import MoveFrameData

def get_melty_char_frame_data(char_path: str, moon_path: str) -> List[MoveFrameData]:
    wiki_url = f"https://wiki.gbl.gg/w/Melty_Blood/MBAACC/{char_path}/{moon_path}"
    # TODO: implement scraping.
    # Placeholder to avoid accidentally making requests on runs during development.
    response = None
    # response = requests.get(wiki_url)
    frame_data_list = scraper.scrape_frame_data(wiki_html=response.text)
    return []

def get_melty_frame_data():
    for char in melty.char_paths:
        for moon in melty.moon_paths:
            data = get_melty_char_frame_data(char, moon)

if __name__ == '__main__':
    get_melty_frame_data()
