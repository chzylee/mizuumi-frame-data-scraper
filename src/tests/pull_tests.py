import contextlib
import io
import os
import shutil
import tempfile
import unittest
from decimal import Decimal

import dataset
import dynamo
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
        self.assertEqual(len(report["created"]), 5)
        self.assertEqual(table.scan_calls, 3)  # 2 + 2 + 1
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_item_written_as_stored_minus_content_hash(self):
        stored = item(moves=[move("5A", image="HAND_FIXED.png"), move("5A", image="variant.png")],
                      content_hash="deadbeef")
        pull_from_dynamodb.pull(FakeTable([stored]), self.dir)
        written = dataset.load_dir(self.dir)["kouma/crescent_kouma.json"]
        expected = dict(stored)
        del expected["content_hash"]
        self.assertEqual(written, expected)
        self.assertEqual([m["image"] for m in written["moves"]], ["HAND_FIXED.png", "variant.png"])

    def test_items_without_guard_stay_without_guard(self):
        pull_from_dynamodb.pull(FakeTable([item()]), self.dir)
        self.assertNotIn("guard", dataset.load_dir(self.dir)["kouma/crescent_kouma.json"]["moves"][0])

    def test_decimal_numbers_are_written_as_json_numbers(self):
        pull_from_dynamodb.pull(FakeTable([item(version=Decimal("3"))]), self.dir)
        self.assertEqual(dataset.load_dir(self.dir)["kouma/crescent_kouma.json"]["version"], 3)

    def test_item_deleted_from_table_removes_its_file_and_empty_dir(self):
        table = FakeTable([item(char="Ciel"), item(char="Len")])
        pull_from_dynamodb.pull(table, self.dir)
        del table.store[("Len", "Crescent_Moon")]
        report = pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(report["removed"], ["len/crescent_len.json"])
        self.assertEqual(dataset.list_files(self.dir), ["ciel/crescent_ciel.json"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "len")))

    def test_second_pull_of_same_table_changes_nothing(self):
        table = FakeTable([item(char="Ciel"), item(char="Len")])
        pull_from_dynamodb.pull(table, self.dir)
        mtimes = {n: os.path.getmtime(os.path.join(self.dir, n)) for n in dataset.list_files(self.dir)}
        report = pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(report["created"] + report["updated"], [])
        self.assertEqual(len(report["unchanged"]), 2)
        self.assertEqual(mtimes, {n: os.path.getmtime(os.path.join(self.dir, n)) for n in dataset.list_files(self.dir)})

    def test_reports_created_and_updated_separately(self):
        table = FakeTable([item(char="Ciel")])
        pull_from_dynamodb.pull(table, self.dir)
        table.store[("Ciel", "Crescent_Moon")]["moves"][0]["active"] = "9"
        table.store[("Len", "Crescent_Moon")] = item(char="Len")
        report = pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(report["updated"], ["ciel/crescent_ciel.json"])
        self.assertEqual(report["created"], ["len/crescent_len.json"])

    def test_unmapped_item_still_gets_a_file(self):
        pull_from_dynamodb.pull(FakeTable([item(char="Mystery: Char")]), self.dir)
        self.assertEqual(dataset.list_files(self.dir), ["_unmapped/Mystery%3A Char/Crescent_Moon.json"])
        errors, warnings = dataset.check_dir(self.dir)
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)

    def test_pull_never_writes_to_the_table(self):
        table = FakeTable([item()])
        pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(table.put_count, 0)

    def test_cli_uses_get_table_and_prints_summary(self):
        original = dynamo.get_table
        dynamo.get_table = lambda: FakeTable([item()])
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = pull_from_dynamodb.main(["--data-dir", self.dir])
        finally:
            dynamo.get_table = original
        self.assertEqual(code, 0)
        self.assertIn("  created: 1", out.getvalue())
        self.assertIn("kouma/crescent_kouma.json", out.getvalue())


if __name__ == "__main__":
    unittest.main()
