import copy
import os
import shutil
import subprocess
import tempfile
import unittest

import dataset
import push_to_dynamodb as push
from fakes import FakeTable, item, move


def known_for(*versions_by_file):
    """Build a known-states map from (filename, item-or-None) pairs."""
    known = {}
    for name, version in versions_by_file:
        known.setdefault(name, set()).add(push.state_of(version))
    return known


class PushTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def data(self, *items):
        dataset.mirror(self.dir, list(items))

    def run_push(self, table, known, **kwargs):
        return {p["name"]: p for p in push.run(table, self.dir, known, **kwargs)}


class TestPlanStatuses(PushTestCase):
    def test_insert_when_table_lacks_item(self):
        self.data(item())
        table = FakeTable()
        plans = self.run_push(table, known_for(("kouma-C.json", None)), dry_run=False)
        self.assertEqual(plans["kouma-C"]["status"], "insert")
        self.assertEqual(plans["kouma-C"]["result"], "written")
        self.assertIn(("Kouma_Kishima", "Crescent_Moon"), table.store)

    def test_unchanged_writes_nothing(self):
        live = item(content_hash="old")
        self.data(item())
        table = FakeTable([live])
        plans = self.run_push(table, {}, dry_run=False)
        self.assertEqual(plans["kouma-C"]["status"], "unchanged")
        self.assertEqual(table.put_count, 0)

    def test_update_backfills_guard_and_keeps_hand_fixed_image(self):
        live = item(moves=[move("5A", image="HAND_FIXED.png")], content_hash="old")
        baseline = dataset.item_from_table(live)
        desired = item(moves=[move("5A", image="HAND_FIXED.png", guard="LH")])
        self.data(desired)
        table = FakeTable([live])
        plans = self.run_push(table, known_for(("kouma-C.json", baseline)), dry_run=False)
        self.assertEqual(plans["kouma-C"]["status"], "update")
        stored = table.store[("Kouma_Kishima", "Crescent_Moon")]
        self.assertEqual(stored["moves"][0]["guard"], "LH")
        self.assertEqual(stored["moves"][0]["image"], "HAND_FIXED.png")
        self.assertEqual(stored["content_hash"], dataset.item_hash(desired))
        self.assertIn("~ 5A: guard: (absent) -> 'LH'", plans["kouma-C"]["detail"])

    def test_table_only_item_is_reported_and_never_deleted(self):
        self.data(item(char="Ciel"))
        orphan = item(char="Len")
        table = FakeTable([orphan, item(char="Ciel")])
        plans = self.run_push(table, {}, dry_run=False)
        self.assertEqual(plans["len-C"]["status"], "table-only")
        self.assertIn(("Len", "Crescent_Moon"), table.store)
        self.assertEqual(table.put_count, 0)

    def test_dry_run_plans_the_same_but_writes_nothing(self):
        live = item(content_hash="old")
        desired = item(moves=[move("5A", guard="L")])
        self.data(desired)
        table = FakeTable([live])
        known = known_for(("kouma-C.json", dataset.item_from_table(live)))
        dry = self.run_push(table, known, dry_run=True)
        self.assertEqual(dry["kouma-C"]["status"], "update")
        self.assertEqual(dry["kouma-C"]["result"], "would write")
        self.assertEqual(table.put_count, 0)
        real = self.run_push(table, known, dry_run=False)
        self.assertEqual(real["kouma-C"]["detail"], dry["kouma-C"]["detail"])
        self.assertEqual(table.put_count, 1)

    def test_written_item_is_then_unchanged(self):
        live = item(content_hash="old")
        self.data(item(moves=[move("5A", guard="L")]))
        table = FakeTable([live])
        self.run_push(table, known_for(("kouma-C.json", dataset.item_from_table(live))), dry_run=False)
        again = self.run_push(table, {}, dry_run=False)
        self.assertEqual(again["kouma-C"]["status"], "unchanged")
        self.assertEqual(table.put_count, 1)


