import re
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

    # --- DOM helpers -------------------------------------------------------
    # MediaWiki changed its heading markup. The section id used to live on a
    # <span class="mw-headline"> inside the heading; it now lives on the heading
    # element itself, which is wrapped in <div class="mw-heading mw-headingN">.
    # These helpers tolerate both layouts so a future wiki change is less likely
    # to silently break parsing again.
    _HEADING_LEVELS = ("h2", "h3", "h4", "h5", "h6")

    def _heading_id(self, heading: any) -> any:
        # Current DOM: id on the heading. Legacy DOM: id on a child span.
        heading_id = heading.get("id")
        if heading_id is not None:
            return heading_id
        first_child = heading.contents[0] if heading.contents else None
        return first_child.get("id") if hasattr(first_child, "get") else None

    def _resolve_heading(self, node: any) -> any:
        # Return the heading element for a sibling node, whether it is a bare
        # heading (legacy DOM) or wrapped in <div class="mw-heading"> (current DOM).
        if node.name in self._HEADING_LEVELS:
            return node
        if node.name == "div" and "mw-heading" in (node.get("class") or []):
            return node.find(self._HEADING_LEVELS)
        return None

    def _section_start_node(self, start_tag: any) -> any:
        # Walk siblings from the heading's wrapper div when present, so the
        # section content (move tables, sub-headings) is actually traversed.
        parent = start_tag.parent
        if parent is not None and parent.name == "div" and "mw-heading" in (parent.get("class") or []):
            return parent
        return start_tag

    def _find_heading(self, soup: any, level: str, search_id: str) -> any:
        start_tag = soup.find(level, id=search_id)
        if start_tag is not None:
            logger.log_info(f"Found {search_id}!", self.isLoggingOn)
            return start_tag
        # Legacy DOM fallback: id on a child span of the heading.
        for heading in soup.find_all(level):
            if self._heading_id(heading) == search_id:
                logger.log_info(f"Found {search_id} (legacy markup)!", self.isLoggingOn)
                return heading
        return None

    def _find_move_images(self, table: any) -> list:
        # Move hitbox images used to carry class "lazyimg"; current MediaWiki tags
        # them "mw-file-element". Support both so either markup yields images.
        images = table.find_all("img", {"class": "lazyimg"})
        if not images:
            images = table.find_all("img", {"class": "mw-file-element"})
        return images

    def _parse_frame_data(self, move_table: any, curr_row_index: int) -> MoveData:
        # Get data for the move relative to starting row for this move.
        proration_row = move_table.find_all("tr")[curr_row_index + 1] # Next row has this data.
        framedata_row = move_table.find_all("tr")[curr_row_index + 3] # Skip next row and the one with headers to get to this data row.
        proration_contents = [item for item in proration_row.contents if item != "\n"]
        framedata_contents = [item for item in framedata_row.contents if item != "\n"]
        # Placement of data within row is static. Top row is
        # [Damage, Red Damage, Proration, Cancel, Guard]; bottom row is
        # [First Active, Active, Recovery, Frame Adv, Circuit, Invuln].
        proration = proration_contents[2].get_text().strip()
        # Guard sits two columns past Proration (after Cancel). Some pages/moves
        # have no Guard column, so fall back to "" rather than index off the end.
        guard = proration_contents[4].get_text().strip() if len(proration_contents) > 4 else ""
        first_active = framedata_contents[0].get_text().strip()
        active = framedata_contents[1].get_text().strip()
        recovery = framedata_contents[2].get_text().strip()
        frame_adv = framedata_contents[3].get_text().strip()
        invuln = framedata_contents[5].get_text().strip()
        frame_data = MoveFrameData(
            proration=proration,
            guard=guard,
            first_active=first_active,
            active=active,
            recovery=recovery,
            frame_adv=frame_adv,
            invuln=invuln
        )
        return frame_data

    def _get_alt_inputs(self, move_input: str) -> List[str]:
        alts = []
        logger.log_info(f"Finding alts for {move_input}", self.isLoggingOn)

        if move_input == "5A~6A~6A":
            alts.append("5A6AA")

        if "X" in move_input:
            alts.append(move_input.replace("X", "A"))
            alts.append(move_input.replace("X", "B"))
            alts.append(move_input.replace("X", "C"))

        move_parts = move_input.split("~")
        logger.log_data("Move parts", move_parts, self.isLoggingOn)
        if len(move_parts) > 1: # i.e. case of move with follow ups
            alts.append("".join(move_parts)) # include an alt of input without ~'s.

            directions = []
            for part in move_parts:
                direction_match = InputComponents.get_directions_component_match(part)
                if direction_match is not None:
                    directions.append(direction_match.group())

            logger.log_data("Directions", directions, self.isLoggingOn)
            if len(directions) > 1:
                prev_dir = directions[0]
                follow_up_parts = []
                for index in range(1, len(directions)):
                    curr_dir = directions[index]
                    if len(curr_dir) == 1: # Only care about single-direction followups (e.g. 4B)
                        if curr_dir == prev_dir[-1]: # check if dir matches last dir of previous input
                            follow_up_parts.append(move_parts[index][1:]) # Add just the button part of the move (e.g. B)

                    prev_dir = curr_dir

                edited_follow_up_count = len(follow_up_parts)
                if edited_follow_up_count > 0:
                    move_start = "".join(move_parts[0:len(move_parts) - edited_follow_up_count])
                    logger.log_info(f"Simplified follow ups for {move_start}", self.isLoggingOn)
                    # Merge trimmed parts of follow ups with the preserved parts of move.
                    alts.append(f"{move_start}{"".join(follow_up_parts)}")
                    alts.append(f"{move_start}~{"".join(follow_up_parts)}") # Have alt with ~ before trims.

        for alt in alts:
            if "X" in alt:
                alts.append(alt.replace("X", "A"))
                alts.append(alt.replace("X", "B"))
                alts.append(alt.replace("X", "C"))

        if "[A/B]" in move_input:
            alts.append(move_input.replace("[A/B]", "[A]"))
            alts.append(move_input.replace("[A/B]", "[B]"))
            alts.append(move_input.replace("[A/B]", "[A]").replace("~", ""))
            alts.append(move_input.replace("[A/B]", "[B]").replace("~", ""))
        if "[B/C]" in move_input:
            alts.append(move_input.replace("[B/C]", "[B]"))
            alts.append(move_input.replace("[B/C]", "[C]"))
            alts.append(move_input.replace("[B/C]", "[B]").replace("~", ""))
            alts.append(move_input.replace("[B/C]", "[C]").replace("~", ""))
        if "A/B" in move_input and "[A/B]" not in move_input:
            alts.append(move_input.replace("A/B", "A"))
            alts.append(move_input.replace("A/B", "B"))
            alts.append(move_input.replace("A/B", "A").replace("~", ""))
            alts.append(move_input.replace("A/B", "B").replace("~", ""))
        if "B/C" in move_input and "[B/C]" not in move_input:
            alts.append(move_input.replace("B/C", "B"))
            alts.append(move_input.replace("B/C", "C"))
            alts.append(move_input.replace("B/C", "B").replace("~", ""))
            alts.append(move_input.replace("B/C", "C").replace("~", ""))

        # Use a set to track seen items
        seen = set()
        distinct_alts = []
        for alt in alts:
            if alt not in seen:
                seen.add(alt)
                distinct_alts.append(alt)

        return distinct_alts

    def _get_move_data_from_tag(self, soup: any, start_tag: any) -> List[MoveData]:
        # A missing section yields no moves rather than crashing on None.parent.
        # The caller decides whether to try another starting heading.
        if start_tag is None:
            return []
        current_tag = self._section_start_node(start_tag).find_next_sibling()

        move_list = []
        current_move = None

        # <h3>s separate "Normal Moves", "Universal Mechanics", "Special Moves".
        # Start from Normal Moves and continue until the next <h3>. Also stop at the
        # end of the document so a missing/renamed section can't walk off the end
        # (previously this raised AttributeError on None).
        while current_tag is not None:
            heading = self._resolve_heading(current_tag)
            if heading is not None:
                logger.log_info(f"Current heading: <{heading.name}>", self.isLoggingOn)
                if heading.name == "h3":
                    break  # Reached the next top-level section.
                if heading.name == "h5":
                    h5_id = self._heading_id(heading)
                    logger.log_info(f"h5 id: {h5_id}", self.isLoggingOn)
                    # Avoid odd cases such as special dashes.
                    if h5_id is not None and "(" not in h5_id and "dash" not in h5_id.lower():
                        current_move = WikiInputComponents.from_string(h5_id)
                current_tag = current_tag.find_next_sibling()
                continue
            if current_tag.name == "table" and current_move is not None:
                logger.log_info("in table", self.isLoggingOn)
                images = self._find_move_images(current_tag)
                logger.log_data("Images", images, self.isLoggingOn)
                inner_table = current_tag.find("table", {"class": "wikitable"})

                rows = inner_table.find_all("tr")
                next_row_index = -1 # Used to mark rows we can skip due to processing relative to move header row.
                current_move.index = 0

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
                        logger.log_data("Button Header", button_header, self.isLoggingOn)
                        # Get image at index most closely matching index of the move variant
                        # as some moves have different hitbox images for different variations.
                        logger.log_info(f"Total move images: {len(images)}", self.isLoggingOn)
                        logger.log_info(f"Curent move index: {current_move.index}", self.isLoggingOn)
                        image_index = current_move.index if current_move.index < len(images) else len(images) - 1

                        button_text = WikiInputComponents.standardize_button_text(button_header.text)
                        logger.log_info(f"Button text: {button_text}", self.isLoggingOn)
                        if button_text[0] != "~": # Is not a follow-up and therefore separate move.
                            current_move.follow_up = "" # Refresh follow ups since it is new move.

                        follow_up_index = button_text.find("~")
                        if follow_up_index > -1: # If ~ was found.
                            current_move.follow_up += button_text[follow_up_index:]
                        else:
                            # Extract only the button part of the text if there is no follow up as this implies that direction is already stored.
                            try:
                                multiple_buttons_match = InputComponents.get_multiple_buttons_match(button_text)
                                if multiple_buttons_match is not None:
                                    current_move.button = multiple_buttons_match.group()
                                else:
                                    current_move.button = InputComponents.get_button_component_match(button_text).group()
                            except:
                                # If we cannot extract button only, must be an odd case of text, so use full text found.
                                current_move.button = button_text
                        logger.log_info(f"New button found: {current_move.button}", self.isLoggingOn)

                    # Some moves (e.g. joke-character gimmicks) have no hitbox image;
                    # fall back to an empty string instead of indexing off the end.
                    if images:
                        safe_index = image_index if 0 <= image_index < len(images) else len(images) - 1
                        image = self.base_url + images[safe_index].get("src")
                    else:
                        image = ""
                    logger.log_info(f"Current move: {current_move}", self.isLoggingOn)
                    logger.log_info(f"Image URL: {image}", self.isLoggingOn)

                    # Header for damage in frame data table spans more columns than all other move attributes.
                    damage_header = row.find(string="Damage")
                    if damage_header is not None:
                        damage_text = damage_header.get_text()
                        if damage_text == "Damage":
                            logger.log_info("Found start of move data table", self.isLoggingOn)
                            # Next is row after the one with frame data for this move as we will process in this iteration rel to this row.
                            next_row_index = index + 4
                            current_move.index += 1 # Increment to count which variation of the move we are on.

                            frame_data = self._parse_frame_data(inner_table, index)

                            move_input = current_move.get_full_input()
                            alts = self._get_alt_inputs(move_input)

                            move_data = MoveData(
                                input=move_input,
                                image=image,
                                frame_data=frame_data,
                                alts=alts
                            )
                            logger.log_data("Move Data", move_data.to_dict(), self.isLoggingOn)
                            move_list.append(move_data)

            current_tag = current_tag.find_next_sibling()

        return move_list

    def _get_moves_from_candidates(self, soup: any, candidates: List[Tuple[str, str]]) -> List[MoveData]:
        # Try each (heading level, section id) in order and return moves from the
        # first section that exists and yields any. Page layouts vary (especially
        # joke characters), so a section can live under different headings.
        for level, section_id in candidates:
            start_tag = self._find_heading(soup, level, section_id)
            if start_tag is None:
                continue
            move_list = self._get_move_data_from_tag(soup, start_tag)
            if move_list:
                return move_list
        return []

    def _log_moves(self, label: str, move_list: List[MoveData]) -> None:
        move_dicts = [move.to_dict() for move in move_list]
        # Forcibly log move output every time so we can always sanity check output.
        logger.log_json(label=label, data=move_dicts, isLoggingOn=True)

    def get_normals_data(self, soup: any) -> List[MoveData]:
        # Standard pages start normals at the "Standing Normals" h4. Some joke
        # characters (e.g. Neco-Arc Full Moon) place 5A/5B/5C directly under the
        # "Normal Moves" h3 with no Standing_Normals subheading, so fall back to
        # the h3 (the walk still stops at the next h3, Universal Mechanics).
        normals_data = self._get_moves_from_candidates(soup, [
            ("h4", "Standing_Normals"),
            ("h4", "Standing_Moves"),
            ("h3", "Normal_Moves"),
        ])
        self._log_moves("NORMALS", normals_data)
        return normals_data

    def get_specials_data(self, soup: any) -> List[MoveData]:
        # "Ground" vs "Grounded" varies; if there's no specials h4 at all, the
        # moves live directly under the "Special Moves" h3.
        specials_data = self._get_moves_from_candidates(soup, [
            ("h4", "Grounded_Specials"),
            ("h4", "Ground_Specials"),
            ("h3", "Special_Moves"),
        ])
        self._log_moves("SPECIALS", specials_data)
        return specials_data
