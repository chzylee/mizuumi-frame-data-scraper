import logger
from typing import List, Tuple
from bs4 import BeautifulSoup
from models.dynamodb import *
from models.wikiinput import WikiInputComponents

class Scraper:
    base_url: str
    isLoggingOn: bool

    def __init__(self, base_url: str, isLoggingOn=False):
        self.base_url = base_url
        self.isLoggingOn = isLoggingOn

    def scrape_frame_data(self, wiki_html: str) -> MeltyChar:
        wiki_soup = BeautifulSoup(markup=wiki_html, features="html.parser")
        normals_data = self.get_normals_data(wiki_soup)
        specials_data = self.get_specials_data(wiki_soup)
        char_data = MeltyChar()
        char_data.moves = normals_data + specials_data
        return char_data

    # No type annotation for beautifulsoup tags.
    def _find_starting_h4(self, soup: any, search_label: str) -> any:
        for h4 in soup.find_all("h4"):
            logger.log_data("h4", h4, self.isLoggingOn)
            current_section = h4.contents[0].get("id")
            logger.log_info(f"Current Section: {current_section}", self.isLoggingOn)
            if current_section == search_label:
                logger.log_info(f"Found {search_label}!", self.isLoggingOn)
                start_tag = h4
                return start_tag

    def _parse_frame_data(self, move_table: any, curr_row_index: int) -> MoveData:
        # Get data for the move relative to starting row for this move.
        proration_row = move_table.find_all("tr")[curr_row_index + 1] # Next row has this data.
        framedata_row = move_table.find_all("tr")[curr_row_index + 3] # Skip next row and the one with headers to get to this data row.
        proration_contents = [item for item in proration_row.contents if item != "\n"]
        framedata_contents = [item for item in framedata_row.contents if item != "\n"]
        # Placement of data within row is static.
        proration = proration_contents[2].get_text().strip()
        first_active = framedata_contents[0].get_text().strip()
        active = framedata_contents[1].get_text().strip()
        recovery = framedata_contents[2].get_text().strip()
        frame_adv = framedata_contents[3].get_text().strip()
        invuln = framedata_contents[5].get_text().strip()
        frame_data = MoveFrameData(
            proration=proration,
            first_active=first_active,
            active=active,
            recovery=recovery,
            frame_adv=frame_adv,
            invuln=invuln
        )
        return frame_data

    def _get_move_data(self, soup: any, start_move_category: str) -> List[MoveData]:
        # Standing Normals is first section for normals.
        start_tag = self._find_starting_h4(soup, start_move_category)
        current_tag = start_tag.find_next_sibling()

        move_list = []

        # <h3>s separate "Normal Moves", "Universal Mechanics", "Special Moves"
        # Start from Normal Moves and continue until Universal Mechanics
        while current_tag.name != "h3":
            logger.log_info(f"Current tag: <{current_tag.name}>", self.isLoggingOn)
            if current_tag.name == "h5":
                logger.log_info(f"h5 id: {current_tag.contents[0].get("id")}", self.isLoggingOn)
                current_move = WikiInputComponents.from_string(current_tag.contents[0].get("id"))
            if current_tag.name == "table":
                logger.log_info("in table", self.isLoggingOn)
                images = current_tag.find_all("img", {"class": "lazyimg"})
                inner_table = current_tag.find("table", {"class": "wikitable"})

                rows = inner_table.find_all("tr")
                next_row_index = -1 # Used to mark rows we can skip due to processing relative to move header row.
                current_move.index = -1

                for index in range(len(rows)):
                    if index < next_row_index:
                        continue # Skip until designated next row.

                    row = rows[index]

                    # Variations of moves are labeled with a column spanning 4 rows to cover whole frame data table.
                    button_header = row.find("th", {"rowspan": "4"})
                    if button_header is None:
                        logger.log_info("No button header found", self.isLoggingOn)
                        image_index = 0
                    else: # Found a variant of a move for a specific button.
                        # Get image at index most closely matching index of the move variant
                        # as some moves have different hitbox images for different variations.
                        image_index = current_move.index if current_move.index < len(images) else len(images) - 1

                        button_text = WikiInputComponents.standardize_button_text(button_header.text)
                        logger.log_info(f"Button text: {button_text}", self.isLoggingOn)

                        follow_up_index = button_text.find("~")
                        if follow_up_index > -1:
                            current_move.follow_up = button_text[follow_up_index:]
                        else:
                            current_move.button = button_text
                        logger.log_info(f"New button found: {current_move.button}", self.isLoggingOn)

                    image = self.base_url + images[image_index].get("src")
                    logger.log_info(f"Current move: {current_move}", self.isLoggingOn)
                    logger.log_info(f"Image URL: {image}", self.isLoggingOn)

                    # Header for damage in frame data table spans more columns than all other move attributes.
                    damage_header = row.find("th", {"colspan": "2"})
                    if damage_header is not None:
                        damage_text = damage_header.contents[0].get_text()
                        if damage_text == "Damage":
                            logger.log_info("Found start of move data table", self.isLoggingOn)
                            # Next is row after the one with frame data for this move as we will process in this iteration rel to this row.
                            next_row_index = index + 4
                            current_move.index += 1 # Increment to count which variation of the move we are on.

                            frame_data = self._parse_frame_data(inner_table, index)
                            move_data = MoveData(
                                input=current_move.get_full_input(),
                                image=image,
                                frame_data=frame_data
                            )
                            logger.log_data("Move Data", move_data, self.isLoggingOn)
                            move_list.append(move_data)

            current_tag = current_tag.find_next_sibling()

        return move_list

    def get_normals_data(self, soup: any) -> List[MoveData]:
        normals_data = self._get_move_data(soup=soup, start_move_category="Standing_Normals")
        normals_dicts = [normal.to_dict() for normal in normals_data]
        logger.log_json(label="NORMALS", data=normals_dicts, isLoggingOn=self.isLoggingOn)
        return normals_data

    def get_specials_data(self, soup: any) -> List[MoveData]:
        specials_data = self._get_move_data(soup=soup, start_move_category="Grounded_Specials")
        specials_dicts = [special.to_dict() for special in specials_data]
        logger.log_json(label="SPECIALS", data=specials_dicts, isLoggingOn=self.isLoggingOn)
        return specials_data
