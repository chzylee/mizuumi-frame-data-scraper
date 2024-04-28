from typing import List
from bs4 import BeautifulSoup
from models.framedata import MoveFrameData

def scrape_frame_data(wiki_html: str) -> List[MoveFrameData]:
    wiki_soup = BeautifulSoup(markup=wiki_html, features="html.parser")
    return []
