import io
import os
import contextlib
import unittest

# bs4 is only needed for the scraper itself. Guard the import so the rest of the
# unit-test suite still runs in environments without scraping dependencies.
try:
    from scraper import Scraper
    _HAS_SCRAPER_DEPS = True
except ImportError:
    _HAS_SCRAPER_DEPS = False

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
BASE_URL = "https://mizuumi.wiki"


def _fixture(name):
    return os.path.join(FIXTURE_DIR, name)


def _scrape(name):
    with open(_fixture(name), encoding="utf-8") as html_file:
        html = html_file.read()
    scraper = Scraper(base_url=BASE_URL, isLoggingOn=False)
    # The scraper force-logs its move output; keep test runs quiet.
    with contextlib.redirect_stdout(io.StringIO()):
        return scraper.scrape_frame_data(html)


@unittest.skipUnless(_HAS_SCRAPER_DEPS, "scraper dependencies (bs4) not installed")
class TestScraperAgainstSavedPages(unittest.TestCase):
    """Pins parsing against saved wiki snapshots.

    These exist because a MediaWiki heading-markup change silently broke parsing
    for every character. Committing real page snapshots means the next such change
    fails a test instead of quietly serving stale/no data.
    """

    def _require(self, name):
        if not os.path.exists(_fixture(name)):
            self.skipTest(f"fixture {name} not present")
        return name

    def test_standard_character_known_move_frame_data(self):
        name = self._require("kouma_C.html")
        char = _scrape(name)
        by_input = {move.input: move for move in char.moves}
        self.assertIn("5A", by_input)
        five_a = by_input["5A"]
        # Values read directly from the Kouma Crescent page frame-data table.
        self.assertEqual(five_a.first_active, "5")
        self.assertEqual(five_a.active, "4")
        self.assertEqual(five_a.recovery, "8")
        self.assertEqual(five_a.frame_adv, "0")
        # Guard is the new field: the column two past Proration on the top row.
        self.assertEqual(five_a.guard, "LH")
        self.assertTrue(five_a.image.startswith("https://mizuumi.wiki/"))

    def test_cumulative_follow_up_labels_are_not_doubled(self):
        # Akiha's 2B chain is labelled 2B / ~2B / ~2B~2B: the last label spells out the
        # whole chain so far, so it must replace the follow-up, not be appended to it.
        name = self._require("akiha_C.html")
        inputs = [move.input for move in _scrape(name).moves]
        self.assertIn("2B~2B~2B", inputs)
        self.assertNotIn("2B~2B~2B~2B", inputs)
        self.assertIn("2B~2B", inputs)  # step-by-step labels still accumulate
        three = next(move for move in _scrape(name).moves if move.input == "2B~2B~2B")
        self.assertEqual(three.alts, ["2B2B2B", "2BBB", "2B~BB"])

    def test_maids_moves_carry_the_lead_maid(self):
        # Each maid can lead, and the wiki names the move tables H5A / K5A and the
        # special headings H236X / K236X. Inputs keep that letter.
        name = self._require("maids_C.html")
        inputs = [move.input for move in _scrape(name).moves]
        for expected in ("H5A", "K5A", "Hj.B~B", "K2B~2B", "H236A", "K236[B]~A~B~C", "Kj.214A"):
            self.assertIn(expected, inputs)
        self.assertNotIn("5A", inputs)
        self.assertIn("22D", inputs)  # shared moves have no lead
        # Listed under "Kohaku Specials" with no K on its own heading.
        self.assertIn("K1632143C", inputs)
        self.assertNotIn("1632143C", inputs)

    def test_guard_is_populated_for_scraped_moves(self):
        # Every move on a standard page should carry a (non-None) guard string.
        name = self._require("kouma_C.html")
        char = _scrape(name)
        self.assertTrue(all(isinstance(m.guard, str) for m in char.moves))
        self.assertTrue(any(m.guard for m in char.moves))

    def test_previously_skipped_characters_now_parse(self):
        # Maids (tag pair), Neco-Arc and Neco-Arc Chaos (joke chars) were commented
        # out as "weird pages." They should parse to real movelists now.
        for name in ("maids_C.html", "neco_C.html", "nac_C.html"):
            if not os.path.exists(_fixture(name)):
                continue
            with self.subTest(fixture=name):
                char = _scrape(name)
                self.assertGreater(len(char.moves), 0)

    def test_normals_without_standing_normals_heading_still_parse(self):
        # Neco-Arc Full Moon puts 5A/5B/5C directly under the "Normal Moves" h3
        # with no "Standing Normals" h4. This used to crash the whole page; the
        # h3 fallback now reaches the standing normals.
        name = self._require("neco_F.html")
        char = _scrape(name)
        by_input = {move.input: move for move in char.moves}
        # Standing normals (only reachable via the h3 fallback) must be present...
        for std_normal in ("5A", "5C", "2A"):
            self.assertIn(std_normal, by_input)
        # ...alongside specials, i.e. the full movelist, not a partial one.
        self.assertGreater(len(char.moves), 20)


if __name__ == "__main__":
    unittest.main()
