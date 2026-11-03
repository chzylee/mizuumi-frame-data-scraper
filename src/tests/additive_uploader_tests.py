import unittest
import uploader


class FakeTable:
    """Minimal in-memory stand-in for a boto3 DynamoDB Table.

    Lets us prove the additive/idempotent upload behavior without AWS: it counts
    how many times put_item is actually called so we can assert that unchanged
    data is never re-written.
    """

    def __init__(self):
        self.store = {}
        self.put_count = 0

    def get_item(self, Key):
        key = (Key[uploader.PARTITION_KEY], Key[uploader.SORT_KEY])
        item = self.store.get(key)
        return {"Item": item} if item is not None else {}

    def put_item(self, Item):
        self.put_count += 1
        key = (Item[uploader.PARTITION_KEY], Item[uploader.SORT_KEY])
        self.store[key] = Item


def make_item(char="Kouma_Kishima", moon="Crescent_Moon", moves=None):
    return {
        "character_name": char,
        "moon": moon,
        "moves": moves if moves is not None else [{"input": "5A", "active": "4"}],
    }


class TestAdditiveUploader(unittest.TestCase):
    def test_new_item_is_inserted_and_written_once(self):
        table = FakeTable()
        status = uploader.upload_item(table, make_item())
        self.assertEqual(status, "inserted")
        self.assertEqual(table.put_count, 1)

    def test_reupload_identical_item_is_unchanged_and_not_rewritten(self):
        table = FakeTable()
        uploader.upload_item(table, make_item())
        status = uploader.upload_item(table, make_item())  # same data again
        # Idempotent: unchanged data must not trigger a second write.
        self.assertEqual(status, "unchanged")
        self.assertEqual(table.put_count, 1)

    def test_changed_item_is_updated(self):
        table = FakeTable()
        uploader.upload_item(table, make_item())
        changed = make_item(moves=[{"input": "5A", "active": "5"}])  # active 4 -> 5
        status = uploader.upload_item(table, changed)
        self.assertEqual(status, "updated")
        self.assertEqual(table.put_count, 2)

    def test_key_order_is_not_treated_as_a_change(self):
        table = FakeTable()
        uploader.upload_item(table, {
            "moon": "Crescent_Moon", "character_name": "Ciel",
            "moves": [{"a": "1", "b": "2"}],
        })
        status = uploader.upload_item(table, {
            "moves": [{"b": "2", "a": "1"}], "character_name": "Ciel",
            "moon": "Crescent_Moon",
        })
        self.assertEqual(status, "unchanged")
        self.assertEqual(table.put_count, 1)

    def test_upload_never_deletes_existing_characters(self):
        table = FakeTable()
        uploader.upload_item(table, make_item(char="Ciel"))
        uploader.upload_item(table, make_item(char="Kouma_Kishima"))
        # Re-running one character leaves the others intact (additive, never destructive).
        uploader.upload_item(table, make_item(char="Kouma_Kishima"))
        keys = set(table.store.keys())
        self.assertIn(("Ciel", "Crescent_Moon"), keys)
        self.assertIn(("Kouma_Kishima", "Crescent_Moon"), keys)

    def test_content_hash_is_stored_on_write(self):
        table = FakeTable()
        uploader.upload_item(table, make_item())
        stored = next(iter(table.store.values()))
        self.assertIn(uploader.HASH_ATTR, stored)

    def test_backfill_adds_guard_without_overwriting_manual_image(self):
        table = FakeTable()
        key = ("Kouma_Kishima", "Crescent_Moon")
        # Original upload, then a manual image fix lands directly in the table
        # (DynamoDB is the source of truth for image URLs).
        uploader.upload_item(table, make_item(
            moves=[{"input": "5A", "active": "4", "image": "scraped_old.png"}]))
        table.store[key]["moves"][0]["image"] = "MANUAL_FIX.png"

        # Re-scrape now yields the new guard field plus a different scraped image.
        status = uploader.upload_item(table, make_item(
            moves=[{"input": "5A", "active": "4", "image": "scraped_new.png", "guard": "LH"}]))

        move = table.store[key]["moves"][0]
        self.assertEqual(status, "updated")
        self.assertEqual(move["image"], "MANUAL_FIX.png")  # manual fix preserved
        self.assertEqual(move["guard"], "LH")              # new field added

    def test_backfill_is_idempotent_after_image_preserved(self):
        table = FakeTable()
        key = ("Kouma_Kishima", "Crescent_Moon")
        uploader.upload_item(table, make_item(
            moves=[{"input": "5A", "active": "4", "image": "scraped_old.png"}]))
        table.store[key]["moves"][0]["image"] = "MANUAL_FIX.png"
        scraped = make_item(
            moves=[{"input": "5A", "active": "4", "image": "scraped_new.png", "guard": "LH"}])
        uploader.upload_item(table, scraped)   # first run: updated
        before = table.put_count
        status = uploader.upload_item(table, scraped)  # second run: no-op
        self.assertEqual(status, "unchanged")
        self.assertEqual(table.put_count, before)

    def test_image_preserved_per_variant_for_repeated_inputs(self):
        table = FakeTable()
        key = ("Kouma_Kishima", "Crescent_Moon")
        uploader.upload_item(table, make_item(moves=[
            {"input": "2C", "active": "3", "image": "a_old.png"},
            {"input": "2C", "active": "5", "image": "b_old.png"},
        ]))
        stored = table.store[key]["moves"]
        stored[0]["image"], stored[1]["image"] = "A_FIX.png", "B_FIX.png"

        uploader.upload_item(table, make_item(moves=[
            {"input": "2C", "active": "3", "image": "a_new.png", "guard": "L"},
            {"input": "2C", "active": "5", "image": "b_new.png", "guard": "H"},
        ]))
        moves = table.store[key]["moves"]
        self.assertEqual([m["image"] for m in moves], ["A_FIX.png", "B_FIX.png"])
        self.assertEqual([m["guard"] for m in moves], ["L", "H"])

    def test_new_character_inserts_scraped_image(self):
        table = FakeTable()
        status = uploader.upload_item(table, make_item(
            char="Neco-Arc", moves=[{"input": "5A", "image": "scraped.png", "guard": "M"}]))
        move = next(iter(table.store.values()))["moves"][0]
        self.assertEqual(status, "inserted")
        self.assertEqual(move["image"], "scraped.png")  # nothing to preserve yet
        self.assertEqual(move["guard"], "M")

    def test_partial_scrape_is_refused_as_destructive(self):
        # A page that failed to parse normals (like the old neco-F bug) would
        # produce far fewer moves. That must never shrink the stored record.
        table = FakeTable()
        key = ("Kouma_Kishima", "Crescent_Moon")
        uploader.upload_item(table, make_item(moves=[
            {"input": "5A", "image": "a.png"},
            {"input": "5B", "image": "b.png"},
            {"input": "2A", "image": "c.png"},
        ]))
        before = table.put_count
        status = uploader.upload_item(table, make_item(moves=[{"input": "236B", "image": "x.png"}]))
        self.assertEqual(status, "skipped")
        self.assertEqual(table.put_count, before)            # nothing written
        self.assertEqual(len(table.store[key]["moves"]), 3)  # stored data intact

    def test_empty_scrape_is_refused(self):
        table = FakeTable()
        key = ("Kouma_Kishima", "Crescent_Moon")
        uploader.upload_item(table, make_item(moves=[{"input": "5A", "image": "a.png"}]))
        before = table.put_count
        status = uploader.upload_item(table, make_item(moves=[]))
        self.assertEqual(status, "skipped")
        self.assertEqual(table.put_count, before)
        self.assertEqual(table.store[key]["moves"][0]["image"], "a.png")

    def test_dropped_duplicate_variant_is_refused(self):
        # Two 5B variants stored; a scrape with only one would halve them.
        table = FakeTable()
        uploader.upload_item(table, make_item(moves=[
            {"input": "5B", "image": "b1.png"},
            {"input": "5B", "image": "b2.png"},
        ]))
        before = table.put_count
        status = uploader.upload_item(table, make_item(moves=[{"input": "5B", "image": "bx.png"}]))
        self.assertEqual(status, "skipped")
        self.assertEqual(table.put_count, before)

    def test_dry_run_writes_nothing(self):
        table = FakeTable()
        key = ("Kouma_Kishima", "Crescent_Moon")
        uploader.upload_item(table, make_item(moves=[{"input": "5A", "active": "4"}]))
        before = table.put_count
        status = uploader.upload_item(
            table, make_item(moves=[{"input": "5A", "active": "5"}]), dry_run=True)
        self.assertEqual(status, "updated")            # would update...
        self.assertEqual(table.put_count, before)      # ...but wrote nothing
        self.assertEqual(table.store[key]["moves"][0]["active"], "4")  # stored data intact


if __name__ == "__main__":
    unittest.main()
