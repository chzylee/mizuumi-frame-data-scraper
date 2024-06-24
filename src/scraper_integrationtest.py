import requests
from scraper import Scraper

def test_scraper(html_filepath: str):
    url = "https://wiki.gbl.gg/w/Melty_Blood/MBAACC/Kouma_Kishima/Crescent_Moon"
    wiki_html = requests.get(url).text
    base_url = "https://wiki.gbl.gg"

    scraper = Scraper(base_url=base_url, isLoggingOn=True)
    melty_char = scraper.scrape_frame_data(wiki_html)
    melty_char.character_name = "Aoko"
    melty_char.moon = "C"

if __name__ == '__main__':
    test_html_path = "./tests/caoko_wiki_test.html" # Rel to project base dir.
    test_scraper(test_html_path)