class TestDriftGuard(PushTestCase):
    def setUp(self):
        super().setUp()
        self.baseline = item(moves=[move("5A", image="pulled.png")])
        self.desired = item(moves=[move("5A", image="pulled.png", guard="LH")])
        self.data(self.desired)
        self.known = known_for(("kouma-C.json", self.baseline))

    def test_console_edit_after_baseline_is_refused(self):
        console_edit = item(moves=[move("5A", image="CONSOLE_FIX.png")], content_hash="stale")
        table = FakeTable([console_edit])
        plans = self.run_push(table, self.known, dry_run=False)
        self.assertEqual(plans["kouma-C"]["status"], "refused")
        self.assertEqual(plans["kouma-C"]["reason"], "drift")
        self.assertEqual(table.store[("Kouma_Kishima", "Crescent_Moon")]["moves"][0]["image"], "CONSOLE_FIX.png")
        self.assertEqual(table.put_count, 0)
        self.assertFalse(push.succeeded(list(plans.values())))

    def test_force_overwrites_a_drifted_item(self):
        table = FakeTable([item(moves=[move("5A", image="CONSOLE_FIX.png")])])
        plans = self.run_push(table, self.known, dry_run=False, force={"kouma-C"})
        self.assertEqual(plans["kouma-C"]["status"], "update")
        self.assertIn("forced past drift guard", plans["kouma-C"]["detail"])
        self.assertEqual(table.store[("Kouma_Kishima", "Crescent_Moon")]["moves"][0]["guard"], "LH")

    def test_item_deleted_from_table_after_baseline_is_refused(self):
        table = FakeTable()
        plans = self.run_push(table, self.known, dry_run=False)
        self.assertEqual(plans["kouma-C"]["reason"], "drift")
        self.assertEqual(table.put_count, 0)

    def test_item_that_appeared_in_table_outside_pipeline_is_refused(self):
        # data/ had no such item at the baseline, but now the table has one.
        table = FakeTable([item(moves=[move("5A", image="someone_else.png")])])
        plans = self.run_push(table, known_for(("kouma-C.json", None)), dry_run=False)
        self.assertEqual(plans["kouma-C"]["reason"], "drift")

    def test_no_known_states_refuses_every_change(self):
        table = FakeTable([self.baseline])
        plans = self.run_push(table, {}, dry_run=False)
        self.assertEqual(plans["kouma-C"]["reason"], "drift")

    def test_one_refusal_does_not_block_other_items(self):
        other_live = item(char="Ciel")
        other_desired = item(char="Ciel", moves=[move("5A", guard="H")])
        self.data(self.desired, other_desired)
        table = FakeTable([item(moves=[move("5A", image="CONSOLE_FIX.png")]), other_live])
        known = dict(self.known, **known_for(("ciel-C.json", other_live)))
        plans = self.run_push(table, known, dry_run=False)
        self.assertEqual(plans["kouma-C"]["status"], "refused")
        self.assertEqual(plans["ciel-C"]["result"], "written")

    def test_unknown_force_name_is_an_error(self):
        with self.assertRaises(ValueError):
            self.run_push(FakeTable([self.baseline]), self.known, force={"kuoma-C"})


class TestMoveRemovalGuard(PushTestCase):
    def setUp(self):
        super().setUp()
        self.live = item(moves=[move("5A"), move("2C", image="a.png"), move("2C", image="b.png")])
        self.known = known_for(("kouma-C.json", self.live))

    def test_update_that_drops_a_variant_is_refused(self):
        self.data(item(moves=[move("5A"), move("2C", image="a.png")]))
        table = FakeTable([self.live])
        plans = self.run_push(table, self.known, dry_run=False)
        self.assertEqual(plans["kouma-C"]["reason"], "move-removal")
        self.assertIn("- removed move 2C (#2)", plans["kouma-C"]["detail"])
        self.assertEqual(table.put_count, 0)

    def test_allowed_removal_is_written(self):
        self.data(item(moves=[move("5A")]))
        table = FakeTable([self.live])
        plans = self.run_push(table, self.known, dry_run=False, allow_move_removal={"kouma-C"})
        self.assertEqual(plans["kouma-C"]["result"], "written")
        self.assertEqual(len(table.store[("Kouma_Kishima", "Crescent_Moon")]["moves"]), 1)

    def test_adding_and_reordering_is_not_removal(self):
        self.data(item(moves=[move("2C", image="a.png"), move("5A"), move("2C", image="b.png"), move("6C")]))
        table = FakeTable([self.live])
        plans = self.run_push(table, self.known, dry_run=False)
        self.assertEqual(plans["kouma-C"]["status"], "update")
        self.assertIn("+ added move 6C", plans["kouma-C"]["detail"])
        self.assertIn("move order changed", plans["kouma-C"]["detail"])


class TestConditionalWrite(PushTestCase):
    def test_change_between_read_and_write_fails_instead_of_overwriting(self):
        live = item(content_hash="h")
        self.data(item(moves=[move("5A", guard="L")]))
        table = FakeTable([live])

        def concurrent_console_edit(t):
            t.store[("Kouma_Kishima", "Crescent_Moon")]["moves"][0]["image"] = "RACE.png"
        table.before_put = concurrent_console_edit

        plans = self.run_push(table, known_for(("kouma-C.json", dataset.item_from_table(live))), dry_run=False)
        self.assertEqual(plans["kouma-C"]["result"], "conflict")
        self.assertEqual(table.store[("Kouma_Kishima", "Crescent_Moon")]["moves"][0]["image"], "RACE.png")
        self.assertFalse(push.succeeded(list(plans.values())))

    def test_insert_fails_if_item_appears_before_write(self):
        self.data(item())
        table = FakeTable()
        table.before_put = lambda t: t.store.__setitem__(("Kouma_Kishima", "Crescent_Moon"), item(moves=[]))
        plans = self.run_push(table, known_for(("kouma-C.json", None)), dry_run=False)
        self.assertEqual(plans["kouma-C"]["result"], "conflict")

    def test_condition_covers_every_non_key_attribute(self):
        kwargs = push.condition_for(item(content_hash="h", extra="x"))
        names = set(kwargs["ExpressionAttributeNames"].values())
        self.assertEqual(names, {"character_name", "content_hash", "extra", "moves"})
        self.assertTrue(kwargs["ConditionExpression"].startswith("attribute_exists(#pk)"))


