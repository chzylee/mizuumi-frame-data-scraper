import os
import shutil
import tempfile
import unittest
from decimal import Decimal

import dataset
import pull_from_dynamodb
from fakes import FakeTable, item, move


class TestPull(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_mirrors_every_item_across_scan_pages(self):
        chars = ["Ciel", "Kouma_Kishima", "Len", "Roa", "Hisui"]
        table = FakeTable([item(char=c) for c in chars], page_size=2)
        report = pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(len(report["written"]), 5)
        self.assertEqual(table.scan_calls, 3)  # 2 + 2 + 1
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_item_written_as_stored_minus_content_hash(self):
        stored = item(moves=[move("5A", image="HAND_FIXED.png"), move("5A", image="variant.png")],
                      content_hash="deadbeef")
        pull_from_dynamodb.pull(FakeTable([stored]), self.dir)
        written = dataset.load_dir(self.dir)["kouma-C.json"]
        expected = dict(stored)
        del expected["content_hash"]
        self.assertEqual(written, expected)
        self.assertEqual([m["image"] for m in written["moves"]], ["HAND_FIXED.png", "variant.png"])

    def test_items_without_guard_stay_without_guard(self):
        pull_from_dynamodb.pull(FakeTable([item()]), self.dir)
        self.assertNotIn("guard", dataset.load_dir(self.dir)["kouma-C.json"]["moves"][0])

    def test_decimal_numbers_are_written_as_json_numbers(self):
        pull_from_dynamodb.pull(FakeTable([item(version=Decimal("3"))]), self.dir)
        self.assertEqual(dataset.load_dir(self.dir)["kouma-C.json"]["version"], 3)

    def test_item_deleted_from_table_removes_its_file(self):
        table = FakeTable([item(char="Ciel"), item(char="Len")])
        pull_from_dynamodb.pull(table, self.dir)
        del table.store[("Len", "Crescent_Moon")]
        report = pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(report["removed"], ["len-C.json"])
        self.assertEqual(dataset.list_files(self.dir), ["ciel-C.json"])

    def test_second_pull_of_same_table_changes_nothing(self):
        table = FakeTable([item(char="Ciel"), item(char="Len")])
        pull_from_dynamodb.pull(table, self.dir)
        mtimes = {n: os.path.getmtime(os.path.join(self.dir, n)) for n in dataset.list_files(self.dir)}
        report = pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(report["written"], [])
        self.assertEqual(len(report["unchanged"]), 2)
        self.assertEqual(mtimes, {n: os.path.getmtime(os.path.join(self.dir, n)) for n in dataset.list_files(self.dir)})

    def test_unmapped_item_still_gets_a_file(self):
        pull_from_dynamodb.pull(FakeTable([item(char="Mystery_Char")]), self.dir)
        files = dataset.list_files(self.dir)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith(dataset.UNMAPPED_PREFIX))
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_pull_never_writes_to_the_table(self):
        table = FakeTable([item()])
        pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(table.put_count, 0)


if __name__ == "__main__":
    unittest.main()
