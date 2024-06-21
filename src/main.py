import requests
import json
import file_helper
from scraper import Scraper
from data import melty
from models.dynamodb import MeltyChar

def get_melty_char_frame_data(char_path: str, moon_path: str) -> MeltyChar:
    base_url = "https://wiki.gbl.gg"
    wiki_url = f"{base_url}/w/Melty_Blood/MBAACC/{char_path}/{moon_path}"

    # Placeholder to avoid accidentally making requests on runs during development.
    response = requests.get(wiki_url)
    scraper = Scraper(base_url=base_url, isLoggingOn=True)
    melty_char = scraper.scrape_frame_data(wiki_html=response.text)
    return melty_char

def get_all_melty_frame_data() -> None:
    for char in melty.char_paths:
        for moon in melty.moon_paths:
            data = get_melty_char_frame_data(char, moon)
            file_name = file_helper.get_filename(char_name=char, moon=moon)
            with open(file_name, "w") as json_file:
                json.dump(data, json_file, indent=4)

if __name__ == "__main__":
    get_all_melty_frame_data()
