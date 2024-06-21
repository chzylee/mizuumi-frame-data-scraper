import json
from typing import List, Tuple
from bs4 import BeautifulSoup
from models.dynamodb import *
from models.wikiinput import WikiInputComponents

class SpecialsScraper:
    def scrape_specials(self, soup: any) -> List[object]:
        base_url = "https://wiki.gbl.gg"

        for h4 in soup.find_all("h4"):
            print(h4)
            current_section = h4.contents[0].get("id")
            print(current_section)
            if current_section == "Grounded_Specials":
                print("Found grounded specials!")
                start_tag = h4
                break

        current_tag = start_tag.find_next_sibling()

        specials_list = []

        # <h3>s separate "Normal Moves", "Universal Mechanics", "Special Moves"
        # Start from Normal Moves and continue until Universal Mechanics
        while current_tag.name != "h3":
            print(f"Current tag: <{current_tag.name}>")
            if current_tag.name == "h5":
                current_move = current_tag.contents[0].get("id")
                current_direction = current_move.replace("X", "")
            print(f"Current move: {current_move}")
            if current_tag.name == "table":
                print("in table")

                images = current_tag.find_all("img", {"class": "lazyimg"})
                inner_table = current_tag.find("table", {"class": "wikitable"})

                rows = inner_table.find_all("tr")
                next_row_index = -1 # Used to mark rows we can skip due to processing relative to header row.
                move_index = -1

                for index in range(len(rows)):
                    if index < next_row_index:
                        continue # Skip until designated next row.

                    row = rows[index]
                    print("row")
                    # print(row)
                    move_button = row.find("th", {"rowspan": "4"})
                    print("button")
                    # print(move_button)
                    if move_button is not None:
                        button_text = move_button.text.replace(" ", "").replace("\n", "").replace("\r", "")
                        print("button text")
                        print(button_text)
                        extra_index = button_text.find("(")
                        if extra_index > -1:
                            button_text = button_text[:extra_index]
                        if "EX" in button_text:
                            button_text = button_text.replace("EX", "C")

                        follow_up_index = button_text.find("~")
                        if follow_up_index > -1:
                            current_move = saved_move + button_text[follow_up_index:]
                        else:
                            current_move = current_direction + button_text
                            saved_move = current_move
                        print("new button found: " + current_move)

                    print("current button: " + current_move)

                    damage_header = row.find("th", {"colspan": "2"})
                    if damage_header is not None:
                        damage_text = damage_header.contents[0].get_text()
                        if damage_text == "Damage":
                            print("Found start of move data table")
                            # Next is row after the one with frame data for this move as we will process in this iteration rel to this row.
                            next_row_index = index + 4
                            move_index += 1 # Increment to count which variation of the move we are on.

                            special_header = row.find("th", {"rowspan": "4"})
                            if special_header is None:
                                print("No special header found")
                                image_index = 0
                            else:
                                # special_header_label = special_header.get_text()
                                image_index = move_index if move_index < len(images) else len(images) - 1
                            image = base_url + images[image_index].get("src")

                            # Get data for the move relative to starting row for this move.
                            proration_row = inner_table.find_all("tr")[index + 1] # Next row has this data.
                            framedata_row = inner_table.find_all("tr")[index + 3] # Skip next row and the one with headers to get to this data row.
                            proration_contents = [item for item in proration_row.contents if item != "\n"]
                            framedata_contents = [item for item in framedata_row.contents if item != "\n"]
                            # Placement of data within row is static.
                            proration = proration_contents[2].get_text().strip()
                            first_active = framedata_contents[0].get_text().strip()
                            active = framedata_contents[1].get_text().strip()
                            recovery = framedata_contents[2].get_text().strip()
                            frame_adv = framedata_contents[3].get_text().strip()
                            invuln = framedata_contents[5].get_text().strip()
                            move_data = {
                                "input": current_move,
                                "image": image,
                                "proration": proration,
                                "first_active": first_active,
                                "active": active,
                                "recovery": recovery,
                                "frame_adv": frame_adv,
                                "invuln": invuln
                            }
                            print(move_data)
                            specials_list.append(move_data)

            current_tag = current_tag.find_next_sibling()

        print("SPECIALS")
        print(json.dumps(specials_list, indent=4))

        return specials_list