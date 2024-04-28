import unittest
from data import inputreader as InputReader

class TestInputReader(unittest.TestCase):
    def test_match_ground_normal_given_valid_input_returns_formatted_input(self):
        input = InputReader.match_ground_normal("5b")
        self.assertEqual(input, "5B") # Button should be capitalized.

    def test_match_ground_normal_given_charged_input_returns_formatted_input(self):
        input = InputReader.match_ground_normal("5[c]")
        self.assertEqual(input, "5[C]")

    def test_match_ground_normal_given_invalid_input_returns_None(self):
        input = InputReader.match_ground_normal("B") # Not a valid normal.
        self.assertIsNone(input)

    def test_match_air_normal_given_valid_input_returns_formatted_input(self):
        input = InputReader.match_air_normal("j.c")
        self.assertEqual(input, "j.C")

    def test_match_air_normal_given_charged_input_returns_formatted_input(self):
        input = InputReader.match_air_normal("j.[c]")
        self.assertEqual(input, "j.[C]")

    def test_match_air_normal_given_no_period_after_j_returns_formatted_input(self):
        input = InputReader.match_air_normal("jC")
        self.assertEqual(input, "j.C") # Add "." even when not given.

    def test_match_air_normal_given_invalid_input_returns_None(self):
        input = InputReader.match_air_normal("j5A") # Not valid air normal notation.
        self.assertIsNone(input)

    def test_match_ground_special_given_valid_input_returns_formatted_input(self):
        input = InputReader.match_ground_special("623a")
        self.assertEqual(input, "623A")

    def test_match_ground_special_given_charged_input_returns_formatted_input(self):
        input = InputReader.match_ground_special("623[b]")
        self.assertEqual(input, "623[B]")

    def test_match_ground_special_given_22_input_returns_formatted_input(self):
        input = InputReader.match_ground_special("22b")
        self.assertEqual(input, "22B")

    def test_match_ground_normal_given_invalid_input_returns_None(self):
        input = InputReader.match_ground_special("63214C") # Not a valid special.
        self.assertIsNone(input)

    def test_match_air_cmd_normal_given_valid_input_returns_formatted_input(self):
        input = InputReader.match_air_cmd_normal("j.6a")
        self.assertEqual(input, "j.6A")

    def test_match_air_cmd_normal_given_charged_input_returns_formatted_input(self):
        input = InputReader.match_air_cmd_normal("j.2[c]")
        self.assertEqual(input, "j.2[C]")

    def test_match_air_cmd_normal_given_no_period_after_j_returns_formatted_input(self):
        input = InputReader.match_air_cmd_normal("j6a")
        self.assertEqual(input, "j.6A")

    def test_match_air_cmd_normal_given_invalid_input_returns_None(self):
        input = InputReader.match_air_cmd_normal("jC") # Not valid air cmd normal notation.
        self.assertIsNone(input)

    def test_match_air_special_given_valid_input_returns_formatted_input(self):
        input = InputReader.match_air_special("j.236b")
        self.assertEqual(input, "j.236B")

    def test_match_air_special_given_charged_input_returns_formatted_input(self):
        input = InputReader.match_air_special("j214[a]")
        self.assertEqual(input, "j.214[A]")

    def test_match_air_special_given_no_period_after_j_returns_formatted_input(self):
        input = InputReader.match_air_special("j236b")
        self.assertEqual(input, "j.236B")

    def test_match_air_special_given_invalid_input_returns_None(self):
        input = InputReader.match_air_special("j2B") # Not valid air special notation.
        self.assertIsNone(input)

if __name__ == '__main__':
    unittest.main()
