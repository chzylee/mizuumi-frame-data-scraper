class MoveFrameData:
    input: str
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
