import os
import shutil
import tempfile
import unittest

import dataset
import fill_from_scrape
from fakes import item, move


class TestFillFromScrape(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.root, "data")
        self.scraped_dir = os.path.join(self.root, "scraped")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def setup_files(self, data_items, scraped_items):
        dataset.mirror(self.data_dir, data_items)
        dataset.mirror(self.scraped_dir, scraped_items)

    def stored(self, name="kouma/crescent_kouma.json"):
        return dataset.load_dir(self.data_dir)[name]

    def test_fills_only_the_named_field_and_never_image(self):
        self.setup_files(
            [item(moves=[move("5A", image="HAND_FIXED.png", active="3")])],
            [item(moves=[move("5A", image="scraped.png", active="99", guard="LH")])],
        )
        reports = fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"])
        result = self.stored()["moves"][0]
        self.assertEqual(result["guard"], "LH")
        self.assertEqual(result["image"], "HAND_FIXED.png")
        self.assertEqual(result["active"], "3")
        self.assertEqual(reports["kouma/crescent_kouma.json"]["changed"], 1)
        self.assertEqual(dataset.validate_dir(self.data_dir), [])

    def test_image_is_filled_when_explicitly_named(self):
        self.setup_files([item(moves=[move("5A", image="old.png")])],
                         [item(moves=[move("5A", image="new.png")])])
        fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["image"])
        self.assertEqual(self.stored()["moves"][0]["image"], "new.png")

    def test_matches_variants_by_occurrence(self):
        self.setup_files(
            [item(moves=[move("2C"), move("5A"), move("2C")])],
            [item(moves=[move("2C", guard="L"), move("2C", guard="H"), move("5A", guard="LH")])],
        )
        fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"])
        moves = self.stored()["moves"]
        self.assertEqual([(m["input"], m["guard"]) for m in moves], [("2C", "L"), ("5A", "LH"), ("2C", "H")])

    def test_reports_unmatched_moves_on_both_sides(self):
        self.setup_files([item(moves=[move("5A"), move("j.C")])],
                         [item(moves=[move("5A", guard="LH"), move("236A", guard="LH")])])
        report = fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"])["kouma/crescent_kouma.json"]
        self.assertEqual(report["data_only"], ["j.C"])
        self.assertEqual(report["scrape_only"], ["236A"])
        self.assertNotIn("guard", self.stored()["moves"][1])

    def test_field_missing_from_scrape_is_reported_and_left_alone(self):
        self.setup_files([item(moves=[move("5A", guard="H")])], [item(moves=[move("5A")])])
        report = fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"])["kouma/crescent_kouma.json"]
        self.assertEqual(report["missing_field"], ["5A.guard"])
        self.assertEqual(self.stored()["moves"][0]["guard"], "H")

    def test_reports_files_without_counterpart(self):
        self.setup_files([item(char="Ciel")], [item(char="Len")])
        reports = fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"])
        self.assertEqual(reports["_data_files_without_scrape"], ["ciel/crescent_ciel.json"])
        self.assertEqual(reports["_scrape_files_without_data"], ["len/crescent_len.json"])

    def test_dry_run_writes_nothing(self):
        self.setup_files([item()], [item(moves=[move("5A", guard="LH")])])
        before = dataset.read_file(os.path.join(self.data_dir, "kouma", "crescent_kouma.json"))
        reports = fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"], dry_run=True)
        self.assertEqual(reports["kouma/crescent_kouma.json"]["changed"], 1)
        self.assertEqual(dataset.read_file(os.path.join(self.data_dir, "kouma", "crescent_kouma.json")), before)

    def test_second_fill_is_a_no_op(self):
        self.setup_files([item()], [item(moves=[move("5A", guard="LH")])])
        fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"])
        again = fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["guard"])
        self.assertEqual(again["kouma/crescent_kouma.json"]["changed"], 0)
        self.assertFalse(again["kouma/crescent_kouma.json"]["written"])

    def test_identity_fields_cannot_be_filled(self):
        self.setup_files([item()], [item()])
        with self.assertRaises(ValueError):
            fill_from_scrape.fill(self.data_dir, self.scraped_dir, ["input"])


if __name__ == "__main__":
    unittest.main()
