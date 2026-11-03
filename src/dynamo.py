"""The DynamoDB boundary: the one place that knows the table's name and how to
read all of it. Only the GitHub Actions workflows call get_table(); everything
else takes a table object so it can be tested with an in-memory fake.
"""
from typing import List

TABLE_NAME = "MBAACC-Frame-Data"
REGION = "us-east-2"


def get_table():
    # Imported lazily so the pipeline logic stays testable without boto3/AWS.
    import boto3
    return boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


def scan_all(table) -> List[dict]:
    """Every item in the table, following Scan pagination to the end.

    ConsistentRead so a pull right after a write sees that write.
    """
    items: List[dict] = []
    kwargs = {"ConsistentRead": True}
    while True:
        page = table.scan(**kwargs)
        items.extend(page.get("Items", []))
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            return items
        kwargs["ExclusiveStartKey"] = last_key


def is_conditional_check_failure(error: Exception) -> bool:
    """True for botocore's ConditionalCheckFailedException (checked by code so
    this module never has to import botocore)."""
    response = getattr(error, "response", None) or {}
    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
