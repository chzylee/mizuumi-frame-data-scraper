import unittest
from types import SimpleNamespace

from data import errata

try:
    from scraper import Scraper
    _get_alts = Scraper(base_url="", isLoggingOn=False)._get_alt_inputs
except ImportError:  # bs4 missing: alts only need the string logic, so stub it
    _get_alts = None


def _char(name, moon, inputs):
    moves = [SimpleNamespace(input=i, alts=[]) for i in inputs]
    return SimpleNamespace(character_name=name, moon=moon, moves=moves)


@unittest.skipIf(_get_alts is None, "scraper dependencies (bs4) not installed")
class TestErrata(unittest.TestCase):
    def test_neco_half_unlabelled_5a_chain_is_renamed_with_alts(self):
        char = _char("Neco-Arc", "Half_Moon", ["5A", "5A", "5A", "5B"])
        warnings = errata.apply_input_corrections(char, _get_alts)
        self.assertEqual(warnings, [])
        self.assertEqual([m.input for m in char.moves], ["5A", "5A~6A", "5A~6A~6A", "5B"])
        # Same alts as the 5A~6A~6A on every other Half Moon page.
        self.assertEqual(char.moves[1].alts, ["5A6A"])
        self.assertEqual(char.moves[2].alts, ["5A6AA", "5A6A6A", "5A6A~A"])

    def test_other_pages_are_untouched(self):
        char = _char("Neco-Arc", "Full_Moon", ["5A", "5A"])
        self.assertEqual(errata.apply_input_corrections(char, _get_alts), [])
        self.assertEqual([m.input for m in char.moves], ["5A", "5A"])

    def test_a_correction_that_no_longer_matches_is_reported(self):
        # e.g. the wiki page got fixed and now labels its variants.
        char = _char("Neco-Arc", "Half_Moon", ["5A", "5A~6A", "5A~6A~6A"])
        warnings = errata.apply_input_corrections(char, _get_alts)
        self.assertEqual(len(warnings), 2)
        self.assertEqual([m.input for m in char.moves], ["5A", "5A~6A", "5A~6A~6A"])


if __name__ == "__main__":
    unittest.main()