class TestRunRefusesInvalidData(PushTestCase):
    def test_invalid_data_dir_refuses_to_push(self):
        with open(os.path.join(self.dir, "kouma-C.json"), "w") as handle:
            handle.write("{")
        table = FakeTable([item()])
        with self.assertRaises(ValueError):
            push.run(table, self.dir, {}, dry_run=False)
        self.assertEqual(table.put_count, 0)


def _git_available():
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


@unittest.skipUnless(_git_available(), "git not installed")
class TestKnownStatesFromGit(unittest.TestCase):
    """Runs against a real throwaway git repository."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "test")
        self.git("config", "core.autocrlf", "false")
        self.data_dir = os.path.join(self.repo, "data")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, *items, message="c"):
        dataset.mirror(self.data_dir, list(items))
        with open(os.path.join(self.repo, "README"), "a") as handle:
            handle.write(message)  # so every commit has a change
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def test_without_tag_every_committed_version_is_known(self):
        pulled = item(moves=[move("5A", image="pulled.png")])
        self.commit(pulled, message="bootstrap pull")
        self.commit(item(moves=[move("5A", image="pulled.png", guard="LH")]), message="backfill")
        known, baseline = push.known_states(self.repo, "HEAD")
        self.assertIn("no `dynamodb-deployed` tag", baseline)
        self.assertIn(push.state_of(pulled), known["kouma-C.json"])
        # A console edit made after the pull was never committed, so it is unknown.
        console = item(moves=[move("5A", image="CONSOLE.png")])
        self.assertNotIn(push.state_of(console), known["kouma-C.json"])

    def test_with_tag_only_versions_since_the_tag_are_known(self):
        ancient = item(moves=[move("5A", image="ancient.png")])
        self.commit(ancient, message="old")
        deployed = item(moves=[move("5A", image="deployed.png")])
        self.commit(deployed, message="deployed")
        self.git("tag", push.BASELINE_TAG)
        pulled = item(moves=[move("5A", image="absorbed_console_edit.png")])
        self.commit(pulled, message="pull PR merged")
        self.commit(item(moves=[move("5A", image="absorbed_console_edit.png", guard="L")]), message="edit")
        known, baseline = push.known_states(self.repo, "HEAD")
        self.assertIn("plus 2 later commit(s)", baseline)
        states = known["kouma-C.json"]
        self.assertIn(push.state_of(deployed), states)
        self.assertIn(push.state_of(pulled), states)       # a pull merged after the deploy
        self.assertNotIn(push.state_of(ancient), states)   # older than the baseline

    def test_absent_is_known_only_if_some_commit_lacked_the_file(self):
        self.commit(item(char="Ciel"), message="one")
        self.git("tag", push.BASELINE_TAG)
        self.commit(item(char="Ciel"), item(char="Len"), message="add len")
        known, _ = push.known_states(self.repo, "HEAD")
        self.assertIn(push.ABSENT, known["len-C.json"])      # new file: insert allowed
        self.assertNotIn(push.ABSENT, known["ciel-C.json"])  # existed throughout

    def test_tag_not_in_history_is_an_error(self):
        self.commit(item(), message="one")
        self.git("checkout", "-q", "--orphan", "other")
        self.commit(item(char="Ciel"), message="unrelated")
        self.git("tag", push.BASELINE_TAG)
        self.git("checkout", "-q", "main")
        with self.assertRaises(RuntimeError):
            push.known_states(self.repo, "HEAD")

    def test_end_to_end_bootstrap_then_console_edit_is_refused(self):
        pulled = item(moves=[move("5A", image="HAND_FIXED.png")], content_hash="h")
        self.commit(dataset.item_from_table(pulled), message="bootstrap pull")
        self.commit(item(moves=[move("5A", image="HAND_FIXED.png", guard="LH")]), message="backfill")
        known, _ = push.known_states(self.repo, "HEAD")

        clean = FakeTable([copy.deepcopy(pulled)])
        plans = {p["name"]: p for p in push.run(clean, self.data_dir, known, dry_run=False)}
        self.assertEqual(plans["kouma-C"]["result"], "written")

        edited = copy.deepcopy(pulled)
        edited["moves"][0]["image"] = "EDITED_AFTER_PULL.png"
        drifted = FakeTable([edited])
        plans = {p["name"]: p for p in push.run(drifted, self.data_dir, known, dry_run=False)}
        self.assertEqual(plans["kouma-C"]["reason"], "drift")
        self.assertEqual(drifted.put_count, 0)


if __name__ == "__main__":
    unittest.main()
