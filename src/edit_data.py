import json
import filehelper
import uploader

def upload_all_melty_frame_data() -> None:
    filehelper.ensure_json_dir_exists()
    table = uploader.get_table()

    char = "Archetype:_Earth"
    moon = "Half_Moon"

    file_name = filehelper.get_filename(char_name=char, moon=moon)
    file_path = filehelper.get_upload_json_path(file_name)
    print(f"Uploading data from file at {file_path}")
    with open(file_path, encoding="utf-8") as json_file:
        data = json.load(json_file)
    # Deliberate override: push this file verbatim (no merge), so this is the way
    # to actually change a hand-owned field like an image URL.
    uploader.force_upload_item(table, data)
    print(f"Inserted char data for {moon} {char}")
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    upload_all_melty_frame_data()

