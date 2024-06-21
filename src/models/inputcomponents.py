import re
from typing import Union
from data.inputreader import input_matchers

class InputComponents:
    air: Union[str, None]
    directions: Union[str, None]
    button: Union[str, None]
    follow_up: Union[str, None]

    # All components optional to cover all types.
    def __init__(self, air=None, directions=None, button=None, follow_up=None):
        self.air = air
        self.directions = directions
        self.button = button
        self.follow_up = follow_up

    @classmethod
    def get_air_component_match(cls, input: str) -> Union[re.Match, None]:
        air_match = re.search(r"j.", input)
        return air_match if air_match else None

    @classmethod
    def get_directions_component_match(cls, input: str) -> Union[re.Match, None]:
        directions_match = re.search(r"(63214)|([1-9]{1,3})", input)
        return directions_match if directions_match else None

    @classmethod
    def get_button_component_match(cls, input: str) -> Union[re.Match, None]:
        button_match = re.search(r"(\[[ABCDX]\])|[ABCDX]", input)
        return button_match if button_match else None

    @classmethod
    def from_string(cls, input: str) -> "InputComponents":
        air_match = cls.get_air_component_match(input)
        directions_match = cls.get_directions_component_match(input)
        button_match = cls.get_button_component_match(input)

        air = air_match.group() if air_match else None
        directions = directions_match.group() if directions_match else None
        button = button_match.group() if button_match else None

        return cls(air=air, directions=directions, button=button)

    def __str__(self) -> str:
        air = "" if self.air == None else self.air
        directions = "" if self.directions == None else self.directions
        button = "" if self.button == None else self.button
        follow_up = "" if self.follow_up == None else self.follow_up
        return f"{air}{directions}{button}{follow_up}"

    def get_full_input(self) -> str:
        return str(self)

    # Determines if input is plain normal.
    # Charged normals are organized differently, so they arent considered plain normals.
    def is_normal(self) -> bool:
        if (
            input_matchers.match_ground_normal(str(self)) or
            input_matchers.match_air_normal(str(self)) or
            input_matchers.match_air_cmd_normal(str(self))
        ) and not self.is_charged():
            return True
        return False

    def is_charged(self) -> bool:
        return "[" in self.button and "]" in self.button

    def is_special(self) -> bool:
        return len(self.directions) > 1

    def is_air(self) -> bool:
        return self.air != None
