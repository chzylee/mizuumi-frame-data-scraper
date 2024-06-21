import requests
import json
import filehelper
from scraper import Scraper
from data import melty, mizuumi
from models.dynamodb import MeltyChar

def get_melty_char_frame_data(char_path: str, moon_path: str) -> MeltyChar:
    base_url = "https://wiki.gbl.gg"
    wiki_url = f"{base_url}/w/Melty_Blood/MBAACC/{char_path}/{moon_path}"
    print(f"Scraping data from {wiki_url}")

    # Placeholder to avoid accidentally making requests on runs during development.
    response = requests.get(wiki_url)
    scraper = Scraper(base_url=base_url, isLoggingOn=True)
    try:
        melty_char = scraper.scrape_frame_data(wiki_html=response.text)
        melty_char.character_name = char_path
        melty_char.moon = moon_path
    except:
        char_short = mizuumi.get_char_name(char_path)
        moon_short = mizuumi.get_moon_letter(moon_path)
        print(f"Error occurred scraping frame data for {moon_short}-{char_short}")
        raise
    return melty_char

def get_all_melty_frame_data() -> None:
    filehelper.ensure_json_dir_exists()

    for char in melty.char_paths:
        for moon in melty.moon_paths:
            data = get_melty_char_frame_data(char, moon)
            file_name = filehelper.get_filename(char_name=char, moon=moon)
            with open(file_name, "w") as json_file:
                json.dump(data.to_dict(), json_file, indent=4)

if __name__ == "__main__":
    get_all_melty_frame_data()
