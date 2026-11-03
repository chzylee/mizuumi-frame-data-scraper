import contextlib
import io
import os
import shutil
import tempfile
import unittest
from decimal import Decimal

import dataset
import dynamo
import push_to_dynamodb as push
from fakes import FakeTable, item, move

KOUMA = ("Kouma_Kishima", "Crescent_Moon")


class PushTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def data(self, *items):
        dataset.mirror(self.dir, list(items))

    def run_push(self, table, apply=True):
        return {p["name"]: p for p in push.run(table, self.dir, apply=apply)}


class TestPlan(PushTestCase):
    def test_insert_when_table_lacks_item(self):
        self.data(item())
        table = FakeTable()
        plans = self.run_push(table)
        self.assertEqual(plans["kouma/crescent_kouma"]["status"], "insert")
        self.assertEqual(plans["kouma/crescent_kouma"]["result"], "written")
        self.assertIn(KOUMA, table.store)

    def test_unchanged_writes_nothing_even_with_a_stale_stored_hash(self):
        self.data(item())
        table = FakeTable([item(content_hash="stale")])
        plans = self.run_push(table)
        self.assertEqual(plans["kouma/crescent_kouma"]["status"], "unchanged")
        self.assertEqual(table.put_count, 0)

    def test_update_backfills_guard_keeps_image_and_stores_hash(self):
        self.data(item(moves=[move("5A", image="HAND_FIXED.png", guard="LH")]))
        table = FakeTable([item(moves=[move("5A", image="HAND_FIXED.png")], content_hash="old")])
        plans = self.run_push(table)
        entry = plans["kouma/crescent_kouma"]
        self.assertEqual(entry["status"], "update")
        self.assertIn("~ 5A: guard: (absent) -> 'LH'", entry["detail"])
        stored = table.store[KOUMA]
        self.assertEqual(stored["moves"][0]["guard"], "LH")
        self.assertEqual(stored["moves"][0]["image"], "HAND_FIXED.png")
        self.assertEqual(stored["content_hash"], dataset.item_hash(entry["item"]))

    def test_console_edit_with_unchanged_stored_hash_is_still_overwritten(self):
        # A console edit doesn't touch content_hash; the push must still notice it.
        want = item()
        self.data(want)
        edited = item(moves=[move("5A", image="CONSOLE.png")], content_hash=dataset.item_hash(want))
        table = FakeTable([edited])
        plans = self.run_push(table)
        self.assertEqual(plans["kouma/crescent_kouma"]["status"], "update")
        self.assertEqual(table.store[KOUMA]["moves"][0]["image"], "5A.png")

    def test_removed_moves_are_written_and_shown(self):
        self.data(item(moves=[move("5A")]))
        table = FakeTable([item(moves=[move("5A"), move("2C"), move("2C")])])
        plans = self.run_push(table)
        detail = plans["kouma/crescent_kouma"]["detail"]
        self.assertIn("- removed move 2C", detail)
        self.assertIn("- removed move 2C (#2)", detail)
        self.assertEqual(len(table.store[KOUMA]["moves"]), 1)

    def test_added_and_reordered_moves_are_shown(self):
        self.data(item(moves=[move("5B"), move("5A"), move("6C")]))
        table = FakeTable([item(moves=[move("5A"), move("5B")])])
        detail = self.run_push(table)["kouma/crescent_kouma"]["detail"]
        self.assertIn("+ added move 6C", detail)
        self.assertIn("move order changed", detail)

    def test_table_only_item_is_reported_and_never_deleted(self):
        self.data(item(char="Ciel"))
        table = FakeTable([item(char="Ciel"), item(char="Len")])
        plans = self.run_push(table)
        self.assertEqual(plans["len/crescent_len"]["status"], "table-only")
        self.assertIn(("Len", "Crescent_Moon"), table.store)
        self.assertEqual(table.put_count, 0)

    def test_numbers_are_written_as_decimal(self):
        self.data(item(version=1.5))
        table = FakeTable()
        self.run_push(table)
        self.assertEqual(table.store[KOUMA]["version"], Decimal("1.5"))

    def test_second_push_is_all_unchanged(self):
        self.data(item(moves=[move("5A", guard="L")]), item(char="Ciel"))
        table = FakeTable([item()])
        self.run_push(table)
        writes = table.put_count
        again = self.run_push(table)
        self.assertEqual({p["status"] for p in again.values()}, {"unchanged"})
        self.assertEqual(table.put_count, writes)


class TestDryRun(PushTestCase):
    def test_plan_mode_plans_the_same_but_writes_nothing(self):
        self.data(item(moves=[move("5A", guard="L")]))
        table = FakeTable([item()])
        dry = self.run_push(table, apply=False)
        self.assertEqual(dry["kouma/crescent_kouma"]["result"], "would write")
        self.assertEqual(table.put_count, 0)
        real = self.run_push(table)
        self.assertEqual(real["kouma/crescent_kouma"]["detail"], dry["kouma/crescent_kouma"]["detail"])
        self.assertEqual(table.put_count, 1)

    def test_invalid_data_refuses_to_push(self):
        os.makedirs(os.path.join(self.dir, "kouma"))
        with open(os.path.join(self.dir, "kouma", "crescent_kouma.json"), "w") as handle:
            handle.write("{")
        table = FakeTable([item()])
        with self.assertRaises(ValueError):
            push.run(table, self.dir, apply=True)
        self.assertEqual(table.put_count, 0)


class TestCli(PushTestCase):
    def call(self, *args):
        original = dynamo.get_table
        dynamo.get_table = lambda: self.table
        summary = os.path.join(self.dir, "..", os.path.basename(self.dir) + "-summary.md")
        self.addCleanup(lambda: os.path.exists(summary) and os.remove(summary))
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = push.main([*args, "--data-dir", self.dir, "--summary-file", summary])
        finally:
            dynamo.get_table = original
        with open(summary, encoding="utf-8") as handle:
            return code, out.getvalue(), handle.read()

    def test_default_is_plan_mode_and_summary_has_the_diff(self):
        self.data(item(moves=[move("5A", guard="L")]))
        self.table = FakeTable([item()])
        code, out, summary = self.call()
        self.assertEqual(code, 0)
        self.assertIn("PLAN, nothing written", out)
        self.assertIn("guard: (absent) -> 'L'", summary)
        self.assertEqual(self.table.put_count, 0)

    def test_write_flag_writes(self):
        self.data(item(moves=[move("5A", guard="L")]))
        self.table = FakeTable([item()])
        code, out, _ = self.call("--apply")
        self.assertEqual(code, 0)
        self.assertEqual(self.table.put_count, 1)


if __name__ == "__main__":
    unittest.main()
