"""In-memory stand-in for a boto3 DynamoDB Table (no AWS needed).

Implements exactly what the pipeline uses: paginated scan, and put_item with the
small condition-expression grammar push_to_dynamodb emits
(attribute_exists / attribute_not_exists / `#name = :value`, joined by AND).
Values compare with Python equality, which for the nested lists/maps here
matches DynamoDB's deep equality.
"""
import copy
from decimal import Decimal


class ConditionalCheckFailed(Exception):
    """Shaped like botocore's ClientError for ConditionalCheckFailedException."""

    def __init__(self):
        super().__init__("The conditional request failed")
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    def __init__(self, items=None, page_size=2):
        self.store = {}
        self.page_size = page_size
        self.put_count = 0
        self.scan_calls = 0
        # Called before each put is evaluated; lets a test simulate a concurrent edit.
        self.before_put = None
        for item in items or []:
            self.store[self._key(item)] = copy.deepcopy(item)

    @staticmethod
    def _key(item):
        return (item["character_name"], item["moon"])

    def scan(self, ConsistentRead=False, ExclusiveStartKey=None):
        self.scan_calls += 1
        keys = sorted(self.store)
        start = 0
        if ExclusiveStartKey is not None:
            start = keys.index((ExclusiveStartKey["character_name"], ExclusiveStartKey["moon"])) + 1
        page_keys = keys[start:start + self.page_size]
        page = {"Items": [copy.deepcopy(self.store[k]) for k in page_keys]}
        if start + self.page_size < len(keys):
            last = page_keys[-1]
            page["LastEvaluatedKey"] = {"character_name": last[0], "moon": last[1]}
        return page

    def put_item(self, Item, ConditionExpression=None, ExpressionAttributeNames=None,
                 ExpressionAttributeValues=None):
        if self.before_put is not None:
            self.before_put(self)
        for value in _walk(Item):
            if isinstance(value, float):
                raise TypeError("Float types are not supported. Use Decimal types instead.")
        existing = self.store.get(self._key(Item))
        if ConditionExpression and not self._holds(
                existing, ConditionExpression, ExpressionAttributeNames or {}, ExpressionAttributeValues or {}):
            raise ConditionalCheckFailed()
        self.put_count += 1
        self.store[self._key(Item)] = copy.deepcopy(Item)
        return {}

    @staticmethod
    def _holds(existing, expression, names, values):
        for term in expression.split(" AND "):
            term = term.strip()
            if term.startswith("attribute_not_exists("):
                attr = names[term[len("attribute_not_exists("):-1]]
                if existing is not None and attr in existing:
                    return False
            elif term.startswith("attribute_exists("):
                attr = names[term[len("attribute_exists("):-1]]
                if existing is None or attr not in existing:
                    return False
            else:
                left, right = (part.strip() for part in term.split("="))
                attr = names[left]
                if existing is None or attr not in existing or existing[attr] != values[right]:
                    return False
        return True


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def move(move_input, **fields):
    base = {
        "input": move_input, "image": f"{move_input}.png", "first_active": "5",
        "active": "3", "recovery": "10", "frame_adv": "0", "proration": "80%",
        "invuln": "-", "alts": [],
    }
    base.update(fields)
    return base


def item(char="Kouma_Kishima", moon="Crescent_Moon", moves=None, **extra):
    result = {"character_name": char, "moon": moon,
              "moves": moves if moves is not None else [move("5A")]}
    result.update(extra)
    return result


__all__ = ["FakeTable", "ConditionalCheckFailed", "move", "item", "Decimal"]
