import re
from models.inputcomponents import InputComponents

class WikiInputComponents(InputComponents):
    index: int

    # Assumes given input string is from the wiki.
    @classmethod
    def from_string(cls, input: str) -> "WikiInputComponents":
        air_match = cls.get_air_component_match(input)
        directions_match = cls.get_directions_component_match(input)

        air = air_match.group() if air_match else None
        directions = directions_match.group() if directions_match else None
        if directions_match is not None:
            # Start after directions if present.
            button_start_index = directions_match.start() + len(directions)
        else:
            # If no directions, must be air normal, so start after air portion.
            button_start_index = len(air)
        buttons = input[button_start_index:]

        return cls(air=air, directions=directions, button=buttons)

    @classmethod
    def standardize_button_text(cls, button_text: str) -> str:
        formatted_text = button_text.replace(" ", "").replace("\n", "").replace("\r", "")
        extra_text_index = formatted_text.find("(")
        if extra_text_index > -1:
            formatted_text = formatted_text[:extra_text_index]
        if "EX" in formatted_text:
            formatted_text = formatted_text.replace("EX", "C")

        return formatted_text


