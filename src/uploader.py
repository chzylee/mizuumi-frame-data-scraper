import boto3
import json
import filehelper
from data import melty

def upload_all_melty_frame_data() -> None:
    filehelper.ensure_json_dir_exists()

    dynamodb = boto3.resource("dynamodb", region_name="us-east-2")
    table = dynamodb.Table("MBAACC-Frame-Data")

    for char in melty.char_paths:
        for moon in melty.moon_paths:
            file_name = filehelper.get_filename(char_name=char, moon=moon)
            with open(file_name) as json_file:
                data = json.load(json_file)
                table.put_item(Item=data)
                print(f"Inserted char data: {data}")

if __name__ == "__main__":
    upload_all_melty_frame_data()

