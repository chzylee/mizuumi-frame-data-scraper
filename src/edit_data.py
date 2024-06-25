import boto3
import json
import filehelper

def upload_all_melty_frame_data() -> None:
    filehelper.ensure_json_dir_exists()

    dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
    table = dynamodb.Table("MBAACC-Frame-Data")

    char = "Archetype:_Earth"
    moon = "Half_Moon"

    file_name = filehelper.get_filename(char_name=char, moon=moon)
    file_path = filehelper.get_upload_json_path(file_name)
    print(f"Uploading data from file at {file_path}")
    with open(file_path) as json_file:
        data = json.load(json_file)
        table.put_item(Item=data)
        print(f"Inserted char data for {moon} {char}")
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    upload_all_melty_frame_data()

