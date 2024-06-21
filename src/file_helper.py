import os
from data import mizuumi

JSON_DIRECTORY = './json'

def ensure_json_dir_exists() -> None:
    # Create the directory if it doesn't exist
    os.makedirs(JSON_DIRECTORY, exist_ok=True)

def get_filename(char_name: str, moon: str) -> str:
    char_short = mizuumi.get_char_name(char_name)
    moon_short = mizuumi.get_moon_letter(moon)

    file_name = f"{JSON_DIRECTORY}/{char_short}-{moon_short}.json"
    return file_name
