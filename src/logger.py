import json

def log_info(message: str, isLoggingOn: bool) -> None:
    if isLoggingOn:
        print(message)

def log_data(label: str, data: any, isLoggingOn: bool) -> None:
    if isLoggingOn:
        print(label)
        print(data)
        print("-------------------")

def log_json(label: str, data: any, isLoggingOn: bool) -> None:
    if isLoggingOn:
        print(label)
        print(json.dumps(data, indent=4))
