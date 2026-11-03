import os
import shutil
import tempfile
import unittest
from decimal import Decimal

import dataset
from fakes import item, move


class TestValues(unittest.TestCase):
    def test_integral_decimal_becomes_int(self):
        self.assertEqual(dataset.to_plain({"n": Decimal("4")}), {"n": 4})
        self.assertIsInstance(dataset.to_plain(Decimal("4")), int)

    def test_fractional_decimal_becomes_float_when_exact(self):
        self.assertEqual(dataset.to_plain(Decimal("1.5")), 1.5)

    def test_decimal_that_would_lose_precision_is_rejected(self):
        with self.assertRaises(ValueError):
            dataset.to_plain(Decimal("0.12345678901234567890123"))

    def test_sets_are_rejected_not_silently_converted(self):
        with self.assertRaises(TypeError):
            dataset.to_plain({"tags": {"a", "b"}})

    def test_to_dynamo_turns_floats_into_decimal(self):
        self.assertEqual(dataset.to_dynamo({"x": [1.5, 2, "s"]}), {"x": [Decimal("1.5"), 2, "s"]})

    def test_round_trip_through_dynamo_types(self):
        original = {"a": 1, "b": 2.25, "c": ["x"], "d": {"e": 3}}
        self.assertEqual(dataset.to_plain(dataset.to_dynamo(original)), original)

    def test_item_from_table_strips_content_hash(self):
        raw = item(content_hash="abc")
        self.assertNotIn("content_hash", dataset.item_from_table(raw))


class TestCanonicalFormat(unittest.TestCase):
    def test_key_order_is_fixed_regardless_of_input_order(self):
        a = {"moves": [{"alts": [], "input": "5A", "zeta": "1", "image": "i"}], "moon": "Half_Moon", "character_name": "Ciel"}
        b = {"character_name": "Ciel", "moon": "Half_Moon", "moves": [{"image": "i", "zeta": "1", "input": "5A", "alts": []}]}
        self.assertEqual(dataset.dumps(a), dataset.dumps(b))

    def test_known_keys_first_unknown_keys_sorted_after(self):
        text = dataset.dumps({"z": 1, "moves": [{"zz": "1", "aa": "2", "alts": [], "input": "5A"}],
                              "moon": "Half_Moon", "character_name": "Ciel", "a": 2})
        top = [line.strip().split(":")[0] for line in text.splitlines() if line.startswith('  "')]
        self.assertEqual(top, ['"character_name"', '"moon"', '"moves"', '"a"', '"z"'])
        self.assertLess(text.index('"input"'), text.index('"alts"'))
        self.assertLess(text.index('"alts"'), text.index('"aa"'))
        self.assertLess(text.index('"aa"'), text.index('"zz"'))

    def test_move_order_is_preserved(self):
        text = dataset.dumps(item(moves=[move("5C"), move("5A"), move("5B")]))
        self.assertLess(text.index('"5C"'), text.index('"5A"'))
        self.assertLess(text.index('"5A"'), text.index('"5B"'))

    def test_trailing_newline_and_unicode_kept_literal(self):
        text = dataset.dumps(item(moves=[move("5A", proration="80% → 70%")]))
        self.assertTrue(text.endswith("}\n"))
        self.assertIn("→", text)


class TestFilenames(unittest.TestCase):
    def test_known_key_uses_scrape_convention(self):
        self.assertEqual(dataset.filename_for_key("Akiha_Tohno", "Crescent_Moon"), "akiha-C.json")
        self.assertEqual(dataset.filename_for_key("Archetype:_Earth", "Half_Moon"), "hime-H.json")

    def test_unknown_key_gets_a_safe_stable_name(self):
        name = dataset.filename_for_key("Some: Weird/Char", "Full_Moon")
        self.assertTrue(name.startswith(dataset.UNMAPPED_PREFIX))
        self.assertTrue(name.endswith(".json"))
        self.assertNotRegex(name, r"[:/\\ ]")
        self.assertEqual(name, dataset.filename_for_key("Some: Weird/Char", "Full_Moon"))

    def test_unknown_moon_on_known_character_is_not_dropped(self):
        self.assertTrue(dataset.filename_for_key("Ciel", "Eclipse").startswith(dataset.UNMAPPED_PREFIX))

    def test_keys_that_slug_the_same_do_not_collide(self):
        self.assertNotEqual(dataset.filename_for_key("A B", "X"), dataset.filename_for_key("A_B", "X"))


