import os
from data import mizuumi

JSON_DIRECTORY = './json'
JSON_UPLOAD_DIRECTORY = './json/json_save'

def ensure_json_dir_exists() -> None:
    # Create the directory if it doesn't exist
    os.makedirs(JSON_DIRECTORY, exist_ok=True)

def get_filename(char_name: str, moon: str) -> str:
    char_short = mizuumi.get_char_name(char_name)
    moon_short = mizuumi.get_moon_letter(moon)

    file_name = f"{char_short}-{moon_short}.json"
    return file_name

def get_json_save_path(file_name: str) -> str:
    file_path = f"{JSON_DIRECTORY}/{file_name}"
    return file_path

    file_name = f"{JSON_DIRECTORY}/{char_short}-{moon_short}.json"
    return file_name

def get_upload_json_path(file_name: str) -> str:
    file_path = f"{JSON_UPLOAD_DIRECTORY}/{file_name}"
    return file_path
