"""In-memory stand-in for a boto3 DynamoDB Table (no AWS needed).

Implements exactly what the pipeline uses: paginated scan and put_item (which,
like boto3, rejects floats).
"""
import copy


class FakeTable:
    def __init__(self, items=None, page_size=2):
        self.store = {}
        self.page_size = page_size
        self.put_count = 0
        self.scan_calls = 0
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

    def put_item(self, Item):
        for value in _walk(Item):
            if isinstance(value, float):
                raise TypeError("Float types are not supported. Use Decimal types instead.")
        self.put_count += 1
        self.store[self._key(Item)] = copy.deepcopy(Item)
        return {}


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


__all__ = ["FakeTable", "move", "item"]
