from typing import List
from bs4 import BeautifulSoup
from models.framedata import MoveFrameData
from models.dynamodb import MeltyChar

def scrape_frame_data(wiki_html: str) -> MeltyChar:
    wiki_soup = BeautifulSoup(markup=wiki_html, features="html.parser")
    return None
