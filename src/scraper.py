import logger
from typing import List, Tuple
from bs4 import BeautifulSoup
from models.dynamodb import *
from models.inputcomponents import InputComponents
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

    def _find_starting_h3(self, soup: any, search_id: str) -> any:
        for h3 in soup.find_all("h3"):
            logger.log_data("h3", h3, self.isLoggingOn)
            current_section = h3.contents[0].get("id")
            logger.log_info(f"Current Section: {current_section}", self.isLoggingOn)
            if current_section == search_id:
                logger.log_info(f"Found {search_id}!", self.isLoggingOn)
                start_tag = h3
                return start_tag

    # No type annotation for beautifulsoup tags.
    def _find_starting_h4(self, soup: any, search_id: str) -> any:
        for h4 in soup.find_all("h4"):
            logger.log_data("h4", h4, self.isLoggingOn)
            current_section = h4.contents[0].get("id")
            logger.log_info(f"Current Section: {current_section}", self.isLoggingOn)
            if current_section == search_id:
                logger.log_info(f"Found {search_id}!", self.isLoggingOn)
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

    def _get_move_data_from_tag(self, soup: any, start_tag: any) -> List[MoveData]:
        current_tag = start_tag.find_next_sibling()

        move_list = []
        current_move = None

        # <h3>s separate "Normal Moves", "Universal Mechanics", "Special Moves"
        # Start from Normal Moves and continue until Universal Mechanics
        while current_tag.name != "h3":
            logger.log_info(f"Current tag: <{current_tag.name}>", self.isLoggingOn)
            if current_tag.name == "h5":
                h5_id = current_tag.contents[0].get("id")
                logger.log_info(f"h5 id: {h5_id}", self.isLoggingOn)
                # Avoid odd cases such as special dashes.
                if "(" not in h5_id and "dash" not in h5_id.lower():
                    current_move = WikiInputComponents.from_string(h5_id)
            if current_tag.name == "table" and current_move is not None:
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
                            # Extract only the button part of the text if there is no follow up as this implies that direction is already stored.
                            try:
                                current_move.button = InputComponents.get_button_component_match(button_text).group()
                            except:
                                # If we cannot extract button only, must be an odd case of text, so use full text found.
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
                            logger.log_data("Move Data", move_data.to_dict(), self.isLoggingOn)
                            move_list.append(move_data)

            current_tag = current_tag.find_next_sibling()

        return move_list

    def _get_move_data_from_h4(self, soup: any, start_move_category: str) -> List[MoveData]:
        # Standing Normals is first section for normals.
        start_tag = self._find_starting_h4(soup, start_move_category)
        move_list = self._get_move_data_from_tag(soup, start_tag)
        return move_list

    def _get_move_data_from_h3(self, soup: any, start_move_category: str) -> List[MoveData]:
        # Standing Normals is first section for normals.
        start_tag = self._find_starting_h3(soup, start_move_category)
        move_list = self._get_move_data_from_tag(soup, start_tag)
        return move_list

    def _log_moves(self, label: str, move_list: List[MoveData]) -> None:
        move_dicts = [move.to_dict() for move in move_list]
        # Forcibly log move output every time so we can always sanity check output.
        logger.log_json(label=label, data=move_dicts, isLoggingOn=True)

    def get_normals_data(self, soup: any) -> List[MoveData]:
        try:
            normals_data = self._get_move_data_from_h4(soup=soup, start_move_category="Standing_Normals")
        except:
            normals_data = self._get_move_data_from_h4(soup=soup, start_move_category="Standing_Moves")
        self._log_moves("NORMALS", normals_data)
        return normals_data

    def get_specials_data(self, soup: any) -> List[MoveData]:
        try:
            specials_data = self._get_move_data_from_h4(soup=soup, start_move_category="Grounded_Specials")
        except:
            try:
                # Some pages may label these as Ground instead of Grounded for some reason.
                specials_data = self._get_move_data_from_h4(soup=soup, start_move_category="Ground_Specials")
            except:
                # If there is no h4 for Ground Specials, should be higher level h3 with Special Moves.
                specials_data = self._get_move_data_from_h3(soup=soup, start_move_category="Special_Moves")
        self._log_moves("SPECIALS", specials_data)
        return specials_data
