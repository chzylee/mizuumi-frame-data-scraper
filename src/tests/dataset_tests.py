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


def key(char, moon):
    return {"character_name": char, "moon": moon}


class TestPaths(unittest.TestCase):
    def test_known_key_uses_short_name_dir_and_moon_short_file(self):
        self.assertEqual(dataset.path_for(key("Akiha_Tohno", "Crescent_Moon")), "akiha/crescent_akiha.json")
        self.assertEqual(dataset.path_for(key("Archetype:_Earth", "Half_Moon")), "hime/half_hime.json")
        self.assertEqual(dataset.path_for(key("Hisui_%26_Kohaku", "Full_Moon")), "maids/full_maids.json")

    def test_every_known_character_and_moon_maps_to_a_distinct_safe_path(self):
        from data import melty
        paths = [dataset.path_for(key(c, m)) for c in melty.char_paths for m in melty.moon_paths]
        self.assertEqual(len(set(paths)), len(paths))
        for path in paths:
            self.assertFalse(dataset.is_unmapped(path), path)
            self.assertNotRegex(path, r'[<>:"\|?*]')

    def test_unknown_character_goes_under_unmapped_with_illegal_chars_encoded(self):
        path = dataset.path_for(key('Some: Weird/Char?', "Full_Moon"))
        self.assertEqual(path, "_unmapped/Some%3A Weird%2FChar%3F/Full_Moon.json")
        self.assertTrue(dataset.is_unmapped(path))

    def test_percent_already_in_a_key_is_kept_literally(self):
        self.assertEqual(dataset.path_for(key("New_%26_Char", "Half_Moon")),
                         "_unmapped/New_%26_Char/Half_Moon.json")

    def test_unknown_moon_on_known_character_is_not_dropped(self):
        self.assertEqual(dataset.path_for(key("Ciel", "Eclipse_Moon")), "_unmapped/Ciel/Eclipse_Moon.json")

    def test_dot_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            dataset.path_for(key("..", "Full_Moon"))


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
        os.makedirs(os.path.dirname(self.path(name)), exist_ok=True)
        with open(self.path(name), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)


class TestMirror(DirTestCase):
    def test_writes_unchanged_and_removes(self):
        first = dataset.mirror(self.dir, [item(char="Ciel"), item(char="Kouma_Kishima")])
        self.assertEqual(first["created"], ["ciel/crescent_ciel.json", "kouma/crescent_kouma.json"])
        changed = dataset.mirror(self.dir, [item(char="Ciel", moves=[move("5B")]), item(char="Kouma_Kishima")])
        self.assertEqual(changed["updated"], ["ciel/crescent_ciel.json"])
        self.assertEqual(changed["unchanged"], ["kouma/crescent_kouma.json"])
        second = dataset.mirror(self.dir, [item(char="Ciel", moves=[move("5B")])])
        self.assertEqual(second["unchanged"], ["ciel/crescent_ciel.json"])
        self.assertEqual(second["removed"], ["kouma/crescent_kouma.json"])
        self.assertEqual(dataset.list_files(self.dir), ["ciel/crescent_ciel.json"])
        self.assertFalse(os.path.exists(self.path("kouma")))  # emptied dir removed

    def test_files_use_lf_line_endings(self):
        dataset.mirror(self.dir, [item()])
        with open(self.path("kouma/crescent_kouma.json"), "rb") as handle:
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
        self.write_raw("kouma/crescent_kouma.json", "{not json")
        self.assertOneError("not valid JSON")

    def test_missing_required_move_key(self):
        bad = item()
        del bad["moves"][0]["invuln"]
        self.write_raw("kouma/crescent_kouma.json", dataset.dumps(bad))
        self.assertOneError("missing invuln")

    def test_missing_guard_is_allowed(self):
        self.write_raw("kouma/crescent_kouma.json", dataset.dumps(item()))
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_missing_top_level_key(self):
        bad = item()
        del bad["moon"]
        self.write_raw("kouma/crescent_kouma.json", dataset.dumps(bad))
        self.assertOneError("'moon' must be a non-empty string")

    def test_content_hash_not_allowed(self):
        self.write_raw("kouma/crescent_kouma.json", dataset.dumps(item(content_hash="x")))
        self.assertOneError("bookkeeping")

    def test_path_must_match_key(self):
        self.write_raw("ciel/crescent_ciel.json", dataset.dumps(item()))
        self.assertOneError("belongs at kouma/crescent_kouma.json")

    def test_flat_file_at_data_root_fails_path_check(self):
        self.write_raw("kouma-C.json", dataset.dumps(item()))
        self.assertOneError("belongs at kouma/crescent_kouma.json")

    def test_duplicate_key(self):
        self.write_raw("kouma/crescent_kouma.json", dataset.dumps(item()))
        self.write_raw("kouma/half_kouma.json", dataset.dumps(item()))
        self.assertOneError("duplicate key")

    def test_unmapped_item_is_a_warning_not_an_error(self):
        self.write_raw("_unmapped/Mystery/Crescent_Moon.json", dataset.dumps(item(char="Mystery")))
        errors, warnings = dataset.check_dir(self.dir)
        self.assertEqual(errors, [])
        self.assertTrue(any("_unmapped" in w for w in warnings), warnings)

    def test_non_canonical_formatting_fails(self):
        import json
        self.write_raw("kouma/crescent_kouma.json", json.dumps(item(), indent=4) + "\n")
        self.assertOneError("not in canonical format")

    def test_crlf_line_endings_fail(self):
        self.write_raw("kouma/crescent_kouma.json", dataset.dumps(item()).replace("\n", "\r\n"))
        self.assertOneError("not in canonical format")

    def test_format_dir_fixes_formatting(self):
        import json
        self.write_raw("kouma/crescent_kouma.json", json.dumps(item(), indent=4))
        self.assertEqual(dataset.format_dir(self.dir), ["kouma/crescent_kouma.json"])
        self.assertEqual(dataset.validate_dir(self.dir), [])

    def test_check_command_exit_codes(self):
        import contextlib, io
        dataset.mirror(self.dir, [item()])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(dataset.main(["check", self.dir]), 0)
            self.write_raw("kouma/crescent_kouma.json", "{")
            self.assertEqual(dataset.main(["check", self.dir]), 1)


if __name__ == "__main__":
    unittest.main()
