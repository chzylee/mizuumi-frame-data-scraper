from typing import List

class MoveFrameData:
    first_active: str
    active: str
    recovery: str
    frame_adv: str
    proration: str
    invuln: str

    # All properties required.
    def __init__(
        self,
        first_active: str,
        active: str,
        recovery: str,
        frame_adv: str,
        proration: str,
        invuln: str
    ):
        self.first_active = first_active
        self.active = active
        self.recovery = recovery
        self.frame_adv = frame_adv
        self.proration = proration
        self.invuln = invuln

class MoveData(MoveFrameData):
    input: str
    image: str

    # All properties required.
    def __init__(
        self,
        input: str,
        image: str,
        first_active: str,
        active: str,
        recovery: str,
        frame_adv: str,
        proration: str,
        invuln: str
    ):
        self.input = input
        self.image = image
        self.first_active = first_active
        self.active = active
        self.recovery = recovery
        self.frame_adv = frame_adv
        self.proration = proration
        self.invuln = invuln

    def __init__(
        self,
        input: str,
        image: str,
        frame_data: MoveFrameData
    ):
        self.input = input
        self.image = image
        self.first_active = frame_data.first_active
        self.active = frame_data.active
        self.recovery = frame_data.recovery
        self.frame_adv = frame_data.frame_adv
        self.proration = frame_data.proration
        self.invuln = frame_data.invuln

    def to_dict(self) -> dict:
        return {
            "input": self.input,
            "image": self.image,
            "first_active": self.first_active,
            "active": self.active,
            "recovery": self.recovery,
            "frame_adv": self.frame_adv,
            "proration": self.proration,
            "invuln": self.invuln
        }

class MeltyChar:
    character_name: str
    moon: str
    moves: List[MoveData]
