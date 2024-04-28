import re

def _match_ground_move(input: str, regex: re.Pattern) -> str:
    match = input.upper() if re.match(pattern=regex, string=input) else None
    return match

def _match_air_move(input: str, regex: re.Pattern) -> str:
    match = None
    if re.match(pattern=regex, string=input):
        match_end = input.upper()[1:]
        # Ensure we add "." after j if it was not included in input.
        match = f"j.{match_end}" if input[1] != "." else f"j{match_end}"
    return match

def match_ground_normal(input: str) -> str:
    # Allow lowercase in input and allow charged input (e.g. 5[C])
    ground_normal_regex = r"[1-9](([AaBbCc])|(\[[AaBbCc]\]))"
    # match() returns None on failure to match which fails if cond.
    match = _match_ground_move(input, ground_normal_regex)
    return match

def match_air_normal(input: str) -> str:
    air_normal_regex = r"[Jj]\.?(([AaBbCc])|(\[[AaBbCc]\]))" # Start with J since we made input upper.
    match = _match_air_move(input, air_normal_regex)
    return match

def match_ground_special(input: str) -> str:
    ground_special_regex = r"[1-6]{2,3}(([AaBbCc])|(\[[AaBbCc]\]))"
    match = _match_ground_move(input, ground_special_regex)
    return match

def match_air_cmd_normal(input: str) -> str:
    air_cmd_normal_regex = r"[Jj]\.?[1-9](([AaBbCc])|(\[[AaBbCc]\]))" # Start with J since we made input upper.
    match = _match_air_move(input, air_cmd_normal_regex)
    return match

def match_air_special(input: str) -> str:
    air_special_regex = r"[Jj]\.?[1-6]{2,3}(([AaBbCc])|(\[[AaBbCc]\]))" # Start with J since we made input upper.
    match = _match_air_move(input, air_special_regex)
    return match

input_matchers = [
    match_ground_normal,
    match_air_normal,
    match_ground_special,
    match_air_cmd_normal,
    match_air_special
]
