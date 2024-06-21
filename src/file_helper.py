import os

JSON_DIRECTORY = './json'

def ensure_json_dir_exists() -> None:
    # Create the directory if it doesn't exist
    os.makedirs(JSON_DIRECTORY, exist_ok=True)

def get_filename(char_name: str, moon: str) -> str:
    file_name = f"{JSON_DIRECTORY}/{char_name}-{moon}.json"
    return file_name
