import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal

import baseline
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
        self.assertEqual(report["created"] + report["updated"], [])
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

    def test_reports_created_and_updated_separately(self):
        table = FakeTable([item(char="Ciel")])
        pull_from_dynamodb.pull(table, self.dir)
        table.store[("Ciel", "Crescent_Moon")]["moves"][0]["active"] = "9"
        table.store[("Len", "Crescent_Moon")] = item(char="Len")
        report = pull_from_dynamodb.pull(table, self.dir)
        self.assertEqual(report["updated"], ["ciel-C.json"])
        self.assertEqual(report["created"], ["len-C.json"])

    def test_outside_git_the_pending_check_is_skipped_and_said_so(self):
        report = pull_from_dynamodb.pull(FakeTable([item()]), self.dir)
        self.assertIsNone(report["reverted"])
        self.assertIn("skipped", report["pending_check"])
        self.assertIn("pending-edit check: skipped", pull_from_dynamodb.format_report(report))

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


def _git_available():
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


@unittest.skipUnless(_git_available(), "git not installed")
class TestPendingEditWarning(unittest.TestCase):
    """A pull reverts data/ edits that differ from the dynamodb-deployed tag."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.repo, "data")
        for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.com"),
                     ("config", "user.name", "t"), ("config", "core.autocrlf", "false")):
            self.git(*args)

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def commit(self, *items):
        dataset.mirror(self.data_dir, list(items))
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "c")

    def deployed(self, *items):
        self.commit(*items)
        self.git("tag", baseline.BASELINE_TAG)

    def test_no_tag_skips_the_check_and_says_so(self):
        self.commit(item())
        report = pull_from_dynamodb.pull(FakeTable([item()]), self.data_dir)
        self.assertIsNone(report["reverted"])
        self.assertIn("no `dynamodb-deployed` tag", report["pending_check"])
        self.assertIn("skipped", pull_from_dynamodb.format_markdown(report))

    def test_committed_unpushed_edit_that_pull_reverts_is_listed(self):
        v1 = item(moves=[move("5A")])
        self.deployed(v1, item(char="Ciel"))
        self.commit(item(moves=[move("5A", guard="LH")]), item(char="Ciel"))  # approved, not pushed
        report = pull_from_dynamodb.pull(FakeTable([v1, item(char="Ciel")]), self.data_dir)
        self.assertEqual(report["reverted"], ["kouma-C.json"])
        text = pull_from_dynamodb.format_report(report)
        self.assertIn("WARNING: this pull REVERTED unpushed edits in 1 file(s)", text)
        self.assertIn("  - kouma-C.json", text)
        markdown = pull_from_dynamodb.format_markdown(report)
        self.assertIn("[!WARNING]", markdown)
        self.assertIn("`kouma-C.json`", markdown)

    def test_uncommitted_local_edit_is_listed(self):
        v1 = item()
        self.deployed(v1)
        dataset.mirror(self.data_dir, [item(moves=[move("5A", guard="H")])])  # not committed
        report = pull_from_dynamodb.pull(FakeTable([v1]), self.data_dir)
        self.assertEqual(report["reverted"], ["kouma-C.json"])

    def test_new_unpushed_file_removed_by_pull_is_listed(self):
        self.deployed(item(char="Ciel"))
        self.commit(item(char="Ciel"), item(char="Len"))  # Len added on main, not pushed
        report = pull_from_dynamodb.pull(FakeTable([item(char="Ciel")]), self.data_dir)
        self.assertEqual(report["removed"], ["len-C.json"])
        self.assertEqual(report["reverted"], ["len-C.json"])

    def test_console_edit_on_a_clean_file_is_not_a_reverted_edit(self):
        self.deployed(item())
        console = item(moves=[move("5A", image="CONSOLE.png")])
        report = pull_from_dynamodb.pull(FakeTable([console]), self.data_dir)
        self.assertEqual(report["updated"], ["kouma-C.json"])
        self.assertEqual(report["reverted"], [])
        self.assertNotIn("WARNING", pull_from_dynamodb.format_report(report))

    def test_pending_edit_the_table_already_has_is_not_reverted(self):
        self.deployed(item())
        v2 = item(moves=[move("5A", guard="LH")])
        self.commit(v2)
        report = pull_from_dynamodb.pull(FakeTable([v2]), self.data_dir)
        self.assertEqual(report["unchanged"], ["kouma-C.json"])
        self.assertEqual(report["reverted"], [])

    def test_pull_does_not_commit_or_move_refs(self):
        self.deployed(item())
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True).stdout
        pull_from_dynamodb.pull(FakeTable([item(char="Ciel")]), self.data_dir)
        after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repo, capture_output=True, text=True).stdout
        self.assertEqual(head, after)


if __name__ == "__main__":
    unittest.main()
