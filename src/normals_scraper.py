import json
from typing import List, Tuple
from bs4 import BeautifulSoup
from models.dynamodb import *
from models.wikiinput import WikiInputComponents

class NormalsScraper:
    def verify_first_h4(self, tag):
        text = tag.contents[0].text
        print(text)
        if text == "Standing Normals":
            print("Matched starting <h4>")
        else:
            print("ERROR: First <h4> was not 'Standing Normals'")
            raise Exception()

    def verify_first_move_h5(self, tag):
        child_id = tag.contents[0].get("id")
        print(f"h5 child id: {child_id}")
        if child_id == "5A":
            print("Matched first <h5> for 5A")
        else:
            print("ERROR: First <h5> did not have child with id 5A")
            raise Exception()

    def scrape_normals(self, soup: any) -> List[object]:
        base_url = "https://wiki.gbl.gg"

        start_tag = soup.find("h4")
        self.verify_first_h4(start_tag)
        current_tag = start_tag.find_next_sibling()
        self.verify_first_move_h5(current_tag)

        normals_list = []

        # <h3>s separate "Normal Moves", "Universal Mechanics", "Special Moves"
        # Start from Normal Moves and continue until Universal Mechanics
        while current_tag.name != "h3":
            print(f"Current tag: <{current_tag.name}>")
            if current_tag.name == "h5":
                current_move = current_tag.contents[0].get("id")
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
                        print("skipping row")
                        continue # Skip until designated next row.

                    row = rows[index]
                    damage_header = row.find("th", {"colspan": "2"})
                    print("Damage header")
                    print(damage_header)
                    if damage_header is not None:
                        damage_text = damage_header.contents[0].get_text()
                        print("damage text")
                        print(damage_text)
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
                            normals_list.append(move_data)

            current_tag = current_tag.find_next_sibling()

        print("NORMALS")
        print(json.dumps(normals_list, indent=4))

        return normals_list