class TestMoveIdentities(unittest.TestCase):
    def test_repeated_inputs_count_occurrences(self):
        ids = dataset.move_identities([move("5A"), move("2C"), move("2C"), move("5A")])
        self.assertEqual(ids, [("5A", 0), ("2C", 0), ("2C", 1), ("5A", 1)])


class DirTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.dir, name)

    def write_raw(self, name, text):
        with open(self.path(name), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)


class TestMirror(DirTestCase):
    def test_writes_unchanged_and_removes(self):
        first = dataset.mirror(self.dir, [item(char="Ciel"), item(char="Kouma_Kishima")])
        self.assertEqual(first["created"], ["ciel-C.json", "kouma-C.json"])
        changed = dataset.mirror(self.dir, [item(char="Ciel", moves=[move("5B")]), item(char="Kouma_Kishima")])
        self.assertEqual(changed["updated"], ["ciel-C.json"])
        self.assertEqual(changed["unchanged"], ["kouma-C.json"])
        second = dataset.mirror(self.dir, [item(char="Ciel", moves=[move("5B")])])
        self.assertEqual(second["unchanged"], ["ciel-C.json"])
        self.assertEqual(second["removed"], ["kouma-C.json"])
        self.assertEqual(dataset.list_files(self.dir), ["ciel-C.json"])

    def test_files_use_lf_line_endings(self):
        dataset.mirror(self.dir, [item()])
        with open(self.path("kouma-C.json"), "rb") as handle:
            self.assertNotIn(b"\r\n", handle.read())

    def test_two_items_for_one_file_is_an_error(self):
        with self.assertRaises(ValueError):
            dataset.mirror(self.dir, [item(), item()])


class TestValidate(DirTestCase):
    def test_canonical_files_pass(self):
        dataset.mirror(self.dir, [item(), item(char="Ciel", moves=[move("5A", guard="LH")])])
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_empty_or_missing_dir_passes(self):
        self.assertEqual(dataset.validate_dir(self.path("nope")), [])

    def assertOneError(self, needle):
        errors = dataset.validate_dir(self.dir)
        self.assertTrue(any(needle in e for e in errors), errors)

    def test_invalid_json(self):
        self.write_raw("kouma-C.json", "{not json")
        self.assertOneError("not valid JSON")

    def test_missing_required_move_key(self):
        bad = item()
        del bad["moves"][0]["invuln"]
        self.write_raw("kouma-C.json", dataset.dumps(bad))
        self.assertOneError("missing invuln")

    def test_missing_guard_is_allowed(self):
        self.write_raw("kouma-C.json", dataset.dumps(item()))
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_missing_top_level_key(self):
        bad = item()
        del bad["moon"]
        self.write_raw("kouma-C.json", dataset.dumps(bad))
        self.assertOneError("'moon' must be a non-empty string")

    def test_content_hash_not_allowed(self):
        self.write_raw("kouma-C.json", dataset.dumps(item(content_hash="x")))
        self.assertOneError("bookkeeping")

    def test_filename_must_match_key(self):
        self.write_raw("ciel-C.json", dataset.dumps(item()))
        self.assertOneError("belongs in kouma-C.json")

    def test_duplicate_key(self):
        self.write_raw("kouma-C.json", dataset.dumps(item()))
        self.write_raw("kouma-H.json", dataset.dumps(item()))
        self.assertOneError("duplicate key")

    def test_non_canonical_formatting_fails(self):
        import json
        self.write_raw("kouma-C.json", json.dumps(item(), indent=4) + "\n")
        self.assertOneError("not in canonical format")

    def test_crlf_line_endings_fail(self):
        self.write_raw("kouma-C.json", dataset.dumps(item()).replace("\n", "\r\n"))
        self.assertOneError("not in canonical format")

    def test_format_dir_fixes_formatting(self):
        import json
        self.write_raw("kouma-C.json", json.dumps(item(), indent=4))
        self.assertEqual(dataset.format_dir(self.dir), ["kouma-C.json"])
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_check_command_exit_codes(self):
        import contextlib, io
        dataset.mirror(self.dir, [item()])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dataset.main(["check", self.dir]), 0)
            self.write_raw("kouma-C.json", "{")
            self.assertEqual(dataset.main(["check", self.dir]), 1)


if __name__ == "__main__":
    unittest.main()
